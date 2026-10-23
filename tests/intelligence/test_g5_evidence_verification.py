"""M63 / G5 evidence verification gate (pipelines/g5_verify.py).

Part A replays the 24 challenged cases of the independent adjudication (preview/M63_G5_EVIDENCE_DECISIONS.json) on the real evidence root: none of the 21 that the adjudication
rejected or called incomplete may be VERIFIED without both legs. Part B uses a synthetic company so wrong-year, wrong-company, wrong-basis, wrong-project, unrelated-metric,
conflicting-source, missing-probe and compound claims can be built exactly. Part C checks the proposed bundle and the investor fallback."""
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
BUNDLE = Path(os.environ.get("G5B_DIR", "/private/tmp/claude-501/g5b"))
DECISIONS = REPO / "preview" / "M63_G5_EVIDENCE_DECISIONS.json"
needs_root = pytest.mark.skipif(not ROOT.exists(), reason="evidence root absent")
needs_bundle = pytest.mark.skipif(not (BUNDLE / "bundle" / "answers").exists(), reason="scratch bundle absent")
_L: dict = {}


def led(k):
    if k not in _L:
        _L[k] = g4.Ledger(k, ROOT)
    return _L[k]


def judged(L, text, context=""):
    out = []
    for c in G.split_clauses(text):
        cls, _ = G.classify(c)
        if cls in G.GENUINE:
            out.append(G.judge(L, c, cls, context or text))
    return out


# ───────────────────────── Part A: the 24 independent challenge cases ─────────────────────────
SAMPLE = json.loads(DECISIONS.read_text())["machine_supported_sample"] if DECISIONS.exists() else []


@needs_root
@pytest.mark.parametrize("s", SAMPLE, ids=[x["sample_id"] for x in SAMPLE])
def test_challenged_case_is_not_verified_unless_both_legs_prove_it(s):
    js = judged(led(s["company"]), s["exact_claim"])
    assert js, "the claim is still recognised as an absence claim"
    for j in js:
        v = j["verification"]
        if j["status"].startswith("VERIFIED"):
            assert s["independent_result"] in ("SUPPORTED_WITH_SCOPE", "INCOMPLETE_RECORD_BASIS"), (s["sample_id"], "unsupported VERIFIED")
            if j["status"] == "VERIFIED_NOT_EXTRACTED":
                assert v["source_facts"] and v["record_facts"] and all(r["present"] is False for r in v["record_facts"])      # both legs, record absent in the claim's FY
                assert all(f["company"] == s["company"] and f["fy"] == led(s["company"]).fy and f["page"] for f in v["source_facts"])
        else:
            assert j["fallback"], "a claim that is not verified still gets an investor fallback"


@needs_root
def test_zero_unsupported_verified_promotions_across_the_24():
    bad = []
    for s in SAMPLE:
        for j in judged(led(s["company"]), s["exact_claim"]):
            if j["status"].startswith("VERIFIED") and s["independent_result"] == "FALSE_POSITIVE_VERIFICATION":
                bad.append(s["sample_id"])
    assert bad == []


@needs_root
def test_the_four_incomplete_or_scoped_verifications_carry_their_scope():
    for s in SAMPLE:
        if s["independent_result"] in ("SUPPORTED_WITH_SCOPE", "INCOMPLETE_RECORD_BASIS"):
            for j in judged(led(s["company"]), s["exact_claim"]):
                if j["status"].startswith("VERIFIED"):
                    f = j["verification"]["source_facts"][0]
                    assert f["fy"] and f["basis"] and f["metric"] and f["value"] is not None


@needs_root
def test_sun_geography_in_the_company_model_contradicts_a_blanket_mix_claim():
    j = judged(led("sun_pharma"), "Margins by revenue source and the split of revenue between sources are not extracted into the records")[0]
    assert j["status"] == "CONTRADICTED" and "RECORD_HOLDS_THE_FIGURE" in j["reasons"]
    assert "records already hold revenue by engine" in V.fallback_sentence(j["fallback"])


@needs_root
def test_current_year_probe_is_period_specific_for_data_patterns_roce():
    j = judged(led("datapatterns"), "Return on capital employed is not extracted into the records")[0]
    rf = j["verification"]["record_facts"][0]
    assert rf["present"] is False and "other years with a value" in rf["detail"]     # a FY22 value no longer hides a missing FY26 value
    assert j["status"] == "VERIFIED_NOT_EXTRACTED" and j["verification"]["source_facts"][0]["value"] == 23.0


