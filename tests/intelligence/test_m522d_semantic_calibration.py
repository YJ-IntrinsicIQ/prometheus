"""
ENG-MISSION52.2d — semantic calibration & investor-judgment repair. AI calls used: 0.

Invariant under test:  ABSENCE_OF_VERIFIED_OUTCOME != EVIDENCE_OF_NEGATIVE_BEHAVIOR.
Each S1..S10 test asserts the defect exists in the rejected M52.2c candidate (immutable) and is
absent in the corrected one, so it fails against the old behaviour and passes against the new.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# M59.4 moved the live registry (91 pairs) and served answers on from the M54.13 activation these tests pin. The M54.13 state is preserved,
# byte for byte, in the M59.4 pre-activation backup; these historical release-integrity assertions are evaluated against that preserved state.
_M594 = sorted((Path(__file__).resolve().parents[2] / "governance").glob("m594_backup_*"))[-1]
_M594_REG = _M594 / "approval_registry.json"
_M594_SUN = _M594 / "sun_pharma__shadow_level3_hybrid_answers.json"

ASK = REPO / "companies" / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
UNIT = "how_good_is_management_synthesis"

OLD = ASK / "regeneration_candidate_how_good_is_management_6c381d74ba14_v5.json"
OLD_FILE = "sha256:6af009356186a314bf29bb82ebbdf24a0c9b651d568c4d6fce828acb1a7b9bd0"
NEW = ASK / "regeneration_candidate_how_good_is_management_166d0a4f52b8_v5.json"
NEW_FILE = "sha256:968fd15e7f6a72806cf76fc112fa7ffa160b5678e5bd7036cccd5d9d425c0aed"
NEW_ANSWER = "sha256:84a207ec22b3b3c132c182e78319f09d9c2a558d927665c787d6465a5cedb861"
NEW_EXEC = "sha256:166d0a4f52b81b483e157313305522ef59376e0c347c05cf5430a61c88ead616"
NEW_CONTRACT_FP = "sha256:046004b4d4edb04fab7eaca641b24a73279f2851b483824c3af0349a0deb41f9"
EVIDENCE_FP = "sha256:9be9bd11b1be74a157aa2ceae2bc5f144833e7f11856d6f7a0d8f8b303f23e42"
DEP_DIGEST = "sha256:6efac80fe433e5b9363be14d7bfc96efa02b389e43a75451ade9c8b99cedb6f3"
APPROVAL_DIGEST = "sha256:6ee8c1efef89c05b44408fd3340c0bafbd7bca54621480e1cc156c142672958d"
M37_8 = "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"
HIST_REG = REPO / "governance" / "approval_registry.pre_m5413.json"   # preserved pre-M54.13 snapshots
HIST_ANS = ASK / "shadow_level3_hybrid_answers.pre_m5413.json"
ACTIVATED_REG = "sha256:58fc5eea5126cbdf5f7932341713feaf8519b420adf5a373a050a340d705b60f"                                  # M54.13 activation
ACTIVATED_ANS = "sha256:9b6d8bad07c39aa8532272ef24b5fb8195cb96eeb988b3bd847f15d569d31998"

HIST = {
    "regeneration_candidate_how_good_is_management_559650df434c_v5.json": "sha256:50bec2d5b076d92605c1d20aa8a1c3d2d81ac3a4730052bdf662217977e596bc",
    "regeneration_candidate_how_good_is_management_76315ffdb926_v5.json": "sha256:b175c7b2f7b761d0f90f33f1c3a82a3b56194b9416312a343c5ccf633964563a",
    "regeneration_candidate_how_good_is_management_2f7e73f8dab8_v5.json": "sha256:288a03e334029a3881514f393a62e93a91eaed48ea1e285c56bf6d48228d2739",
    "regeneration_candidate_how_good_is_management_0700190f323a_v5.json": "sha256:760216cfa877e35e85b4f4552da3045db45193fc557c2e59d6592cb46708cdb8",
    "regeneration_candidate_how_good_is_management_6c381d74ba14_v5.json": OLD_FILE,
    "regeneration_candidate_how_good_is_management_b8883c421f74_v5.json": "sha256:e7c51f0c8b84ca9edbb1eda70491ad60eaeef5f7600c2b16b0452c21de09c543",   # interim build, superseded before review
    "regeneration_candidate_how_good_is_management_165add2d253e_v5.json": "sha256:11e1bce79875d62a6ebb38212239e5a9dd04dd5839ff81acb199c1b7005ab8bb",   # interim build, superseded before review
    "regeneration_candidate_how_good_is_management_4779f07b3629_v5.json": "sha256:fd7dbfb22ac686e905d5fd9af7497d61d99e1c87a6e46673cccf61c63c2c625c",   # interim build, superseded before review
    "shadow_level3_hybrid_answers.json": M37_8,
}


def _sha(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def _st(v: str) -> str:
    return str(v).split(" — ")[0].strip()


def _flat(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return " ".join(_flat(x) for x in v)
    if isinstance(v, dict):
        return " ".join(_flat(x) for x in v.values())
    return str(v)


def _public(a: dict) -> dict:
    return {k: v for k, v in a.items() if not k.startswith("_") and k not in ("claims", "deterministic_precision_facts")}


@pytest.fixture(scope="module")
def old():
    return json.loads(OLD.read_text())["answer"]


@pytest.fixture(scope="module")
def cand():
    return json.loads(NEW.read_text())


@pytest.fixture(scope="module")
def new(cand):
    return cand["answer"]


@pytest.fixture(scope="module")
def fp():
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    return build_management_quality_fact_pack_v2("sun_pharma")


@pytest.fixture(scope="module")
def enr(fp):
    from intelligence.management_quality.fact_pack_enrichment_v5 import enrich_fact_pack_v5
    return enrich_fact_pack_v5(fp)


# ── S1-S10 ──────────────────────────────────────────────────────────────────
def test_m522d_s1_candor_not_inconsistent_without_proof(old, new, enr):
    assert _st(old["management_consistency_map"]["Candor and consistency"]) == "INCONSISTENT"      # the defect
    v = new["management_consistency_map"]["Candor and consistency"]
    assert _st(v) == "UNABLE_TO_VERIFY"
    assert "disclosure-verification gap" in v and "not evidence of concealment" in v
    assert enr["contradictions"]["genuine_contradictions"] == 0 and enr["contradictions"]["types"] == {"repeated_unresolved": 10}
    assert "not a contradiction" in v


def test_m522d_s2_risk_handling_needs_exposure_response_outcome(old, new):
    assert _st(old["management_consistency_map"]["Risk handling"]) == "INCONSISTENT"
    v = new["management_consistency_map"]["Risk handling"]
    assert _st(v) == "UNABLE_TO_VERIFY"
    assert "management's response to each exposure and its observed outcome" in v
    assert "a persistent risk can coexist with effective mitigation" in v
    assert "Supply-chain disruption" in v, "recurring-risk observations are preserved separately"


def test_m522d_s3_adaptability_not_computed_from_incomparable_counts(old, new):
    assert re.search(r"\d+ reported operational items against \d+ negative", old["management_consistency_map"]["Adaptability"])
    v = new["management_consistency_map"]["Adaptability"]
    assert _st(v) == "UNABLE_TO_VERIFY" and not re.search(r"against \d+ negative", v)
    assert "challenge -> management response -> follow-up -> outcome" in v and "not combined into a score" in v
    assert "captive hybrid power plant" in v, "documented plan changes are kept as observations"


def test_m522d_s4_execution_not_inferred_from_operational_labels(old, new):
    assert _st(old["management_consistency_map"]["Execution discipline"]) == "PARTIALLY_CONSISTENT"
    v = new["management_consistency_map"]["Execution discipline"]
    assert _st(v) == "UNABLE_TO_VERIFY"
    assert "original scope, timeline or budget" in v and "no failure is inferred from missing confirmation" in v
    ev = " ".join(new["what_evidence_shows"])
    assert "not evidence of delivery reliability or of failure" in ev


def test_m522d_s5_distributions_observation_policy_effectiveness_separated(old, new):
    assert "Shareholder distributions" in old["management_consistency_map"] and _st(old["management_consistency_map"]["Shareholder distributions"]) == "PARTIALLY_CONSISTENT"
    cm = new["management_consistency_map"]
    assert "Shareholder distributions" not in cm
    pol, eff = cm["Distribution policy consistency"], cm["Capital allocation effectiveness"]
    assert _st(pol) == _st(eff) == "UNABLE_TO_VERIFY"
    assert "dividend line items in FY20–FY22 and FY24–FY26 (no FY23 record)" in pol, "observations preserved"
    assert "extraction gap" in pol and "buybacks need not occur annually" in pol
    assert "missing attribution is not poor allocation" in eff
    assert "an extraction gap rather than no payment" in " ".join(new["what_evidence_shows"])


def test_m522d_s6_evidence_confidence_scoped(old, new):
    assert "longitudinal evidence across available source streams" in " ".join(old["key_points"]) and "does not verify" not in " ".join(old["key_points"])
    ec = new["management_consistency_map"]["Evidence confidence"]
    assert ec.startswith("HIGH") and "Source-evidence coverage only" in ec and "not a confidence rating of any management-quality judgment" in ec
    assert any(k.startswith("Source-evidence coverage: HIGH") and "does not verify outcomes or rate management quality" in k for k in new["key_points"])
    dpf = next(d for d in new["deterministic_precision_facts"] if d["metric"] == "Evidence confidence")
    assert "does not verify outcomes or rate management quality" in dpf["semantic_meaning"]


def test_m522d_s7_tracker_scope_not_misrepresented(old, new, enr):
    assert "0 of 25 tracked progression items confirmed delivered" not in new["simple_answer"]
    assert "management-progression tracker records 0 of its 25 tracked items" in new["simple_answer"]
    assert "separate records document product approvals, launches and operational activity" in new["simple_answer"]
    tr = enr["tracker"]
    assert tr["tracked_items"] == 25 and tr["confirmed_delivered_in_tracker"] == 0 and tr["tracker_status_changed"] is False
    assert tr["population"] == {"strategic commitment statement": 16, "commentary theme": 7, "legacy project": 2}
    assert "not a ledger of company deliveries" in tr["scope_note"]
    assert "management delivered nothing" not in _flat(new).lower()    # TRACKER_SCOPE_NOT_MISREPRESENTED
    dpf = next(d for d in new["deterministic_precision_facts"] if d["metric"] == "Delivery follow-through")
    assert "management-progression tracker" in dpf["semantic_meaning"] and "not a finding about all company activity" in dpf["semantic_meaning"]


def test_m522d_s8_nidlegy_filing_deadline_approval_independent(old, new, enr):
    c = next(x for x in enr["commitments"] if x["id"] == "MC-0031")
    assert (c["FILING_DELIVERY"], c["DEADLINE_ADHERENCE"], c["REGULATORY_APPROVAL"]) == (
        "FILING_CONFIRMED_BY_SOURCE_TEXT", "UNABLE_TO_VERIFY", "NOT_EVIDENCED_PENDING")
    assert {v["date"] for v in c["validation_statements"]} == {"June 2024", "June 3, 2025"} and c["dated_statements"] == []
    says = next(x for x in new["what_management_says"] if "MC-0031" in x)
    for token in ("FILING: submitted", "DEADLINE (H1CY24 target): UNABLE_TO_VERIFY", "APPROVAL: not evidenced", "a separate milestone",
                  "original PDF pages not available for confirmation"):
        assert token in says, token
    mon = next(x for x in new["what_to_monitor"] if "marketing-authorisation" in x)
    assert "target: H1CY24" not in mon and "separate, forward-looking milestone" in mon and "concerned the filing" in mon
    old_mon = next(x for x in old["what_to_monitor"] if "marketing-authorisation" in x)
    assert "H1CY24" in old_mon and "[MC-0031, target: H1CY24]" in old_mon, "old wording attached the filing target to the approval milestone"


def test_m522d_s9_temporal_and_financial_scope(new, enr, fp):
    says = " ".join(new["what_management_says"])
    assert "calendar or financial year not specified in the source" in says
    assert "target period has passed under either year convention" in says
    fs = enr["financial_scope"]
    assert fs["revenue"]["basis"] == fs["pat"]["basis"] == "consolidated" and fs["revenue"]["period"] == "March 31, 2026"
    assert fs["revenue"]["status"] == "ACTUAL" and fs["npm"]["status"] == "DERIVED"
    assert fs["revenue"]["value"] == fp["financial_context"]["revenue"]["value"] and fs["pat"]["value"] == fp["financial_context"]["pat"]["value"]
    econ = new["what_may_mean_economically"]
    for token in ("consolidated", "year ended March 31, 2026", "actual (not guidance)", "profit attributable to owners of the parent", "NPM is derived", "p.243"):
        assert token in econ, token
    assert "NPM 19.6% (derived)" in new["simple_answer"]


def test_m522d_s10_material_claims_traceable(new):
    claims = new["claims"]
    assert len(claims) >= 15
    types = {c["claim_type"] for c in claims}
    assert {"BEHAVIOR_CLASSIFICATION", "REGULATORY_MILESTONE", "FINANCIAL", "TRANSACTION_STATUS", "ABSENCE", "COMMITMENT", "PROGRESS", "SCOPE_STATEMENT"} <= types
    assert len({c["claim_id"] for c in claims}) == len(claims)
    for c in claims:
        assert set(c) >= {"claim_id", "claim_type", "claim_text", "evidence_refs", "verification_status", "limitations"}
        if c["claim_type"] != "ABSENCE" and c["verification_status"] != "NO_EVIDENCE_FOUND_IN_SEARCHED_SOURCES":
            assert c["evidence_refs"], c["claim_id"]
        for r in c["evidence_refs"]:
            assert r["source"] and "location" in r and "period" in r
    fin = [c for c in claims if c["claim_type"] == "FINANCIAL"]
    assert any("p.243" in r["location"] for c in fin for r in c["evidence_refs"])


# ── Calibration rules ───────────────────────────────────────────────────────
def test_m522d_01_absence_of_evidence_rule_in_builders(fp, enr):
    from intelligence.management_quality.investor_sections import build_management_consistency_map
    # synthetic: huge numbers of recurring risks, delays and no contradictions must never produce an adverse verdict
    big = json.loads(json.dumps(enr))
    big["behavior"]["dimensions"]["risk_handling"]["counts"].update(negative=99)
    big["behavior"]["dimensions"]["candor_and_consistency"]["counts"].update(negative=99)
    cm = build_management_consistency_map({**fp, "enrichment_v5": big})
    for label in ("Risk handling", "Candor and consistency", "Execution discipline", "Adaptability"):
        assert _st(cm[label]) == "UNABLE_TO_VERIFY", label


def test_m522d_02_genuine_contradictions_still_classify(fp, enr):
    from intelligence.management_quality.investor_sections import build_management_consistency_map
    synth = json.loads(json.dumps(enr))
    synth["contradictions"]["genuine"] = [
        {"signal_id": f"CONTRA-X{i}", "type": "statement_contradicted_by_fact", "earlier_period": f"fy2{i}", "later_period": f"fy2{i + 1}", "source_item_id": "MP-X"}
        for i in range(3)]
    synth["contradictions"]["genuine_contradictions"] = 3
    v = build_management_consistency_map({**fp, "enrichment_v5": synth})["Candor and consistency"]
    assert _st(v) == "INCONSISTENT" and "Evidence: 3 contradictions" in v and "CONTRA-X0" in v
    one = json.loads(json.dumps(enr))
    one["contradictions"]["genuine"] = synth["contradictions"]["genuine"][:1]
    assert _st(build_management_consistency_map({**fp, "enrichment_v5": one})["Candor and consistency"]) == "UNABLE_TO_VERIFY", "one signal is not a pattern"


def test_m522d_03_supported_classifications_preserved(new):
    v = new["management_consistency_map"]["Strategic clarity (stated)"]
    assert _st(v) == "CONSISTENT" and "Evidence: 23 statements across FY20–FY26" in v and "statements with statements" in v
    assert new["where_management_was_consistent"] and new["where_management_was_consistent"][0].startswith("Strategic clarity (stated)")
    # not everything defaults to UNKNOWN: supported observations remain
    ev = " ".join(new["what_evidence_shows"])
    for token in ("LEQSELVI: US FDA approval reported July 2024", "UNLOXCYT", "ILUMYA", "Alchemee", "Concert", "Organon", "dividend line items"):
        assert token in ev, token


def test_m522d_04_classification_proof_contract():
    from intelligence.management_quality.investor_sections import classify_behavior
    full = {"dimension": "d", "behavior": "b", "explanation": "e", "limitations": ["l"], "comparison_periods": ["fy20", "fy21", "fy22"],
            "comparable_observations": 3, "source_refs": ["r"], "direction": "consistent"}
    assert classify_behavior(full) == "CONSISTENT"
    for k in ("dimension", "behavior", "explanation", "limitations", "source_refs"):
        assert classify_behavior({**full, k: None}) == "UNABLE_TO_VERIFY", k
    assert classify_behavior({**full, "comparison_periods": ["fy20", "fy21"]}) == "UNABLE_TO_VERIFY"
    assert classify_behavior({**full, "comparable_observations": 2}) == "UNABLE_TO_VERIFY"
    assert classify_behavior({**full, "direction": "unknown"}) == "UNABLE_TO_VERIFY"
    import intelligence.management_quality.investor_sections as inv
    assert not hasattr(inv, "classify_dimension"), "count-arithmetic classifier removed"


def test_m522d_05_every_nonunknown_classification_carries_evidence(new):
    for label, v in new["management_consistency_map"].items():
        if label == "Evidence confidence":
            continue
        assert "Observed:" in v and "Limitations:" in v
        if _st(v) != "UNABLE_TO_VERIFY":
            assert "Evidence:" in v
        else:
            assert "Not established:" in v


def test_m522d_06_negative_claims_are_bounded(new, enr):
    cov = enr["search_coverage"]["text"]
    assert "7 annual reports (FY20–FY26)" in cov and "FY25 Q3" in cov and "FY25 Q4" in cov
    flat = _flat(_public(new))
    for phrase in ("do not document", "no result is disclosed", "not disclosed in the record", "none is disclosed"):
        assert phrase not in flat.lower(), phrase
    assert flat.count("sources searched") >= 6
    ab = [c for c in new["claims"] if c["claim_type"] == "ABSENCE"]
    assert ab and all(c["verification_status"] == "NO_EVIDENCE_FOUND_IN_SEARCHED_SOURCES" and any("searched" in l for l in c["limitations"]) for c in ab)
    assert any("does not establish that the event did not occur" in l for c in ab for l in c["limitations"]) or \
           any("not evidence that no action was taken" in l for c in ab for l in c["limitations"])


def test_m522d_07_semantic_guards_reject_each_old_defect(new, fp):
    from intelligence.management_quality.investor_sections import validate_section_quality
    def with_(**changes):
        return {**new, **changes}
    cases = {
        "BLOCKED_PHRASE: poor risk management": with_(what_evidence_shows=new["what_evidence_shows"] + ["This reflects poor risk management"]),
        "UNBOUNDED_ABSENCE_CLAIM": with_(what_is_not_yet_proven=new["what_is_not_yet_proven"] + " No result is disclosed."),
        "ARITHMETIC_CLASSIFICATION_FROM_INCOMPARABLE_COUNTS": with_(what_evidence_shows=["12 reported operational items against 9 negative items"]),
        "FILING_DEADLINE_ATTACHED_TO_APPROVAL_MILESTONE": with_(what_to_monitor=new["what_to_monitor"] + ["Nidlegy EMA marketing-authorisation decision [MC-0031, target: H1CY24]"]),
        "TRACKER_SCOPE_NOT_STATED": with_(simple_answer=new["simple_answer"] + " Overall 0 of 25 items confirmed delivered."),
        "EVIDENCE_CONFIDENCE_NOT_SCOPED": with_(management_consistency_map={**new["management_consistency_map"], "Evidence confidence": "HIGH — multiple source streams"}),
        "CLASSIFICATION_WITHOUT_EVIDENCE": with_(management_consistency_map={**new["management_consistency_map"],
            "Risk handling": "INCONSISTENT — Observed: recurring risks. Limitations: none."}),
        "BLOCKED_PHRASE: failed to deliver": with_(simple_answer=new["simple_answer"] + " Management failed to deliver."),
    }
    for expected, bad in cases.items():
        issues = validate_section_quality(bad, {**fp, "enrichment_v5": {}} if False else fp)
        assert any(expected in i for i in issues), (expected, issues)
    assert validate_section_quality(new, fp) == []


def test_m522d_08_mc0029_mc0039_progress_reported_not_absent(old, new, enr):
    assert "no result is disclosed in the record" in " ".join(old["what_management_says"])         # old false negative
    c29 = next(c for c in enr["commitments"] if c["id"] == "MC-0029")["progress"]
    c39 = next(c for c in enr["commitments"] if c["id"] == "MC-0039")["progress"]
    assert c29["basis"] == "DERIVED_FROM_DISPOSAL_TABLE" and c29["management_achievement_statement"] == "NOT_FOUND_IN_SEARCHED_SOURCES"
    by = {r["period"]: r for r in c29["series"]}
    assert by["fy25"]["co_processed_tonnes"] == 4325 and by["fy25"]["total_tonnes"] == 9250 and by["fy25"]["value"] == 46.8
    assert by["fy26"]["value"] == 59.9 and c29["progress_state"] == "REPORTED_AT_OR_ABOVE_TARGET_LEVEL"
    vals = {r["period"]: r["value"] for r in c39["series"]}
    assert vals == {"fy24": 21.85, "fy25": 24.69, "fy26": 16.7} and c39["latest_below_prior_report"] is True
    says = " ".join(new["what_management_says"])
    assert "21.85% (FY24); 24.69% (FY25); 16.7% (FY26)" in says and "not a management-stated percentage" in says
    assert "restatement or boundary change is not established" in says


def test_m522d_09_organon_lifecycle_staged(new, enr):
    org = next(x for x in new["what_evidence_shows"] if x.startswith("Organon"))
    for token in ("SIGNED", "CLOSING: not completed in the sources searched", "Integration planning", "OPERATIONAL INTEGRATION, FINANCIAL CONSOLIDATION",
                  "none can be attributed before closing is verified", "evidence cutoff: FY26 annual report"):
        assert token in org, token
    assert "no integration or operating contribution can exist" not in _flat(new).lower()
    t = enr["capital"]["announced_transactions"][0]
    assert t["integration_planning_statement"]["page"] == 15 and t["agreement_date"] == "April 27, 2026"
    assert "not part of FY26 reported results" in new["what_may_mean_economically"]


def test_m522d_10_tracker_reconciliation_item_level(enr):
    tr = enr["tracker"]
    assert len(tr["items"]) == 25 and sum(tr["verdict_counts"].values()) == 25
    allowed = {"MATCHED_DELIVERY_EVIDENCE", "MATCHED_PARTIAL_PROGRESS", "NO_MATCH_FOUND", "AMBIGUOUS_MATCH"}
    for i in tr["items"]:
        assert i["verdict"] in allowed and i["item_id"] and i["lifecycle_status"] and i["initiative"] and "reason" in i
        assert (i["verdict"] in ("MATCHED_DELIVERY_EVIDENCE", "MATCHED_PARTIAL_PROGRESS")) == i["same_item"]
    partial = [i for i in tr["items"] if i["verdict"] == "MATCHED_PARTIAL_PROGRESS"]
    assert [i["item_id"] for i in partial] == ["MP-0111-market_positioning_challenges"]
    assert all(i["lifecycle_status"] in ("announced", "in_progress") for i in tr["items"]), "tracker statuses untouched"


def test_m522d_11_claims_field_investigated(old):
    assert old["claims"] == []                       # the rejected candidate shipped an empty claims array
    m37 = json.loads((ASK / "shadow_level3_hybrid_answers.json").read_text())["answers"]["how-good-is-management"]["answer"]
    assert m37["claims"] == [], "the empty field is a convention of earlier certified answers, but validators read claims[].evidence_refs"
    import inspect
    from intelligence import external_investor_value_validator as eiv
    assert "evidence_refs" in inspect.getsource(eiv)


# ── Hygiene, replay, determinism ────────────────────────────────────────────
def test_m522d_12_no_company_or_product_hardcoding():
    import intelligence.management_quality.fact_pack_enrichment_v5 as en
    import intelligence.management_quality.investor_sections as inv
    for mod in (inv, en):
        text = re.sub(r"#.*|\"\"\"[\s\S]*?\"\"\"", "", Path(mod.__file__).read_text()).lower()
        for name in ("leqselvi", "unloxcyt", "ilumya", "nidlegy", "organon", "sun_pharma", "sun pharma", "alchemee"):
            assert name not in text, (mod.__name__, name)


@pytest.mark.parametrize("company", ["sun_pharma", "data_patterns", "tanla", "ujjivan"])
def test_m522d_13_four_company_replay(company):
    import pipelines.pacp_adversarial as pa
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    f = build_management_quality_fact_pack_v2(company)
    a = build_management_answer_v5(f)
    assert not a.get("_section_quality_violations") and not a.get("_rating_violations")
    assert pa.run_adversarial_suite(a, company, "how-good-is-management")["overall"] == "PASS"
    flat = _flat(_public(a))
    if company != "sun_pharma":
        for leak in ("Nidlegy", "Organon", "LEQSELVI", "Alchemee", "MC-0031"):
            assert leak not in flat, leak
    if company == "data_patterns":
        assert a["management_consistency_map"] == {} and a["what_to_monitor"] == [] and a["claims"] == []
    for label, v in a["management_consistency_map"].items():
        if label not in ("Evidence confidence", "Strategic clarity (stated)"):
            assert _st(v) == "UNABLE_TO_VERIFY", (company, label)


def test_m522d_14_determinism_5_x_4():
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    for co in ("sun_pharma", "data_patterns", "tanla", "ujjivan"):
        outs = {json.dumps(build_management_answer_v5(build_management_quality_fact_pack_v2(co)), sort_keys=True) for _ in range(5)}
        assert len(outs) == 1, co


# ── Gates and identity (bound to the exact new candidate) ───────────────────
def test_m522d_15_gate_chain_on_exact_candidate(cand, fp):
    import pipelines.pacp_adversarial as pa
    from intelligence.external_investor_value_validator import validate_management_answer_eiv
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    from intelligence.management_quality.capability_parity_validator import validate_management_semantic_capability_parity
    from intelligence.management_quality.investor_sections import validate_section_quality
    a = cand["answer"]
    assert pa.run_adversarial_suite(a, "sun_pharma", "how-good-is-management")["overall"] == "PASS"
    assert validate_management_answer_eiv(a, fp)["overall"] == "PASS"
    assert validate_management_answer_eiv_v2(a, fp)["overall"] == "PASS"
    assert validate_management_semantic_capability_parity(a)["overall"] == "PASS"
    assert validate_section_quality(a, fp) == []
    schema = json.loads((REPO / "schemas" / "management_quality_answer_contract_v3.json").read_text())
    assert [f for f in schema["required_fields"] if a.get(f) in (None, "", [], {})] == []
    bad = []
    def walk(p, v):
        if isinstance(v, str) and not pa._would_survive_sanitizer(v):
            bad.append(p)
        elif isinstance(v, list):
            [walk(f"{p}[{i}]", x) for i, x in enumerate(v)]
        elif isinstance(v, dict):
            [walk(f"{p}.{k}", x) for k, x in v.items() if not str(k).startswith("_")]
    walk("", a)
    assert bad == []


def test_m522d_16_identity_and_official_freshness(cand):
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5, compute_execution_id_v5
    from intelligence.management_quality.contract_manifest import CONTRACT_V5_POLICY_DIGEST
    from intelligence.management_quality.fact_pack_enrichment_v5 import enrich_fact_pack_v5
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.regeneration_executor import verify_candidate_freshness
    from intelligence.regeneration_planner import _load_dependency_registry
    assert _sha(NEW) == NEW_FILE and cand["candidate_digest"] == NEW_ANSWER
    assert "sha256:" + hashlib.sha256(json.dumps(cand["answer"], sort_keys=True).encode()).hexdigest() == NEW_ANSWER
    assert CONTRACT_V5_POLICY_DIGEST == cand["contract_v5_fingerprint"] == NEW_CONTRACT_FP
    assert compute_execution_id_v5("sun_pharma", UNIT, EVIDENCE_FP, NEW_CONTRACT_FP) == cand["execution_id"] == NEW_EXEC
    assert cand["evidence_fingerprint"] == EVIDENCE_FP and cand["dependency_contract_digest"] == DEP_DIGEST
    f = build_management_quality_fact_pack_v2("sun_pharma")
    assert build_management_answer_v5(f) == cand["answer"], "stored candidate equals a fresh canonical regeneration"
    assert enrich_fact_pack_v5(f)["input_manifest_digest"] == cand["enrichment_input_manifest_digest"]
    fr = verify_candidate_freshness(cand, REPO / "companies", _load_dependency_registry())
    assert fr["freshness"] == "CURRENT" and fr["current_evidence_fingerprint"] == EVIDENCE_FP
    assert verify_candidate_freshness(json.loads(OLD.read_text()), REPO / "companies", _load_dependency_registry())["freshness"] == "CURRENT"   # same evidence, same dependency contract
    assert (cand["ai_calls_made"], cand["zero_ai_calls"]) == (0, True) and cand["schema_version"] == "m522d_candidate_v1"
    assert NEW_CONTRACT_FP != json.loads(OLD.read_text())["contract_v5_fingerprint"] and cand["answer"] != json.loads(OLD.read_text())["answer"]
    assert cand["semantic_changes_vs_superseded"], "candidate records which fields changed vs the rejected candidate"


def test_m522d_17_dependency_registry_and_evidence_unchanged():
    reg = REPO / "governance" / "answer_dependency_registry.json"
    assert _sha(reg) == "sha256:9f4201e30a2123aebf66a057b4beb67dfbcd7f42e6c09d6151ea6198e28c2000"
    from intelligence.regeneration_executor import _compute_evidence_fingerprint
    from intelligence.regeneration_planner import _load_dependency_registry
    assert _compute_evidence_fingerprint("sun_pharma", REPO / "companies", _load_dependency_registry()) == EVIDENCE_FP


def test_m522d_18_historical_artifacts_immutable():
    for name, digest in HIST.items():
        path = HIST_ANS if name == "shadow_level3_hybrid_answers.json" else ASK / name
        assert path.exists(), name
        if digest:
            assert _sha(path) == digest, name
    assert NEW.name not in HIST


def test_m522d_19_release_state_unchanged_and_unapproved(cand):
    assert _sha(HIST_REG) == APPROVAL_DIGEST          # historical baseline
    assert _sha(_M594_REG) == ACTIVATED_REG
    approvals = json.loads(_M594_REG.read_text())["approvals"]
    assert len(approvals) == 20 and cand["execution_id"] not in json.dumps(approvals) and NEW_FILE.split(":")[1] not in json.dumps(approvals)
    assert _sha(HIST_ANS) == M37_8
    assert _sha(_M594_SUN) == ACTIVATED_ANS
    launch = json.loads((REPO / ".claude" / "launch.json").read_text())
    matrix = next(c for c in launch["configurations"] if c["name"] == "ask-intrinsiciq-canary")["env"]["PROMETHEUS_LEVEL3_UI_CANARY_MATRIX"].split(",")
    assert sorted(matrix) == sorted(approvals) and len(matrix) == 20
    build = (REPO / "scratchpad" / "m522d_build_candidate.py").read_text().lower()
    assert "answer_certification" not in build and "mode_approve" not in build and "activate" not in build
    # Serving code never references candidates; the isolated Story/Cockpit adapters (src/lib/story) are covered by the TypeScript suite.
    for p in (REPO / "apps" / "ask-intrinsiciq" / "src").rglob("*.ts*"):
        if "lib/story" in p.as_posix():
            continue
        assert "regeneration_candidate" not in p.read_text(), p


def test_m522d_20_zero_ai_calls_no_provider_imported():
    code = ("import sys;from intelligence.management_quality.assembler_v5 import build_management_answer_v5 as a;"
            "from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2 as b;"
            "from intelligence.regeneration_planner import plan_regeneration;"
            "a(b('sun_pharma'));plan_regeneration('sun_pharma');"
            "print(sorted(m for m in sys.modules if m.split('.')[0] in ('openai','anthropic') or m.startswith('knowledge.ai')))")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env={**os.environ, "PYTHONPATH": str(REPO)}, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-300:]
    assert out.stdout.strip().splitlines()[-1] == "[]"
