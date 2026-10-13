"""
ENG-MISSION52.2c — dependency-contract promotion, evidence completeness, official freshness.
30 checks (M522C-01 .. M522C-30). AI calls used: 0. Production source files are never mutated:
every mutation runs on an isolated temp copy.
"""
from __future__ import annotations

import builtins
import contextlib
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# M59.4 moved the live registry (91 pairs) and served answers on from the M54.13 activation these tests pin. The M54.13 state is preserved,
# byte for byte, in the M59.4 pre-activation backup; these historical release-integrity assertions are evaluated against that preserved state.
_M594 = sorted((Path(__file__).resolve().parents[2] / "governance").glob("m594_backup_*"))[-1]
_M594_REG = _M594 / "approval_registry.json"
_M594_SUN = _M594 / "sun_pharma__shadow_level3_hybrid_answers.json"

GOV = REPO / "governance"
ASK = REPO / "companies" / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
UNIT = "how_good_is_management_synthesis"

REG_V4 = GOV / "answer_dependency_registry.json"
REG_V3 = GOV / "answer_dependency_registry.v3_pre_m52.json"
REG_V3_DIGEST = "sha256:240b8aaa7549f405608fe629df4cf333a547a8ec39e143cd90c0589955cd2570"
APPROVAL = _M594_REG
LIVE_APPROVAL = GOV / "approval_registry.json"   # the real, current registry (for the test that proves the harness cannot mutate it)
APPROVAL_DIGEST = "sha256:6ee8c1efef89c05b44408fd3340c0bafbd7bca54621480e1cc156c142672958d"
HIST_APPROVAL = GOV / "approval_registry.pre_m5413.json"      # preserved pre-M54.13 snapshots
HIST_ANS = REPO / "companies" / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / "shadow_level3_hybrid_answers.pre_m5413.json"
ACTIVATED_APPROVAL = "sha256:58fc5eea5126cbdf5f7932341713feaf8519b420adf5a373a050a340d705b60f"                 # M54.13 activation
ACTIVATED_ANS = "sha256:9b6d8bad07c39aa8532272ef24b5fb8195cb96eeb988b3bd847f15d569d31998"
OLD_OFFICIAL_FP = "sha256:6793736f4298b82142d39d0439f299d7c11f0310ada29ff0a9cc99fac06c2aad"
INHERITED_FP = "sha256:dc623eac6e2350742314f7f4ad44c817e8fe9bb2b4a717e6a864e1da206605a2"

NEW = ASK / "regeneration_candidate_how_good_is_management_6c381d74ba14_v5.json"
NEW_FILE = "sha256:6af009356186a314bf29bb82ebbdf24a0c9b651d568c4d6fce828acb1a7b9bd0"
NEW_EXEC = "sha256:6c381d74ba14f3ffc999ee503e8094cb0c2d989adb221899ce082b7def1356ea"
NEW_CONTRACT_FP = "sha256:47e3f5ba77979a23bb2c27486c846e2f0584fd1f039401d1b70401f6e5c1bd6f"
NEW_EVIDENCE_FP = "sha256:9be9bd11b1be74a157aa2ceae2bc5f144833e7f11856d6f7a0d8f8b303f23e42"
NEW_DEP_DIGEST = "sha256:6efac80fe433e5b9363be14d7bfc96efa02b389e43a75451ade9c8b99cedb6f3"
ANSWER_DIGEST = "sha256:4d2df2ae968d5a9d53d6bfa0618c8e9df11b7c3ad042f19172e1ef266e2ad7e7"
PREV_CANDIDATE = ASK / "regeneration_candidate_how_good_is_management_2f7e73f8dab8_v5.json"