# ───────────────────────── Part B: fresh adversarial claims on a synthetic company ─────────────────────────
class FakeL:
    def __init__(self, tmp, key="acme", fy="fy26", bank=False, chunks=(), trends=None, model=None, projects=None, basis="consolidated"):
        self.key, self.fy, self.bank, self.name, self._c, self.facts, self._basis = key, fy, bank, "Acme Ltd", {}, {}, basis
        self.cdir = tmp / "companies" / key
        self.mem = self.cdir / "company_memory"
        (self.cdir / fy / "extracted").mkdir(parents=True)
        (self.cdir / fy / "extracted" / "clean_chunks.json").write_text(json.dumps({"chunks": [{"page": p, "text": t} for p, t in chunks]}))
        for rel, obj in (("financials/financial_trends.json", {"trend_groups": trends or {}}), ("company_model/company_model.json", model or {}), ("projects/projects_registry.json", {"projects": projects or []}),
                         ("capacity/capacity_registry.json", {"capacity_items": []})):
            f = self.mem / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(obj))

    def j(self, path):
        k = str(path)
        if k not in self._c:
            try:
                self._c[k] = json.loads(Path(path).read_text())
            except Exception:
                self._c[k] = None
        return self._c[k]

    def m(self, rel):
        return self.j(self.mem / rel)

    def section_basis(self, page):
        return self._basis


def series(group, metric, pts):
    return {group: {metric: {"series": [{"year": y, "value": v, "basis": b} for y, v, b in pts]}}}


def verify(L, text):
    out = G.judge(L, text, G.classify(text)[0], text)
    return out


ROCE_TEXT = [(40, "Return on Capital Employed 24.2% Free Cash Flow INR 477 Cr")]


def test_baseline_both_legs_present_verifies(tmp_path):
    L = FakeL(tmp_path, chunks=ROCE_TEXT, trends=series("return_on_capital", "roce", [("fy22", 30.0, "consolidated")]))
    j = verify(L, "Return on capital employed is not extracted into the records")
    assert j["status"] == "VERIFIED_NOT_EXTRACTED" and j["verification"]["source_facts"][0]["page"] == 40


def test_wrong_year_in_the_claim_blocks_verification(tmp_path):
    L = FakeL(tmp_path, chunks=ROCE_TEXT)
    j = verify(L, "Return on capital employed for FY24 is not extracted into the records")
    assert not j["status"].startswith("VERIFIED") and any(r.startswith("WRONG_OR_UNMATCHED_PERIOD") for r in j["reasons"])


def test_record_value_in_the_claims_year_contradicts(tmp_path):
    L = FakeL(tmp_path, chunks=ROCE_TEXT, trends=series("return_on_capital", "roce", [("fy26", 24.0, "consolidated")]))
    assert verify(L, "Return on capital employed is not extracted into the records")["status"] == "CONTRADICTED"


def test_wrong_company_source_fact_is_rejected(tmp_path, monkeypatch):
    L = FakeL(tmp_path, trends=series("return_on_capital", "roce", []))
    other = V.source_fact("someone_else", "fy26", "consolidated", "roce", 40, "ROCE 24.2%", 24.2, "%")
    monkeypatch.setitem(V.EXTRACTORS, "roce", lambda _L: [other])
    j = verify(L, "Return on capital employed is not extracted into the records")
    assert not j["status"].startswith("VERIFIED") and any(r.startswith(("SOURCE_IDENTITY_MISMATCH", "NO_EXACT_SOURCE_FACT")) for r in j["reasons"])


def test_standalone_source_against_consolidated_record_is_not_verified(tmp_path):
    L = FakeL(tmp_path, chunks=ROCE_TEXT, basis="standalone", trends=series("return_on_capital", "roce", [("fy26", None, "consolidated")]))
    L.mem.joinpath("financials/financial_trends.json").write_text(json.dumps({"trend_groups": {"return_on_capital": {"roce": {"series": []}}}}))
    ok = verify(L, "Return on capital employed is not extracted into the records")
    assert ok["status"] == "VERIFIED_NOT_EXTRACTED" and ok["verification"]["source_facts"][0]["basis"] == "standalone"      # the scope names the basis
    probe = V.record_fact("acme", "fy26", "roce", False, "x", "", basis="consolidated")
    src = V.source_fact("acme", "fy26", "standalone", "roce", 40, "", 24.2, "%")
    L2 = FakeL(tmp_path / "b", chunks=ROCE_TEXT)
    V.EXTRACTORS_BACKUP = V.EXTRACTORS["roce"]
    try:
        V.EXTRACTORS["roce"] = lambda _L: [src]
        V.PROBES["roce"] = lambda _L, _t: probe
        j = verify(L2, "Return on capital employed is not extracted into the records")
    finally:
        V.EXTRACTORS["roce"] = V.EXTRACTORS_BACKUP
        V.PROBES["roce"] = V._trend_probe
    assert not j["status"].startswith("VERIFIED") and any(r.startswith("BASIS_MISMATCH") for r in j["reasons"])


