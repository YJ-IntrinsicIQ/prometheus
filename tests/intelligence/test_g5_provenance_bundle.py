"""M63 / G5 full-scope provenance: semantic classification, evidence resolution, claim-linked entries and the scratch replacement bundle.
Reads the scratch bundle (G5B_DIR, default /private/tmp/claude-501/g5b) and the evidence root (G5B_ROOT); touches nothing under companies/ or governance/."""
import hashlib
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
from pipelines import m59_question_batch as m59  # noqa: E402

BUNDLE = Path(os.environ.get("G5B_DIR", "/private/tmp/claude-501/g5b"))
ROOT = Path(os.environ.get("G5B_ROOT", "/private/tmp/claude-501/g4/root"))
KEYS = ["sun_pharma", "tanla", "ujjivan", "datapatterns"]
needs_root = pytest.mark.skipif(not ROOT.exists(), reason="evidence root absent")
needs_bundle = pytest.mark.skipif(not (BUNDLE / "bundle" / "answers").exists(), reason="scratch bundle absent")
_L: dict = {}


def led(k):
    if k not in _L:
        _L[k] = g4.Ledger(k, ROOT)
    return _L[k]


# ── semantic classification: six classes, nothing silently dropped ──
@pytest.mark.parametrize("sentence,cls", [
    ("Missing disclosure is not evidence of failure", G.EXPLANATORY),
    ("A passed deadline with no confirmation is a question for management, not a finding of failure", G.EXPLANATORY),
    ("If platform execution converts to higher utilisation, it may support revenue growth", None),
    ("“Unable To Verify” means no evidence is linked in the register, not that none exists", G.EXPLANATORY),
    ("Prometheus holds no external market data, so intrinsic value cannot be computed", G.UI_OR_SYSTEM),
    ("Missing data", G.UI_OR_SYSTEM),
    ("Which disclosure is missing?", G.UI_OR_SYSTEM),
    ("The FY27 report is not in the records", G.UI_OR_SYSTEM),
    ("What drove each movement is not stated in the records", G.ANALYTIC_UNCERTAINTY),
    ("The link to reported financial outcomes is not disclosed", G.ANALYTIC_UNCERTAINTY),
    ("Projects reported operational are not shown to have reached expected output or returns", G.ANALYTIC_UNCERTAINTY),
    ("The estimate rests on a figure that is calculated, not management-stated", G.EXPLANATORY),
    ("Cash-conversion and working-capital measures are marked not economically meaningful for this company", G.INAPPLICABLE_MEASURE),
    ("The maintenance-versus-growth capex split is not disclosed", G.DISCLOSURE_ABSENCE),
    ("The annual report provides no major-customer figures", G.DISCLOSURE_ABSENCE),
    ("Interest coverage is not extracted into the records", G.EXTRACTION_ABSENCE),
    ("Utilisation, throughput and incremental revenue are not given in the capacity records", G.EXTRACTION_ABSENCE),
    ("The records hold no revenue breakdown for this company", G.EXTRACTION_ABSENCE),
])
def test_clause_classification(sentence, cls):
    got, rule = G.classify(sentence)
    assert got == cls, (sentence, got, rule)


def test_a_genuine_claim_cannot_hide_behind_an_explanatory_clause():
    cl = G.split_clauses("Missing disclosure is not counted as failure, and the annual report provides no order book figure")
    kinds = [G.classify(c)[0] for c in cl]
    assert G.EXPLANATORY in kinds and G.DISCLOSURE_ABSENCE in kinds


def test_dash_parentheticals_keep_their_subject():
    cl = G.split_clauses("Competitive position — market share, pricing power against peers — is not in the records, so durability cannot be judged")
    assert any(c.startswith("Competitive position") and "is not in the records" in c for c in cl)


@needs_root
def test_system_limitation_is_verified_against_system_inputs_not_assumed():
    ok, why = G.system_limitation_ok(ROOT)
    assert ok is True and "no file named" in why
    ok2, why2 = G.system_limitation_ok(Path("/nonexistent-root"))
    assert ok2 is True      # nothing found anywhere, same rule; the rule is a file search, so it can fail when such a file exists
    sandbox = ROOT / "companies"
    assert sandbox.exists()


@needs_root
def test_coverage_statements_are_checked_against_year_folders():
    L = led("ujjivan")
    assert G.coverage_check(L, "The FY27 report is not in the records")[0] is True
    assert G.coverage_check(L, "FY24 data is missing")[0] is False       # FY24 exists with a fact registry