HIST_CANDIDATES = {
    "regeneration_candidate_how_good_is_management_0700190f323a_v5.json": "sha256:760216cfa877e35e85b4f4552da3045db45193fc557c2e59d6592cb46708cdb8",
    "regeneration_candidate_how_good_is_management_559650df434c_v5.json": "sha256:50bec2d5b076d92605c1d20aa8a1c3d2d81ac3a4730052bdf662217977e596bc",
    "regeneration_candidate_how_good_is_management_76315ffdb926_v5.json": "sha256:b175c7b2f7b761d0f90f33f1c3a82a3b56194b9416312a343c5ccf633964563a",
    "regeneration_candidate_how_good_is_management_39631f315761_v5.json": "sha256:b42918bbd90975fa6821d85dc22496497c4895d666296bd9e6aeb0974dbe443d",
    "regeneration_candidate_how_good_is_management_8cf1232fb7eb_v5.json": "sha256:2820876ab5a9b9490c4020e1ec5799cbcd60ff34644f51590b9191694727e6db",
    "regeneration_candidate_how_good_is_management_2f7e73f8dab8_v5.json": "sha256:288a03e334029a3881514f393a62e93a91eaed48ea1e285c56bf6d48228d2739",
    "shadow_level3_hybrid_answers.json": "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43",
}


def _sha(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def reg():
    return json.loads(REG_V4.read_text())


@pytest.fixture(scope="module")
def hist():
    return json.loads(REG_V3.read_text())


@pytest.fixture(scope="module")
def cand():
    return json.loads(NEW.read_text())


# ── isolated copy of sun_pharma's fingerprinted inputs ──────────────────────
@pytest.fixture(scope="module")
def iso():
    from intelligence.evidence_fingerprints import MODULE_SOURCE_MAP
    src = REPO / "companies" / "sun_pharma"
    root = Path(tempfile.mkdtemp(prefix="m522c_"))
    dst = root / "sun_pharma"
    rels = {v for v in MODULE_SOURCE_MAP.values()}
    for fy in json.loads((src / "company_memory/financial_year_index.json").read_text())["years_used"] + ["fy27"]:
        for p in list((src / fy / "extracted").glob("clean_chunks.json")) + list((src / fy / "quarters").glob("Q*/quarterly_chunks.json")):
            rels.add(str(p.relative_to(src)))
    rels.add("company_memory/cim_v1.json")
    for rel in rels:
        if (src / rel).exists():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, dst / rel)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _official(root: Path, registry) -> str:
    from intelligence.regeneration_executor import _compute_evidence_fingerprint
    return _compute_evidence_fingerprint("sun_pharma", root, registry)


@contextlib.contextmanager
def mutated(root: Path, rel: str, how: str = "probe"):
    path = root / "sun_pharma" / rel
    original, st = path.read_bytes(), path.stat()
    data = json.loads(original)
    if how == "probe":
        data["_m522c_probe"] = "mutated"
    elif how == "timestamp_field_only":
        data["generated_at"] = "2099-01-01T00:00:00Z"
    path.write_bytes(json.dumps(data).encode())
    os.utime(path, (st.st_atime, st.st_mtime))   # content changes, timestamp does not
    try:
        yield
    finally:
        path.write_bytes(original)
        os.utime(path, (st.st_atime, st.st_mtime))


def _trace_reads(company="sun_pharma"):
    reads = set()
    real_open, rt, rb = builtins.open, pathlib.Path.read_text, pathlib.Path.read_bytes
    marker = f"companies/{company}/"

    def note(p):
        s = str(p)
        if marker in s and "ask_intrinsiciq" not in s:
            reads.add(s.split(marker, 1)[1])

    def op(f, *a, **k):
        if not isinstance(f, int) and (not a or "r" in str(a[0])):
            note(f)
        return real_open(f, *a, **k)
    builtins.open = op
    pathlib.Path.read_text = lambda self, *a, **k: (note(self), rt(self, *a, **k))[1]
    pathlib.Path.read_bytes = lambda self, *a, **k: (note(self), rb(self, *a, **k))[1]
    try:
        from intelligence.management_quality.assembler_v5 import build_management_answer_v5
        from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
        build_management_answer_v5(build_management_quality_fact_pack_v2(company))
    finally:
        builtins.open, pathlib.Path.read_text, pathlib.Path.read_bytes = real_open, rt, rb
    return reads