def test_unrelated_metric_is_not_a_source_fact(tmp_path):
    L = FakeL(tmp_path, chunks=[(12, "Return on Equity 15.2% Debt Service Coverage Ratio 2.1 Net worth 450")])
    assert not verify(L, "Return on capital employed is not extracted into the records")["status"].startswith("VERIFIED")
    assert not verify(L, "Interest coverage is not extracted into the records")["status"].startswith("VERIFIED")


def test_number_before_label_layout_and_growth_rates_are_leads_not_facts(tmp_path):
    L = FakeL(tmp_path, chunks=[(6, "17% ROE and 23% ROCE 32% Revenue and 27% EBITDA CAGR"), (10, "Book Value per Share Earnings per Share 8% YoY 18% YoY")])
    assert V.EXTRACTORS["roce"](L) == [] and V.EXTRACTORS["book_value"](L) == []


def test_conflicting_values_on_one_basis_fail_closed(tmp_path):
    L = FakeL(tmp_path, chunks=[(40, "Return on Capital Employed 24.2% for the year"), (41, "Return on Capital Employed 19.0% for the year")])
    j = verify(L, "Return on capital employed is not extracted into the records")
    assert not j["status"].startswith("VERIFIED") and "SOURCE_CONFLICT_SAME_BASIS" in j["reasons"]


def test_profile_without_a_destination_probe_can_never_verify(tmp_path):
    L = FakeL(tmp_path, chunks=[(8, "Research and development expense 120.5 crore; pipeline stage II 3 molecules")])
    j = verify(L, "Research and development spending is not in the structured records")
    assert not j["status"].startswith("VERIFIED") and "NO_DESTINATION_RECORD_PROBE" in j["reasons"]


def test_compound_claim_needs_every_component(tmp_path):
    L = FakeL(tmp_path, chunks=ROCE_TEXT + [(41, "Book Value per Share 310.0")], trends={**series("return_on_capital", "roce", []), **series("per_share", "book_value_per_share", [("fy26", 310.0, "consolidated")])})
    j = verify(L, "Return on capital employed and book value per share are not extracted into the records")
    assert j["status"] == "CONTRADICTED"                                  # book value is in the record even though ROCE is not
    L2 = FakeL(tmp_path / "c", chunks=ROCE_TEXT, trends=series("return_on_capital", "roce", []))
    j2 = verify(L2, "Return on capital employed and book value per share are not extracted into the records")
    assert not j2["status"].startswith("VERIFIED")                        # book value has no source fact


def test_revenue_and_margins_are_independent_components(tmp_path):
    L = FakeL(tmp_path, model={"economic_engines": {"coverage_status": "SUPPORTED", "engines": [{"engine_name": "India", "history": [{"revenue_share": 0.4}]}]}})
    j = verify(L, "Margins by revenue source and the split of revenue between sources are not extracted into the records")
    assert j["status"] == "CONTRADICTED"


def test_named_project_must_exist_in_the_records(tmp_path):
    L = FakeL(tmp_path, projects=[{"project_name": "Halol Expansion", "expected_cost": "", "expected_output_or_capacity": "", "current_status": "operational"}])
    j = verify(L, "Utilisation is not given in the project records for the Zeta Plant")
    assert not j["status"].startswith("VERIFIED") and any(r.startswith("SUBJECT_NOT_IN_RECORD") for r in j["reasons"])


def test_project_cost_output_returns_are_separate_components(tmp_path):
    L = FakeL(tmp_path, projects=[{"project_name": "Halol Expansion", "expected_cost": "", "expected_output_or_capacity": "5 million units", "current_status": "operational"}])
    j = verify(L, "Cost, output, utilisation and returns are not given in the project records")
    assert j["verification"]["record_facts"] and all(r["present"] is False for r in j["verification"]["record_facts"])      # a planned output is not an achieved one
    L2 = FakeL(tmp_path / "d", projects=[{"project_name": "Halol Expansion", "actual_output": "4 million units"}])
    assert verify(L2, "Cost, output, utilisation and returns are not given in the project records")["status"] == "CONTRADICTED"


def test_not_disclosed_is_never_verified_even_with_a_failed_search(tmp_path):
    L = FakeL(tmp_path, chunks=[(1, "Revenue grew")])
    j = verify(L, "The annual report provides no ROCE figure")
    assert j["status"].startswith("UNRESOLVED") and "NOT_DISCLOSED_NEEDS_HUMAN_SIGNOFF" in j["reasons"]