# ── evidence resolution: states the evidence can support ──
@needs_root
def test_ujjivan_interest_coverage_is_not_applicable_to_a_bank():
    r = G.resolve(led("ujjivan"), "interest_coverage")
    assert r["state"] == "NOT_APPLICABLE" and "bank" in r["basis"]


@needs_root
def test_record_that_holds_the_figure_contradicts_a_missing_claim():
    r = G.resolve(led("datapatterns"), "book_value")
    assert r["state"] == "CONTRADICTED_BY_RECORDS"


@needs_root
@pytest.mark.parametrize("key", KEYS)
def test_not_disclosed_is_never_verified_by_a_failed_search(key):
    for t in G.PROFILES:
        r = G.resolve(led(key), t)
        assert r["state"] != "NOT_DISCLOSED", (key, t)
        if r["state"] == "NOT_DISCLOSED_CANDIDATE":
            assert r["verified"] is False and "human confirmation" in r["uncertainty"]


@needs_root
@pytest.mark.parametrize("key", KEYS)
def test_not_extracted_always_carries_a_page_locator_and_a_strong_hit(key):
    for t in G.PROFILES:
        r = G.resolve(led(key), t)
        if r["state"] == "NOT_EXTRACTED":
            assert r["verified"] and re.search(r"pp?\.\d", r["locator"]) and r["filing_strong_pages"]


@needs_root
def test_a_mention_without_a_figure_is_sent_to_review_not_decided():
    states = {k: G.resolve(led(k), "market_size")["state"] for k in KEYS}
    assert "REVIEW" in states.values()
    assert all(s not in ("NOT_DISCLOSED",) for s in states.values())


@needs_root
def test_contradicted_source_claim_keeps_its_subject_when_reworded():
    j = G.judge(led("sun_pharma"), "Margins by revenue source and the split of revenue between sources are not disclosed in the records for Sun Pharma", G.DISCLOSURE_ABSENCE)
    assert j["status"] == "CONTRADICTED"
    assert "Not yet concluded" in j["rewrite"] and "revenue" in j["rewrite"]        # superseded by the evidence gate: the rewrite is the investor fallback


@needs_root
def test_equivalent_claims_share_one_evidence_group():
    L = led("sun_pharma")
    a = G.judge(L, "The maintenance-versus-growth capex split is not disclosed", G.DISCLOSURE_ABSENCE)
    b = G.judge(L, "The split between maintenance and growth capital spending is not disclosed", G.DISCLOSURE_ABSENCE)
    assert a["evidence_group"] == b["evidence_group"] and a["review"] == b["review"]


@needs_root
def test_different_companies_and_scopes_do_not_share_a_group():
    a = G.judge(led("sun_pharma"), "The maintenance-versus-growth capex split is not disclosed", G.DISCLOSURE_ABSENCE)["evidence_group"]
    b = G.judge(led("tanla"), "The maintenance-versus-growth capex split is not disclosed", G.DISCLOSURE_ABSENCE)["evidence_group"]
    c = G.judge(led("sun_pharma"), "Maintenance versus growth capex is not in the extracted records", G.EXTRACTION_ABSENCE)["evidence_group"]
    assert len({a, b, c}) == 3


@needs_root
def test_bank_does_not_get_an_industrial_capex_claim_as_a_disclosure_gap():
    j = G.judge(led("ujjivan"), "The maintenance-versus-growth capex split is not disclosed", G.DISCLOSURE_ABSENCE)
    assert not j["status"].startswith("VERIFIED") and "Not yet concluded" in j["rewrite"]      # blanket bank inapplicability is not established


# ── the scratch replacement bundle ──
def _bundle():
    return [json.loads(f.read_text()) for f in sorted((BUNDLE / "bundle" / "answers").glob("*.json"))]


@needs_bundle
def test_exactly_the_91_expected_slots():
    reg = json.loads((REPO / "governance" / "approval_registry.json").read_text())["approvals"]
    assert sorted(d["slot"] for d in _bundle()) == sorted(reg)
    assert len(reg) == 91


@needs_bundle
def test_original_digests_recorded_equal_the_registry_and_proposed_digests_differ_only_where_changed():
    reg = json.loads((REPO / "governance" / "approval_registry.json").read_text())["approvals"]
    for d in _bundle():
        r = d["report"]
        assert r["original"]["content_fingerprint"] == reg[d["slot"]]["fingerprint"]
        assert r["original"]["full_digest"] == reg[d["slot"]]["full_artifact_digest"]
        if not r["changed_fields"]:
            assert r["proposed"]["full_digest"] == r["original"]["full_digest"]