def _covered(reg, company="sun_pharma"):
    """Company-relative paths official freshness covers for the V5 unit."""
    from intelligence.evidence_fingerprints import MODULE_SOURCE_MAP, SOURCE_MANIFEST_MODULES
    mods = reg["m52_contract_v5_override"]["contract"]["upstream_modules"]
    covered = {MODULE_SOURCE_MAP[m] for m in mods if m in MODULE_SOURCE_MAP}
    root = REPO / "companies" / company
    spec = SOURCE_MANIFEST_MODULES["source_text_chunks"]
    try:
        years = json.loads((root / spec["years_from"]).read_text())[spec["years_key"]]
    except Exception:
        years = []
    for fy in years:
        covered.add(spec["annual"].format(fy=fy))
        for pat in spec["globs"]:
            covered.update(str(p.relative_to(root)) for p in root.glob(pat.format(fy=fy)))
    return covered


# ── Part II ─────────────────────────────────────────────────────────────────
def test_m522c_01_historical_registry_preserved(reg, hist):
    from intelligence.regeneration_executor import _compute_evidence_fingerprint
    assert _sha(REG_V3) == REG_V3_DIGEST
    assert {k: v for k, v in reg.items() if k not in ("m52_contract_v5_override", "dependency_contract_version")} == \
           {k: v for k, v in hist.items() if k != "dependency_contract_version"}
    assert hist["dependency_contract_version"] == "3" and reg["dependency_contract_version"] == "4"
    # the historical contract still reproduces the historical official fingerprint
    assert _compute_evidence_fingerprint("sun_pharma", REPO / "companies", hist) == OLD_OFFICIAL_FP


def test_m522c_02_versioned_v5_override_valid(reg):
    from intelligence.evidence_fingerprints import MODULE_SOURCE_MAP, SOURCE_MANIFEST_MODULES
    from intelligence.shadow_change_detector import effective_contract_digest, get_effective_contract
    c = get_effective_contract(UNIT, reg)
    assert get_effective_contract("how-good-is-management", reg) == c
    assert (c["generation_mode"], c["ai_call_count"], c["ai_regeneration_required"]) == ("DETERMINISTIC", 0, False)
    assert reg["m52_contract_v5_override"]["governance"]["status"] == "PROMOTED"
    assert effective_contract_digest(c) == NEW_DEP_DIGEST != ""
    for m in c["upstream_modules"]:
        assert m in MODULE_SOURCE_MAP or m in SOURCE_MANIFEST_MODULES, m
    assert set(c["optional_modules"]) <= set(c["upstream_modules"]) and len(c["upstream_modules"]) == 14
    hist = reg["m52_contract_v5_override"]["governance"]["historical_record_retained"]
    assert hist["class"] == "B_LLM_REQUIRED" and hist["ai_call_count"] == 1
    assert reg["questions"]["how-good-is-management"]["class"] == "B_LLM_REQUIRED"
    assert reg["generation_units"][UNIT]["ai_call_count"] == 1, "historical meaning retained alongside the override"
    assert len(reg["questions"]) == 37 and len(reg["generation_units"]) == 7


def test_m522c_03_unrelated_classifications_unchanged(reg, hist):
    for q in hist["questions"]:
        assert reg["questions"][q] == hist["questions"][q], q
    for u in hist["generation_units"]:
        assert reg["generation_units"][u] == hist["generation_units"][u], u
    assert reg["m43_promotion"] == hist["m43_promotion"] and reg["m44_promotion"] == hist["m44_promotion"]
    from intelligence.shadow_change_detector import _resolve_upstream_modules
    for u in hist["generation_units"]:
        if u != UNIT:
            assert _resolve_upstream_modules(u, reg) == _resolve_upstream_modules(u, hist), u
    assert _resolve_upstream_modules(UNIT, reg) != _resolve_upstream_modules(UNIT, hist)


