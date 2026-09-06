"""Risk Evolution Intelligence builder."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from knowledge.company_memory import parse_financial_year

from .classifier import classify_risk_category, is_generic_boilerplate, sanitize_public_text, extract_affected_area
from .contracts import (
    RiskAssessment,
    RiskConfidence,
    RiskDefinition,
    RiskMateriality,
    RiskProgressionAdapter,
    RISK_CATEGORIES,
    RISK_STATUSES,
)
from .manifest import build_risk_manifest
from .materiality import assess_materiality
from .mitigation import extract_mitigations, assess_mitigation_effectiveness, build_mitigation_summary
from .normalizer import normalize_candidate, deduplicate_risks
from .progression import build_risk_event, build_timeline, assess_risk_trajectory, derive_progression_status
from .validators import validate_risk_payload
from .writer import write_all_risk_outputs, print_risk_summary


def _utc_now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Dict[str, Any] | List[Any]:
    """Load JSON file safely."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _discover_years(company_root: Path) -> List[Path]:
    """Discover fiscal year directories."""
    if not company_root.exists():
        return []
    return sorted(
        [path for path in company_root.iterdir() if path.is_dir() and path.name.lower().startswith("fy")],
        key=lambda path: parse_financial_year(path.name),
    )


def _load_year_record(year_dir: Path) -> Dict[str, Any]:
    """Load yearly company memory artifacts."""
    record: Dict[str, Any] = {
        "year": year_dir.name,
        "sort_key": parse_financial_year(year_dir.name),
        "source_artifacts": {},
    }
    
    # Candidate sources for risks
    candidate_sources = [
        ("company_intelligence", Path("intelligence") / "company_intelligence.json"),
        ("management_summary", Path("intelligence") / "management_summary.json"),
        ("financial_audit_report", Path("financials") / "financial_audit_report.json"),
    ]
    
    for source_name, rel_path in candidate_sources:
        path = year_dir / rel_path
        payload = _load_json(path)
        found = bool(payload)
        record["source_artifacts"][source_name] = {"path": str(path), "found": found}
        record[source_name] = payload if isinstance(payload, (dict, list)) else {}
    
    return record


