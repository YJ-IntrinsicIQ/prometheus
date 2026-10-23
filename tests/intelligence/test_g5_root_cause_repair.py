"""M63 / G5 root-cause repair: the five defects of the independent mechanism audit (D1-D5), written first as failing regression tests.

The 34 audit claims (23 of which the previous gate wrongly VERIFIED) are replayed on the real evidence root through the real gate; no company, claim or expected answer is hard-coded
in the production code. D4/D5 are checked on the 91 proposed answers and, in the app, by tests/vitest files that read the same scratch candidate."""
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

ROOT = Path(os.environ.get("G5B_ROOT", "/private/tmp/claude-501/g4/root"))
WORK = Path(os.environ.get("G5C_DIR", "/private/tmp/claude-501/g5c"))
CASES = json.loads((REPO / "tests/fixtures/g5_mechanism_audit_cases.json").read_text())["cases"]
needs_root = pytest.mark.skipif(not ROOT.exists(), reason="evidence root absent")
needs_bundle = pytest.mark.skipif(not (WORK / "bundle" / "answers").exists(), reason="scratch candidate absent")
_L: dict = {}


def led(k):
    if k not in _L:
        _L[k] = g4.Ledger(k, ROOT)
    return _L[k]


def judged(k, text):
    out = []
    for c in G.split_clauses(text):
        cls, _ = G.classify(c)
        if cls in G.GENUINE:
            out.append(G.judge(led(k), c, cls, text))
    return out


# ───────────────────── the documented failures (D1-D3): 23 unsupported VERIFIED ─────────────────────
@needs_root
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_audit_claim_is_not_verified_unless_the_exact_claim_is_proven(case):
    js = judged(case["company"], case["claim"])
    assert js, "still recognised as an absence claim"
    if case["expect"] == "must_not_verify":
        assert not any(j["status"].startswith("VERIFIED") for j in js), (case["id"], case["audit_boundary"], [(j["status"], j["reasons"]) for j in js])
    else:                                  # the positive control: DP standalone FY26 ROCE 23%, record null for FY26
        j = js[0]
        assert j["status"] == "VERIFIED_NOT_EXTRACTED"
        f = j["verification"]["source_facts"][0]
        assert f["value"] == 23.0 and f["basis"] == "standalone" and f["fy"] == "fy26" and f["unit"] == "%"


@needs_root
def test_zero_unsupported_verified_across_the_documented_23():
    bad = [c["id"] for c in CASES if c["audit_found_unsupported_verified"] and any(j["status"].startswith("VERIFIED") for j in judged(c["company"], c["claim"]))]
    assert bad == []


@needs_root
def test_d1_claim_identity_company_basis_period_qualifier_and_forecast_are_matched():
    cases = {
        "Tanla return on capital employed is not extracted into the records": ("datapatterns", "WRONG_COMPANY"),
        "Consolidated return on capital employed is not extracted into the records": ("datapatterns", "BASIS_"),
        "Return on capital employed for the EMI-EMC Testing Facility is not extracted into the records": ("datapatterns", "QUALIFIER_NOT_MATCHED"),
        "Expected return on capital employed is not extracted into the records": ("datapatterns", "FORECAST_NOT_ACTUAL"),
        "Return on capital employed of 22% is not extracted into the records": ("datapatterns", "ASSERTED_VALUE_"),
    }
    for text, (k, code) in cases.items():
        j = judged(k, text)[0]
        assert not j["status"].startswith("VERIFIED") and any(r.startswith(code) for r in j["reasons"]), (text, j["reasons"])


@needs_root
def test_d2_every_asserted_component_is_verified_or_the_claim_fails_closed():
    for k, text in (("datapatterns", "Return on capital employed and inventory turnover are not extracted into the records"), ("tanla", "Return on capital employed and product defect rates are not extracted into the records"),
                    ("sun_pharma", "Contingent liabilities and export-control exposure are not extracted into the records"), ("ujjivan", "Interest coverage and product pipeline do not apply to a bank")):
        j = judged(k, text)[0]
        assert not j["status"].startswith("VERIFIED") and any(r.startswith("UNSUPPORTED_COMPONENT") for r in j["reasons"]), (text, j["reasons"])
        assert "components" in j["verification"] and len(j["verification"]["components"]) >= 2


