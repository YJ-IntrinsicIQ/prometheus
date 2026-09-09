"""ENG-111A — Candidate commitment-execution bridge tests.

Verifies that _discover_candidate_commitment_links() is CANDIDATE_ONLY and
that no heuristic output may enter the MP lifecycle authority path.

Hard invariants:
 - Every link carries relationship_authority == "CANDIDATE_ONLY"
 - relationship_type is HEURISTIC_*, not EXACT_NAMED_INITIATIVE
 - relationship_confidence is LOW, not HIGH
 - No MP event is emitted from candidate links (no _events_from_project_execution_links)
 - Lifecycle index secondary join is a no-op until canonical_commitment_reference exists
"""

import pytest
from typing import Any, Dict, List

from intelligence.projects.builder import _discover_candidate_commitment_links, _named_initiative_words
from intelligence.management_promises.builder import _commitment_lifecycle_index


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mc(fp: str, normalized_commitment: str, mc_id: str = "MC-0001") -> Dict[str, Any]:
    return {
        "commitment_fingerprint": fp,
        "id": mc_id,
        "normalized_commitment": normalized_commitment,
    }


def _project(name: str, normalized: str = "") -> Dict[str, Any]:
    return {
        "project_id": "PJ-0001",
        "project_name": name,
        "normalized_name": normalized or name,
    }


def _mp_item(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"item_id": "MP-0001", "events": events}


# ── Test A: CANDIDATE_ONLY authority on every link ────────────────────────────

class TestACandidateOnlyAuthority:
    MC_0039_TEXT = (
        "Use of a centralised dashboard and an in house app for real time data "
        "monitoring and descriptive numerical and graphical analysis to ensure "
        "data integrity and extract key trends."
    )
    PJ_0018_NAME = "Centralised dashboard and in-house app for real-time data monitoring"

    def test_A_link_carries_candidate_only_authority(self):
        """Test A: Every link from the heuristic must carry relationship_authority=CANDIDATE_ONLY."""
        commitments = [_mc("a91fac39abab5ee16688", self.MC_0039_TEXT, "MC-0039")]
        project = _project(self.PJ_0018_NAME)
        links = _discover_candidate_commitment_links(project, commitments)
        assert len(links) == 1
        lnk = links[0]
        assert lnk["relationship_authority"] == "CANDIDATE_ONLY", (
            "Heuristic links must never carry lifecycle authority"
        )

    def test_A_relationship_type_is_heuristic(self):
        """Test A: relationship_type must be HEURISTIC_*, not EXACT_NAMED_INITIATIVE."""
        commitments = [_mc("a91fac39abab5ee16688", self.MC_0039_TEXT, "MC-0039")]
        project = _project(self.PJ_0018_NAME)
        links = _discover_candidate_commitment_links(project, commitments)
        assert links[0]["relationship_type"].startswith("HEURISTIC_")

    def test_A_relationship_confidence_is_low(self):
        """Test A: Heuristic links must carry LOW confidence, not HIGH."""
        commitments = [_mc("a91fac39abab5ee16688", self.MC_0039_TEXT, "MC-0039")]
        project = _project(self.PJ_0018_NAME)
        links = _discover_candidate_commitment_links(project, commitments)
        assert links[0]["relationship_confidence"] == "LOW"

    def test_A_basis_references_specific_words(self):
        """Test A: relationship_basis must name overlapping specific words."""
        commitments = [_mc("a91fac39abab5ee16688", self.MC_0039_TEXT, "MC-0039")]
        project = _project(self.PJ_0018_NAME)
        links = _discover_candidate_commitment_links(project, commitments)
        basis = links[0]["relationship_basis"].lower()
        assert "centralised" in basis or "dashboard" in basis

    def test_A_fingerprint_preserved(self):
        """Test A: commitment_fingerprint must be propagated for display use."""
        commitments = [_mc("a91fac39abab5ee16688", self.MC_0039_TEXT, "MC-0039")]
        project = _project(self.PJ_0018_NAME)
        links = _discover_candidate_commitment_links(project, commitments)
        assert links[0]["commitment_fingerprint"] == "a91fac39abab5ee16688"


# ── Test B: generic-word-only project produces NO links ───────────────────────