# ── Part III ────────────────────────────────────────────────────────────────
def test_m522c_04_all_21_known_inputs_tracked(reg):
    reads = _trace_reads()
    assert len(reads) == 21
    assert sorted(reads - _covered(reg)) == []


def test_m522c_05_transitive_dependency_completeness(reg):
    pytest.importorskip("intelligence.management_quality.fact_pack_enrichment_v5")
    for company in ("sun_pharma", "data_patterns", "datapatterns", "tanla", "ujjivan", "ltts"):
        if not (REPO / "companies" / company).is_dir():
            continue
        reads = _trace_reads(company)
        assert sorted(reads - _covered(reg, company)) == [], company


# ── Part IV: adversarial false-clean tests (isolated copy) ───────────────────
def _all_inputs(reg):
    return sorted(_covered(reg))


def _assert_dirty(iso, reg, rel, base, how="probe"):
    with mutated(iso, rel, how):
        assert _official(iso, reg) != base, f"FALSE-CLEAN: {rel}"


def test_m522c_06_project_changes_dirty(iso, reg):
    base = _official(iso, reg)
    _assert_dirty(iso, reg, "company_memory/projects/projects_registry.json", base)


def test_m522c_07_capital_allocation_changes_dirty(iso, reg):
    base = _official(iso, reg)
    for rel in ("company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json",
                "company_memory/capital_allocation_outcomes/capital_allocation_longitudinal_profile.json"):
        _assert_dirty(iso, reg, rel, base)


def test_m522c_08_evidence_file_changes_dirty(iso, reg):
    base = _official(iso, reg)
    for rel in ("company_memory/management_quality/management_quality_evidence.json",
                "company_memory/verification_entities.json",
                "company_memory/management_commitments/management_commitments.json",
                "company_memory/management_progression/management_progression.json",
                "company_memory/management_commentary/commentary_themes.json",
                "company_memory/management_quality/management_quality_dimensions.json",
                "company_memory/management_quality/management_quality_summary.json"):
        _assert_dirty(iso, reg, rel, base)


def test_m522c_09_financial_source_changes_dirty(iso, reg):
    base = _official(iso, reg)
    for rel in ("company_memory/financial_year_index.json", "company_memory/financial_truth_pack.json"):
        _assert_dirty(iso, reg, rel, base)


def test_m522c_10_annual_chunk_changes_dirty(iso, reg):
    base = _official(iso, reg)
    annual = [r for r in _all_inputs(reg) if r.endswith("extracted/clean_chunks.json")]
    assert len(annual) == 7
    for rel in annual:
        _assert_dirty(iso, reg, rel, base)


def test_m522c_11_quarterly_chunk_changes_dirty(iso, reg):
    base = _official(iso, reg)
    quarterly = [r for r in _all_inputs(reg) if r.endswith("quarterly_chunks.json")]
    assert len(quarterly) == 2
    for rel in quarterly:
        _assert_dirty(iso, reg, rel, base)


def test_m522c_12_new_eligible_source_dirty(iso, reg):
    base = _official(iso, reg)
    root = iso / "sun_pharma"
    donor = root / "fy25/quarters/Q4/quarterly_chunks.json"
    for new in ("fy25/quarters/Q1/quarterly_chunks.json", "fy26/quarters/Q1/quarterly_chunks.json"):
        target = root / new
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(donor, target)
        try:
            assert _official(iso, reg) != base, f"FALSE-CLEAN: added {new}"
        finally:
            shutil.rmtree(target.parent.parent if target.parent.parent.name == "quarters" and not any(target.parent.parent.iterdir() ) else target.parent, ignore_errors=True)
            if target.exists():
                target.unlink()
    assert _official(iso, reg) == base