@needs_root
def test_d2_applicability_is_decided_per_component_with_no_sector_blanket():
    assert judged("ujjivan", "Interest coverage does not apply to a bank")[0]["status"] == "VERIFIED_NOT_APPLICABLE"
    assert not judged("ujjivan", "Customer retention does not apply to a bank")[0]["status"].startswith("VERIFIED")
    assert not judged("ujjivan", "Return on capital employed and customer retention do not apply to a bank")[0]["status"].startswith("VERIFIED")


@needs_root
def test_d3_mixed_basis_table_keeps_its_local_basis_and_every_column():
    facts = V.EXTRACTORS["interest_coverage"](led("sun_pharma"))
    assert facts and all(f["basis"] in ("standalone", "consolidated") for f in facts), [f["basis"] for f in facts]       # never the 'unknown' stamp on a mixed table
    j = judged("sun_pharma", "Consolidated interest coverage of 49.5 times is not extracted into the records")[0]
    assert not j["status"].startswith("VERIFIED")
    f = V.EXTRACTORS["roce"](led("datapatterns"))[0]
    assert f["values"][:3] == [23.0, 22.0, 7.0] and f["value"] == 23.0                                                    # current, prior, variance columns kept
    for v in ("22%", "7%"):
        assert not judged("datapatterns", f"Return on capital employed of {v} is not extracted into the records")[0]["status"].startswith("VERIFIED")


@needs_root
def test_d3_contingent_liability_keeps_unit_and_subcategory_and_does_not_prove_a_total():
    fs = V.EXTRACTORS["contingent"](led("sun_pharma"))
    assert fs and all(f["unit"].lower().startswith("inr") and "million" in f["unit"].lower() and f.get("subcategory") for f in fs)
    assert not judged("sun_pharma", "Total contingent liabilities of 443.6 million rupees are not extracted into the records")[0]["status"].startswith("VERIFIED")
    assert not judged("sun_pharma", "Contingent liabilities are not extracted into the records")[0]["status"].startswith("VERIFIED")        # a subcategory is not the aggregate


@needs_root
def test_d3_concentration_subtype_basis_denominator_and_counts_are_preserved():
    assert not judged("ujjivan", "Customer concentration is not extracted into the records")[0]["status"].startswith("VERIFIED")        # 17.16% is depositor funding concentration
    assert not judged("ujjivan", "Borrower concentration of 17.16% is not extracted into the records")[0]["status"].startswith("VERIFIED")
    assert not judged("tanla", "Consolidated customer concentration is not extracted into the records")[0]["status"].startswith("VERIFIED")
    assert not judged("tanla", "Customer concentration for three major customers is not extracted into the records")[0]["status"].startswith("VERIFIED")
    assert judged("ujjivan", "Deposit concentration is not extracted into the records")[0]["status"] == "VERIFIED_NOT_EXTRACTED"


@needs_root
def test_d3_declared_basis_survives_a_null_current_year_row():
    j = judged("datapatterns", "Return on capital employed is not extracted into the records")[0]
    rf = j["verification"]["record_facts"][0]
    assert rf["present"] is False and rf["basis"] != "unknown"


# ───────────────────── fallback quality (only facts that pass verification) ─────────────────────
@needs_root
def test_fallback_uses_only_verified_facts_and_isolates_the_unproven_component():
    j = judged("sun_pharma", "Margins by revenue source and the split of revenue between sources are not extracted into the records")[0]
    t = j["rewrite"]
    assert "four" in t or "4" in t or "India" in t, t                      # the available mix is stated
    assert re.search(r"margin", t.split("Not yet")[1], re.I) and "revenue and margins" not in t
    w = judged("tanla", "Customer concentration for three major customers is not extracted into the records")[0]
    assert "86" not in (w.get("rewrite") or "")                            # a source fact that failed identity matching is not repeated as established


@needs_root
def test_fallback_is_compact_and_has_no_internal_counts():
    for k, text in (("sun_pharma", "The split between maintenance and growth capital spending is not disclosed"), ("datapatterns", "The maintenance-versus-growth capex split is not disclosed")):
        t = judged(k, text)[0]["rewrite"]
        assert len(t.split()) <= 70 and not re.search(r"\b\d{3,} sections\b", t), t


