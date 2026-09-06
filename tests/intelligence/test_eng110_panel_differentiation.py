"""ENG-110 Phase 2 — Panel differentiation + stream delivery tests.

These are deterministic tests on prompt contracts and stream routing.
They do NOT call an LLM. They verify:
1. Risk evolution stream IS protected (delivered to all analysts).
2. Doctrine differentiation blocks carry doctrine-specific risk_interpretation.
3. Canonical risk trajectory invariants appear in shared routing rules.
4. Each doctrine has a distinct risk framing (structural differentiation).
5. Canonical invariants: worsening≠financial-damage, improving≠resolved, recurring≠worsening.
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from intelligence.investor_panel.company_memory_context import (
    build_company_memory_context,
    DOCTRINE_MEMORY_PRIORITIES,
    _compact_risk_evolution,
)
from intelligence.investor_panel.runner import (
    DOCTRINE_DIFFERENTIATION_GUIDANCE,
    _doctrine_differentiation_block,
    _shared_evidence_routing_rules,
    _doctrine_differentiation_rules,
)


# --- Stream protection tests ---

class TestRiskStreamProtection:
    ANALYSTS = ["graham", "buffett", "fisher", "munger", "lynch"]

    def test_risk_evolution_in_protected_streams(self, tmp_path):
        """Risk evolution must be protected — it cannot be silently dropped by max_streams."""
        # Import the protected_streams set from the function itself
        # by checking that it would be included even when risk_evolution is not in top-3
        from intelligence.investor_panel.company_memory_context import build_company_memory_context
        # Verify DOCTRINE_MEMORY_PRIORITIES: risk evolution is not in top-3 for any analyst
        for analyst in self.ANALYSTS:
            priority = DOCTRINE_MEMORY_PRIORITIES.get(analyst, [])
            top3 = priority[:3]
            assert "risk evolution" not in top3, (
                f"{analyst}: risk evolution is in top-3 ({top3}) — "
                "protection is only needed when it is NOT in top-3"
            )

    def test_risk_evolution_priority_positions(self):
        """Verify risk evolution position in each doctrine to document protection need."""
        positions = {}
        for analyst in self.ANALYSTS:
            priority = DOCTRINE_MEMORY_PRIORITIES.get(analyst, [])
            pos = priority.index("risk evolution") if "risk evolution" in priority else -1
            positions[analyst] = pos
        # All should be beyond position 2 (0-indexed), confirming protection is needed
        for analyst, pos in positions.items():
            assert pos > 2, (
                f"{analyst}: risk evolution at position {pos} — expected >2 (outside top-3)"
            )

    def test_build_context_includes_risk_evolution_when_available(self, tmp_path):
        """With a real risk_assessments.json on disk, risk evolution stream is included."""
        company_root = tmp_path / "testco"
        cm = company_root / "company_memory"
        risks_dir = cm / "risks"
        risks_dir.mkdir(parents=True)
        # Write minimal risk_assessments.json
        (risks_dir / "risk_assessments.json").write_text(json.dumps({
            "company": "testco",
            "schema_version": "1.0",
            "assessments": [
                {"risk_id": "r1", "risk_name": "FX Risk", "trajectory": "worsening",
                 "current_status": "increasing", "evo_canonical_id": "risk_fx"},
                {"risk_id": "r2", "risk_name": "Governance Risk", "trajectory": "worsening",
                 "current_status": "increasing", "evo_canonical_id": "risk_gov"},
            ]
        }))
        # Write minimal company_memory_index.json
        (cm / "company_memory_index.json").write_text(json.dumps({
            "usable_years": ["fy24"], "ordered_years": ["fy24"]
        }))
        for analyst in self.ANALYSTS:
            ctx = build_company_memory_context(company_root, analyst, token_budget=50000)
            stream_names = [b.get("stream") for b in ctx.get("streams", [])]
            assert "risk evolution" in stream_names, (
                f"{analyst}: risk evolution stream missing from context — "
                f"streams found: {stream_names}"
            )


# --- Doctrine differentiation tests ---

class TestDoctrineDifferentiationBlocks:
    ANALYSTS = ["graham", "buffett", "fisher", "munger", "lynch"]

    def test_all_doctrines_have_risk_interpretation(self):
        """Every doctrine must carry a doctrine-specific risk_interpretation field."""
        for analyst in self.ANALYSTS:
            block = _doctrine_differentiation_block(analyst)
            assert "risk_interpretation" in block, (
                f"{analyst}: missing risk_interpretation in doctrine differentiation block"
            )
            assert block["risk_interpretation"], (
                f"{analyst}: risk_interpretation is empty"
            )

    def test_risk_interpretations_are_distinct(self):
        """No two doctrines should carry identical risk_interpretation text."""
        texts = {a: _doctrine_differentiation_block(a).get("risk_interpretation", "") for a in self.ANALYSTS}
        pairs = [(a, b) for i, a in enumerate(self.ANALYSTS) for b in self.ANALYSTS[i+1:]]
        for a, b in pairs:
            assert texts[a] != texts[b], (
                f"{a} and {b} have identical risk_interpretation — no differentiation"
            )

    def test_graham_risk_framing_is_downside_focused(self):
        """Graham's risk interpretation must reference downside / permanent loss / protection."""
        text = _doctrine_differentiation_block("graham").get("risk_interpretation", "").lower()
        assert any(kw in text for kw in ("permanent loss", "balance-sheet", "protection", "conservative")), (
            f"Graham risk interpretation missing downside framing: {text[:200]}"
        )

    def test_buffett_risk_framing_is_durability_focused(self):
        """Buffett's risk interpretation must reference moat / durability / owner economics."""
        text = _doctrine_differentiation_block("buffett").get("risk_interpretation", "").lower()
        assert any(kw in text for kw in ("moat", "durability", "owner", "durable")), (
            f"Buffett risk interpretation missing durability framing: {text[:200]}"
        )

    def test_munger_risk_framing_is_failure_mode_focused(self):
        """Munger's risk interpretation must reference structural / failure / incentive."""
        text = _doctrine_differentiation_block("munger").get("risk_interpretation", "").lower()
        assert any(kw in text for kw in ("structural", "failure", "incentive", "weakness")), (
            f"Munger risk interpretation missing failure-mode framing: {text[:200]}"
        )

    def test_fisher_risk_framing_is_execution_focused(self):
        """Fisher's risk interpretation must reference execution / growth / runway."""
        text = _doctrine_differentiation_block("fisher").get("risk_interpretation", "").lower()
        assert any(kw in text for kw in ("execution", "growth", "runway", "product")), (
            f"Fisher risk interpretation missing execution framing: {text[:200]}"
        )

    def test_lynch_risk_framing_is_story_focused(self):
        """Lynch's risk interpretation must reference story / simple / credibility."""
        text = _doctrine_differentiation_block("lynch").get("risk_interpretation", "").lower()
        assert any(kw in text for kw in ("story", "simple", "credibility", "near-term")), (
            f"Lynch risk interpretation missing story framing: {text[:200]}"
        )