def test_m522c_13_deleted_or_moved_source_dirty(iso, reg):
    base = _official(iso, reg)
    root = iso / "sun_pharma"
    for rel in ("fy24/extracted/clean_chunks.json", "fy25/quarters/Q3/quarterly_chunks.json",
                "company_memory/verification_entities.json", "company_memory/projects/projects_registry.json"):
        path = root / rel
        saved = path.read_bytes()
        path.unlink()
        try:
            assert _official(iso, reg) != base, f"FALSE-CLEAN: removed {rel}"
        finally:
            path.write_bytes(saved)
    moved_from, moved_to = root / "fy25/quarters/Q3/quarterly_chunks.json", root / "fy25/quarters/Q3/quarterly_chunks_renamed.json"
    moved_from.rename(moved_to)
    try:
        assert _official(iso, reg) != base, "FALSE-CLEAN: renamed source"
    finally:
        moved_to.rename(moved_from)
    assert _official(iso, reg) == base


def test_m522c_14_unrelated_changes_stay_clean(iso, reg):
    base = _official(iso, reg)
    with mutated(iso, "company_memory/cim_v1.json"):
        assert _official(iso, reg) == base, "unrelated module must not invalidate V5"
    fy27 = iso / "sun_pharma/fy27/extracted/clean_chunks.json"
    if fy27.exists():
        with mutated(iso, "fy27/extracted/clean_chunks.json"):
            assert _official(iso, reg) == base, "a year outside years_used is not consumed"
    with mutated(iso, "company_memory/verification_entities.json", "timestamp_field_only"):
        assert _official(iso, reg) == base, "non-semantic timestamp field only"


def test_m522c_15_zero_material_false_clean(iso, reg):
    base = _official(iso, reg)
    inputs = sorted(_trace_reads())            # the 21 files the builder actually consumed
    assert len(inputs) == 21 and set(inputs) <= _covered(reg)
    false_clean = []
    for rel in inputs:
        with mutated(iso, rel):
            if _official(iso, reg) == base:
                false_clean.append(rel)
        # same-timestamp content change is covered by mutated() (mtime restored after write)
    assert false_clean == [], false_clean       # MATERIAL_FALSE_CLEAN_COUNT = 0


# ── Part V ──────────────────────────────────────────────────────────────────
def test_m522c_16_official_fingerprint_deterministic(iso, reg):
    runs = {_official(REPO / "companies", reg) for _ in range(5)}
    assert runs == {NEW_EVIDENCE_FP}
    # same fingerprint from a copy in a different absolute location with different mtimes
    for p in (iso / "sun_pharma").rglob("*.json"):
        os.utime(p, (1, 1))
    assert _official(iso, reg) == NEW_EVIDENCE_FP


def test_m522c_17_candidate_binds_to_complete_manifest(cand, reg):
    from intelligence.shadow_change_detector import get_effective_contract
    c = get_effective_contract(UNIT, reg)
    assert cand["dependency_modules"] == c["upstream_modules"] and cand["dependency_contract_digest"] == NEW_DEP_DIGEST
    assert cand["dependency_contract_version"] == "4" and cand["evidence_fingerprint"] == NEW_EVIDENCE_FP
    assert cand["evidence_fingerprint"] not in (OLD_OFFICIAL_FP, INHERITED_FP)
    assert cand["evidence_fingerprint_status"].startswith("OFFICIAL")
    assert cand["enrichment_input_file_count"] == 21