# ───────────────────── D4/D5: what the investor sees ─────────────────────
INTERNAL = re.compile(r"\bg[45]\d*_|\bUNRESOLVED\b|\bNOT_EXTRACTED\b|\bNOT_DISCLOSED\b|\bNOT_APPLICABLE\b|PENDING_HUMAN|_CANDIDATE|NEEDS_REVIEW|UNVERIFIED_SCOPED|replaces_status|evidence_group|record_verified")      # machine tokens (case-sensitive): ordinary English such as 'remain unresolved' is fine


@needs_bundle
def test_d4_no_unsupported_definitive_statement_survives_in_any_of_the_91_answers():
    bad = []
    for f in sorted((WORK / "bundle" / "answers").glob("*.json")):
        d = json.loads(f.read_text())
        k = d["slot"].split(":")[0]
        for fld, _, t in G._text_fields(d["answer"]):
            for sent in re.split(r"(?<=[.;])\s+(?=[A-Z“\d])", " ".join(t.split())):
                for c in G.split_clauses(sent):
                    cls, _r = G.classify(c)
                    if cls in G.GENUINE:
                        j = G.judge(led(k), c, cls, sent)
                        if not j["status"].startswith("VERIFIED") and not j.get("record_statement_ok"):
                            bad.append((d["slot"], c[:100], j["status"]))
    assert bad == [], bad[:5]


@needs_bundle
def test_d4_the_documented_survivors_are_gone():
    a = json.loads((WORK / "bundle" / "answers" / "ujjivan__how-is-capital-allocated.json").read_text())["answer"]
    t = json.dumps({k: v for k, v in a.items() if not k.startswith("g5_")}, ensure_ascii=False)         # investor-visible fields; the audit lists keep the original claim text
    asserted = re.sub(r"“[^”]*”", " ", t)                                                              # a quoted, attributed record statement inside "Not yet concluded" is not an assertion
    assert "FY23 data missing due to merger transition" not in asserted
    assert not re.search(r"Vishvakarma\s+(?:acquisition|transaction)|acquisition[^.]{0,40}Vishvakarma", t) or "could not be matched" in t
    s = json.dumps({k: v for k, v in json.loads((WORK / "bundle" / "answers" / "tanla__what-could-go-wrong.json").read_text())["answer"].items() if not k.startswith("g5_")}, ensure_ascii=False)
    assert "Pending-transaction exposure: mentioned in the filing" not in s


@needs_bundle
def test_d4_ledgers_carry_a_replacement_for_every_unsupported_definitive_projection_statement():
    n = 0
    for k in ("sun_pharma", "tanla", "ujjivan", "datapatterns"):
        led_ = json.loads((WORK / "root" / "companies" / k / "company_memory" / "ask_intrinsiciq" / "g5_absence_provenance.json").read_text())["entries"]
        for e in led_:
            if e["verification"] != "VERIFIED" and not e.get("record_statement_ok"):
                assert e.get("replacement") and "Not yet concluded" in e["replacement"], e["claim"][:80]
                n += 1
    assert n > 0


@needs_bundle
def test_d5_investor_text_of_all_answers_carries_no_internal_verification_metadata():
    for f in sorted((WORK / "bundle" / "answers").glob("*.json")):
        a = json.loads(f.read_text())["answer"]
        for fld, _, t in G._text_fields(a):
            assert not INTERNAL.search(t), (f.name, fld, t[:100])


@needs_bundle
def test_candidate_is_a_new_hash_pinned_directory_and_the_audited_bundle_is_untouched():
    m = json.loads((REPO / "preview" / "m63_g5_root_cause_manifest.json").read_text())
    assert m["bundle_hash_H3"] and m["supersedes"] == "16378855a34a5fbe87e9c0154aceb3ed10d77b233bc36033f2dcd6e5c11d0984"
    assert m["rendered_surfaces_sha256"] and len(m["answers"]) == 91
    assert str(WORK) != "/private/tmp/claude-501/g5b"


@needs_root
def test_a_verified_claim_also_gives_the_verified_source_figure_it_was_checked_against():
    j = judged("tanla", "Return on capital employed is not extracted into the records")[0]
    assert j["status"] == "VERIFIED_NOT_EXTRACTED" and re.search(r"report states return on capital employed \(ROCE\) of 24\.2% \(consolidated, p\.\d+\)", j["supplement"])
    d = judged("datapatterns", "Return on capital employed is not extracted into the records")[0]
    assert "23%" in d["supplement"] and "standalone" in d["supplement"]
