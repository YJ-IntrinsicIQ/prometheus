"""Risk Evolution validation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def validate_risk_payload(
    registry: Dict[str, Any],
    timelines: Dict[str, Any],
    assessments: Dict[str, Any],
    upstream_material_evidence_count: int = 0,
) -> Dict[str, Any]:
    """
    Comprehensive validation of risk evolution artifacts.
    
    Returns a validation report with issues organized by category.
    """
    issues: List[Dict[str, Any]] = []
    
    # Extract data
    risks = registry.get("risks", [])
    risk_timelines = timelines.get("timelines", [])
    risk_assessments = assessments.get("assessments", [])

    if upstream_material_evidence_count > 0 and not risks:
        issues.append({
            "rule": "material_evidence_zero_output",
            "severity": "error",
            "message": f"{upstream_material_evidence_count} material upstream risk candidates produced an empty registry",
        })
    
    # 1. Unique risk IDs
    risk_ids = [r.get("risk_id") for r in risks]
    duplicates = [rid for rid in set(risk_ids) if risk_ids.count(rid) > 1]
    for dup_id in duplicates:
        issues.append({
            "rule": "unique_risk_ids",
            "severity": "error",
            "message": f"Duplicate risk ID: {dup_id}",
        })
    
    # 2. Non-empty risk names
    for risk in risks:
        if not risk.get("risk_name", "").strip():
            issues.append({
                "rule": "non_empty_risk_name",
                "severity": "error",
                "risk_id": risk.get("risk_id"),
                "message": "Risk name is empty",
            })
    
    # 3. Valid risk categories
    from .contracts import RISK_CATEGORIES, RISK_STATUSES, RISK_MATERIALITY_LEVELS
    
    for risk in risks:
        category = risk.get("risk_category")
        if category and category not in RISK_CATEGORIES:
            issues.append({
                "rule": "valid_risk_category",
                "severity": "warning",
                "risk_id": risk.get("risk_id"),
                "message": f"Unknown risk category: {category}",
            })
    
    # 4. Valid risk statuses
    for risk in risks:
        status = risk.get("current_status")
        if status and status not in RISK_STATUSES:
            issues.append({
                "rule": "valid_risk_status",
                "severity": "error",
                "risk_id": risk.get("risk_id"),
                "message": f"Invalid risk status: {status}",
            })
    
    # 5. Chronological order of events
    for timeline in risk_timelines:
        events = timeline.get("events", [])
        for i in range(len(events) - 1):
            current = events[i]
            next_ev = events[i + 1]
            
            current_period = current.get("period", "")
            next_period = next_ev.get("period", "")
            
            if current_period > next_period:
                issues.append({
                    "rule": "chronological_events",
                    "severity": "error",
                    "risk_id": timeline.get("risk_id"),
                    "message": f"Events not in chronological order: {current_period} > {next_period}",
                })
    
    # 6. First observed <= latest period
    for risk in risks:
        first = risk.get("first_observed_period", "")
        latest = risk.get("latest_period", "")
        
        if first and latest and first > latest:
            issues.append({
                "rule": "period_ordering",
                "severity": "error",
                "risk_id": risk.get("risk_id"),
                "message": f"First observed ({first}) is after latest ({latest})",
            })
    
    # 7. Resolved status requires evidence
    for risk in risks:
        status = risk.get("current_status")
        if status == "resolved":
            if not risk.get("counter_evidence") and not risk.get("mitigation_evidence"):
                issues.append({
                    "rule": "resolved_requires_evidence",
                    "severity": "error",
                    "risk_id": risk.get("risk_id"),
                    "message": "Resolved risk requires evidence of resolution",
                })
    
    # 8. Mitigated status requires observable evidence
    for risk in risks:
        status = risk.get("current_status")
        if status == "mitigated":
            mitigations = risk.get("mitigations", [])
            has_effective = any(m.get("latest_status") == "effective" for m in mitigations)
            
            if not has_effective and not risk.get("mitigation_evidence"):
                issues.append({
                    "rule": "mitigated_requires_evidence",
                    "severity": "warning",
                    "risk_id": risk.get("risk_id"),
                    "message": "Mitigated status lacks observable mitigation evidence",
                })
    
    # 9. Persistent requires multi-period evidence
    for risk in risks:
        status = risk.get("current_status")
        if status == "persistent":
            events = next(
                (t.get("events", []) for t in risk_timelines if (t.get("risk_id") or t.get("subject_id")) == risk.get("risk_id")),
                []
            )
            
            periods = set(e.get("period") for e in events if e.get("period"))
            if len(periods) < 2:
                issues.append({
                    "rule": "persistent_multi_period",
                    "severity": "warning",
                    "risk_id": risk.get("risk_id"),
                    "message": "Persistent status claimed but only single-period evidence available",
                })
    
    # 10. Absence of mention ≠ resolved
    for risk in risks:
        status = risk.get("current_status")
        if status == "resolved":
            # Check if latest event is explicit resolution
            timeline = next(
                (t for t in risk_timelines if t.get("risk_id") == risk.get("risk_id")),
                {}
            )
            events = timeline.get("events", [])
            
            if events:
                latest_type = events[-1].get("event_type", "")
                if latest_type not in ["risk_resolved", "counter_evidence"]:
                    issues.append({
                        "rule": "explicit_resolution_required",
                        "severity": "warning",
                        "risk_id": risk.get("risk_id"),
                        "message": "Resolved status should be supported by explicit resolution evidence",
                    })
    
    # 11. Management reassurance ≠ mitigation
    for risk in risks:
        mitigations = risk.get("mitigations", [])
        for mitigation in mitigations:
            action = mitigation.get("mitigation_action", "").lower()
            if any(word in action for word in ["believe", "confident", "assure", "reassure", "management said"]):
                issues.append({
                    "rule": "no_reassurance_as_mitigation",
                    "severity": "warning",
                    "risk_id": risk.get("risk_id"),
                    "message": "Management reassurance should not be treated as mitigation evidence",
                })
    
    # 12. Materiality contains basis and limitations
    for risk in risks:
        materiality = risk.get("materiality")
        if materiality:
            if not materiality.get("basis"):
                issues.append({
                    "rule": "materiality_basis",
                    "severity": "warning",
                    "risk_id": risk.get("risk_id"),
                    "message": "Materiality assessment lacks basis",
                })
            
            if materiality.get("level") and not materiality.get("limitations"):
                if materiality.get("level") != "low":
                    issues.append({
                        "rule": "materiality_limitations",
                        "severity": "warning",
                        "risk_id": risk.get("risk_id"),
                        "message": f"Materiality level '{materiality.get('level')}' lacks documented limitations",
                    })
    
    # 13. Conviction impact uses investor-conviction meaning
    for assessment in risk_assessments:
        impact = assessment.get("conviction_impact")
        if impact:
            valid_impacts = {"strengthened", "weakened", "unchanged", "unclear"}
            if impact not in valid_impacts:
                issues.append({
                    "rule": "conviction_impact_semantics",
                    "severity": "error",
                    "risk_id": assessment.get("risk_id"),
                    "message": f"Invalid conviction impact: {impact} (should be investor conviction change)",
                })
    
    # 14. Linked IDs validation
    for risk in risks:
        for commit_id in risk.get("related_commitment_ids", []):
            if not commit_id.strip():
                issues.append({
                    "rule": "valid_commitment_links",
                    "severity": "warning",
                    "risk_id": risk.get("risk_id"),
                    "message": "Empty commitment ID in links",
                })
        
        for project_id in risk.get("related_project_ids", []):
            if not project_id.strip():
                issues.append({
                    "rule": "valid_project_links",
                    "severity": "warning",
                    "risk_id": risk.get("risk_id"),
                    "message": "Empty project ID in links",
                })
    
    # 15. Source references preserved
    for risk in risks:
        if not risk.get("source_references"):
            issues.append({
                "rule": "source_references",
                "severity": "warning",
                "risk_id": risk.get("risk_id"),
                "message": "No source references tracked",
            })
    
    # 16. Trigger conditions present for material risks
    for risk in risks:
        materiality = risk.get("materiality", {})
        if materiality.get("level") == "high":
            if not risk.get("trigger_conditions"):
                issues.append({
                    "rule": "trigger_conditions",
                    "severity": "warning",
                    "risk_id": risk.get("risk_id"),
                    "message": "High-materiality risk lacks trigger conditions",
                })
    
    # 17. Disconfirming evidence present for material risks
    for risk in risks:
        materiality = risk.get("materiality", {})
        if materiality.get("level") == "high":
            if not risk.get("disconfirming_evidence"):
                issues.append({
                    "rule": "disconfirming_evidence",
                    "severity": "warning",
                    "risk_id": risk.get("risk_id"),
                    "message": "High-materiality risk lacks disconfirming evidence criteria",
                })
    
    # 18. Confidence contains basis and limitations
    for risk in risks:
        confidence = risk.get("confidence", {})
        if confidence:
            if not confidence.get("basis"):
                issues.append({
                    "rule": "confidence_basis",
                    "severity": "warning",
                    "risk_id": risk.get("risk_id"),
                    "message": "Confidence lacks basis",
                })
    
    # 19. Investor implication doesn't overstate certainty
    for risk in risks:
        implication = risk.get("investor_implication", "").lower()
        if any(word in implication for word in ["certainly", "definitely", "must", "will definitely"]):
            issues.append({
                "rule": "investor_implication_caution",
                "severity": "warning",
                "risk_id": risk.get("risk_id"),
                "message": "Investor implication overstates certainty",
            })
    
    # 20. No generic risk-factor boilerplate
    for risk in risks:
        name = risk.get("risk_name", "").lower()
        if any(phrase in name for phrase in ["the industry is competitive", "growth could slow", "may be uncertainty"]):
            issues.append({
                "rule": "no_boilerplate",
                "severity": "warning",
                "risk_id": risk.get("risk_id"),
                "message": "Risk name contains generic boilerplate language",
            })
    
    # 21. Serialization is deterministic
    # This is checked during write
    
    # 22. No internal pipeline terminology leaks
    for risk in risks:
        fields_to_check = [
            "risk_name", "risk_mechanism", "progression_summary",
            "what_changed", "why_it_changed", "investor_implication"
        ]
        
        for field in fields_to_check:
            text = risk.get(field, "").lower()
            internal_terms = ["company_memory", "progression_engine", "source_chunk", "artifact"]
            
            if any(term in text for term in internal_terms):
                issues.append({
                    "rule": "no_internal_terminology",
                    "severity": "error",
                    "risk_id": risk.get("risk_id"),
                    "field": field,
                    "message": f"Internal pipeline terminology in {field}",
                })
    
    # 23. Unresolved questions remain visible
    for risk in risks:
        if risk.get("current_status") in ["unable_to_verify", "contradictory"]:
            if not risk.get("unresolved_questions"):
                issues.append({
                    "rule": "unresolved_questions_visible",
                    "severity": "warning",
                    "risk_id": risk.get("risk_id"),
                    "message": "Risk with uncertain status should document unresolved questions",
                })
    
    # 24. Duplicate risks handled conservatively
    # This is checked during deduplication
    
    # 25. Rising conviction requires improvement evidence
    for assessment in risk_assessments:
        conviction = assessment.get("conviction_impact")
        if conviction == "strengthened":
            risk_id = assessment.get("risk_id")
            risk = next((r for r in risks if r.get("risk_id") == risk_id), {})
            status = risk.get("current_status")
            
            if status not in ["reducing", "mitigated", "resolved"]:
                issues.append({
                    "rule": "strengthened_requires_improvement",
                    "severity": "error",
                    "risk_id": risk_id,
                    "message": "Conviction strengthened requires improving risk status",
                })
    
    # Build summary
    error_count = sum(1 for i in issues if i.get("severity") == "error")
    warning_count = sum(1 for i in issues if i.get("severity") == "warning")
    
    status = "pass" if error_count == 0 else "fail"
    if warning_count > 0 and error_count == 0:
        status = "warning"
    
    return {
        "status": status,
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issues,
        "rules_checked": 25,
    }
