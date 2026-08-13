"""Risk materiality assessment."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .contracts import RiskMateriality


def assess_materiality(
    risk_id: str,
    risk_name: str,
    description: str,
    category: str,
    affected_area: Optional[str],
    persistence_count: int,
    evidence_quality: str,
    financial_impact: Optional[float] = None,
    is_concentration_risk: bool = False,
) -> RiskMateriality:
    """
    Assess the materiality of a risk using a transparent model.
    
    Returns a RiskMateriality object with level, affected_dimensions, basis, and limitations.
    """
    
    # Initialize scoring
    materiality_score = 0
    affected_dimensions: List[str] = []
    basis: List[str] = []
    limitations: List[str] = []
    
    # Dimension 1: Persistence
    if persistence_count >= 3:
        materiality_score += 3
        basis.append("persistent across three or more periods")
        affected_dimensions.append("persistence")
    elif persistence_count >= 2:
        materiality_score += 2
        basis.append("mentioned in multiple periods")
        affected_dimensions.append("persistence")
    elif persistence_count == 1:
        materiality_score += 1
        basis.append("single-period observation")
        affected_dimensions.append("persistence")
        limitations.append("limited evidence of persistence")
    else:
        limitations.append("cannot assess persistence")
    
    # Dimension 2: Evidence quality
    evidence_weights = {
        "direct": 3,
        "derived": 2,
        "partial": 1,
        "conflicting": 0,
        "missing": -1,
    }
    
    evidence_score = evidence_weights.get(evidence_quality, 0)
    materiality_score += evidence_score
    
    if evidence_quality == "direct":
        basis.append("audited or explicit operational evidence")
        affected_dimensions.append("evidence quality")
    elif evidence_quality == "derived":
        basis.append("derived from structured company memory")
        affected_dimensions.append("evidence quality")
    else:
        limitations.append(f"evidence quality is {evidence_quality}")
    
    # Dimension 3: Risk mechanism clarity
    mechanism_score = _assess_mechanism_clarity(description)
    materiality_score += mechanism_score
    
    if mechanism_score > 0:
        basis.append("clear risk mechanism identified")
        affected_dimensions.append("mechanism clarity")
    else:
        limitations.append("risk mechanism is unclear")
    
    # Dimension 4: Affected business area
    area_materiality = _assess_area_materiality(affected_area)
    materiality_score += area_materiality
    
    if area_materiality > 0:
        affected_dimensions.append(affected_area or "operations")
        basis.append(f"affects {affected_area or 'core operations'}")
    
    # Dimension 5: Concentration risk
    if is_concentration_risk:
        materiality_score += 3
        basis.append("concentration risk identified")
        affected_dimensions.append("customer or supplier concentration")
    
    # Dimension 6: Financial impact
    if financial_impact is not None:
        if financial_impact > 100:  # Crores
            materiality_score += 3
            basis.append(f"quantified impact >{financial_impact} Cr")
            affected_dimensions.append("cash generation")
        elif financial_impact > 20:
            materiality_score += 2
            basis.append(f"quantified impact >{financial_impact} Cr")
            affected_dimensions.append("cash generation")
        else:
            materiality_score += 1
            basis.append(f"quantified impact ~{financial_impact} Cr")
    
    # Category-specific adjustments
    category_multipliers = {
        "financial": 1.5,
        "working_capital": 1.4,
        "customer": 1.3,
        "regulatory": 1.2,
        "execution": 1.1,
    }
    
    multiplier = category_multipliers.get(category, 1.0)
    materiality_score *= multiplier
    
    # Determine level
    if materiality_score >= 8:
        level = "high"
    elif materiality_score >= 4:
        level = "medium"
    elif materiality_score >= 1:
        level = "low"
    else:
        level = "unclear"
    
    # Add base limitations
    if not basis:
        limitations.append("insufficient evidence for materiality assessment")
        level = "unclear"
    
    return RiskMateriality(
        level=level,
        affected_dimensions=list(set(affected_dimensions)),  # Deduplicate
        basis=basis,
        limitations=limitations,
    )


def _assess_mechanism_clarity(description: str) -> int:
    """Score how clear the risk mechanism is (0-2)."""
    if not description:
        return 0
    
    text = description.lower()
    
    # Look for causal language
    clarity_indicators = [
        "because",
        "results in",
        "leads to",
        "causes",
        "exposes",
        "if",
        "would",
        "could",
        "risk that",
    ]
    
    found = sum(1 for indicator in clarity_indicators if indicator in text)
    
    if found >= 2:
        return 2
    elif found >= 1:
        return 1
    else:
        return 0


def _assess_area_materiality(affected_area: Optional[str]) -> int:
    """Score how material the affected area is (0-2)."""
    if not affected_area:
        return 0
    
    area_lower = affected_area.lower()
    
    # Critical areas
    critical = ["cash generation", "revenue", "profit", "financial position"]
    if any(c in area_lower for c in critical):
        return 2
    
    # Important areas
    important = ["operations", "execution", "competitive", "capacity", "compliance"]
    if any(i in area_lower for i in important):
        return 1
    
    return 0


def apply_materiality_override(
    materiality: RiskMateriality,
    override_reason: Optional[str],
) -> RiskMateriality:
    """
    Apply a manual override to materiality assessment.
    
    Used when evidence clearly indicates a different level than the automated score suggests.
    """
    if not override_reason:
        return materiality
    
    if "high" in override_reason.lower():
        materiality.level = "high"
        materiality.basis.append(f"Manual override: {override_reason}")
    elif "low" in override_reason.lower():
        materiality.level = "low"
        materiality.basis.append(f"Manual override: {override_reason}")
    elif "medium" in override_reason.lower():
        materiality.level = "medium"
        materiality.basis.append(f"Manual override: {override_reason}")
    
    return materiality
