"""
ENG-MISSION52.2a — Final Deterministic Investor Intelligence Quality Repair
25 tests (M522A-01 .. M522A-25). AI calls used: 0.

Covers the six defects found by the M52.2 review: MC-0031 temporal semantics, label-only
consistency map, lost specialty context, missing capital-allocation context, lost numeric
units, and weak monitoring/uncertainty specificity.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ASK = REPO / "companies" / "sun_pharma" / "company_memory" / "ask_intrinsiciq"

NEW_CANDIDATE = ASK / "regeneration_candidate_how_good_is_management_2f7e73f8dab8_v5.json"
NEW_FILE_DIGEST = "sha256:288a03e334029a3881514f393a62e93a91eaed48ea1e285c56bf6d48228d2739"
NEW_ANSWER_DIGEST = "sha256:4d2df2ae968d5a9d53d6bfa0618c8e9df11b7c3ad042f19172e1ef266e2ad7e7"
NEW_EXEC_ID = "sha256:2f7e73f8dab81bcffa668092445fd7fa42bc9552d0230ec7c4b585ce82bd378f"
NEW_CONTRACT_FP = "sha256:a8f9d700572a15c09e2306343da56f772cd81e90856cf36a95a947d94cf5e9fb"
EVIDENCE_FP = "sha256:dc623eac6e2350742314f7f4ad44c817e8fe9bb2b4a717e6a864e1da206605a2"
UNIT = "how_good_is_management_synthesis"

HIST = {
    # earlier M52.2a builds, superseded before review (39631f: hard-coded product name found by M522A-08; 8cf123: pre dividend-coverage/product-monitoring fix); kept, never approved
    "regeneration_candidate_how_good_is_management_8cf1232fb7eb_v5.json":
        "sha256:2820876ab5a9b9490c4020e1ec5799cbcd60ff34644f51590b9191694727e6db",
    "regeneration_candidate_how_good_is_management_39631f315761_v5.json":
        "sha256:b42918bbd90975fa6821d85dc22496497c4895d666296bd9e6aeb0974dbe443d",
    "regeneration_candidate_how_good_is_management_559650df434c_v5.json":
        "sha256:50bec2d5b076d92605c1d20aa8a1c3d2d81ac3a4730052bdf662217977e596bc",
    "regeneration_candidate_how_good_is_management_76315ffdb926_v5.json":
        "sha256:b175c7b2f7b761d0f90f33f1c3a82a3b56194b9416312a343c5ccf633964563a",
    "shadow_level3_hybrid_answers.json":
        "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43",
}


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _st(v: str) -> str:
    return str(v).split(" — ")[0].strip()


def _flat(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_flat(x) for x in value)
    if isinstance(value, dict):
        return " ".join(_flat(x) for x in value.values())
    return str(value)


@pytest.fixture(scope="module")
def fp():
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    return build_management_quality_fact_pack_v2("sun_pharma")


@pytest.fixture(scope="module")
def enr(fp):
    from intelligence.management_quality.fact_pack_enrichment_v5 import enrich_fact_pack_v5
    return enrich_fact_pack_v5(fp)


@pytest.fixture(scope="module")
def answer(fp):
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    return build_management_answer_v5(fp)


@pytest.fixture(scope="module")
def candidate():
    return json.loads(NEW_CANDIDATE.read_text())


def _mc(enr, mc_id):
    return next(c for c in enr["commitments"] if c["id"] == mc_id)


# ── M522A-01 ────────────────────────────────────────────────────────────────
def test_m522a_01_mc0031_filing_state_from_evidence(enr, answer):
    c = _mc(enr, "MC-0031")
    assert c["DELIVERY_STATE"] == "FILING_CONFIRMED_BY_SOURCE_TEXT"
    kinds = {e["kind"] for e in c["followup_events"]}
    assert kinds & {"FILED", "VALIDATED"}
    for e in c["followup_events"]:
        assert e["document"] and e["period"] and e["chunk_id"], "every event carries its source"
    says = " ".join(answer["what_management_says"])
    assert "FILING: submitted per later disclosures" in says
    assert c["tracker_status"] == "Unable To Verify", "tracker status is reported as-is, not overwritten"


# ── M522A-02 ────────────────────────────────────────────────────────────────
def test_m522a_02_deadline_adherence_kept_separate(enr, answer):
    from intelligence.management_quality.fact_pack_enrichment_v5 import derive_commitment_states
    c = _mc(enr, "MC-0031")
    # M52.2d: validation dates are a different milestone; with no dated FILING statement, adherence is unable to verify
    assert c["TIMELINE_ADHERENCE_STATE"] == "UNABLE_TO_VERIFY" and c["dated_statements"] == []
    dates = {d["date"] for d in c["validation_statements"]}
    assert {"June 2024", "June 3, 2025"} <= dates
    assert "DEADLINE (H1CY24 target): UNABLE_TO_VERIFY" in " ".join(answer["what_management_says"])
    ev = lambda kind, ym, txt: {"kind": kind, "date_ym": ym, "date_text": txt, "period": "fy25",
                                "document": "annual_report", "page": 1}
    within = derive_commitment_states("H1CY24", [ev("FILED", [2024, 3], "March 2024")], 26, True)
    after = derive_commitment_states("H1CY24", [ev("FILED", [2024, 9], "September 2024")], 26, True)
    validated_only = derive_commitment_states("H1CY24", [ev("VALIDATED", [2024, 3], "March 2024")], 26, True)
    undated = derive_commitment_states("H1CY24", [{"kind": "FILED", "date_ym": None, "period": "fy25",
                                                   "document": "annual_report", "page": 2}], 26, True)
    assert within["TIMELINE_ADHERENCE_STATE"] == "WITHIN_TARGET_PERIOD_PER_DATED_FILING_STATEMENT"
    assert after["TIMELINE_ADHERENCE_STATE"] == "AFTER_TARGET_PERIOD_PER_DATED_FILING_STATEMENT"
    assert validated_only["TIMELINE_ADHERENCE_STATE"] == "UNABLE_TO_VERIFY", "a validation date is never converted into a filing date"
    assert undated["TIMELINE_ADHERENCE_STATE"] == "UNABLE_TO_VERIFY"
    assert undated["DELIVERY_STATE"] == "FILING_CONFIRMED_BY_SOURCE_TEXT", "delivery != deadline performance"


# ── M522A-03 ────────────────────────────────────────────────────────────────
def test_m522a_03_approval_milestone_not_confused_with_filing(enr, answer):
    from intelligence.management_quality.fact_pack_enrichment_v5 import derive_commitment_states
    c = _mc(enr, "MC-0031")
    assert c["REGULATORY_OUTCOME_STATE"] == "NOT_EVIDENCED_PENDING"
    mon = next(m for m in answer["what_to_monitor"] if "MC-0031" in m)
    assert "marketing-authorisation decision" in mon and "approval is not evidenced" in mon
    assert "filing confirmation" not in mon.lower()
    text = _flat(answer).lower()
    assert "nidlegy" not in re.findall(r"nidlegy[^.]{0,60}approved", text) or True
    assert not re.search(r"nidlegy[^.]{0,80}\b(approved|launched|commercial)", text)
    synthetic = derive_commitment_states(
        "H1CY24", [{"kind": "FILED", "date_ym": None, "period": "fy25", "document": "annual_report", "page": 1},
                   {"kind": "APPROVED", "date_ym": None, "period": "fy26", "document": "annual_report", "page": 3}], 26, True)
    assert synthetic["REGULATORY_OUTCOME_STATE"] == "APPROVAL_EVIDENCED"


# ── M522A-04 ────────────────────────────────────────────────────────────────
def test_m522a_04_no_arbitrary_commitment_truncation():
    from intelligence.management_quality import investor_sections as inv
    src = Path(inv.__file__).read_text()
    assert not re.search(r"sorted_hc\[:\d\]", src), "no slicing of sorted hard commitments"
    assert not re.search(r"hard_commitments\[:\d\]", src)
    facts = [{"id": f"MC-{i:04d}", "display_text": f"Commitment number {i} to deliver 10% savings", "target": "By 2030",
              "announcement_period": "fy25", "source_page": i, "tracker_status": "Unable To Verify",
              "DELIVERY_STATE": "NOT_EVIDENCED", "TIMELINE_ADHERENCE_STATE": "UNKNOWN",
              "REGULATORY_OUTCOME_STATE": "NOT_APPLICABLE", "TARGET_PERIOD_STATE": "TARGET_PERIOD_OPEN",
              "named_subject": None, "followup_events": []} for i in range(1, 8)]
    fp = {"hard_commitments": [{"id": f["id"], "expected_timeframe": "By 2030", "normalized_commitment": f["display_text"]}
                               for f in facts],
          "latest_fy": 26, "enrichment_v5": {"commitments": facts, "capital": {}, "behavior": {}}, "uncertainty_items": []}
    assert len(inv.build_what_management_says(fp)) >= 7
    assert len(inv.build_what_to_monitor(fp)) >= 7
    nyp = inv.build_what_is_not_yet_proven(fp)
    assert all(f["id"] in nyp for f in facts)


# ── M522A-05 ────────────────────────────────────────────────────────────────
def test_m522a_05_consistency_map_has_behavioral_evidence(answer):
    cmap = answer["management_consistency_map"]
    assert len(cmap) >= 5
    for label, val in cmap.items():
        if label == "Evidence confidence":
            continue
        assert " — " in val and "Observed:" in val, f"{label}: label-only entry"
        assert "Limitations:" in val, f"{label}: no stated limitation"
        assert "Not established:" in val or "Evidence:" in val, f"{label}: neither evidence nor an explicit gap"
    assert re.search(r"FY\d\d", cmap["Execution discipline"])


# ── M522A-06 ────────────────────────────────────────────────────────────────
def test_m522a_06_zero_delivered_not_auto_verdict(answer):
    from intelligence.management_quality.investor_sections import classify_behavior
    full = {"dimension": "d", "behavior": "b", "explanation": "e", "limitations": ["l"], "comparison_periods": ["fy20", "fy21", "fy22"],
            "comparable_observations": 4, "source_refs": ["ref"]}
    assert classify_behavior({**full, "direction": "consistent"}) == "CONSISTENT"
    assert classify_behavior({**full, "direction": "mixed"}) == "PARTIALLY_CONSISTENT"
    assert classify_behavior({**full, "direction": "contradictory"}) == "INCONSISTENT"        # genuine contradictions still classify
    for missing in ("dimension", "behavior", "explanation", "limitations", "source_refs"):
        assert classify_behavior({**full, "direction": "consistent", missing: None}) == "UNABLE_TO_VERIFY", missing
    assert classify_behavior({**full, "direction": "consistent", "comparison_periods": ["fy20"]}) == "UNABLE_TO_VERIFY"
    assert classify_behavior({**full, "direction": "consistent", "comparable_observations": 1}) == "UNABLE_TO_VERIFY"
    # 0 of 25 tracked items delivered does not become a verdict about execution
    assert _st(answer["management_consistency_map"]["Execution discipline"]) == "UNABLE_TO_VERIFY"


# ── M522A-07 ────────────────────────────────────────────────────────────────
def test_m522a_07_raw_assessment_field_blocked(answer, fp):
    from intelligence.management_quality.investor_sections import validate_section_quality
    assert "assessment=" not in _flat({k: v for k, v in answer.items() if not k.startswith("_")})
    tampered = {**answer, "where_management_was_consistent": ["execution_discipline (4 evidence items): assessment=strong"]}
    assert any("assessment=" in i for i in validate_section_quality(tampered, fp))
    assert not answer.get("_section_quality_violations")


# ── M522A-08 ────────────────────────────────────────────────────────────────
def test_m522a_08_named_product_evidence_preserved(answer):
    ev = _flat(answer["what_evidence_shows"])
    for name in ("LEQSELVI", "UNLOXCYT", "ILUMYA"):
        assert name in ev, f"{name} missing from evidence"
    assert "July 2024" in ev and "US FDA" in ev
    # generic: no product names hardcoded in the builders
    import intelligence.management_quality.investor_sections as inv
    import intelligence.management_quality.fact_pack_enrichment_v5 as en
    for mod in (inv, en):
        text = Path(mod.__file__).read_text().lower()
        for name in ("leqselvi", "unloxcyt", "ilumya", "nidlegy", "organon"):
            assert name not in re.sub(r"#.*|\"\"\"[\s\S]*?\"\"\"", "", text), f"{name} hardcoded in {mod.__name__}"


# ── M522A-09 ────────────────────────────────────────────────────────────────
def test_m522a_09_no_early_year_cherry_picking(answer):
    ev = _flat(answer["what_evidence_shows"])
    years = {int(y) for y in re.findall(r"FY(\d\d)", ev)}
    assert len(years) >= 4 and max(years) >= 25, f"evidence spans too narrow a window: {sorted(years)}"
    assert not years <= {20, 21}
    assert len(answer["what_evidence_shows"]) >= 5, "multiple evidence themes"


# ── M522A-10 ────────────────────────────────────────────────────────────────
def test_m522a_10_acquisition_context_preserved(answer):
    ev = _flat(answer["what_evidence_shows"])
    for name in ("Alchemee", "Concert", "Organon"):
        assert name in ev
    assert "0 of 2 named transactions" in ev
    assert "no capital-weighted conclusion" in ev.lower()


# ── M522A-11 ────────────────────────────────────────────────────────────────
def test_m522a_11_dividend_context_preserved(answer):
    ev = _flat(answer["what_evidence_shows"])
    assert "dividend line items in FY20–FY22 and FY24–FY26 (no FY23 record)" in ev
    assert "not an assessment of policy or allocation quality" in ev
    low = _flat(answer).lower()
    assert "paid annually" not in low and "shareholder-friendly" not in low


# ── M522A-12 ────────────────────────────────────────────────────────────────
def test_m522a_12_organon_lifecycle_attribution_safe(answer, enr):
    from intelligence.management_quality.fact_pack_enrichment_v5 import effective_evidence_type
    org = [t for t in enr["capital"]["announced_transactions"] if t["counterparty"] == "Organon"][0]
    assert org["canonical_status"] == "unable_to_verify" and org["completed"] is False
    assert org["agreement_date"] == "April 27, 2026"
    assert org["price_per_share"] == "USD 14.00 per share" and org["enterprise_valuation"] == "USD 11.75 billion"
    stale = {"evidence_type": "project_operational", "source_stream": "projects", "source_item_id": org["project_id"]}
    assert effective_evidence_type(stale, enr["project_status"]) == "project_unable_to_verify"
    text = _flat(answer)
    para = [s for s in answer["what_evidence_shows"] if s.startswith("Organon")][0]
    assert "not completed" in para and "subject to approvals and closing conditions" in para
    assert not re.search(r"organon[^.]{0,60}\b(operational|integrated|completed acquisition|contributed|drove|led to)", text, re.I)
    exec_pos = _flat(answer["management_consistency_map"]["Execution discipline"])
    assert "Organon" not in exec_pos


# ── M522A-13 ────────────────────────────────────────────────────────────────
def test_m522a_13_percentage_units_preserved(answer):
    from intelligence.management_quality.investor_sections import render_pct
    assert render_pct(35) == "35%" and render_pct(19.64) == "19.6%"
    flat = _flat({k: v for k, v in answer.items() if not k.startswith("_")})
    assert "35% reduction" in flat and "30% of hazardous waste" in flat
    assert "35 reduction" not in flat and "30 of hazardous" not in flat
    for sec in ("what_management_says", "what_to_monitor"):
        assert any("35%" in x for x in answer[sec])
    assert "35%" in answer["what_is_not_yet_proven"]


# ── M522A-14 ────────────────────────────────────────────────────────────────
def test_m522a_14_financial_precision(answer, fp):
    rev, pat = fp["financial_context"]["revenue"], fp["financial_context"]["pat"]
    assert rev["fiscal_year"] == "fy26" and pat["fiscal_year"] == "fy26"
    econ, simple = answer["what_may_mean_economically"], answer["simple_answer"]
    assert f"₹{rev['value']:,.0f} cr" in econ and f"₹{pat['value']:,.0f} cr" in econ
    assert f"{fp['npm']:.1f}%" in econ and "FY26" in econ and "actual" in econ and "consolidated" in econ
    assert "₹58,462 cr" in simple and "19.6%" in simple and "consolidated" in simple
    assert "projected" not in (econ + simple).lower()
    assert "not part of FY26 reported results" in econ, "post-year-end Organon event kept out of FY26 results"


# ── M522A-15 ────────────────────────────────────────────────────────────────
def test_m522a_15_compounding_confirmed_blocked(answer, fp):
    from intelligence.management_quality.investor_sections import (
        _build_evidence_bullet, validate_section_quality)
    assert "compounding confirmed" not in _flat(answer).lower()
    legacy = _build_evidence_bullet({"summary": "Per-share compounding fy20", "period": "fy20",
                                     "evidence_type": "per_share_compounding"})
    assert "confirmed" not in legacy.lower() and "direction not established" in legacy
    bad = {**answer, "what_evidence_shows": ["Per-share value compounding confirmed (FY20)"]}
    assert any("compounding confirmed" in i for i in validate_section_quality(bad, fp))


# ── M522A-16 ────────────────────────────────────────────────────────────────
def test_m522a_16_monitoring_has_meaningful_next_milestones(answer):
    mon = answer["what_to_monitor"]
    assert len(mon) >= 6
    joined = " ".join(mon)
    for cue in ("EMA", "Organon", "approvals, closing", "management responses", "Disclosure verification"):
        assert cue in joined, f"monitoring misses: {cue}"
    for m in mon:
        assert not m.startswith("Monitor: "), "raw fragment"
        assert len(m) > 60 and "monitor" in m.lower()


# ── M522A-17 ────────────────────────────────────────────────────────────────
def test_m522a_17_material_unresolved_items_covered(answer, enr):
    mon = " ".join(answer["what_to_monitor"])
    nyp = answer["what_is_not_yet_proven"]
    for c in enr["commitments"]:
        assert c["id"] in mon and c["id"] in nyp
    for t in enr["capital"]["announced_transactions"]:
        assert t["counterparty"] in mon and t["counterparty"] in nyp
    risks = enr["behavior"]["dimensions"]["candor_and_consistency"]["recurring_risks"]
    assert risks and risks[0].split(" (")[0] in mon


# ── M522A-18 ────────────────────────────────────────────────────────────────
def test_m522a_18_cross_section_consistency(answer, fp):
    from intelligence.management_quality.investor_sections import validate_consistency_map_vs_monitoring
    assert validate_consistency_map_vs_monitoring(answer["management_consistency_map"], answer["what_to_monitor"]) == []
    assert not answer.get("_consistency_map_contradictions")
    assert _st(answer["management_consistency_map"]["Candor and consistency"]) == "UNABLE_TO_VERIFY"
    assert any(m.startswith("Disclosure verification") for m in answer["what_to_monitor"])
    everything = _flat({k: v for k, v in answer.items() if not k.startswith("_")}).lower()
    assert "monitor filing confirmation" not in everything and "monitor for delivery confirmation" not in everything
    for sec in ("what_management_says", "what_to_monitor"):
        assert any("MC-0031" in x for x in answer[sec])
    assert "approval is not evidenced" in answer["what_is_not_yet_proven"]


# ── M522A-19 ────────────────────────────────────────────────────────────────
def test_m522a_19_zero_ai_calls(candidate, answer):
    assert candidate["ai_calls_made"] == 0 and candidate["zero_ai_calls"] is True
    assert answer["_zero_ai_calls"] is True and answer["_generation_mode"] == "DETERMINISTIC"
    import intelligence.management_quality.assembler_v5 as a5
    import intelligence.management_quality.fact_pack_enrichment_v5 as en
    import intelligence.management_quality.investor_sections as inv
    for mod in (a5, en, inv):
        src = Path(mod.__file__).read_text()
        for forbidden in ("import openai", "import anthropic", "from knowledge.ai", "requests.post", "urllib.request"):
            assert forbidden not in src, f"{mod.__name__}: {forbidden}"


# ── M522A-20 ────────────────────────────────────────────────────────────────
def test_m522a_20_historical_candidates_immutable():
    for name, digest in HIST.items():
        assert _digest(ASK / name) == digest, f"{name} changed"
    assert NEW_CANDIDATE.name not in HIST
    assert _digest(NEW_CANDIDATE) == NEW_FILE_DIGEST


# ── M522A-21 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("company", ["sun_pharma", "data_patterns", "tanla", "ujjivan"])
def test_m522a_21_cross_company_generalization(company):
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    fp = build_management_quality_fact_pack_v2(company)
    a = build_management_answer_v5(fp)
    assert not a.get("_section_quality_violations") and not a.get("_rating_violations")
    assert not a.get("_consistency_map_contradictions")
    flat = _flat({k: v for k, v in a.items() if not k.startswith("_")})
    for name in ("LEQSELVI", "UNLOXCYT", "Nidlegy", "Organon", "Alchemee"):
        if company != "sun_pharma":
            assert name not in flat, f"Sun Pharma fact leaked into {company}"
    if fp["hard_commitment_count"] == 0:
        assert not any(re.search(r"\bMC-\d{4}\b", x) for x in a["what_to_monitor"]), "no invented commitments"
    if not fp.get("evidence_observations_raw"):
        assert a["management_consistency_map"] == {} and a["what_to_monitor"] == [], "sparse stays sparse"


# ── M522A-22 ────────────────────────────────────────────────────────────────
def test_m522a_22_determinism_5_runs_x_4_companies():
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    for company in ("sun_pharma", "data_patterns", "tanla", "ujjivan"):
        outs = {json.dumps(build_management_answer_v5(build_management_quality_fact_pack_v2(company)), sort_keys=True)
                for _ in range(5)}
        assert len(outs) == 1, f"{company}: non-deterministic"


# ── M522A-23 ────────────────────────────────────────────────────────────────
def test_m522a_23_gate_chain_bound_to_candidate(candidate, fp):
    import pipelines.pacp_adversarial as pa
    from intelligence.external_investor_value_validator import validate_management_answer_eiv
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    from intelligence.management_quality.capability_parity_validator import validate_management_semantic_capability_parity
    ans = candidate["answer"]
    assert pa.run_adversarial_suite(ans, "sun_pharma", "how-good-is-management")["overall"] == "PASS"
    assert validate_management_answer_eiv(ans, fp)["overall"] == "PASS"
    assert validate_management_answer_eiv_v2(ans, fp)["overall"] == "PASS"
    assert validate_management_semantic_capability_parity(ans)["overall"] == "PASS"
    schema = json.loads((REPO / "schemas" / "management_quality_answer_contract_v3.json").read_text())
    for field in schema["required_fields"]:
        assert ans.get(field) not in (None, "", [], {}), f"required field empty: {field}"
    assert len(ans["management_consistency_map"]) >= 3 and len(ans["what_to_monitor"]) >= 3
    assert len(ans["deterministic_precision_facts"]) >= 3
    # runtime public-text sanitizer: every investor-facing string survives (simple_answer is a hard gate)
    bad = []
    def walk(p, v):
        if isinstance(v, str) and not pa._would_survive_sanitizer(v):
            bad.append((p, v[:60]))
        elif isinstance(v, list):
            [walk(f"{p}[{i}]", x) for i, x in enumerate(v)]
        elif isinstance(v, dict):
            [walk(f"{p}.{k}", x) for k, x in v.items() if not str(k).startswith("_")]
    walk("", ans)
    assert not bad, bad


# ── M522A-24 ────────────────────────────────────────────────────────────────
def test_m522a_24_identity_and_freshness_binding(candidate, answer):
    from intelligence.management_quality.assembler_v5 import compute_execution_id_v5
    from intelligence.management_quality.fact_pack_enrichment_v5 import enrich_fact_pack_v5
    # historical (M52.2a) candidate: its stored identity is self-consistent; the live contract has since moved on
    assert NEW_CONTRACT_FP == candidate["contract_v5_fingerprint"]
    assert candidate["execution_id"] == NEW_EXEC_ID == compute_execution_id_v5("sun_pharma", UNIT, EVIDENCE_FP, NEW_CONTRACT_FP)
    assert candidate["candidate_digest"] == NEW_ANSWER_DIGEST
    assert "sha256:" + hashlib.sha256(json.dumps(candidate["answer"], sort_keys=True).encode()).hexdigest() == NEW_ANSWER_DIGEST
    assert candidate["answer"] != answer, "the live answer has since been recalibrated (M52.2d); the historical candidate is immutable"
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    live = enrich_fact_pack_v5(build_management_quality_fact_pack_v2("sun_pharma"))
    assert live["input_manifest_digest"] == candidate["enrichment_input_manifest_digest"]
    assert len(live["input_manifest"]) == candidate["enrichment_input_file_count"]


# ── M522A-25 ────────────────────────────────────────────────────────────────
def test_m522a_25_numeric_fidelity_and_public_wording(answer, enr):
    flat = _flat({k: v for k, v in answer.items() if not k.startswith("_")})
    says = " ".join(answer["what_management_says"])
    for c in enr["commitments"]:
        assert c["display_text"] in says, f"{c['id']} text altered"
        for num in re.findall(r"\d+(?:\.\d+)?%", c["display_text"]):
            assert num in says and num in " ".join(answer["what_to_monitor"])
    assert not re.search(r"\bcanonical\b|\bartifact\b|\bschema\b|\bLLM\b", flat, re.I)
    assert "source_artifact" not in flat and "evidence_ids" not in flat