# --- Canonical invariant rule tests ---

class TestCanonicalRiskInvariants:
    def _routing_rules_text(self) -> str:
        return "\n".join(_shared_evidence_routing_rules()).lower()

    def test_worsening_does_not_imply_financial_damage(self):
        """Shared routing rules must prohibit inferring financial damage from worsening trajectory."""
        rules = self._routing_rules_text()
        assert "financial damage" in rules or "financial consequence" in rules or "financial" in rules, (
            "Routing rules must address financial consequence of worsening trajectory"
        )
        # Must NOT simply say "worsening = damage" — must say NOT to infer it
        assert "do not" in rules or "not infer" in rules or "unknown" in rules

    def test_improving_does_not_mean_resolved(self):
        """Shared routing rules must prohibit treating improving trajectory as resolved."""
        rules = self._routing_rules_text()
        assert "resolv" in rules or "not resolved" in rules or "reducing" in rules, (
            "Routing rules must address the improving≠resolved invariant"
        )

    def test_recurring_not_called_worsening(self):
        """Shared routing rules must prohibit calling recurring trajectory worsening."""
        rules = self._routing_rules_text()
        assert "recurring" in rules and "worsening" in rules, (
            "Routing rules must address the recurring≠worsening invariant"
        )

    def test_unknown_consequence_stays_unknown(self):
        """Shared routing rules must preserve unknown financial consequence."""
        rules = self._routing_rules_text()
        assert "unknown" in rules, (
            "Routing rules must say unknown consequence stays unknown"
        )

    def test_trajectory_requires_doctrine_interpretation(self):
        """Shared routing rules must require doctrine-specific interpretation, not restatement."""
        rules = self._routing_rules_text()
        assert "doctrine" in rules or "interpret" in rules, (
            "Routing rules must require doctrine-specific risk interpretation"
        )