def test_m522c_18_official_freshness_current(cand, reg):
    from intelligence.regeneration_executor import verify_candidate_freshness
    roots = REPO / "companies"
    assert verify_candidate_freshness(cand, roots, reg)["freshness"] == "CURRENT"
    old = json.loads(PREV_CANDIDATE.read_text())
    assert verify_candidate_freshness(old, roots, reg)["freshness"] == "DIRTY", "incomplete-contract artifact is never CURRENT"
    for tweak in ({"evidence_fingerprint": INHERITED_FP}, {"dependency_contract_digest": "sha256:" + "0" * 64},
                  {"dependency_contract_digest": None}):
        assert verify_candidate_freshness({**cand, **tweak}, roots, reg)["freshness"] == "DIRTY"
    # candidate produced under the historical contract cannot be CURRENT under v4 even if its old FP reproduces
    assert verify_candidate_freshness({**cand, "evidence_fingerprint": OLD_OFFICIAL_FP}, roots, reg)["freshness"] == "DIRTY"


# ── Part VI ─────────────────────────────────────────────────────────────────
def _mg(plan):
    return next(u for u in plan["units"] if u["generation_unit"] == UNIT)


def test_m522c_19_all_v5_planner_paths_zero_ai(monkeypatch):
    import intelligence.regeneration_planner as rp
    for co in ("sun_pharma", "tanla"):
        for plan in (rp.plan_regeneration(co, changed_modules=["management_progression", "projects_registry"]),
                     rp.plan_regeneration(co, forced_reasons={UNIT: ["PROMPT_VERSION_CHANGED"]})):
            u = _mg(plan)
            assert u["planned_ai_calls"] == 0 and u["effective_generation_mode"] == "DETERMINISTIC"
            assert u["ai_regeneration_required"] is False and u["effective_contract_id"] == "m52_contract_v5_override.v1"
    clean = rp.plan_regeneration("sun_pharma")
    assert _mg(clean)["decision"] == "REUSE" and clean["total_planned_calls"] == 0
    monkeypatch.setattr(rp, "load_fingerprint_registry", lambda *a, **k: None)
    assert _mg(rp.plan_regeneration("sun_pharma"))["planned_ai_calls"] == 0
    # the new modules are real dependencies: a projects_registry change plans a (0-call) rebuild
    dirty = rp.plan_regeneration("sun_pharma", changed_modules=["projects_registry"], baseline=None)
    assert _mg(dirty)["decision"] == "WOULD_REGENERATE" and "projects_registry" in _mg(dirty)["changed_modules"]


def test_m522c_20_unrelated_ai_units_unchanged(reg, hist, monkeypatch):
    import intelligence.regeneration_planner as rp
    others = [u for u in hist["generation_units"] if u != UNIT]
    assert len(others) == 6
    assert all(rp._planned_ai_calls(u, reg) == 1 == rp._planned_ai_calls(u, hist) for u in others)
    monkeypatch.setattr(rp, "load_fingerprint_registry", lambda *a, **k: None)
    plan = rp.plan_regeneration("sun_pharma")
    for u in plan["units"]:
        if u["generation_unit"] != UNIT:
            assert u["planned_ai_calls"] == 1 and u["ai_regeneration_required"] is True
            assert u["effective_contract_id"] == "HISTORICAL_M39_M44"


# ── Part VII ────────────────────────────────────────────────────────────────
def test_m522c_21_old_candidates_immutable():
    for name, digest in HIST_CANDIDATES.items():
        assert _sha(HIST_ANS if name == "shadow_level3_hybrid_answers.json" else ASK / name) == digest, name
    assert NEW.name not in HIST_CANDIDATES


def test_m522c_22_new_candidate_identity_correct(cand):
    """Historical (M52.2c) candidate: its stored identity is self-consistent. The live Contract V5 FP
    moved on in M52.2d, so only stored values and pure functions are checked here."""
    from intelligence.management_quality.assembler_v5 import compute_execution_id_v5
    assert _sha(NEW) == NEW_FILE
    assert cand["contract_v5_fingerprint"] == NEW_CONTRACT_FP
    assert compute_execution_id_v5("sun_pharma", UNIT, NEW_EVIDENCE_FP, NEW_CONTRACT_FP) == cand["execution_id"] == NEW_EXEC
    assert cand["candidate_digest"] == ANSWER_DIGEST == "sha256:" + hashlib.sha256(json.dumps(cand["answer"], sort_keys=True).encode()).hexdigest()
    assert (cand["ai_calls_made"], cand["zero_ai_calls"]) == (0, True) and cand["schema_version"] == "m522c_candidate_v1"
    assert NEW_CONTRACT_FP != "sha256:a8f9d700572a15c09e2306343da56f772cd81e90856cf36a95a947d94cf5e9fb"


