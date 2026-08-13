"""Risk mitigation tracking."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .contracts import RiskMitigation


def extract_mitigations(
    risk_data: Dict[str, Any],
    events: List[Dict[str, Any]],
) -> List[RiskMitigation]:
    """
    Extract mitigation actions from risk data and progression events.
    
    Returns a list of RiskMitigation objects.
    """
    mitigations: List[RiskMitigation] = []
    seen_actions = set()
    
    # Extract from explicit mitigation events
    for event in events:
        if "mitigation" not in event.get("event_type", ""):
            continue
        
        action = event.get("title", "")
        if not action or action in seen_actions:
            continue
        
        seen_actions.add(action)
        
        mitigation = RiskMitigation(
            mitigation_action=action,
            announcement_period=event.get("period", ""),
            execution_evidence=event.get("description"),
            latest_status=_infer_mitigation_status(event.get("event_type")),
            confidence={
                "level": event.get("confidence", {}).get("level", "low")
                if isinstance(event.get("confidence"), dict)
                else "low",
            },
            source_references=[
                {
                    "event_id": event.get("event_id"),
                    "period": event.get("period"),
                }
            ],
        )
        
        mitigations.append(mitigation)
    
    return mitigations


def assess_mitigation_effectiveness(
    risk_status: str,
    mitigations: List[RiskMitigation],
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Assess how effective the mitigations have been.
    
    Returns a dict with effectiveness assessment, evidence, and confidence.
    """
    if not mitigations:
        return {
            "assessment": "no mitigations announced",
            "effectiveness": "unable_to_verify",
            "evidence": [],
            "confidence": {"level": "low"},
        }
    
    # Check mitigation status
    effective_count = sum(
        1 for m in mitigations
        if m.latest_status in ["effective", "partially_effective"]
    )
    
    ineffective_count = sum(
        1 for m in mitigations
        if m.latest_status in ["ineffective", "announced"]
    )
    
    # Count evidence events
    mitigation_evidence_events = [
        e for e in events
        if e.get("event_type") == "mitigation_evidence"
    ]
    
    # Assess effectiveness based on evidence and status
    if effective_count > 0 and mitigation_evidence_events:
        effectiveness = "partially_effective"
        assessment = f"{effective_count} mitigations show observable evidence of effect"
    elif ineffective_count >= effective_count and len(mitigations) > 0:
        effectiveness = "in_progress"
        assessment = f"{len(mitigations)} mitigations announced but effectiveness not yet clear"
    elif risk_status in ["resolving", "reduced", "resolved"]:
        effectiveness = "effective"
        assessment = "Risk trajectory shows improvement following mitigation"
    else:
        effectiveness = "unable_to_verify"
        assessment = "Insufficient evidence to assess mitigation effectiveness"
    
    return {
        "assessment": assessment,
        "effectiveness": effectiveness,
        "mitigation_count": len(mitigations),
        "with_evidence": len(mitigation_evidence_events),
        "confidence": {
            "level": "medium" if mitigation_evidence_events else "low",
            "basis": [
                "observable effect tracking" if mitigation_evidence_events else "announcement only"
            ],
        },
    }


def _infer_mitigation_status(event_type: str) -> str:
    """Infer mitigation status from event type."""
    status_map = {
        "mitigation_announced": "announced",
        "mitigation_started": "in_progress",
        "mitigation_evidence": "partially_effective",
    }
    
    return status_map.get(event_type, "announced")


def build_mitigation_summary(
    mitigations: List[RiskMitigation],
) -> str:
    """
    Build a concise narrative summary of mitigation efforts.
    """
    if not mitigations:
        return "No mitigations announced."
    
    if len(mitigations) == 1:
        m = mitigations[0]
        return f"Mitigation announced in {m.announcement_period}: {m.mitigation_action}. Status: {m.latest_status}."
    
    # Multiple mitigations
    announced = [m for m in mitigations if m.latest_status == "announced"]
    in_progress = [m for m in mitigations if m.latest_status == "in_progress"]
    effective = [m for m in mitigations if m.latest_status in ["partially_effective", "effective"]]
    
    summary_parts = []
    
    if announced:
        summary_parts.append(f"{len(announced)} announced mitigation(s)")
    
    if in_progress:
        summary_parts.append(f"{len(in_progress)} in progress")
    
    if effective:
        summary_parts.append(f"{len(effective)} showing observable effect")
    
    return "Multiple mitigation efforts: " + ", ".join(summary_parts) + "."


def identify_unproven_mitigations(
    mitigations: List[RiskMitigation],
) -> List[Dict[str, Any]]:
    """
    Identify mitigations that have been announced but lack observable evidence.
    
    This is important for tracking management reassurance vs. demonstrated mitigation.
    """
    unproven = []
    
    for mitigation in mitigations:
        if mitigation.latest_status in ["announced", "in_progress"]:
            unproven.append({
                "mitigation_action": mitigation.mitigation_action,
                "announcement_period": mitigation.announcement_period,
                "status": mitigation.latest_status,
                "evidence_type": "none" if not mitigation.execution_evidence else "partial",
                "reason": "Announced but not yet demonstrated" if mitigation.latest_status == "announced"
                else "In progress, effect not yet observable",
            })
    
    return unproven