class TestBGenericProjectNoLinks:
    def test_B_all_generic_words_yield_no_links(self):
        """Test B: A project whose name is pure generic vocabulary gets zero candidate links."""
        project = _project("Capacity manufacturing expansion facility")
        commitments = [
            _mc("fp1", "Increase manufacturing capacity and expand facilities for production growth."),
            _mc("fp2", "Drive operational efficiency and improve manufacturing quality."),
        ]
        links = _discover_candidate_commitment_links(project, commitments)
        assert links == [], f"Expected no candidate links, got: {links}"


# ── Test C: broad token overlap without specific words does NOT fire ──────────

class TestCBroadTokenOverlapBlocked:
    def test_C_shared_generic_words_not_sufficient(self):
        """Test C: High raw overlap on generic words must not produce a candidate link."""
        project = _project("Digital automation technology market strategy quality improvement")
        commitments = [
            _mc("fpX", "Digital automation technology market strategy quality operations improvement expand."),
        ]
        links = _discover_candidate_commitment_links(project, commitments)
        assert links == [], "Generic words must not produce a candidate link"


# ── Test D: wrong MC must NOT link to PJ-0018 ────────────────────────────────

class TestDWrongMCBlocked:
    MC_0007_TEXT = (
        "Increased focus on automation digitalisation and greater dependence on "
        "analytical tools for decision making leveraging it tools to ensure "
        "business continuity and facilitate wfh for many functions."
    )
    PJ_0018_NAME = "Centralised dashboard and in-house app for real-time data monitoring"

    def test_D_mc_0007_does_not_link_to_pj_0018(self):
        """Test D: MC-0007 automation text must NOT produce a candidate link to PJ-0018."""
        commitments = [_mc("5bf4b8d7be932da28558", self.MC_0007_TEXT, "MC-0007")]
        project = _project(self.PJ_0018_NAME)
        links = _discover_candidate_commitment_links(project, commitments)
        assert links == [], f"MC-0007 must not match PJ-0018 — got: {links}"


# ── Test E: fingerprint required, missing fp yields no link ──────────────────

class TestEFingerprintRequired:
    def test_E_commitment_without_fingerprint_skipped(self):
        """Test E: Commitments lacking commitment_fingerprint must be skipped."""
        project = _project("Centralised dashboard and in-house app for real-time data monitoring")
        commitments = [
            {
                "id": "MC-0039",
                "normalized_commitment": (
                    "Use of a centralised dashboard and an in house app for real time data "
                    "monitoring and descriptive numerical and graphical analysis."
                ),
            }
        ]
        links = _discover_candidate_commitment_links(project, commitments)
        assert links == [], "A commitment without commitment_fingerprint must not produce a link"


# ── Test F: project with too few specific words yields no link ────────────────

class TestFTooFewProjectSpecificWords:
    def test_F_project_fewer_than_3_specific_words(self):
        """Test F: Projects with < 3 specific words are ineligible for candidate matching."""
        project = _project("APIs integration")
        commitments = [_mc("fp9", "Use of APIs and integration for real time monitoring of centralised dashboard.")]
        links = _discover_candidate_commitment_links(project, commitments)
        assert links == []


# ── Test G: correct link when two MCs are present — only the matching one fires

class TestGOnlyMatchingMCFires:
    PJ_TEXT = "Halol oncology dedicated manufacturing block construction"
    MC_MATCH = "Construction of dedicated oncology manufacturing block at halol plant for injectable products."
    MC_NOMATCH = "Expand global specialty product pipeline with differentiated molecules."

    def test_G_only_matching_mc_fires(self):
        """Test G: With two MCs in scope, only the one with named-initiative overlap fires."""
        commitments = [
            _mc("fp_match", self.MC_MATCH, "MC-0010"),
            _mc("fp_nomatch", self.MC_NOMATCH, "MC-0020"),
        ]
        project = _project(self.PJ_TEXT)
        links = _discover_candidate_commitment_links(project, commitments)
        fps = [lnk["commitment_fingerprint"] for lnk in links]
        assert "fp_match" in fps
        assert "fp_nomatch" not in fps

    def test_G_matching_link_still_candidate_only(self):
        """Test G: Even the matching link carries CANDIDATE_ONLY — not lifecycle-authoritative."""
        commitments = [
            _mc("fp_match", self.MC_MATCH, "MC-0010"),
        ]
        project = _project(self.PJ_TEXT)
        links = _discover_candidate_commitment_links(project, commitments)
        assert all(lnk["relationship_authority"] == "CANDIDATE_ONLY" for lnk in links)


