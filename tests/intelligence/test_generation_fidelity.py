"""Generation-source hardening: the instructions and typed evidence that reach the model must carry each record's exact meaning (event type, status, amount unit, period, page).

These tests drive the REAL generation path (relationship_aware_composer.compose_answer_from_plan -> get_llm(...).generate) with a capturing stand-in for the provider (no AI call,
no cost) and assert on what the model would actually be given, for several companies and wordings. The downstream G5 verification gate is checked as the safety net."""
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from intelligence.ask_intrinsiciq import evidence_reasoner, relationship_aware_composer as C  # noqa: E402
from knowledge.capital_allocation_taxonomy import event_nature  # noqa: E402

CASES = {
    # id: (record, expected nature, expected completion, words that must be allowed, words that must be forbidden)
    "ujjivan_vishvakarma": ({"value": "Acquired 200 equity shares of Vishvakarma Payments Private Limited", "category": "Equity investment (minority stake)", "amount": "200 shares at INR 10 per share (total INR 2,000)",
                             "source_year": "fy21", "evidence_references": {"page": 77}}, "minority_or_subscription", "completed", ["invested in"], ["acquisition", "takeover"]),
    "other_bank_subscription": ({"value": "Subscribed to 5,000 equity shares of Zeta Fintech Pvt Ltd at par", "category": "Equity investment", "amount": "5,000 shares (total INR 50,000)",
                                 "source_year": "fy24", "evidence_references": {"page": 112}}, "minority_or_subscription", "unspecified", ["subscribed to shares of"], ["acquisition", "takeover"]),
    "sun_organon_pending": ({"value": "Proposed acquisition of Organon (signed; closing pending)", "category": "Acquisition", "status": "announced, subject to regulatory approvals", "source_year": "fy26",
                             "evidence_references": {"page": 311}}, "acquisition", "pending", ["agreed to acquire", "proposed acquisition"], ["completed", "closed"]),
    "completed_acquisition": ({"value": "Acquired 100% of Omega Skincare Corporation", "category": "Acquisition (business combination)", "status": "completed", "source_year": "fy23",
                               "evidence_references": {"page": 291}}, "acquisition", "completed", ["acquired"], []),
    "ufsl_amalgamation": ({"value": "Scheme of amalgamation with Ujjivan Financial Services; Effective Date April 30, 2024", "category": "Merger / amalgamation", "status": "effective", "source_year": "fy25",
                           "evidence_references": {"page": 327}}, "merger_or_amalgamation", "completed", ["amalgamation of"], ["acquired the company"]),
}


@pytest.mark.parametrize("cid", CASES)
def test_event_nature_is_decided_from_the_typed_record(cid):
    rec, nature, completion, allowed, forbidden = CASES[cid]
    n = event_nature(rec.get("category", ""), rec["value"], rec.get("status", ""))
    assert n["nature"] == nature and n["completion"] == completion
    assert all(w in n["allowed_wording"] for w in allowed) and all(w in n["forbidden_wording"] for w in forbidden)


class Capture:
    """Stands in for the provider: records exactly what the model is given."""
    def __init__(self):
        self.calls = []

    def generate(self, prompt, response_schema=None, max_tokens=None, system_prompt=None, **kw):
        self.calls.append({"prompt": prompt, "system": system_prompt})
        return type("R", (), {"text": json.dumps({"simple_answer": "ok", "why_it_matters": "ok", "investor_interpretation": "ok", "key_points": ["a", "b"]})})()


def run_pathway(monkeypatch, records, company="Acme"):
    cap = Capture()
    import knowledge.ai as ai
    monkeypatch.setattr(ai, "get_llm", lambda **k: cap)
    plan = C.build_composition_plan([], [], typed_evidence=records)
    C.compose_answer_from_plan(plan, "How is capital allocated?", company, model="test")
    return cap.calls[0]


@pytest.mark.parametrize("cid", CASES)
def test_the_model_is_given_the_events_type_status_amount_and_reference(monkeypatch, cid):
    rec, nature, completion, allowed, forbidden = CASES[cid]
    call = run_pathway(monkeypatch, [rec])
    for part in (call["system"], call["prompt"]):
        line = next(l for l in part.splitlines() if "[E1]" in l)
        assert f"nature: {nature}; status: {completion}" in line
        assert rec["value"] in line and (rec.get("category", "not stated") in line)
        assert f"p.{rec['evidence_references']['page']}" in line and rec["source_year"].upper() in line
        if rec.get("amount"):
            assert rec["amount"] in line                      # a share count keeps its unit wording; it is never turned into a currency figure
        for w in forbidden:
            assert w in line.split("never say:")[1]
        for w in allowed:
            assert w in line.split("say:")[1]


