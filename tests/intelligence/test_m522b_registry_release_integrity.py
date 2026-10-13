"""
ENG-MISSION52.2b — Restored registry verification & release integrity. AI calls: 0.

The two strict-xfail tests encode OPEN blockers: they flip to a hard failure the moment the
blocker is resolved, which forces this file (and the release verdict) to be updated.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# M59.4 moved the live registry (91 pairs) and served answers on from the M54.13 activation these tests pin. The M54.13 state is preserved,
# byte for byte, in the M59.4 pre-activation backup; these historical release-integrity assertions are evaluated against that preserved state.
_M594 = sorted((Path(__file__).resolve().parents[2] / "governance").glob("m594_backup_*"))[-1]
_M594_REG = _M594 / "approval_registry.json"
_M594_SUN = _M594 / "sun_pharma__shadow_level3_hybrid_answers.json"

REG = _M594_REG
DEP = REPO / "governance" / "answer_dependency_registry.v3_pre_m52.json"   # M52.2b state = the historical v3 contract
DEP_LIVE = REPO / "governance" / "answer_dependency_registry.json"
ASK = REPO / "companies" / "sun_pharma" / "company_memory" / "ask_intrinsiciq"

HIST_REG = REPO / "governance" / "approval_registry.pre_m5413.json"          # preserved pre-M54.13 snapshots
HIST_ANS = REPO / "companies" / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / "shadow_level3_hybrid_answers.pre_m5413.json"
ACTIVATED_REG = "sha256:58fc5eea5126cbdf5f7932341713feaf8519b420adf5a373a050a340d705b60f"                                                   # M54.13 activation (corrected Sun answers)
ACTIVATED_ANS = "sha256:9b6d8bad07c39aa8532272ef24b5fb8195cb96eeb988b3bd847f15d569d31998"
APPROVAL_REGISTRY_FILE_DIGEST = "sha256:6ee8c1efef89c05b44408fd3340c0bafbd7bca54621480e1cc156c142672958d"
DEPENDENCY_REGISTRY_FILE_DIGEST = "sha256:240b8aaa7549f405608fe629df4cf333a547a8ec39e143cd90c0589955cd2570"
M37_8_RAW = "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"
M37_8_FP = "37e04b439bf5cfa3"
CANDIDATE = ASK / "regeneration_candidate_how_good_is_management_2f7e73f8dab8_v5.json"
CANDIDATE_FILE_DIGEST = "sha256:288a03e334029a3881514f393a62e93a91eaed48ea1e285c56bf6d48228d2739"
CANDIDATE_EVIDENCE_FP = "sha256:dc623eac6e2350742314f7f4ad44c817e8fe9bb2b4a717e6a864e1da206605a2"
UNIT = "how_good_is_management_synthesis"
SLUG_DIR = {"datapatterns": "datapatterns"}


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def approvals():
    return json.loads(REG.read_text())["approvals"]


@pytest.fixture(scope="module")
def dep():
    return json.loads(DEP.read_text())


# ── Part I: approval registry ───────────────────────────────────────────────
def test_m522b_01_approval_registry_structure(approvals):
    raw = json.loads(REG.read_text())
    assert raw["schema_version"] == 3 and raw["_artifact_identity_version"] == "2"
    assert len(approvals) == 20
    pairs = [(v["company"], v["question"]) for v in approvals.values()]
    assert len(set(pairs)) == 20, "company-question pairs must be unique"
    assert all(k == f"{v['company']}:{v['question']}" for k, v in approvals.items())
    assert len({c for c, _ in pairs}) == 4 and len({q for _, q in pairs}) == 5
    for v in approvals.values():
        assert re.fullmatch(r"[0-9a-f]{64}", v["full_artifact_digest"]) and re.fullmatch(r"[0-9a-f]{16}", v["fingerprint"])
        assert v["artifact_identity_version"] == "2" and v["approved_by"] and v["approved_at"]


def test_m522b_02_all_20_identities_reconcile(approvals):
    mismatches = []
    for key, rec in approvals.items():
        co, q = key.split(":")
        data = json.loads((_M594 / f"{co}__shadow_level3_hybrid_answers.json").read_text())   # the served files as registered in M54.13 (preserved in the M59.4 backup)
        ans = data["answers"][q]["answer"]
        full = hashlib.sha256(json.dumps(ans, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        fp = hashlib.md5(json.dumps({k: v for k, v in ans.items() if k != "deterministic_precision_facts"}, sort_keys=True).encode()).hexdigest()[:16]
        if full != rec["full_artifact_digest"] or fp != rec["fingerprint"]:
            mismatches.append(key)
        assert not rec.get("status"), f"{key}: unexpected status {rec.get('status')}"
    assert mismatches == []


def test_m522b_03_m37_8_approval_binding(approvals):
    approvals = json.loads(HIST_REG.read_text())["approvals"]   # historical baseline: the M37.8 approval, from the preserved snapshot
    rec = approvals["sun_pharma:how-good-is-management"]
    assert rec["fingerprint"] == M37_8_FP and rec["approved_by"] == "yogesh" and "frozen" in rec["note"]
    assert _sha(HIST_ANS) == M37_8_RAW
    ans = json.loads(HIST_ANS.read_text())["answers"]["how-good-is-management"]["answer"]
    assert hashlib.sha256(json.dumps(ans, sort_keys=True, ensure_ascii=True).encode()).hexdigest() == rec["full_artifact_digest"]
    assert rec["full_artifact_digest"] != M37_8_RAW.split(":")[1], "canonical-answer digest and raw-file digest are different identities"


def test_m522b_04_registry_bytes_preserved():
    assert _sha(HIST_REG) == APPROVAL_REGISTRY_FILE_DIGEST, "historical approval registry snapshot changed"
    assert _sha(REG) == ACTIVATED_REG, "activated approval registry changed"
    assert _sha(DEP) == DEPENDENCY_REGISTRY_FILE_DIGEST, "historical v3 registry bytes changed"
    assert json.loads(DEP_LIVE.read_text())["dependency_contract_version"] == "4"   # promoted in M52.2c


# ── Part II: dependency registry ────────────────────────────────────────────
def test_m522b_05_dependency_registry_structure(dep):
    from intelligence.evidence_fingerprints import MODULE_SOURCE_MAP
    assert dep["dependency_contract_version"] == "3"
    assert len(dep["questions"]) == 37 and len(dep["generation_units"]) == 7
    units = set(dep["generation_units"])
    for q, spec in dep["questions"].items():
        for u in spec.get("upstream_generation_units", []):
            assert u in units, f"{q} references unknown unit {u}"
    for u, spec in dep["generation_units"].items():
        for m in spec["upstream_modules"]:
            assert m in MODULE_SOURCE_MAP or m.startswith("pcim:"), f"{u}: unknown module {m}"
    assert dep["m44_promotion"] and dep["m43_promotion"]


def test_m522b_06_m39_classification_preserved(dep):
    q = dep["questions"]["how-good-is-management"]
    assert (q["class"], q["generation_mode"], q["generation_unit"]) == ("B_LLM_REQUIRED", "AI_PRECOMPUTED", UNIT)
    assert dep["generation_units"][UNIT]["ai_call_count"] == 1, "historical registry entry is not silently rewritten"
    challenge = REPO / "governance" / "M39_CLASSIFICATION_CHALLENGE_how_good_is_management_v5.json"
    assert challenge.exists()
    c = json.loads(challenge.read_text())
    assert c["status"] in ("PROPOSED_NOT_PROMOTED", "PROMOTED_IN_M52_2C") and c["authorization_required"] is True


# ── Part II: planner ────────────────────────────────────────────────────────
def _mgmt(plan):
    return next(u for u in plan["units"] if u["generation_unit"] == UNIT)


def test_m522b_07_v5_planner_zero_ai_all_paths(monkeypatch):
    import intelligence.regeneration_planner as rp
    dirty = rp.plan_regeneration("sun_pharma", changed_modules=["management_progression"])
    assert _mgmt(dirty)["planned_ai_calls"] == 0 and _mgmt(dirty)["decision"] == "WOULD_REGENERATE"
    forced = rp.plan_regeneration("sun_pharma", forced_reasons={UNIT: ["PROMPT_VERSION_CHANGED"]})
    assert _mgmt(forced)["planned_ai_calls"] == 0
    monkeypatch.setattr(rp, "load_fingerprint_registry", lambda *a, **k: None)
    nobase = rp.plan_regeneration("sun_pharma")
    assert _mgmt(nobase)["planned_ai_calls"] == 0
    other = [u for u in nobase["units"] if u["generation_unit"] != UNIT]
    assert other and all(u["planned_ai_calls"] == 1 for u in other), "AI units keep their AI plan"
    assert rp.TOKEN_TELEMETRY[UNIT]["planned_ai_calls"] == 0 and rp._planned_ai_calls("graham_panel") == 1


def test_m522b_08_planner_never_invokes_a_provider():
    import intelligence.regeneration_planner as rp
    src = Path(rp.__file__).read_text()
    for forbidden in ("import openai", "import anthropic", "from knowledge.ai", "requests.post"):
        assert forbidden not in src


# ── Part II/III: dependency coverage and official freshness (OPEN blockers) ─
def _trace_v5_reads():
    import builtins
    reads = set()
    real_open, rt, rb = builtins.open, pathlib.Path.read_text, pathlib.Path.read_bytes
    def note(p):
        s = str(p)
        if "companies/sun_pharma" in s and "ask_intrinsiciq" not in s:
            reads.add(os.path.relpath(s, REPO))
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
        build_management_answer_v5(build_management_quality_fact_pack_v2("sun_pharma"))
    finally:
        builtins.open, pathlib.Path.read_text, pathlib.Path.read_bytes = real_open, rt, rb
    return reads


@pytest.mark.xfail(strict=True, reason="RB-3: 15 of 21 V5 inputs are outside official freshness tracking (see M39 challenge)")
def test_m522b_09_v5_dependency_coverage_complete(dep):
    from intelligence.evidence_fingerprints import MODULE_SOURCE_MAP
    tracked_paths = {f"companies/sun_pharma/{MODULE_SOURCE_MAP[m]}" for m in dep["generation_units"][UNIT]["upstream_modules"]}
    untracked = sorted(r for r in _trace_v5_reads() if r not in tracked_paths)
    assert untracked == [], untracked


@pytest.mark.xfail(strict=True, reason="RB-4: candidate evidence fingerprint is not the official evidence fingerprint")
def test_m522b_10_official_freshness_current():
    from intelligence.regeneration_executor import _compute_evidence_fingerprint
    assert _compute_evidence_fingerprint("sun_pharma", Path("companies"), json.loads(DEP.read_text())) == json.loads(CANDIDATE.read_text())["evidence_fingerprint"]


def test_m522b_11_official_fingerprint_matches_execution_history():
    """The official value is stable and equals what every recorded M45-M51 execution used."""
    from intelligence.regeneration_executor import _compute_evidence_fingerprint
    official = _compute_evidence_fingerprint("sun_pharma", Path("companies"), json.loads(DEP.read_text()))
    manifest = (ASK / "regeneration_execution_manifest.json").read_text()
    assert official == "sha256:6793736f4298b82142d39d0439f299d7c11f0310ada29ff0a9cc99fac06c2aad"
    assert official.split(":")[1][:12] in manifest
    assert CANDIDATE_EVIDENCE_FP != official


def test_m522b_12_candidate_identity_verified():
    from intelligence.management_quality.assembler_v5 import compute_execution_id_v5
    from intelligence.management_quality.contract_manifest import CONTRACT_V5_POLICY_DIGEST
    c = json.loads(CANDIDATE.read_text())
    assert _sha(CANDIDATE) == CANDIDATE_FILE_DIGEST
    assert c["contract_v5_fingerprint"] == "sha256:a8f9d700572a15c09e2306343da56f772cd81e90856cf36a95a947d94cf5e9fb"   # historical; live FP moved in M52.2c
    assert compute_execution_id_v5("sun_pharma", UNIT, c["evidence_fingerprint"], c["contract_v5_fingerprint"]) == c["execution_id"]
    assert "sha256:" + hashlib.sha256(json.dumps(c["answer"], sort_keys=True).encode()).hexdigest() == c["candidate_digest"]


# ── Part IV: guards, canary, V5 stays unapproved ────────────────────────────
@pytest.mark.parametrize("status,expected", [
    (None, True), ("PENDING_INDEPENDENT_REVIEW", False), ("PENDING_MIGRATION_REVIEW", False), ("REVOKED", False)])
def test_m522b_13_python_approval_guard(status, expected, approvals, monkeypatch):
    import pipelines.answer_certification as ac
    rec = dict(approvals["sun_pharma:how-good-is-management"])
    if status:
        rec["status"] = status
    monkeypatch.setattr(ac, "_load_registry", lambda: {"approvals": {"sun_pharma:how-good-is-management": rec}})
    ok, _ = ac._is_approved("sun_pharma", "how-good-is-management", rec["fingerprint"])
    assert ok is expected
    assert ac._is_approved("sun_pharma", "how-good-is-management", "0" * 16)[0] is False
    assert ac._is_approved("sun_pharma", "no-such-question", rec["fingerprint"])[0] is False


def test_m522b_14_runtime_guard_source_blocks_every_non_approved_state():
    src = (REPO / "apps/ask-intrinsiciq/src/lib/ask-intrinsiciq/load-answer-card.ts").read_text()
    for cls in ("APPROVAL_NOT_REGISTERED", "APPROVAL_PENDING_INDEPENDENT_REVIEW", "APPROVAL_PENDING_MIGRATION_REVIEW",
                "APPROVAL_REVOKED", "APPROVAL_FINGERPRINT_MISMATCH", "FULL_ARTIFACT_DIGEST_MISMATCH"):
        assert cls in src, cls
    assert "Registry unreadable — fail closed" in src or "fail closed" in src.lower()
    test = (REPO / "apps/ask-intrinsiciq/src/lib/ask-intrinsiciq/release-guard.test.ts")
    assert test.exists() and "S5_revoked" in test.read_text()


def test_m522b_15_canary_matrix_is_the_20_registered_pairs(approvals):
    launch = json.loads((REPO / ".claude" / "launch.json").read_text())
    matrix = next(c for c in launch["configurations"] if c["name"] == "ask-intrinsiciq-canary")["env"]["PROMETHEUS_LEVEL3_UI_CANARY_MATRIX"].split(",")
    assert len(matrix) == 20 and sorted(matrix) == sorted(approvals)


def test_m522b_16_v5_candidate_unapproved_and_inactive(approvals):
    c = json.loads(CANDIDATE.read_text())
    assert c["execution_id"] not in json.dumps(approvals) and CANDIDATE_FILE_DIGEST.split(":")[1] not in json.dumps(approvals)
    assert len(approvals) == 20 and "human_approved" not in c
    # the runtime serves only shadow_level3_hybrid_answers.json (M37.8 baseline, activated in M54.13), never candidate files
    assert _sha(HIST_ANS) == M37_8_RAW
    assert _sha(_M594_SUN) == ACTIVATED_ANS
    # Serving code never references candidates. The isolated Story/Cockpit adapters (src/lib/story) name one candidate file for the
    # dev-only preview and are held to the same rule by the TypeScript suite (cockpit mode never reads it).
    for p in (REPO / "apps" / "ask-intrinsiciq" / "src").rglob("*.ts*"):
        if "lib/story" in p.as_posix():
            continue
        assert "regeneration_candidate" not in p.read_text() and "regeneration_executor" not in p.read_text(), p
    review = json.loads((REPO / "governance" / "ENG_MISSION52_2A_V5_HUMAN_REVIEW.json").read_text())
    assert review["HUMAN_DECISION"] == "PENDING"