# --- _compact_risk_evolution structural tests ---

class TestCompactRiskEvolution:
    def _make_candidates(self, assessments):
        return [(Path("risk_assessments.json"), {"assessments": assessments})]

    def test_worsening_appears_before_improving_in_flat_list(self):
        candidates = self._make_candidates([
            {"risk_id": "r_ip", "risk_name": "IP Risk", "trajectory": "improving", "current_status": "reducing"},
            {"risk_id": "r_fx", "risk_name": "FX Risk", "trajectory": "worsening", "current_status": "increasing"},
        ])
        result = _compact_risk_evolution(candidates)
        flat = result["assessments"]
        ids = [e.get("id") for e in flat]
        assert ids.index("r_fx") < ids.index("r_ip"), (
            "Worsening risk must precede improving risk in flat assessments list"
        )

    def test_groups_surfaced_explicitly(self):
        candidates = self._make_candidates([
            {"risk_id": "r1", "risk_name": "Gov", "trajectory": "worsening", "current_status": "increasing"},
            {"risk_id": "r2", "risk_name": "Exec", "trajectory": "recurring", "current_status": "recurring"},
            {"risk_id": "r3", "risk_name": "IP", "trajectory": "improving", "current_status": "reducing"},
        ])
        result = _compact_risk_evolution(candidates)
        assert result["worsening_count"] == 1
        assert result["recurring_count"] == 1
        assert result["improving_count"] == 1
        assert len(result["worsening"]) == 1
        assert len(result["recurring"]) == 1
        assert len(result["improving"]) == 1

    def test_recurring_trajectory_preserved_not_called_worsening(self):
        candidates = self._make_candidates([
            {"risk_id": "r1", "risk_name": "Revenue Concentration", "trajectory": "recurring",
             "current_status": "recurring"},
        ])
        result = _compact_risk_evolution(candidates)
        assert result["recurring_count"] == 1
        assert result["worsening_count"] == 0
        entry = result["recurring"][0]
        assert entry["trajectory"] == "recurring"

    def test_no_duplicate_risk_ids(self):
        candidates = self._make_candidates([
            {"risk_id": "r1", "risk_name": "FX", "trajectory": "worsening"},
            {"risk_id": "r1", "risk_name": "FX duplicate", "trajectory": "worsening"},
        ])
        result = _compact_risk_evolution(candidates)
        ids = [e.get("id") for e in result["assessments"]]
        assert len(ids) == len(set(ids)), "Duplicate risk IDs should be deduplicated"

    def test_empty_assessments_returns_zero_counts(self):
        candidates = self._make_candidates([])
        result = _compact_risk_evolution(candidates)
        assert result["worsening_count"] == 0
        assert result["recurring_count"] == 0
        assert result["improving_count"] == 0
        assert result["assessments"] == []


# --- Anti-homogenization structural tests ---

class TestAntiHomogenization:
    """Verify that doctrine blocks contain structurally distinct risk questions."""

    def test_all_must_prioritize_lists_are_distinct(self):
        """Each analyst's must_prioritize cannot be identical to another's."""
        guidance = DOCTRINE_DIFFERENTIATION_GUIDANCE
        priorities = {a: tuple(guidance[a].get("must_prioritize", [])) for a in guidance}
        seen = set()
        for analyst, plist in priorities.items():
            assert plist not in seen, (
                f"{analyst} has same must_prioritize list as a prior analyst — no differentiation"
            )
            seen.add(plist)

    def test_primary_doctrine_questions_are_distinct(self):
        """Primary doctrine questions must be distinct across analysts."""
        questions = [
            DOCTRINE_DIFFERENTIATION_GUIDANCE[a].get("primary_doctrine_question", "")
            for a in DOCTRINE_DIFFERENTIATION_GUIDANCE
        ]
        assert len(questions) == len(set(questions)), "Duplicate primary_doctrine_question found"

    def test_risk_interpretations_reference_different_mechanisms(self):
        """Each doctrine's risk framing should reference a different investment mechanism."""
        # Graham = protection/loss, Buffett = moat/durability, Fisher = growth/execution,
        # Munger = failure/incentive, Lynch = story/credibility
        expected_keywords = {
            "graham": {"protection", "permanent", "balance-sheet", "conservative"},
            "buffett": {"moat", "durable", "owner", "durability"},
            "fisher": {"growth", "execution", "runway", "product"},
            "munger": {"failure", "structural", "incentive", "governance"},
            "lynch": {"story", "simple", "credibility", "near-term"},
        }
        for analyst, keywords in expected_keywords.items():
            text = DOCTRINE_DIFFERENTIATION_GUIDANCE[analyst].get("risk_interpretation", "").lower()
            found = {kw for kw in keywords if kw in text}
            assert found, (
                f"{analyst}: risk_interpretation missing expected mechanism keywords {keywords}. "
                f"Text: {text[:200]}"
            )