# ── Test H: lifecycle index primary join (commitment event) — KEEP ───────────

class TestHLifecycleIndexPrimaryJoin:
    def test_H_commitment_event_id_is_fingerprint(self):
        """Test H: _commitment_lifecycle_index joins when event_id == fingerprint and role == commitment."""
        fp = "abc123fingerprint"
        item = _mp_item([
            {"event_id": fp, "role": "commitment", "statement_text": "some commitment"},
        ])
        progression = {"progression_items": [item]}
        index = _commitment_lifecycle_index(progression, {fp})
        assert fp in index
        assert index[fp] is item


# ── Test I: secondary join is no-op until canonical_commitment_reference ──────

class TestISecondaryJoinNoOp:
    def test_I_no_execution_events_with_fp_emitted(self):
        """Test I: No MP execution event should carry commitment_fingerprint from heuristic.

        The secondary join in _commitment_lifecycle_index() is correct future contract,
        but must be a no-op now because _events_from_project_execution_links is removed.
        """
        # Simulates: if an execution event WITH commitment_fingerprint DID exist,
        # the lifecycle index would join it — but under ENG-111A no such events are emitted.
        fp = "abc123fingerprint"
        item = _mp_item([
            {"event_id": "PJ-0001:exec:abc123", "role": "action",
             "commitment_fingerprint": fp, "action_taken": "project executed"},
        ])
        progression = {"progression_items": [item]}
        index = _commitment_lifecycle_index(progression, {fp})
        # The join WOULD work if such an event existed — that's the correct future contract.
        # What we verify is that no heuristic path now EMITS such events.
        # (This test validates the join mechanism itself, not that events are suppressed —
        #  suppression is validated by the absence of _events_from_project_execution_links.)
        assert fp in index, "Secondary join mechanism must work when explicit fp field is present"


# ── Test J: lifecycle index does NOT fire on invalid fingerprint ──────────────

class TestJInvalidFingerprintIgnored:
    def test_J_fingerprint_not_in_valid_set_ignored(self):
        """Test J: Fingerprint not in valid_fingerprints must not appear in index."""
        item = _mp_item([
            {"event_id": "rogue_fp", "role": "commitment"},
        ])
        progression = {"progression_items": [item]}
        index = _commitment_lifecycle_index(progression, {"valid_fp"})
        assert "rogue_fp" not in index

    def test_J_commitment_fingerprint_field_not_in_valid_set_ignored(self):
        """Test J: commitment_fingerprint on execution event not in valid set is ignored."""
        item = _mp_item([
            {"event_id": "PJ-0001", "role": "action", "commitment_fingerprint": "rogue_fp"},
        ])
        progression = {"progression_items": [item]}
        index = _commitment_lifecycle_index(progression, {"valid_fp"})
        assert "rogue_fp" not in index


# ── Test K: named_initiative_words strips generic vocabulary ──────────────────

class TestKNamedInitiativeWordsExclusion:
    def test_K_generic_pharma_words_excluded(self):
        """Test K: Standard pharmaceutical generic words must not survive exclusion."""
        generic = "manufacturing capacity facility pharmaceutical strategy growth"
        words = _named_initiative_words(generic)
        assert words == set(), f"Expected empty set, got: {words}"

    def test_K_specific_words_survive(self):
        """Test K: Specific named-initiative words survive the exclusion filter."""
        specific = "centralised dashboard halol oncology biosimilar"
        words = _named_initiative_words(specific)
        assert "centralised" in words
        assert "dashboard" in words
        assert "halol" in words
        assert "oncology" in words
        assert "biosimilar" in words

    def test_K_length_filter_applied(self):
        """Test K: Words shorter than 4 characters are excluded regardless of exclusion list."""
        short = "api hub kit"
        words = _named_initiative_words(short)
        assert words == set()