def _extract_risk_candidates(
    year_record: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Extract risk candidates from yearly artifacts."""
    candidates = []
    year = year_record.get("year", "")
    
    # Extract from company_intelligence
    ci = year_record.get("company_intelligence", {})
    if isinstance(ci, dict):
        risks = ci.get("risks", [])
        if isinstance(risks, list):
            for risk in risks:
                if isinstance(risk, dict):
                    candidates.append({
                        **risk,
                        "source_year": year,
                        "source_artifact": "company_intelligence.json",
                    })
    
    # Extract from management_summary
    ms = year_record.get("management_summary", {})
    if isinstance(ms, dict):
        risks = ms.get("risks", [])
        if isinstance(risks, list):
            for risk in risks:
                if isinstance(risk, dict):
                    candidates.append({
                        **risk,
                        "source_year": year,
                        "source_artifact": "management_summary.json",
                    })
    
    # Extract from financial_audit_report warnings
    far = year_record.get("financial_audit_report", {})
    if isinstance(far, dict):
        warnings = far.get("warnings", [])
        if isinstance(warnings, list):
            for warning in warnings:
                if isinstance(warning, dict) and "financial" in warning.get("category", "").lower():
                    candidates.append({
                        "risk_name": warning.get("message", "Financial risk"),
                        "value": warning.get("message", ""),
                        "description": warning.get("description", ""),
                        "category": "financial",
                        "source_year": year,
                        "source_artifact": "financial_audit_report.json",
                        "confidence": {"level": "medium"},
                    })
    
    return candidates


def _extract_company_memory_risk_candidates(company_root: Path) -> List[Dict[str, Any]]:
    """Adapt already-governed multi-year and financial evidence into risk candidates."""
    candidates: List[Dict[str, Any]] = []
    multi_year = _load_json(company_root / "company_memory" / "multi_year" / "risk_evolution.json")
    if isinstance(multi_year, dict):
        # Load trajectory classification sets from the evolution file's top-level lists
        _worsening_ids: set = set(multi_year.get("worsening_risks") or [])
        _improving_ids: set = set(multi_year.get("improving_risks") or [])
        _recurring_ids: set = set(multi_year.get("recurring_risks") or [])

        for risk in multi_year.get("risks") or []:
            if not isinstance(risk, dict):
                continue
            mentions = risk.get("source_mentions") or []
            latest = mentions[-1] if mentions else {}
            description = latest.get("value") or str(risk.get("normalized_risk") or "").replace("_", " ")
            normalized_description = str(description).lower()
            if any(term in normalized_description for term in ("school", "classroom", "teacher", "csr", "community", "ngo", "day care", "apprenticeship", "employee performance review")):
                continue
            material_mechanisms = (
                "customer", "revenue", "order", "working capital", "cash", "liquidity", "margin", "cost",
                "technology", "obsolete", "government contract", "government spending", "capacity utilization",
                "project delay", "deliver", "intellectual property", "competition", "recruit", "retain", "supply",
                "development cycle", "upfront cost", "sector concentration", "product concentration",
            )
            if not risk.get("repeated_years") and not any(term in normalized_description for term in material_mechanisms):
                continue
            raw_name = str(risk.get("normalized_risk") or description).replace("_", " ").title()
            canonical_name = _canonical_risk_name(raw_name, description)
            evo_id = risk.get("risk_id", "")
            # Determine trajectory from evolution classification lists (precedence: worsening > improving > recurring)
            if evo_id in _worsening_ids:
                evo_trajectory: Optional[str] = "worsening"
            elif evo_id in _improving_ids:
                evo_trajectory = "improving"
            elif evo_id in _recurring_ids:
                evo_trajectory = "recurring"
            else:
                evo_trajectory = None
            candidates.append({
                "risk_name": canonical_name,
                "value": description,
                "description": description,
                "category": str(risk.get("normalized_risk") or "other").split("_")[0],
                "source_year": latest.get("source_year") or risk.get("first_seen_year"),
                "source_artifact": "multi_year/risk_evolution.json",
                "source_item_id": evo_id,
                "evidence_ids": list(risk.get("related_evidence_ids") or []),
                "confidence": {"level": "high" if risk.get("repeated_years") else "medium"},
                "current_status": "persistent" if risk.get("repeated_years") else "emerging",
                # Canonical evolution identity and trajectory
                "evo_trajectory": evo_trajectory,
                "evo_canonical_id": evo_id,
                "evo_severity_by_year": risk.get("severity_by_year") or {},
                "evo_latest_severity": risk.get("latest_severity"),
            })

    working_capital = _load_json(company_root / "company_memory" / "financials" / "investor_financial_modules" / "working_capital_quality_drilldown.json")
    if isinstance(working_capital, dict):
        drilldown_items = [item for item in (working_capital.get("drilldown") or []) if isinstance(item, dict)]
        material_period_count = sum(1 for item in drilldown_items if str(item.get("working_capital_intensity_status") or "").lower() in {"severe", "high"})
        for item in drilldown_items:
            if not isinstance(item, dict):
                continue
            severe = str(item.get("working_capital_intensity_status") or "").lower() in {"severe", "high"}
            elevated = str(item.get("cash_strain_risk") or "").lower() in {"elevated", "high", "severe"}
            if not (severe or elevated):
                continue
            year = item.get("fiscal_year")
            description = (
                f"Working-capital intensity is {item.get('working_capital_intensity_status')}; "
                f"receivable days {item.get('receivable_days')}, inventory days {item.get('inventory_days')}, "
                f"and cash-conversion cycle {item.get('cash_conversion_cycle')} days."
            )
            candidates.append({
                "risk_name": "Working-capital and cash-conversion pressure",
                "value": description,
                "description": description,
                "category": "working_capital",
                "source_year": year,
                "source_artifact": "working_capital_quality_drilldown.json",
                "source_item_id": f"working_capital_{year}",
                "confidence": {"level": "high"},
                "current_status": "persistent" if material_period_count >= 2 else "emerging",
            })
    return candidates


def _canonical_risk_name(name: str, description: str = "") -> str:
    """Collapse wording variants into investor-meaningful risk mechanisms."""
    text = f"{name} {description}".lower()
    families = (
        (("working capital", "cash conversion", "receivable days"), "Working-capital and cash-conversion pressure"),
        (("cost inflation", "inflation cost"), "Cost inflation and margin pressure"),
        (("execution challenge", "execution risk", "timing risk"), "Execution and delivery timing risk"),
        (("customer concentration", "revenue concentration"), "Customer and revenue concentration"),
        (("product concentration",), "Product concentration"),
        (("sector concentration",), "Defence-sector concentration"),
        (("technology dependence", "technology disruption", "obsolescence"), "Technology dependence and obsolescence"),
        (("supply chain",), "Supply-chain disruption"),
        (("human capital", "workforce risk", "talent retention"), "Specialist talent capacity and retention"),
        (("intellectual property",), "Intellectual-property protection"),
        (("competition",), "Competitive intensity"),
        (("geopolitical",), "Geopolitical disruption"),
        (("regulatory",), "Regulatory and government-policy exposure"),
    )
    for needles, canonical in families:
        if any(needle in text for needle in needles):
            return canonical
    return name


def _filter_risks(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out generic boilerplate and invalid risks."""
    valid = []
    
    for candidate in candidates:
        risk_name = candidate.get("risk_name") or candidate.get("value", "")
        description = candidate.get("description", risk_name)
        full_text = f"{risk_name} {description} {candidate.get('category', '')}".lower()
        
        # Skip if generic boilerplate
        if is_generic_boilerplate(description):
            continue
        
        # Skip if empty
        if not risk_name.strip():
            continue
        
        # Skip if too generic
        if len(risk_name) < 10:
            continue

        if candidate.get("category") in {"geographic", "competitive", "regulatory"} and not any(
            term in full_text
            for term in (
                "customer",
                "order",
                "project",
                "capacity",
                "working capital",
                "receivable",
                "inventory",
                "payable",
                "delivery",
                "manufacturing",
                "plant",
                "facility",
                "product",
                "cash",
                "margin",
                "company",
                "business",
                "program",
                "programme",
            )
        ):
            continue
        
        valid.append(candidate)
    
    return valid


def _normalize_risks(
    candidates: List[Dict[str, Any]],
    company_slug: str,
) -> List[Dict[str, Any]]:
    """Normalize raw risk candidates."""
    normalized = []
    
    for candidate in candidates:
        try:
            norm = normalize_candidate(candidate, company_slug)
            normalized.append(norm)
        except Exception:
            # Skip candidates that fail normalization
            continue
    
    return normalized


def _enrich_risks(
    risks: List[Dict[str, Any]],
    company_root: Path,
) -> List[Dict[str, Any]]:
    """
    Enrich risks with additional information.
    
    Load related projects, capacity, commitments to enable linking.
    """
    # Load related data (would link to projects, capacity, etc.)
    # For now, just ensure basic enrichment
    
    enriched = []
    for risk in risks:
        enriched_risk = {**risk}
        
        # Add empty collections if not present
        if "related_commitment_ids" not in enriched_risk:
            enriched_risk["related_commitment_ids"] = []
        if "related_project_ids" not in enriched_risk:
            enriched_risk["related_project_ids"] = []
        if "related_capacity_ids" not in enriched_risk:
            enriched_risk["related_capacity_ids"] = []
        if "related_financial_metrics" not in enriched_risk:
            enriched_risk["related_financial_metrics"] = []
        
        enriched.append(enriched_risk)
    
    return enriched


def _build_risk_definitions(
    risks: List[Dict[str, Any]],
) -> List[RiskDefinition]:
    """Build canonical RiskDefinition objects."""
    definitions = []
    
    for risk in risks:
        category = classify_risk_category(f"{risk.get('risk_name', '')} {risk.get('risk_mechanism', '')}")
        affected_area = extract_affected_area(risk.get("risk_mechanism", ""), category)
        source_periods = {str(ref.get("year") or ref.get("period") or "") for ref in risk.get("source_references", []) if str(ref.get("year") or ref.get("period") or "")}
        current_status = risk.get("current_status", "unable_to_verify")
        if current_status == "persistent" and len(source_periods) < 2:
            current_status = "emerging"

        # Apply canonical evolution trajectory to current_status (trajectory takes precedence when available)
        evo_trajectory: Optional[str] = risk.get("evo_trajectory")
        evo_canonical_id: Optional[str] = risk.get("evo_canonical_id")
        if evo_trajectory == "worsening":
            current_status = "increasing"
        elif evo_trajectory == "improving":
            current_status = "reducing"
        elif evo_trajectory == "recurring":
            # recurring is a persistence signal, not a direction; use it only to upgrade from "emerging"
            if current_status in ("emerging", "unable_to_verify"):
                current_status = "recurring"

        risk_name = risk.get("risk_name", "")
        risk_name_lower = risk_name.lower() or "the risk"
        
        # Build materiality assessment
        materiality = assess_materiality(
            risk_id=risk.get("risk_id", ""),
            risk_name=risk.get("risk_name", ""),
            description=risk.get("risk_mechanism", ""),
            category=category,
            affected_area=affected_area,
            persistence_count=1,  # Will be updated when building timelines
            evidence_quality=risk.get("evidence_status", "partial"),
            is_concentration_risk="concentration" in (risk.get("risk_name", "") or "").lower(),
        )
        
        # Build what_changed / why_it_changed using trajectory truth where available.
        # Trajectory from evolution takes precedence over period-count-based fallback.
        if evo_trajectory == "worsening":
            _what_changed = (
                risk.get("what_changed")
                or f"{risk_name} is classified as worsening in the multi-year longitudinal evidence."
            )
            _why_it_changed = (
                risk.get("why_it_changed")
                or f"The multi-year longitudinal evidence classifies {risk_name_lower} as worsening; the risk has intensified across successive periods."
            )
        elif evo_trajectory == "improving":
            _what_changed = (
                risk.get("what_changed")
                or f"{risk_name} shows improvement in the multi-year longitudinal evidence."
            )
            _why_it_changed = (
                risk.get("why_it_changed")
                or f"The multi-year longitudinal evidence indicates improvement in {risk_name_lower}; later periods show reduced severity compared to earlier observations."
            )
        elif evo_trajectory == "recurring":
            _what_changed = (
                risk.get("what_changed")
                or f"{risk_name} has recurred across multiple periods in the multi-year longitudinal evidence."
            )
            _why_it_changed = (
                risk.get("why_it_changed")
                or f"The multi-year longitudinal evidence classifies {risk_name_lower} as recurring; the risk has appeared persistently across successive periods without resolution."
            )
        else:
            # No trajectory data from evolution — fall back to period-count heuristic
            _what_changed = (
                risk.get("what_changed")
                or (
                    f"{risk_name or 'The risk'} remains visible across {len(source_periods)} period(s)."
                    if len(source_periods) >= 2
                    else f"{risk_name or 'The risk'} is identified in the source evidence."
                )
            )
            _why_it_changed = (
                risk.get("why_it_changed")
                or (
                    "Later evidence keeps pointing to the same underlying mechanism."
                    if len(source_periods) >= 2
                    else "No later period is available yet to show whether the risk intensifies or recedes."
                )
            )

        definition = RiskDefinition(
            risk_id=risk.get("risk_id", f"risk_{len(definitions)}"),
            risk_name=risk_name,
            normalized_name=risk.get("normalized_name", ""),
            risk_category=category,
            affected_area=affected_area,
            first_observed_period=risk.get("first_observed_period", ""),
            latest_period=risk.get("latest_period", ""),
            current_status=current_status,
            risk_mechanism=risk.get("risk_mechanism", ""),
            confidence=RiskConfidence(
                level=risk.get("confidence", {}).get("level", "low")
                if isinstance(risk.get("confidence"), dict)
                else "low",
                basis=[f"{len(risk.get('source_references', []))} source reference(s)", f"{len(source_periods)} period(s) covered"],
                limitations=[] if len(source_periods) >= 2 else ["single-period evidence"],
            ),
            evidence_status=risk.get("evidence_status", "missing"),
            source_references=risk.get("source_references", []),
            semantic_quality=risk.get("semantic_quality", {}),
            materiality=materiality,
            trigger_conditions=[f"Later disclosures show that {risk.get('risk_mechanism', risk_name or 'the risk mechanism')} is worsening."],
            disconfirming_evidence=[f"Later disclosures show that {risk.get('risk_mechanism', risk_name or 'the risk mechanism')} has materially reduced."],
            related_commitment_ids=risk.get("related_commitment_ids", []),
            related_project_ids=risk.get("related_project_ids", []),
            related_capacity_ids=risk.get("related_capacity_ids", []),
            related_financial_metrics=risk.get("related_financial_metrics", []),
            what_changed=_what_changed,
            why_it_changed=_why_it_changed,
            progression_summary=(
                risk.get("progression_summary")
                or f"{risk_name or 'The risk'} remains under observation across the available periods."
            ),
            investor_implication=(
                risk.get("investor_implication")
                or (
                    "The risk remains live in the evidence and should stay in view."
                    if current_status in {"emerging", "increasing", "persistent", "recurring"}
                    else "The risk remains visible, but the evidence is still too thin for a stronger judgment."
                )
            ),
            evo_canonical_id=evo_canonical_id,
            evo_trajectory=evo_trajectory,
            evo_severity_by_year=risk.get("evo_severity_by_year") or {},
            evo_latest_severity=risk.get("evo_latest_severity"),
        )
        
        definitions.append(definition)
    
    return definitions


def _build_risk_timelines(
    definitions: List[RiskDefinition],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Build risk progression timelines.
    
    Returns (timelines, assessments)
    """
    timelines = []
    assessments = []
    
    for definition in definitions:
        # Build initial event
        events = []
        
        if definition.risk_mechanism:
            event = build_risk_event(
                risk_id=definition.risk_id,
                period=definition.first_observed_period or "unknown",
                event_type="risk_signal",
                title=definition.risk_name,
                description=definition.risk_mechanism,
                confidence=asdict(definition.confidence),
                source_references=definition.source_references,
                sequence=0,
            )
            events.append(event)
        
        # Add latest assessment event
        if definition.latest_period and definition.latest_period != definition.first_observed_period:
            assessment_event = build_risk_event(
                risk_id=definition.risk_id,
                period=definition.latest_period,
                event_type="latest_assessment",
                title=f"{definition.risk_name} - Latest Assessment",
                description=definition.progression_summary or definition.risk_mechanism,
                confidence=asdict(definition.confidence),
                source_references=definition.source_references,
                sequence=len(events),
            )
            events.append(assessment_event)
        
        # Build timeline
        if events:
            timeline = build_timeline(
                risk_id=definition.risk_id,
                risk_name=definition.risk_name,
                events=events,
                current_state=definition.current_status,
                unresolved=definition.unresolved_questions,
                investor_implication=definition.investor_implication,
                confidence=asdict(definition.confidence),
            )
            
            timelines.append(timeline.to_dict() if hasattr(timeline, "to_dict") else timeline)
        
        # Build assessment
        assessment = RiskAssessment(
            risk_id=definition.risk_id,
            current_status=definition.current_status,
            what_changed=definition.what_changed or (
                f"{definition.risk_name or definition.normalized_name or 'The risk'} remains visible from {definition.first_observed_period or 'the first observed period'} to {definition.latest_period or definition.first_observed_period or 'the latest available period'}."
                if definition.latest_period or definition.first_observed_period
                else f"{definition.risk_name or definition.normalized_name or 'The risk'} is identified in the source evidence."
            ),
            why_it_changed=definition.why_it_changed or (
                "Later evidence keeps pointing to the same underlying mechanism."
                if definition.latest_period and definition.latest_period != definition.first_observed_period
                else "No later period is available yet to show whether the risk intensifies or recedes."
            ),
            conviction_impact="unclear",
            trajectory=definition.evo_trajectory,
            evo_canonical_id=definition.evo_canonical_id,
            latest_evidence=[s.get("artifact", "") for s in definition.source_references],
            unresolved_items=definition.unresolved_questions,
            investor_implication=definition.investor_implication,
            semantic_quality=definition.semantic_quality,
        )
        assessment_dict = assessment.to_dict()
        assessment_dict["period"] = definition.latest_period or definition.first_observed_period or ""
        assessment_dict["latest_period"] = definition.latest_period or definition.first_observed_period or ""
        assessment_dict["risk_name"] = definition.risk_name
        assessment_dict["normalized_name"] = definition.normalized_name
        assessments.append(assessment_dict)

    return timelines, assessments


def build_risk_evolution(
    company: str,
    companies_root: Path | str = Path("companies"),
) -> Dict[str, Path]:
    """
    Build canonical Risk Evolution Intelligence for a company.
    
    Main orchestrator that:
    1. Discovers company memory artifacts
    2. Extracts risk candidates
    3. Normalizes and deduplicates
    4. Enriches with relationships
    5. Builds canonical definitions
    6. Tracks progression
    7. Validates outputs
    8. Writes canonical artifacts
    
    Returns dict of output paths written.
    """
    
    companies_root = Path(companies_root)
    company_root = companies_root / company
    
    if not company_root.exists():
        raise ValueError(f"Company not found: {company_root}")
    
    # Discover years
    years = _discover_years(company_root)
    if not years:
        raise ValueError(f"No fiscal year data found for {company}")
    
    # Load yearly records
    year_records = []
    for year_dir in years:
        record = _load_year_record(year_dir)
        year_records.append(record)
    
    # Extract risk candidates
    all_candidates = []
    upstream_sources: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"found": False, "count": 0})
    
    for year_record in year_records:
        candidates = _extract_risk_candidates(year_record)
        all_candidates.extend(candidates)
        
        # Track which sources were found
        for source_name, source_info in year_record.get("source_artifacts", {}).items():
            if source_info.get("found"):
                upstream_sources[source_name]["found"] = True
                upstream_sources[source_name]["count"] += 1

    company_memory_candidates = _extract_company_memory_risk_candidates(company_root)
    all_candidates.extend(company_memory_candidates)
    upstream_sources["company_memory_structured_evidence"]["found"] = bool(company_memory_candidates)
    upstream_sources["company_memory_structured_evidence"]["count"] = len(company_memory_candidates)
    
    # Filter out generic boilerplate
    valid_candidates = _filter_risks(all_candidates)
    
    # Normalize
    normalized_risks = _normalize_risks(valid_candidates, company)
    
    # Deduplicate
    deduplicated_risks, merge_log = deduplicate_risks(normalized_risks)
    # Final ID-based collapse: same risk_id = same name hash = same risk; keep earliest first_observed_period.
    _seen_ids: dict = {}
    for _r in deduplicated_risks:
        _rid = _r.get("risk_id")
        if _rid not in _seen_ids:
            _seen_ids[_rid] = _r
        else:
            _kept = _seen_ids[_rid]
            if _r.get("latest_period", "") > (_kept.get("latest_period") or ""):
                _kept["latest_period"] = _r["latest_period"]
    deduplicated_risks = list(_seen_ids.values())

    # Enrich
    enriched_risks = _enrich_risks(deduplicated_risks, company_root)
    
    # Build definitions
    definitions = _build_risk_definitions(enriched_risks)
    
    # Build timelines and assessments
    timelines, assessments = _build_risk_timelines(definitions)
    latest_period = ""
    if definitions:
        latest_period = max(
            [str(definition.latest_period or definition.first_observed_period or "") for definition in definitions if str(definition.latest_period or definition.first_observed_period or "").strip()],
            key=lambda value: parse_financial_year(value) if str(value).lower().startswith("fy") else -1,
            default="",
        )
    
    # Convert definitions to dicts
    risks_dicts = [d.to_dict() for d in definitions]
    
    # Validate
    validation_report = validate_risk_payload(
        registry={"risks": risks_dicts},
        timelines={"timelines": timelines},
        assessments={"assessments": assessments},
        upstream_material_evidence_count=len(valid_candidates),
    )
    
    # Build manifest
    manifest = build_risk_manifest(
        company_slug=company,
        risks=risks_dicts,
        timelines=timelines,
        assessments=assessments,
        validation_report=validation_report,
        upstream_sources=dict(upstream_sources),
        merge_log=merge_log,
    )
    
    # Write outputs
    output_paths = write_all_risk_outputs(
        company_root=company_root,
        risks=risks_dicts,
        timelines=timelines,
        assessments=assessments,
        validation_report=validation_report,
        manifest=manifest,
    )
    
    # Print summary
    print_risk_summary(company, risks_dicts, validation_report)
    
    return output_paths