def test_m522c_23_answer_content_parity(cand):
    """M52.2c rebinding changed identity only: the answer equals the M52.2a answer (both immutable)."""
    prev = json.loads(PREV_CANDIDATE.read_text())["answer"]
    assert cand["answer"] == prev
    assert json.dumps(cand["answer"], sort_keys=True) == json.dumps(prev, sort_keys=True)


# ── Part VIII ───────────────────────────────────────────────────────────────
def test_m522c_24_gates_and_four_company_replay(cand):
    import pipelines.pacp_adversarial as pa
    from intelligence.external_investor_value_validator import validate_management_answer_eiv
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    from intelligence.management_quality.capability_parity_validator import validate_management_semantic_capability_parity
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    fp = build_management_quality_fact_pack_v2("sun_pharma")
    a = cand["answer"]
    assert pa.run_adversarial_suite(a, "sun_pharma", "how-good-is-management")["overall"] == "PASS"
    assert validate_management_answer_eiv(a, fp)["overall"] == "PASS"
    assert validate_management_answer_eiv_v2(a, fp)["overall"] == "PASS"
    assert validate_management_semantic_capability_parity(a)["overall"] == "PASS"
    for co in ("sun_pharma", "data_patterns", "tanla", "ujjivan"):
        f = build_management_quality_fact_pack_v2(co)
        ans = build_management_answer_v5(f)
        assert not ans.get("_section_quality_violations") and not ans.get("_rating_violations")
        assert pa.run_adversarial_suite(ans, co, "how-good-is-management")["overall"] == "PASS"
        if co == "data_patterns":
            assert ans["what_evidence_shows"] == [] and ans["management_consistency_map"] == {} and ans["what_to_monitor"] == []
        if co != "sun_pharma":
            assert "Nidlegy" not in json.dumps(ans) and "Organon" not in json.dumps(ans)


def test_m522c_25_determinism_5_runs_x_4_companies():
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    for co in ("sun_pharma", "data_patterns", "tanla", "ujjivan"):
        outs = {json.dumps(build_management_answer_v5(build_management_quality_fact_pack_v2(co)), sort_keys=True) for _ in range(5)}
        assert len(outs) == 1, co


# ── Part IX ─────────────────────────────────────────────────────────────────
def test_m522c_26_approval_registry_bytes_preserved():
    assert _sha(HIST_APPROVAL) == APPROVAL_DIGEST          # historical baseline
    assert _sha(APPROVAL) == ACTIVATED_APPROVAL            # activated state
    approvals = json.loads(HIST_APPROVAL.read_text())["approvals"]
    assert len(approvals) == 20 and "human_approved" not in json.dumps(approvals)
    rec = approvals["sun_pharma:how-good-is-management"]
    assert rec["fingerprint"] == "37e04b439bf5cfa3" and rec["approved_by"] == "yogesh"