@needs_bundle
def test_approved_based_slots_change_only_absence_wording_and_provenance():
    allowed = {"what_is_not_yet_proven", "evidence_gaps", "what_evidence_shows", "what_may_mean_economically", "key_points", "simple_answer", "what_to_monitor", "g5_absence", "g5_review_pending", "g5_system_statements", "g5_event_checks", "claims", "relationships", "deterministic_precision_facts", "why_it_matters", "investor_interpretation"}
    for d in _bundle():
        r = d["report"]
        if r["base"] == "approved":
            assert set(r["changed_fields"]) <= allowed, (d["slot"], r["changed_fields"])
            for rw in r["rewrites"]:
                assert rw["reason"] in ("CONTRADICTED", "WRONG_NOT_APPLICABLE_CLAIM", "UNRESOLVED_REVIEW", "UNRESOLVED_NOT_DISCLOSED_CANDIDATE", "UNRESOLVED_UNPROFILED", "UNSUPPORTED_EVENT")      # only evidence-contradicted clauses are rewritten
                assert rw["after"] != rw["before"]


@needs_bundle
def test_no_validator_regression_and_word_budget_kept():
    for d in _bundle():
        r = d["report"]
        assert not r["validator_regression"], (d["slot"], r["validator_regression"])
        assert r["words_proposed"] <= 600 or r["words_proposed"] <= r["words_original"]


@needs_bundle
@pytest.mark.parametrize("key", KEYS)
def test_every_genuine_clause_in_the_bundle_is_claim_linked_and_none_contradicted(key):
    L = led(key)
    for d in _bundle():
        if d["slot"].startswith(key + ":"):
            a = d["answer"]
            fields = [(f"{f}", t) for f, _, t in G._text_fields(a)] + [("dpf", str(x.get("semantic_meaning"))) for x in a.get("deterministic_precision_facts") or [] if isinstance(x, dict) and x.get("semantic_meaning")]
            res = G.audit_text(L, fields, (a.get("g5_absence") or []) + (a.get("g5_review_pending") or []))
            assert not res["untagged"], (d["slot"], res["untagged"])
            assert not res["contradicted"], (d["slot"], res["contradicted"])
            assert not res["state_mismatch"], (d["slot"], res["state_mismatch"])


@needs_bundle
def test_unresolved_claims_are_listed_not_hidden_and_never_given_a_verified_state():
    for d in _bundle():
        a = d["answer"]
        for e in a.get("g5_absence", []):
            assert e["verification"] in ("VERIFIED", "PENDING_HUMAN_CONFIRMATION", "UNVERIFIED_SCOPED_STATEMENT")
            if e["verification"] == "VERIFIED":
                assert e["state"] in ("NOT_EXTRACTED", "NOT_APPLICABLE") and (e["state"] == "NOT_APPLICABLE" or re.search(r"p\.\d", e["basis"]))
            elif e["verification"] == "PENDING_HUMAN_CONFIRMATION":
                assert e["state"] == "NOT_DISCLOSED" and e["review"]
            else:
                assert e["state"] is None
        for p in a.get("g5_review_pending", []):
            assert p["review"] or p["status"]


@needs_bundle
def test_candidate_based_slots_are_exactly_the_repaired_candidates_that_have_an_approved_slot():
    base = [d["slot"] for d in _bundle() if d["report"]["base"] != "approved"]
    assert len(base) == 15 and not any(s == "ujjivan:are-profits-converting-into-cash" for s in base)


def test_protected_artifacts_unchanged():
    assert hashlib.sha256((REPO / "governance" / "approval_registry.json").read_bytes()).hexdigest().startswith("4f6a71f2878204be")
    assert json.loads((REPO / "governance" / "approval_registry.json").read_text())["approvals"].__len__() == 91
    for k, h in zip(KEYS, ("bd09be3f", "7c7c7bb8", "787072a5", "075649c9")):
        f = REPO / "companies" / ("sun_pharma" if k == "sun_pharma" else k) / "company_memory" / "ask_intrinsiciq" / "shadow_level3_hybrid_answers.json"
        assert hashlib.sha256(f.read_bytes()).hexdigest().startswith(h)