def test_the_contract_reaches_every_generation_prompt(monkeypatch):
    call = run_pathway(monkeypatch, [CASES["ujjivan_vishvakarma"][0]])
    assert "EVIDENCE FIDELITY CONTRACT" in call["system"]
    for kw in ("never what happened", "subscription or minority", "pending transaction", "Never state a cause", "Company-wide results", "count (for example a number of shares) is not a currency amount",
               "facts (what a record states", "interpretation", "unknowns"):
        assert kw in call["system"].replace("\n", " ") or kw.lower() in call["system"].lower(), kw
    assert "EVIDENCE FIDELITY" in evidence_reasoner._SYSTEM_PROMPT and "share subscription or minority investment is not an acquisition" in evidence_reasoner._SYSTEM_PROMPT
    from intelligence import regeneration_executor as R
    assert "EVIDENCE FIDELITY CONTRACT" in R._fidelity_block()
    src = (REPO / "intelligence/ask_intrinsiciq/shadow_runner.py").read_text()
    assert "typed_event_lines(composition_plan.get(\"typed_evidence\"))" in src          # the shadow path's user content (and cache key) carries the typed evidence too


def test_plan_without_typed_evidence_is_unchanged_apart_from_the_contract(monkeypatch):
    call = run_pathway(monkeypatch, [])
    assert "TYPED EVIDENCE RECORDS" not in call["system"] and "Typed evidence records" not in call["prompt"]
    assert "EVIDENCE FIDELITY CONTRACT" in call["system"]


def test_several_records_keep_their_own_meaning_side_by_side(monkeypatch):
    recs = [CASES[c][0] for c in ("ujjivan_vishvakarma", "sun_organon_pending", "completed_acquisition", "ufsl_amalgamation")]
    call = run_pathway(monkeypatch, recs)
    lines = [l for l in call["system"].splitlines() if re.match(r"\s+\[E\d\]", l)]
    assert [re.search(r"nature: (\w+); status: (\w+)", l).groups() for l in lines] == [("minority_or_subscription", "completed"), ("acquisition", "pending"), ("acquisition", "completed"), ("merger_or_amalgamation", "completed")]


def test_downstream_gate_remains_the_safety_net_for_a_model_that_ignores_the_contract(tmp_path):
    """Defence in depth: even if a model writes 'the Zeta acquisition' for a subscription, the G5 event check flags it."""
    from pipelines import g5_verify as V
    from tests.intelligence.test_g5_positive_claims import action, company
    L = company(tmp_path, [action(CASES["other_bank_subscription"][0]["value"], "Equity investment", page=112)])
    bad = V.verify_events(L, "Growth was supported by the Zeta acquisition in FY24.")
    assert bad and bad[0]["status"] == "UNSUPPORTED_EVENT_TYPE"
    good = V.verify_events(L, "The bank invested in Zeta Fintech through an equity subscription in FY24.")
    assert good == []


def test_the_nature_vocabulary_is_shared_by_generation_and_verification():
    from pipelines import g5_verify as V
    import knowledge.capital_allocation_taxonomy as T
    assert V.ACQ_TYPE is T.ACQ_TYPE and V.MINOR_TYPE is T.MINOR_TYPE


@pytest.mark.parametrize("company,name,nature", [("ujjivan", "Vishvakarma", "minority_or_subscription"), ("sun_pharma", "Alchemee", "acquisition")])
def test_real_company_records_reach_the_model_with_their_own_event_type(monkeypatch, company, name, nature):
    recs = C.typed_events_from_timeline(REPO / "companies" / company, [name])
    assert recs, "the record is in the company's timeline"
    call = run_pathway(monkeypatch, recs, company)
    line = next(l for l in call["system"].splitlines() if "[E1]" in l)
    assert f"nature: {nature}" in line and name in line
    if nature == "minority_or_subscription":
        assert "INR 2,000" in line and "FY21" in line and "p.77" in line and "never say: acquisition" in line
