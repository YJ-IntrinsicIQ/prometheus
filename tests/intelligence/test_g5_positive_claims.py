"""M63 / G5 final correction: positive claims need evidence too, and uncertainty wording must never recycle an unsupported premise.

Case A: an investor answer called the Ujjivan FY21 subscription to 200 equity shares of Vishvakarma Payments (FY21 p.77, category 'Equity investment (minority stake)') an
'acquisition'. Case B: the generic fallback quoted unsupported statements ('FY23 data missing due to merger transition'). The tests below were written before the fix and
exercise the shared gate on a synthetic company (event-type, completion, unknown entity, premise echo) and on the real records / the 91 candidate answers / the rendered surfaces."""
import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from pipelines import g4_investor_answers as g4  # noqa: E402
from pipelines import g5_provenance as G  # noqa: E402
from pipelines import g5_verify as V  # noqa: E402
from tests.intelligence.test_g5_evidence_verification import FakeL  # noqa: E402

ROOT = Path(os.environ.get("G5D_ROOT", "/private/tmp/claude-501/g6/root"))
WORK = Path(os.environ.get("G5D_DIR", "/private/tmp/claude-501/g6"))
needs_root = pytest.mark.skipif(not ROOT.exists(), reason="evidence root absent")
needs_bundle = pytest.mark.skipif(not (WORK / "bundle" / "answers").exists(), reason="scratch candidate absent")
_L: dict = {}


def led(k):
    if k not in _L:
        _L[k] = g4.Ledger(k, ROOT)
    return _L[k]


def company(tmp_path, actions, chunks=()):
    """A synthetic company whose capital-allocation timeline holds the given actions."""
    L = FakeL(tmp_path, chunks=list(chunks))
    f = L.mem / "capital_allocation_timeline.json"
    f.write_text(json.dumps({"timeline": [{"fiscal_year": "fy21", "capital_allocation_actions": actions}]}))
    return L


def action(value, category, page=77, amount="", purpose=""):
    return {"value": value, "source_year": "fy21", "category": category, "amount": amount, "purpose": purpose, "evidence_references": {"page": page}}


# ── Case A: the shared event-type check ──
def test_a_minority_equity_investment_is_not_an_acquisition(tmp_path):
    L = company(tmp_path, [action("Acquired 200 equity shares of Zeta Payments Private Limited", "Equity investment (minority stake)", amount="200 shares at INR 10 per share (total INR 2,000)")])
    f = V.verify_events(L, "Unattributed allocations include equity issuance, Zeta acquisition, organic capex.")
    assert f and f[0]["status"] == "UNSUPPORTED_EVENT_TYPE" and f[0]["asserted"] == "acquisition"
    assert "equity investment (minority stake)" in f[0]["replacement"] and "Zeta Payments Private Limited" in f[0]["replacement"] and "acquisition" not in f[0]["replacement"].lower()


def test_a_real_acquisition_record_supports_the_word(tmp_path):
    L = company(tmp_path, [action("Acquired 100% of Omega Skincare Corporation", "Acquisition (business combination)", page=12)])
    f = V.verify_events(L, "The Omega acquisition added a skincare portfolio.")
    assert f and f[0]["status"] == "SUPPORTED_EVENT"


def test_a_event_with_no_matching_record_is_an_unsupported_premise(tmp_path):
    L = company(tmp_path, [action("Acquired 100% of Omega Skincare Corporation", "Acquisition (business combination)")])
    f = V.verify_events(L, "The Nimbus acquisition drove margin expansion.")
    assert f and f[0]["status"] == "UNSUPPORTED_EVENT_PREMISE"


def test_a_completion_needs_a_completed_record(tmp_path):
    L = company(tmp_path, [{**action("Agreement to acquire Orion Pharma", "Acquisition (business combination)"), "status": "signed, subject to regulatory approval"}])
    f = V.verify_events(L, "The completed Orion acquisition is now consolidated.")
    assert f and f[0]["status"] == "UNSUPPORTED_COMPLETION"
    ok = company(tmp_path / "b", [{**action("Acquired 100% of Orion Pharma", "Acquisition (business combination)"), "status": "completed"}])
    assert V.verify_events(ok, "The completed Orion acquisition is now consolidated.")[0]["status"] == "SUPPORTED_EVENT"


def test_a_unrelated_sentences_are_left_alone(tmp_path):
    L = company(tmp_path, [action("Acquired 200 equity shares of Zeta Payments Private Limited", "Equity investment (minority stake)")])
    assert V.verify_events(L, "Revenue grew 10% in FY26 on higher volumes.") == []
    assert V.verify_events(L, "Management's acquisition of skills in digital lending is a stated priority.") == []


@needs_root
def test_a_real_records_describe_vishvakarma_as_a_minority_equity_investment():
    L = led("ujjivan")
    f = V.verify_events(L, "Unverified allocations include equity issuance, Vishvakarma acquisition, organic capex.")
    assert f and f[0]["status"] == "UNSUPPORTED_EVENT_TYPE"
    assert re.search(r"FY21|200 .*shares|2,000|p\.77", f[0]["replacement"]) and "minority" in f[0]["replacement"]


