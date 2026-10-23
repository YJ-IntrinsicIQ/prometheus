"""M59 batch: classification, candidate integrity and certification boundaries. No AI calls; reads existing intelligence only."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines import m59_question_batch as m  # noqa: E402
from pipelines.answer_certification import compute_content_fingerprint, compute_full_artifact_digest  # noqa: E402

REG = ROOT / "governance" / "approval_registry.json"
SERVED = ROOT / "companies"

from pipelines import answer_certification as _ac  # noqa: E402

_ac.configure_companies_root(SERVED, read_only=True)   # these tests only read the served answers


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    """The review state as persisted by the batch and the trust gates (M59.4: the generator is not re-run, since the activated answers now live in the served files)."""
    before = REG.read_bytes()
    pairs = json.loads((ROOT / "preview" / "M59_pairs.json").read_text())["pairs"]
    files = {c: json.loads((ROOT / "companies" / c / "company_memory/ask_intrinsiciq/m59_candidate_answers.json").read_text())["answers"] for c in m.COMPANIES}
    for p in pairs:
        if p["status"] == "READY":
            p["entry"] = files[p["company"]][p["question_id"]]
    assert REG.read_bytes() == before
    return pairs


def test_every_pair_is_classified_exactly_once(rows):
    assert len(rows) == 152 and len({(r["company"], r["question_id"]) for r in rows}) == 152
    assert {r["status"] for r in rows} <= {"APPROVED", "READY", "NEEDS_CORRECTION", "DEFERRED", "BLOCKED", "EXCLUDED_M592"}
    assert sum(r["status"] == "APPROVED" for r in rows) == 20


def test_the_twenty_original_approvals_are_preserved_and_the_registry_holds_exactly_91(rows):
    registry = json.loads(REG.read_text())["approvals"]
    backup = sorted((ROOT / "governance").glob("m594_backup_*"))[-1]
    original = json.loads((backup / "approval_registry.json").read_text())["approvals"]
    assert len(original) == 20 and len(registry) == 91 and set(original) <= set(registry)
    approved = {(r["company"], r["question_id"]) for r in rows if r["status"] == "APPROVED"}
    mapped = {(c, "what-can-break-the-thesis" if q == "what-could-go-wrong" else q) for c, q in (tuple(k.split(":")) for k in original)}
    assert approved == mapped                                     # catalog id what-can-break-the-thesis is served by the vetted alias what-could-go-wrong
    ready = {f"{r['company']}:{r['question_id']}" for r in rows if r["status"] == "READY"}
    assert ready == set(registry) - set(original) and len(ready) == 71    # every READY pair is now registered; nothing else is


def test_alias_semantics_only_the_risk_answer_stands_in(rows):
    assert m.VETTED_ALIASES == {"what-can-break-the-thesis": "what-could-go-wrong"}
    for r in rows:
        if r["question_id"] == "what-was-delivered-last-3-years":
            assert r["status"] != "APPROVED"     # the whole-record delivery answer does not answer a three-year question


def test_last_three_years_answers_cover_the_exact_window(rows):
    for r in rows:
        if r["question_id"] == "what-was-delivered-last-3-years" and r["status"] == "READY":
            a = r["entry"]["answer"]
            co = m.Co(r["company"], json.loads(REG.read_text())["approvals"])
            L = co.latest_year
            assert f"FY{L - 2}–FY{L}" in a["simple_answer"]
            approved = co.approved("what-did-management-actually-deliver")
            assert approved is None or a["simple_answer"] != approved["simple_answer"]


def test_ready_candidates_are_valid_and_digest_exact(rows):
    names = {c: n for c, n in m.NAMES.items()}
    registry = json.loads(REG.read_text())["approvals"]
    for r in (x for x in rows if x["status"] == "READY"):
        a = r["entry"]["answer"]
        co = m.Co(r["company"], registry)
        v = m.validate(a, co, r["question_id"], set())
        # numbers are validated with the handler's own calculation allowance in the batch; here the structural checks must pass
        assert not [k for k in v["failed"] if k != "numbers_trace_to_records"], (r["company"], r["question_id"], v["failed"])
        assert compute_full_artifact_digest(a) == r["full_artifact_digest"] and compute_content_fingerprint(a) == r["fingerprint"]
        for f in ("simple_answer", "what_evidence_shows", "what_may_mean_economically", "what_is_not_yet_proven", "what_to_monitor", "deterministic_precision_facts"):
            assert f in a
        text = m.ntext(a)
        assert not re.search(r"\b(MC|RG|PJ|CAO)-\d{2,}\b", text)
        others = [n for c, n in names.items() if c != r["company"] and n.split()[0] not in names[r["company"]]]
        assert not [n for n in others if n in text], (r["company"], r["question_id"])        # no cross-company leakage


def test_banks_are_never_judged_with_industrial_measures(rows):
    for r in rows:
        if r["company"] == "ujjivan" and r["status"] == "READY":
            t = m.ntext(r["entry"]["answer"])
            assert not re.search(r"owner[- ]earnings|cash conversion cycle|receivable days|inventory days", t, re.I), r["question_id"]
    for q in ("are-profits-converting-into-cash", "what-is-owner-earnings", "is-working-capital-a-concern", "are-per-share-economics-improving"):
        assert next(r for r in rows if r["company"] == "ujjivan" and r["question_id"] == q)["status"] == "DEFERRED"


def test_unapproved_model_written_syntheses_are_never_candidates(rows):
    for r in rows:
        if r["family"] in ("committee-view", "investor-panel"):
            assert r["status"] == "BLOCKED"


def test_hybrid_answers_lose_unsupported_relationships_speculation_and_cross_basis_comparisons(rows):
    for r in rows:
        if r["question_id"] in ("did-execution-lead-to-outcomes", "which-investments-created-value") and r["status"] == "READY":
            a = r["entry"]["answer"]
            assert all(x.get("causal_confidence") == "SUPPORTED" and x.get("acceptance") == "ACCEPT" for x in a["relationships"] if isinstance(x, dict))
            assert not m.SPECULATIVE.search(a["what_may_mean_economically"])
    uj = next(r for r in rows if r["company"] == "ujjivan" and r["question_id"] == "did-execution-lead-to-outcomes")
    assert "198" not in " ".join(uj["entry"]["answer"]["what_evidence_shows"])   # revenue ₹198 crore (unstated basis) → ₹6,354 crore (consolidated) is not comparable


def test_receivables_growth_is_stated_in_percentage_points_not_as_a_multiple(rows):
    sun = next(r for r in rows if r["company"] == "sun_pharma" and r["question_id"] == "is-working-capital-a-concern")
    t = " ".join(sun["entry"]["answer"]["what_evidence_shows"])
    assert "percentage points" in t and "7.7×" not in t and "as fast as" not in t


def test_candidate_files_match_the_review_package(rows):
    pkg = {(p["company"], p["question_id"]): p for p in json.loads((ROOT / "preview" / "M59_pairs.json").read_text())["pairs"]}
    for key in m.COMPANIES:
        doc = json.loads((ROOT / "companies" / key / "company_memory/ask_intrinsiciq/m59_candidate_answers.json").read_text())
        assert doc["ai_calls"] == 0 and doc["schema_version"] == m.SCHEMA
        for q, e in doc["answers"].items():
            assert compute_full_artifact_digest(e["answer"]) == e["candidate"]["full_artifact_digest"] == pkg[(key, q)]["full_artifact_digest"]
    gate = json.loads((ROOT / "preview" / "M59_3_FINAL_AUTHORIZATION_MANIFEST.json").read_text())
    excluded = {(e["company"], e["question_id"]) for e in gate["excluded"]}
    assert {(r["company"], r["question_id"]) for r in rows if r["status"] == "READY"} - excluded == {k for k, p in pkg.items() if p["status"] == "READY"}


def test_activation_refuses_without_owner_authorization():
    before = REG.read_bytes()
    p = subprocess.run([sys.executable, str(ROOT / "pipelines" / "m59_activate.py"), "--families", "financials", "--apply", "--companies-root", str(SERVED), "--authorize-served-write"], capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 2 and "REFUSED" in p.stdout
    dry = subprocess.run([sys.executable, str(ROOT / "pipelines" / "m59_activate.py"), "--families", "financials", "--companies-root", str(SERVED)], capture_output=True, text=True, cwd=ROOT)
    assert dry.returncode == 0 and "DRY RUN" in dry.stdout
    assert REG.read_bytes() == before


# ── M59.1 audit regressions ──
def _ready(rows):
    return [r for r in rows if r["status"] == "READY"]


def _blob(r):
    a = r["entry"]["answer"]
    return " ".join([a["simple_answer"], *a["what_evidence_shows"], a["what_may_mean_economically"], a["what_is_not_yet_proven"], *a["what_to_monitor"]])


def test_sun_capex_is_one_year_not_a_multiyear_total(rows):
    r = next(r for r in rows if r["company"] == "sun_pharma" and r["question_id"] == "what-is-the-return-on-capex")
    assert r["status"] == "READY"
    b = _blob(r)
    assert "FY26" in b and "3,609" in b
    assert not [x for x in re.split(r"(?<=[.;])\s+", b) if "3,609" in x and re.search(r"FY20\s?[–-]\s?FY26", x)]


def test_commitments_are_consistent_across_sun_answers(rows):
    ans = {r["question_id"]: _blob(r) for r in _ready(rows) if r["company"] == "sun_pharma"}
    for q in ("which-promises-are-overdue", "what-was-missed", "did-past-claims-come-true"):
        assert "Co-process" in ans[q] and "reported reached" in ans[q]
    assert not re.search(r"without (?:a )?confirmation[^.]*Co-process", ans["what-was-missed"])


def test_payouts_and_repayments_are_not_value_creation(rows):
    for r in (r for r in _ready(rows) if r["question_id"] == "which-investments-created-value"):
        b = _blob(r)
        assert "not evidence that the capital earned a return" in b
        assert not re.search(r"confirmed (?:deterministic )?outcome", b)


def test_execution_answers_distinguish_absent_records_from_absent_outcomes(rows):
    for r in (r for r in _ready(rows) if r["question_id"] == "did-execution-lead-to-outcomes"):
        assert "not proof that nothing else happened" in r["entry"]["answer"]["simple_answer"]


def test_management_clarification_never_asks_about_internal_trackers(rows):
    for r in _ready(rows):
        if r["question_id"] in ("what-needs-management-clarification", "what-should-i-ask-ir"):
            assert not re.search(r"tracker|progression records|register records", _blob(r), re.I)


def test_understand_answers_use_the_companys_own_business_model(rows):
    for r in _ready(rows):
        if r["question_id"] in ("what-does-company-do", "who-are-the-customers", "how-does-it-make-money"):
            b = _blob(r)
            assert not re.search(r"branded pricing|regulatory approval cycles|volume throughput|\b[a-z]+_[a-z_]+\b|billed on a", b)
    tanla = next(r for r in rows if r["company"] == "tanla" and r["question_id"] == "how-does-it-make-money")
    assert "usage" in _blob(tanla) and "inventory" not in _blob(tanla)


def test_no_candidate_text_is_cut_off(rows):
    for r in _ready(rows):
        assert r["validation"]["no_truncated_text"]["result"] == "PASS", (r["company"], r["question_id"])
        assert r["validation"]["period_consistency"]["result"] == "PASS"
        assert r["validation"]["return_of_capital_not_value"]["result"] == "PASS"


# ── M59.2 final trust gate ──
def test_final_manifest_is_exact_and_matches_the_candidate_artifacts():
    gate = json.loads((ROOT / "preview" / "M59_3_FINAL_AUTHORIZATION_MANIFEST.json").read_text())
    assert gate["activated"] is False and gate["ai_calls"] == 0
    assert gate["counts"]["approve_ready"] + gate["counts"]["corrected"] + gate["counts"]["excluded"] + gate["counts"]["blocked"] == gate["counts"]["reviewed"] == 81
    served = {}
    for e in gate["pairs"]:
        doc = served.setdefault(e["company"], json.loads((ROOT / e["candidate_file"]).read_text())["answers"])
        a = doc[e["question_id"]]["answer"]
        assert compute_full_artifact_digest(a) == e["full_artifact_digest"] and compute_content_fingerprint(a) == e["fingerprint"]
        assert e["verdict"] in ("APPROVE-READY", "CORRECTED") and e["source_verification"] and e["investor_quality"] and e["limitation"]
    listed = {(e["company"], e["question_id"]) for e in gate["pairs"]}
    in_files = {(c, q) for c, d in served.items() for q in d}
    for c in m.COMPANIES:
        in_files |= {(c, q) for q in json.loads((ROOT / "companies" / c / "company_memory/ask_intrinsiciq/m59_candidate_answers.json").read_text())["answers"]}
    assert in_files == listed                                   # nothing outside the manifest is a candidate
    assert not listed & {(e["company"], e["question_id"]) for e in gate["excluded"]}
    registry = json.loads(REG.read_text())["approvals"]
    for e in gate["pairs"]:                                     # M59.4: each is registered at exactly its manifest digest
        assert registry[f"{e['company']}:{e['question_id']}"]["full_artifact_digest"] == e["full_artifact_digest"]
    assert not {f"{x['company']}:{x['question_id']}" for x in gate["excluded"]} & set(registry)


def test_activation_is_idempotent_after_m59_4_and_refuses_already_registered_pairs():
    before = REG.read_bytes()
    dry = subprocess.run([sys.executable, str(ROOT / "pipelines" / "m59_activate.py"), "--families", "all", "--companies-root", str(SERVED)], capture_output=True, text=True, cwd=ROOT)
    assert dry.returncode == 0 and "DRY RUN" in dry.stdout
    assert "selected 71 READY pairs; 0 eligible; 71 refused/skipped" in dry.stdout and "already registered" in dry.stdout
    assert REG.read_bytes() == before


def test_no_candidate_claims_a_missing_disclosure_the_filings_contain():
    gate = json.loads((ROOT / "preview" / "M59_3_FINAL_AUTHORIZATION_MANIFEST.json").read_text())
    assert {e["question_id"] for e in gate["excluded"]} >= {"which-disclosure-is-missing", "what-should-i-ask-ir", "what-incentives-matter"}
    for e in gate["pairs"]:
        t = json.dumps(json.loads((ROOT / e["candidate_file"]).read_text())["answers"][e["question_id"]]["answer"], ensure_ascii=False)
        assert not re.search(r"provided text|remuneration[^.]{0,80}not available|are not in the records|Return on capital employed is not available", t), (e["company"], e["question_id"])


# ── M59.3 commitment integrity ──
FINAL = ROOT / "preview" / "M59_3_FINAL_AUTHORIZATION_MANIFEST.json"


def _cand(e):
    return json.loads((ROOT / e["candidate_file"]).read_text())["answers"][e["question_id"]]["answer"]


def test_hard_commitment_means_target_and_deadline_for_every_company():
    gate = json.loads(FINAL.read_text())
    for e in gate["pairs"]:
        if e["company"] == "sun_pharma":
            continue
        t = json.dumps(_cand(e), ensure_ascii=False)
        assert not re.search(r"\b\d+ hard commitments", t), (e["company"], e["question_id"])   # the register's looser 'verifiable' tier is never called hard
    byq = {(e["company"], e["question_id"]): _cand(e) for e in gate["pairs"]}
    assert "Only 1 carries both" in byq[("tanla", "what-promise-types-dominate")]["simple_answer"]
    assert "Only 1 carries both" in byq[("ujjivan", "what-promise-types-dominate")]["simple_answer"]
    assert "None carries both" in byq[("datapatterns", "what-promise-types-dominate")]["simple_answer"]
    for c in ("tanla", "ujjivan", "datapatterns"):
        for q in ("which-promises-are-overdue", "what-was-missed", "did-past-claims-come-true"):
            s = byq[(c, q)]["simple_answer"]
            assert not re.search(r"\bhard commitments? of", s), (c, q)
    assert "80.6%" in byq[("tanla", "which-promises-are-overdue")]["simple_answer"]   # FY26 engagement score, a related measure, read from the filing
    assert "unconfirmed rather than missed" in byq[("tanla", "what-was-missed")]["simple_answer"]


def test_sun_candidates_are_untouched_by_the_commitment_correction():
    now = {(e["company"], e["question_id"]): e["full_artifact_digest"] for e in json.loads(FINAL.read_text())["pairs"]}
    before = {(e["company"], e["question_id"]): e["full_artifact_digest"] for e in json.loads((ROOT / "preview" / "M59_2_FINAL_AUTHORIZATION_MANIFEST.json").read_text())["pairs"]}
    assert {k: v for k, v in now.items() if k[0] == "sun_pharma"} == {k: v for k, v in before.items() if k[0] == "sun_pharma"}
    assert {k: v for k, v in before.items() if k not in now} == {}          # nothing silently dropped


def test_replacements_are_registered_and_served_and_the_other_fourteen_are_untouched():
    gate = json.loads(FINAL.read_text())
    registry = json.loads(REG.read_text())["approvals"]
    backup = sorted((ROOT / "governance").glob("m594_backup_*"))[-1]
    original = json.loads((backup / "approval_registry.json").read_text())["approvals"]
    reps = {f"{r['company']}:{r['question_id']}": r for r in gate["approved_answers_needing_separate_correction"]}
    assert len(reps) == 6
    for k, r in reps.items():
        c, q = k.split(":")
        assert original[k]["full_artifact_digest"] == r["approved_digest"] != r["replacement_digest"] == registry[k]["full_artifact_digest"]
        served = json.loads((ROOT / "companies" / c / "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json").read_text())["answers"][q]["answer"]
        assert compute_full_artifact_digest(served) == r["replacement_digest"] and compute_content_fingerprint(served) == r["replacement_fingerprint"]
        assert "verifiable commitment" in served["simple_answer"] and not re.search(r"\d+ hard commitments", served["simple_answer"])
    for k, rec in original.items():
        if k not in reps:
            assert registry[k] == rec                           # byte-for-byte the same approval record