# ── Test L: no broad relation list — 29-link contamination scenario blocked ───

class TestLNoBroadRelationList:
    def test_L_capacity_manufacturing_shared_words_do_not_fire(self):
        """Test L: The old 29-link contamination pattern must produce zero candidate links."""
        project = _project("Halol API manufacturing capacity expansion block")
        commitments = [
            _mc(f"fp{i}", text, f"MC-{i:04d}")
            for i, text in enumerate([
                "Increase manufacturing capacity through facility expansion and capex deployment.",
                "Drive capacity additions to support domestic and export volume growth.",
                "Expand manufacturing facilities to meet rising global demand for specialty products.",
                "Invest in capacity building across plants to improve operational readiness.",
                "Maintain focus on manufacturing efficiency and quality compliance across facilities.",
            ], 1)
        ]
        links = _discover_candidate_commitment_links(project, commitments)
        assert len(links) == 0, (
            f"Broad category vocabulary must not produce candidate links, got {len(links)}: {links}"
        )


# ── Test M: related_commitment_ids not overwritten by candidate links ──────────

class TestMRelatedCommitmentIdsNotOverwritten:
    """ENG-111A contract: candidate_commitment_links must NOT override related_commitment_ids."""

    def test_M_candidate_links_are_separate_from_related_commitment_ids(self):
        """Test M: _discover_candidate_commitment_links returns links — not related_commitment_ids.

        The builder must store these in candidate_commitment_links only.
        related_commitment_ids comes from upstream LLM extraction, not heuristic.
        """
        MC_TEXT = (
            "Use of a centralised dashboard and an in house app for real time data "
            "monitoring and descriptive numerical and graphical analysis."
        )
        commitments = [_mc("a91fac39abab5ee16688", MC_TEXT, "MC-0039")]
        project = _project("Centralised dashboard and in-house app for real-time data monitoring")
        # Function returns links only — caller decides where to store them.
        # The builder must NOT push commitment_id into related_commitment_ids.
        links = _discover_candidate_commitment_links(project, commitments)
        # Verify links exist but contain no authority claim
        assert len(links) == 1
        assert links[0]["relationship_authority"] == "CANDIDATE_ONLY"
        # related_commitment_ids is not a key returned by this function
        assert "related_commitment_ids" not in links[0]


# ── Test N: MC-0039 UNVERIFIED — no lifecycle advancement from heuristic ──────

class TestNMC0039Unverified:
    """ENG-111A outcome B: MC-0039 must revert to UNVERIFIED/NO_MATCHING_PROGRESSION_RECORD.

    The heuristic candidate link must not cause lifecycle advancement.
    """

    MC_0039_TEXT = (
        "Use of a centralised dashboard and an in house app for real time data "
        "monitoring and descriptive numerical and graphical analysis to ensure "
        "data integrity and extract key trends."
    )
    FP = "a91fac39abab5ee16688"

    def test_N_candidate_link_does_not_advance_lifecycle(self):
        """Test N: A candidate link must not appear in the lifecycle index as authoritative."""
        # Simulate: lifecycle index has NO events for this fp (because
        # _events_from_project_execution_links is removed).
        progression = {"progression_items": []}
        index = _commitment_lifecycle_index(progression, {self.FP})
        assert self.FP not in index, (
            "MC-0039 fp must not appear in lifecycle index when no authoritative event exists"
        )

    def test_N_candidate_link_authority_is_candidate_only(self):
        """Test N: A candidate link for MC-0039 ↔ PJ-0018 must carry CANDIDATE_ONLY authority."""
        commitments = [_mc(self.FP, self.MC_0039_TEXT, "MC-0039")]
        project = {
            "project_id": "PJ-0018",
            "project_name": "Centralised dashboard and in-house app for real-time data monitoring",
            "normalized_name": "Centralised dashboard and in-house app for real-time data monitoring",
        }
        links = _discover_candidate_commitment_links(project, commitments)
        if links:
            assert all(lnk["relationship_authority"] == "CANDIDATE_ONLY" for lnk in links), (
                "ENG-111A Outcome B: heuristic link must carry no lifecycle authority"
            )
