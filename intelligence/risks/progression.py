"""Risk progression tracking using the Progression Engine."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from intelligence.progression.timeline import build_progression_timeline

from .contracts import RiskProgressionAdapter


def build_risk_event(
    risk_id: str,
    period: str,
    event_type: str,
    title: str,
    description: str,
    confidence: Dict[str, Any],
    source_references: List[Dict[str, Any]],
    sequence: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a progression event for a risk."""
    return {
        "event_id": f"{risk_id}_{event_type}_{period}_{sequence}",
        "stream_type": "risk",
        "subject_id": risk_id,
        "period": period,
        "sequence": sequence,
        "event_type": event_type,
        "title": title,
        "description": description,
        "evidence_status": "direct",
        "confidence": confidence,
        "source_references": source_references,
        "metadata": metadata or {},
    }


def build_timeline(
    risk_id: str,
    risk_name: str,
    events: List[Dict[str, Any]],
    current_state: str,
    unresolved: List[str],
    investor_implication: str,
    confidence: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a progression timeline for a risk."""
    adapter = RiskProgressionAdapter()
    
    # Use the shared progression engine
    timeline = build_progression_timeline(
        subject_id=risk_id,
        stream_type="risk",
        events=events,
        adapter=adapter,
        unresolved_questions=unresolved,
        coverage_status="supported" if events else "unavailable",
    )
    
    # Enhance timeline with risk-specific fields
    timeline["risk_name"] = risk_name
    timeline["investor_implication"] = {
        "summary": investor_implication,
        "conviction_impact": "unclear",
    }
    
    return timeline


def derive_progression_status(
    events: List[Dict[str, Any]],
) -> str:
    """Derive the current risk status from an ordered sequence of events."""
    if not events:
        return "unable_to_verify"
    
    adapter = RiskProgressionAdapter()
    return adapter.derive_current_status(events)


def assess_risk_trajectory(
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Assess the trajectory of a risk over time.
    
    Returns a dict with:
    - direction: improving, worsening, stable, unclear
    - momentum: accelerating, decelerating, steady
    - trend_description: narrative description
    """
    if len(events) < 2:
        return {
            "direction": "unclear",
            "momentum": "unknown",
            "trend_description": "Insufficient evidence to assess trajectory.",
        }
    
    # Analyze event types over time
    recent_events = events[-5:]  # Last 5 events
    
    # Count event types
    intensifying = sum(1 for e in recent_events if e.get("event_type") in ["risk_intensified", "risk_confirmed"])
    reducing = sum(1 for e in recent_events if e.get("event_type") in ["risk_reduced", "mitigation_evidence"])
    mitigating = sum(1 for e in recent_events if e.get("event_type") in ["mitigation_started", "mitigation_evidence"])
    
    # Determine direction
    if intensifying > reducing:
        direction = "worsening"
    elif reducing > intensifying:
        direction = "improving"
    else:
        direction = "stable"
    
    # Determine momentum
    if len(recent_events) >= 3:
        older = events[-5:-3]
        newer = events[-2:]
        
        older_intensity = sum(
            1 for e in older
            if e.get("event_type") in ["risk_intensified", "risk_confirmed", "risk_persisted"]
        )
        newer_intensity = sum(
            1 for e in newer
            if e.get("event_type") in ["risk_intensified", "risk_confirmed", "risk_persisted"]
        )
        
        if newer_intensity > older_intensity:
            momentum = "accelerating"
        elif newer_intensity < older_intensity:
            momentum = "decelerating"
        else:
            momentum = "steady"
    else:
        momentum = "unclear"
    
    # Build description
    descriptions = {
        ("worsening", "accelerating"): "Risk is intensifying and showing signs of acceleration.",
        ("worsening", "steady"): "Risk is worsening at a steady pace.",
        ("worsening", "decelerating"): "Risk is worsening but showing signs of stabilization.",
        ("improving", "accelerating"): "Risk is improving and evidence of mitigation is building.",
        ("improving", "steady"): "Risk is gradually improving.",
        ("improving", "decelerating"): "Risk improvement is slowing.",
        ("stable", "steady"): "Risk remains stable with limited new evidence.",
        ("stable", "accelerating"): "Previously stable risk is beginning to intensify.",
        ("stable", "decelerating"): "Risk that was worsening appears to be stabilizing.",
    }
    
    trend_description = descriptions.get(
        (direction, momentum),
        "Risk trajectory is unclear from available evidence.",
    )
    
    return {
        "direction": direction,
        "momentum": momentum,
        "trend_description": trend_description,
        "recent_event_count": len(recent_events),
        "intensifying_signals": intensifying,
        "reducing_signals": reducing,
    }