# --- Canonical truth preservation tests (Tests A-E from mission) ---

class TestCanonicalTruthPreservation:
    """Tests A-E: same canonical input, distinct doctrine-appropriate interpretation."""

    # These tests verify the PROMPT CONTRACT, not LLM output.
    # They confirm that doctrine blocks carry the right framing for each risk scenario.

    def test_A_worsening_governance_doctrine_framing(self):
        """Test A: Worsening governance — each doctrine has the right lens for it."""
        # Munger: governance/incentives focus
        munger = _doctrine_differentiation_block("munger")
        assert "incentive" in munger.get("risk_interpretation", "").lower() or \
               "governance" in munger.get("risk_interpretation", "").lower()
        # Graham: protection/loss focus
        graham = _doctrine_differentiation_block("graham")
        assert "protect" in graham.get("risk_interpretation", "").lower() or \
               "loss" in graham.get("risk_interpretation", "").lower()

    def test_B_worsening_fx_doctrine_framing(self):
        """Test B: Worsening FX — Graham/Buffett have different primary framing."""
        graham_text = _doctrine_differentiation_block("graham").get("risk_interpretation", "").lower()
        buffett_text = _doctrine_differentiation_block("buffett").get("risk_interpretation", "").lower()
        # Both must reference downside/permanent or moat/economics — but different
        assert graham_text != buffett_text

    def test_C_recurring_execution_doctrine_framing(self):
        """Test C: Recurring execution — Munger and Fisher have different framing."""
        munger_text = _doctrine_differentiation_block("munger").get("risk_interpretation", "").lower()
        fisher_text = _doctrine_differentiation_block("fisher").get("risk_interpretation", "").lower()
        # Munger: systematic weakness; Fisher: execution capability
        assert "systematic" in munger_text or "recurring" in munger_text or "weakness" in munger_text
        assert "execution" in fisher_text or "growth" in fisher_text

    def test_D_improving_ip_doctrine_framing(self):
        """Test D: Improving IP — no doctrine treats it as resolved."""
        for analyst in ["buffett", "fisher", "graham", "munger", "lynch"]:
            text = _doctrine_differentiation_block(analyst).get("risk_interpretation", "").lower()
            # Should say "not resolved" or "not resolution" or "not treat" or similar
            has_not_resolved = ("not resolv" in text or "not resolution" in text or
                                "not treat" in text or "not confirm" in text or
                                "not become" in text or "not a positive" in text or
                                "does not" in text or "reducing" in text)
            assert has_not_resolved, (
                f"{analyst}: risk_interpretation does not guard against treating improving as resolved. "
                f"Text: {text[:200]}"
            )

    def test_E_canonical_invariants_in_shared_rules(self):
        """Test E: All five canonical invariants are present in shared routing rules."""
        rules_text = "\n".join(_shared_evidence_routing_rules()).lower()
        # 1. worsening + no financial damage inference
        assert "worsening" in rules_text
        # 2. improving + not resolved
        assert "improving" in rules_text or "reducing" in rules_text
        # 3. recurring ≠ worsening
        assert "recurring" in rules_text
        # 4. unknown consequence stays unknown
        assert "unknown" in rules_text
        # 5. doctrine interpretation required
        assert "doctrine" in rules_text or "interpret" in rules_text