def test_source_negative_is_contradicted_when_the_report_carries_it(tmp_path):
    L = FakeL(tmp_path, chunks=ROCE_TEXT)
    j = verify(L, "The annual report provides no ROCE figure")
    assert j["status"] == "CONTRADICTED" and j["rewrite"]


def test_inapplicability_is_accepted_only_where_total(tmp_path):
    bank = FakeL(tmp_path, bank=True)
    assert verify(bank, "Interest coverage does not apply to a bank")["status"] == "VERIFIED_NOT_APPLICABLE"
    assert not verify(bank, "The maintenance versus growth capex split does not apply to a bank")["status"].startswith("VERIFIED")
    assert not verify(FakeL(tmp_path / "i"), "Interest coverage does not apply to this company")["status"].startswith("VERIFIED")


def test_risk_response_claim_without_a_named_risk_is_not_verifiable(tmp_path):
    L = FakeL(tmp_path)
    j = verify(L, "No management response is recorded in the risk timeline")
    assert not j["status"].startswith("VERIFIED") and "SUBJECT_NOT_IDENTIFIED" in j["reasons"]


# ───────────────────────── Part C: investor fallback and the bundle ─────────────────────────
INTERNAL = re.compile(r"UNRESOLVED|NOT_EXTRACTED|NOT_DISCLOSED|NOT_APPLICABLE|PENDING_HUMAN|_CANDIDATE|NEEDS_REVIEW|UNVERIFIED_SCOPED")      # (UNVERIFIED alone is the existing commitment-tracker label in approved answers)


@needs_root
def test_fallback_has_the_four_parts_and_prints_no_internal_state():
    j = judged(led("sun_pharma"), "The split between maintenance and growth capital spending is not disclosed")[0]
    fb = j["fallback"]
    assert fb["established"] and fb["not_concluded"] and fb["why_it_matters"] and fb["would_resolve"]
    text = j["rewrite"]
    assert not INTERNAL.search(text) and "Not yet concluded" in text and "disclosed" not in text.split("Not yet concluded")[0].replace("not disclosed", "")


@needs_root
def test_fallback_never_turns_partial_evidence_into_a_conclusion():
    j = judged(led("tanla"), "The maintenance-versus-growth capex split is not disclosed")[0]
    t = j["rewrite"]
    assert not re.search(r"\b(is|are) not disclosed\b|\bdoes not disclose\b|\bnot reported\b", t)
    assert re.search(r"found no|not yet", t)


@needs_root
def test_fallback_for_a_pending_transaction_claim_does_not_assert_pending_exposure():
    j = judged(led("ujjivan"), "Pending-transaction exposure: mentioned in the filing but not yet extracted into the records (the filing discloses a completed corporate action)")
    assert j and not any(x["status"].startswith("VERIFIED") for x in j)


@needs_bundle
def test_bundle_has_no_unsupported_verified_entry_and_no_internal_state_in_investor_text():
    n_ver = 0
    for f in sorted((BUNDLE / "bundle" / "answers").glob("*.json")):
        a = json.loads(f.read_text())["answer"]
        for e in a.get("g5_absence", []):
            if e.get("verification") == "VERIFIED":
                n_ver += 1
                assert e["state"] in ("NOT_EXTRACTED", "NOT_APPLICABLE") and (e["state"] == "NOT_APPLICABLE" or re.search(r"p\.\d", e["basis"]))
        for fld in ("simple_answer", "what_evidence_shows", "what_may_mean_economically", "what_is_not_yet_proven", "what_to_monitor", "key_points", "evidence_gaps"):
            v = a.get(fld)
            for t in v if isinstance(v, list) else [v or ""]:
                assert not INTERNAL.search(str(t)), (f.name, fld, str(t)[:100])
    assert n_ver >= 0


@needs_bundle
def test_bundle_text_keeps_no_source_negative_that_the_gate_cannot_verify():
    L = {}
    bad = []
    for f in sorted((BUNDLE / "bundle" / "answers").glob("*.json")):
        d = json.loads(f.read_text())
        k = d["slot"].split(":")[0]
        L.setdefault(k, led(k))
        for fld, _, t in G._text_fields(d["answer"]):
            for sent in re.split(r"(?<=[.;])\s+(?=[A-Z“\d])", " ".join(t.split())):
                for c in G.split_clauses(sent):
                    cls, _r = G.classify(c)
                    if cls in G.GENUINE:
                        j = G.judge(L[k], c, cls, sent)
                        if j["status"] in ("CONTRADICTED", "WRONG_NOT_APPLICABLE_CLAIM") or (j["topic"] and j["level"] in ("SOURCE_NEGATIVE", "NOT_APPLICABLE") and not j["status"].startswith("VERIFIED")):      # unprofiled sentences stay as approved and are queued
                            bad.append((d["slot"], c[:90]))
    assert bad == []