def test_m522c_27_trust_tests_cannot_mutate_real_registry(monkeypatch, capsys):
    import pipelines.answer_certification as ac
    before = _sha(LIVE_APPROVAL)
    ac.mode_test_trust()                       # the real entrypoint, now self-isolating
    assert _sha(LIVE_APPROVAL) == before and ac.APPROVAL_REGISTRY_PATH == LIVE_APPROVAL
    assert "PASSED" in capsys.readouterr().out
    # a harness that wrote the REAL path would be caught and the run aborted
    real_bytes = LIVE_APPROVAL.read_bytes()
    def evil():
        LIVE_APPROVAL.write_bytes(real_bytes + b" ")
    monkeypatch.setattr(ac, "_mode_test_trust_isolated", evil)
    try:
        with pytest.raises(SystemExit) as exc:
            ac.mode_test_trust()
        assert exc.value.code == 2
    finally:
        LIVE_APPROVAL.write_bytes(real_bytes)
    assert _sha(LIVE_APPROVAL) == before
    # harness writes land in the isolated copy, not the real file
    seen = {}
    def probe():
        seen["path"] = ac.APPROVAL_REGISTRY_PATH
    monkeypatch.setattr(ac, "_mode_test_trust_isolated", probe)
    ac.mode_test_trust()
    assert seen["path"] != LIVE_APPROVAL and "pacp_trust_" in str(seen["path"])


def test_m522c_28_no_activation_and_candidate_unapproved(cand):
    approvals = json.loads(APPROVAL.read_text())["approvals"]
    blob = json.dumps(approvals)
    assert cand["execution_id"] not in blob and NEW_FILE.split(":")[1] not in blob and len(approvals) == 20
    launch = json.loads((REPO / ".claude" / "launch.json").read_text())
    matrix = next(c for c in launch["configurations"] if c["name"] == "ask-intrinsiciq-canary")["env"]["PROMETHEUS_LEVEL3_UI_CANARY_MATRIX"].split(",")
    assert sorted(matrix) == sorted(approvals) and len(matrix) == 20
    assert _sha(HIST_ANS).endswith("830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43")
    assert _sha(_M594_SUN) == ACTIVATED_ANS
    build = (REPO / "scratchpad" / "m522c_build_candidate.py").read_text()
    assert "answer_certification" not in build and "mode_approve" not in build and "activate" not in build.lower()
    # Serving code must never reference a candidate. The isolated Story/Cockpit adapters (src/lib/story) name one candidate
    # file for the dev-only preview; they are held to the same rule by the TypeScript suite (cockpit mode never reads it).
    for p in (REPO / "apps" / "ask-intrinsiciq" / "src").rglob("*.ts*"):
        if "lib/story" in p.as_posix():
            continue
        assert "regeneration_candidate" not in p.read_text(), p


def test_m522c_29_no_provider_invocation():
    code = (
        "import sys, json;from pathlib import Path;"
        "import intelligence.regeneration_planner as rp;"
        "from intelligence.regeneration_executor import verify_candidate_freshness;"
        "from intelligence.management_quality.assembler_v5 import build_management_answer_v5;"
        "from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2 as b;"
        "rp.plan_regeneration('sun_pharma', forced_reasons={'how_good_is_management_synthesis':['X']});"
        "build_management_answer_v5(b('sun_pharma'));"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in ('openai','anthropic') or m.startswith('knowledge.ai')))")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env={**os.environ, "PYTHONPATH": str(REPO)},
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-400:]
    assert out.stdout.strip().splitlines()[-1] == "[]"


def test_m522c_30_runtime_remains_fail_closed():
    ts = (REPO / "apps/ask-intrinsiciq/src/lib/ask-intrinsiciq/load-answer-card.ts").read_text()
    for cls in ("APPROVAL_NOT_REGISTERED", "APPROVAL_PENDING_INDEPENDENT_REVIEW", "APPROVAL_PENDING_MIGRATION_REVIEW",
                "APPROVAL_REVOKED", "APPROVAL_FINGERPRINT_MISMATCH", "FULL_ARTIFACT_DIGEST_MISMATCH"):
        assert cls in ts
    if shutil.which("npx") is None:
        pytest.skip("npx not available")
    out = subprocess.run(["npx", "vitest", "run", "src/lib/ask-intrinsiciq/release-guard.test.ts"],
                         cwd=REPO / "apps" / "ask-intrinsiciq", capture_output=True, text=True, timeout=300)
    assert "Tests  11 passed (11)" in out.stdout + out.stderr, (out.stdout + out.stderr)[-600:]