# ── Case B: uncertainty wording must not recycle the premise ──
PREMISES = ["FY23 data missing due to merger transition", "the satisfaction score itself is not reported)", "this is a related measure, and the satisfaction score is not given", "no approval is reported",
            "Acquisition outcomes (Vishvakarma) not separately disclosed", "the filing date is not stated"]


@pytest.mark.parametrize("claim", PREMISES)
def test_b_generic_fallback_does_not_repeat_the_claim(claim):
    t = V.fallback_sentence(V.generic_fallback(claim))
    assert "“" not in t and "”" not in t, t                                        # nothing is quoted back as a statement
    claim_words = [w for w in re.findall(r"[a-z]{5,}", claim.lower()) if w not in {"which", "there", "their", "these", "other", "reported", "stated", "given", "separately", "disclosed"}]
    predicate = {"missing", "merger", "transition", "approval", "unavailable", "absent"}
    leaked = [w for w in claim_words if w in predicate and w in t.lower()]
    assert leaked == [], (t, leaked)
    assert "Not yet concluded" in t


def test_b_causal_tail_is_dropped_from_the_subject():
    t = V.fallback_sentence(V.generic_fallback("FY23 data missing due to merger transition"))
    assert "FY23 data" in t and not re.search(r"merger|transition|missing", t, re.I)


# ── all 91 candidate answers and the rendered surfaces ──
EVENT_ASSERT = re.compile(r"\bacquisitions?\b|\bacquired\b|\bmerger\b|\bamalgamation\b|\bcompleted\b|\bcompletion\b", re.I)


@needs_bundle
def test_no_unsupported_event_assertion_survives_in_any_of_the_91_answers():
    bad = []
    for f in sorted((WORK / "bundle" / "answers").glob("*.json")):
        d = json.loads(f.read_text())
        k = d["slot"].split(":")[0]
        for fld, _, t in G._text_fields(d["answer"]):
            for sent in re.split(r"(?<=[.;])\s+(?=[A-Z“\d])", " ".join(t.split())):
                for ev in V.verify_events(led(k), sent):
                    if ev["status"] not in ("SUPPORTED_EVENT",):
                        bad.append((d["slot"], fld, ev["status"], sent[:110]))
    assert bad == [], bad[:6]


@needs_bundle
def test_the_vishvakarma_acquisition_is_gone_from_investor_text():
    a = json.loads((WORK / "bundle" / "answers" / "ujjivan__how-is-capital-allocated.json").read_text())["answer"]
    t = json.dumps({k: v for k, v in a.items() if not k.startswith("g5_")}, ensure_ascii=False)
    assert not re.search(r"Vishvakarma\s+acquisition|acquisition[^.]{0,30}Vishvakarma", t, re.I)
    assert "equity investment (minority stake)" in t
    b = json.loads((WORK / "bundle" / "answers" / "ujjivan__what-remains-unresolved.json").read_text())["answer"]
    assert not re.search(r"Vishvakarma\s+acquisition", json.dumps({k: v for k, v in b.items() if not k.startswith("g5_")}, ensure_ascii=False), re.I)


@needs_bundle
def test_no_fallback_in_any_answer_quotes_a_recorded_statement_back():
    for f in sorted((WORK / "bundle" / "answers").glob("*.json")):
        a = json.loads(f.read_text())["answer"]
        for fld, _, t in G._text_fields(a):
            for m in re.finditer(r"Not yet concluded:[^.]*", t):
                assert "“" not in m.group(0), (f.name, m.group(0)[:120])


@needs_bundle
def test_rendered_surfaces_carry_no_unsupported_event_assertion():
    surf = json.loads((WORK / "surf_pass2.json").read_text())
    bad = []
    for k, ss in surf.items():
        for s in ss:
            if s["name"].startswith("question:"):
                continue
            for it in s["items"]:
                if ".g5_" in it["path"]:
                    continue
                for ev in V.verify_events(led(k), it["text"]):
                    if ev["status"] != "SUPPORTED_EVENT":
                        bad.append((k, s["name"], ev["status"], it["text"][:100]))
    assert bad == [], bad[:6]


@needs_root
def test_a_real_records_organon_is_signed_not_completed_and_subsidiary_deals_are_acquisitions():
    L = led("sun_pharma")
    assert V.verify_events(L, "The completed Organon acquisition is now consolidated.")[0]["status"] == "UNSUPPORTED_COMPLETION"
    assert V.verify_events(L, "The Organon acquisition is signed and awaits approvals.")[0]["status"] == "SUPPORTED_EVENT"
    assert V.verify_events(L, "The Alchemee acquisition added a consumer brand.")[0]["status"] == "SUPPORTED_EVENT"


@needs_root
def test_a_period_tokens_and_completed_amalgamation_are_not_misread_as_unsupported_events():
    L = led("ujjivan")
    assert V.verify_events(L, "Comparability is affected by the FY24 merger.") == []
    assert V.verify_events(L, "The Ujjivan Financial Services merger took effect in FY25.")[0]["status"] == "SUPPORTED_EVENT"
