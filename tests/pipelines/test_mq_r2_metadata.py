"""M54.12 — MQ-R2 validates the technical `behavioral_descriptor` metadata, and the three corrected Sun Pharma answers pass PACP."""
import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from pipelines.answer_certification import compute_content_fingerprint, compute_full_artifact_digest
from pipelines import pacp_adversarial as pa

ROOT = Path(__file__).resolve().parents[2]
ASK = ROOT / "companies" / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
QMQ = "how-good-is-management"
MQ = pa.check_mq_behavioral_descriptor_present
KW = {"company": "sun_pharma", "question_id": QMQ}

EXPECTED = {
    "what-has-management-promised": ("02ed5ce98eae4dcd61a8bfa439243dbf7f7b2f65541845e76465640bde598c16", "290105890138e23b"),
    "what-did-management-actually-deliver": ("820d8e38cf71766da0af9e47b347c89c4a92a248dc640095767c3bedc53e9f29", "25d773eb958db636"),
    "how-good-is-management": ("5a8a9d492fceff61016ab00d77d937f8d575ae50dfa9e9da282bc070621bcaee", "acdaef5a5d90096d"),
}


def _j(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _candidates():
    m10 = _j(ASK / "m5410_corrected_candidates.json")["candidates"]
    m11 = _j(ASK / "m5411_management_quality_candidate.json")["candidates"]
    return {
        "what-has-management-promised": m10["what-has-management-promised"]["answer"],
        "what-did-management-actually-deliver": m10["what-did-management-actually-deliver"]["answer"],
        QMQ: m11[QMQ]["answer"],
    }


# The pre-M54.13 approved answer (legacy in-prose format), preserved as a snapshot when the corrected answers were activated.
HIST_ANS = ASK / "shadow_level3_hybrid_answers.pre_m5413.json"
HIST_REG = ROOT / "governance" / "approval_registry.pre_m5413.json"
APPROVED_MQ = _j(HIST_ANS)["answers"][QMQ]["answer"]


# ── MQ-R2 behaviour ──
def test_candidate_passes_with_descriptor_only_in_metadata():
    a = _candidates()[QMQ]
    assert MQ(a, **KW)[0] == "PASS"
    assert not any(d in a["simple_answer"] for d in pa._MQ_BEHAVIORAL_DESCRIPTORS)  # never required in prose
    assert not re.search(r"[A-Z]{3,}_[A-Z_]{3,}", a["simple_answer"])


def test_historical_approved_answer_still_passes():
    assert "FOLLOW_THROUGH_LARGELY_UNVERIFIED" in APPROVED_MQ["simple_answer"]
    assert "behavioral_descriptor" not in APPROVED_MQ
    assert MQ(APPROVED_MQ, **KW) == ("PASS", "behavioral delivery descriptor present in simple_answer (legacy format)")


def test_missing_classification_fails_and_is_not_manufactured():
    a = copy.deepcopy(_candidates()[QMQ])
    del a["behavioral_descriptor"]
    r = MQ(a, **KW)
    assert r[0] == "FAIL" and "missing" in r[1]
    assert "behavioral_descriptor" not in a  # the validator never writes metadata


@pytest.mark.parametrize("bad", ["", "SOMETHING_ELSE", "follow_through_largely_unverified", 5, ["FOLLOW_THROUGH_LARGELY_UNVERIFIED"], {"d": 1}])
def test_invalid_metadata_fails(bad):
    a = copy.deepcopy(_candidates()[QMQ])
    a["behavioral_descriptor"] = bad
    assert MQ(a, **KW)[0] == "FAIL"


def test_conflicting_prose_and_metadata_cannot_pass():
    a = copy.deepcopy(_candidates()[QMQ])
    a["simple_answer"] += " PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS."
    r = MQ(a, **KW)
    assert r[0] == "FAIL" and "contradicts" in r[1]
    ok = copy.deepcopy(_candidates()[QMQ])
    ok["simple_answer"] += " FOLLOW_THROUGH_LARGELY_UNVERIFIED."
    assert MQ(ok, **KW)[0] == "PASS"  # same classification in both places is consistent


def test_legacy_conflict_with_metadata_also_fails():
    a = copy.deepcopy(APPROVED_MQ)
    a["behavioral_descriptor"] = "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED"
    assert MQ(a, **KW)[0] == "FAIL"


def test_existing_negative_fixture_still_fails():
    nf30 = next(f for f in pa.NEGATIVE_FIXTURES if f["id"] == "NF-30") if hasattr(pa, "NEGATIVE_FIXTURES") else None
    if nf30 is None:  # fixture list name differs: locate by id in module globals
        lists = [v for v in vars(pa).values() if isinstance(v, list) and v and isinstance(v[0], dict) and "expected_fail" in v[0]]
        nf30 = next(f for l in lists for f in l if f["id"] == "NF-30")
    assert MQ(nf30["answer"], **KW)[0] == "FAIL"


# ── the three exact candidates ──
@pytest.mark.parametrize("qid", list(EXPECTED))
def test_three_candidates_pass_pacp_exactly(qid):
    a = _candidates()[qid]
    digest, fp = EXPECTED[qid]
    assert compute_full_artifact_digest(a) == digest
    assert compute_content_fingerprint(a) == fp
    suite = pa.run_adversarial_suite(a, "sun_pharma", qid)
    assert suite["fails"] == [] and suite["overall"] == "PASS", suite["fails"]
    assert suite["warns"] == [] and suite["incomplete"] == []
    assert pa.check_runtime_sanitizer_compat(a)[0] == "PASS"


def test_approved_answers_still_pass_the_full_suite():
    answers = _j(ASK / "shadow_level3_hybrid_answers.json")["answers"]
    for qid in EXPECTED:
        s = pa.run_adversarial_suite(answers[qid]["answer"], "sun_pharma", qid)
        assert s["fails"] == [], (qid, s["fails"])


# ── digests and byte-identity ──
def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_files_and_approved_artifacts_unchanged():
    reg = _j(ROOT / "governance" / "approval_registry.json")["approvals"]
    # historical baseline (preserved snapshots, original hashes)
    assert _sha(HIST_REG) == "6ee8c1efef89c05b44408fd3340c0bafbd7bca54621480e1cc156c142672958d"
    assert _sha(HIST_ANS) == "830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"
    # activated state: M54.13 (Sun answers) and then M59.4 (91 pairs); the M54.13 state is recoverable from the preserved M59.4 backup
    backup = sorted((ROOT / "governance").glob("m594_backup_*"))[-1]
    assert _sha(backup / "approval_registry.json") == "58fc5eea5126cbdf5f7932341713feaf8519b420adf5a373a050a340d705b60f"
    assert _sha(backup / "sun_pharma__shadow_level3_hybrid_answers.json") == "9b6d8bad07c39aa8532272ef24b5fb8195cb96eeb988b3bd847f15d569d31998"
    assert _sha(ROOT / "governance" / "approval_registry.json") == "4f6a71f2878204be664bec441a19b840efe2e75c706b5768c5ad200841acb028"
    assert _sha(ASK / "shadow_level3_hybrid_answers.json") == "bd09be3f85ba57cf93226c7dee7c0ba3463b6664d6c9f898b575be428837f5d3"
    assert _sha(ASK / "m5410_corrected_candidates.json") == "90ffa20f633f886f7a520ccfb2dbc4f152cf5db2cf1618b3d44dd9ad5582310d"
    answers = _j(ASK / "shadow_level3_hybrid_answers.json")["answers"]
    for qid, (digest, _) in EXPECTED.items():
        assert compute_full_artifact_digest(answers[qid]["answer"]) == reg[f"sun_pharma:{qid}"]["full_artifact_digest"]
        assert reg[f"sun_pharma:{qid}"]["full_artifact_digest"] == digest  # M54.13: the registry now records exactly the corrected digest
        old = _j(HIST_REG)["approvals"][f"sun_pharma:{qid}"]["full_artifact_digest"]
        assert old != digest  # the old approval could not have covered the new artifact
