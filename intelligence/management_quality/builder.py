from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from knowledge.company_memory import parse_financial_year, validate_lineage

from .contracts import MANAGEMENT_QUALITY_GENERATOR_VERSION, MANAGEMENT_QUALITY_SCHEMA_VERSION
from .dimensions import aggregate_overall_view, confidence_from_coverage, normalize_assessment
from .evidence_linker import build_management_quality_evidence
from .manifest import build_management_quality_manifest
from .paths import get_management_quality_dir
from .synthesis import build_conviction_lists, build_turning_points, evaluate_dimensions
from .validators import validate_management_quality_payload
from .writer import write_json_file


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Dict[str, Any] | List[Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _company_root(company: str) -> Path:
    return Path("companies") / company


def _load_company_payload(path: Path) -> Dict[str, Any]:
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


def _load_list(path: Path, key_options: Tuple[str, ...]) -> List[Dict[str, Any]]:
    payload = _load_company_payload(path)
    for key in key_options:
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _discover_years(company_root: Path) -> List[str]:
    if not company_root.exists():
        return []
    years = [path.name for path in company_root.iterdir() if path.is_dir() and path.name.lower().startswith("fy")]
    try:
        return sorted(years, key=parse_financial_year)
    except Exception:
        return sorted(years)


def _source_file_payloads(company_root: Path) -> Dict[str, Any]:
    financial_root = company_root / "company_memory" / "financials"
    return {
        "commitments": _load_list(company_root / "company_memory" / "management_commitments" / "management_commitments.json", ("commitments",)),
        "management_progression": _load_company_payload(company_root / "company_memory" / "management_progression" / "management_progression.json"),
        "projects": _load_list(company_root / "company_memory" / "projects" / "projects_registry.json", ("projects",)),
        "capacity": _load_list(company_root / "company_memory" / "capacity" / "capacity_registry.json", ("capacity_items", "capacities")),
        "risks": _load_list(company_root / "company_memory" / "risks" / "risk_registry.json", ("risks",)),
        "commentary": _load_list(company_root / "company_memory" / "management_commentary" / "commentary_themes.json", ("themes", "commentary_themes")),
        "capital_allocation_outcomes": _load_list(company_root / "company_memory" / "capital_allocation_outcomes" / "capital_allocation_outcomes.json", ("allocations",)),
        "owner_earnings": _load_list(financial_root / "investor_financial_modules" / "owner_earnings_bridge.json", ("bridges",)),
        "per_share_compounding": _load_list(financial_root / "investor_financial_modules" / "per_share_compounding_analysis.json", ("analysis",)),
        "financial_truth": _load_company_payload(financial_root / "financial_truth_pack.json"),
    }


def _latest_period_from_evidence(evidence_items: List[Dict[str, Any]], years: List[str]) -> str:
    periods = [str(item.get("period") or "").strip().lower() for item in evidence_items if str(item.get("period") or "").strip()]
    periods.extend([year.lower() for year in years if year])
    if not periods:
        return ""
    try:
        return sorted(set(periods), key=parse_financial_year)[-1]
    except Exception:
        return sorted(set(periods))[-1]


def _period_in_analysis_window(period: Any, years: List[str]) -> bool:
    if not years:
        return True
    try:
        period_value = parse_financial_year(str(period or "").lower())
        earliest = parse_financial_year(years[0])
        latest = parse_financial_year(years[-1])
        return earliest <= period_value <= latest
    except Exception:
        return True


def _dimension_lookup(dimensions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(item.get("dimension") or ""): item for item in dimensions if str(item.get("dimension") or "").strip()}


def _build_validation(summary_payload: Dict[str, Any], dimensions_payload: Dict[str, Any], evidence_payload: Dict[str, Any], *, lineage_report: Dict[str, Any], upstream_validation: Dict[str, str]) -> Dict[str, Any]:
    return validate_management_quality_payload(summary_payload, dimensions_payload=dimensions_payload, evidence_payload=evidence_payload, lineage_report=lineage_report, upstream_validation=upstream_validation)


REQUIRED_UPSTREAM_VALIDATION_STREAMS = frozenset({"management_commitments", "management_progression"})
OPTIONAL_UPSTREAM_VALIDATION_STREAMS = frozenset({
    "projects",
    "capacity",
    "risks",
    "management_commentary",
    "capital_allocation_outcomes",
})
OPTIONAL_VALIDATION_TO_SOURCE_KEY = {
    "projects": "projects",
    "capacity": "capacity",
    "risks": "risks",
    "management_commentary": "commentary",
    "capital_allocation_outcomes": "capital_allocation_outcomes",
}


def _status_for_validation_path(path: Path) -> str:
    if not path.exists():
        return "missing"
    return str(_load_company_payload(path).get("status") or "missing").lower()


def _is_hard_invalid_upstream(status: str) -> bool:
    return str(status or "").lower() in {"fail", "failed", "missing"}


def build_management_quality_payloads(*, company: str, company_root: Path) -> Dict[str, Dict[str, Any]]:
    source_payloads = _source_file_payloads(company_root)
    years = _discover_years(company_root)
    validation_paths = {
        "management_commitments": company_root / "company_memory" / "management_commitments" / "commitment_validation.json",
        "management_progression": company_root / "company_memory" / "management_progression" / "management_progression_validation.json",
        "projects": company_root / "company_memory" / "projects" / "projects_validation.json",
        "capacity": company_root / "company_memory" / "capacity" / "capacity_validation.json",
        "risks": company_root / "company_memory" / "risks" / "risk_validation.json",
        "management_commentary": company_root / "company_memory" / "management_commentary" / "commentary_validation.json",
        "capital_allocation_outcomes": company_root / "company_memory" / "capital_allocation_outcomes" / "capital_allocation_validation.json",
    }
    upstream_validation = {
        name: _status_for_validation_path(path)
        for name, path in validation_paths.items()
        if name in REQUIRED_UPSTREAM_VALIDATION_STREAMS or path.exists()
    }
    quarantined_optional_sources = sorted(
        name
        for name, status in upstream_validation.items()
        if name in OPTIONAL_UPSTREAM_VALIDATION_STREAMS and _is_hard_invalid_upstream(status)
    )
    for name in quarantined_optional_sources:
        source_key = OPTIONAL_VALIDATION_TO_SOURCE_KEY.get(name)
        if source_key:
            source_payloads[source_key] = []
    validation_upstream_status = {
        name: status
        for name, status in upstream_validation.items()
        if name in REQUIRED_UPSTREAM_VALIDATION_STREAMS or status not in {"fail", "failed", "missing"}
    }
    evidence_items = build_management_quality_evidence(source_payloads, company_slug=company)
    evidence_items = [item for item in evidence_items if _period_in_analysis_window(item.get("period"), years)]
    latest_period = _latest_period_from_evidence(evidence_items, years)

    source_stream_counts: Dict[str, int] = {}
    for item in evidence_items:
        source_stream_counts[item["source_stream"]] = source_stream_counts.get(item["source_stream"], 0) + 1

    dimension_records, meta = evaluate_dimensions(
        evidence_items=evidence_items,
        source_stream_counts=source_stream_counts,
        latest_period=latest_period,
    )
    dimension_lookup = _dimension_lookup(dimension_records)
    overall_view = aggregate_overall_view(
        dimension_assessments=meta["dimension_assessments"],
        evidence_confidence_level=meta["evidence_confidence_level"],
        dimension_directions=meta["dimension_directions"],
    )
    overall_direction = meta["dimension_directions"].get("evidence_confidence") or "unclear"
    if overall_view in {"strong", "reasonably_strong"} and meta["dimension_directions"]:
        improving = sum(1 for value in meta["dimension_directions"].values() if value == "improving")
        deteriorating = sum(1 for value in meta["dimension_directions"].values() if value == "deteriorating")
        if improving > deteriorating:
            overall_direction = "improving"
        elif deteriorating > improving:
            overall_direction = "deteriorating"
        elif improving or deteriorating:
            overall_direction = "mixed"
        else:
            overall_direction = "stable"
    elif any(value == "deteriorating" for value in meta["dimension_directions"].values()):
        overall_direction = "mixed"
    else:
        overall_direction = "unclear" if meta["evidence_confidence_level"] in {"insufficient", "low"} else "stable"

    conviction_lists = build_conviction_lists(dimension_records, evidence_items)
    turning_points = build_turning_points(evidence_items)
    evidence_confidence = confidence_from_coverage(source_stream_counts, evidence_items)
    degraded = sorted(name for name, status in upstream_validation.items() if status not in {"pass", "passed"})
    if degraded and evidence_confidence.get("level") == "high":
        evidence_confidence["level"] = "medium"
        evidence_confidence.setdefault("limitations", []).append(f"Upstream validation is not clean for: {', '.join(degraded)}")
    weakest_dimension = min(
        (item for item in dimension_records if item.get("dimension") != "evidence_confidence"),
        key=lambda item: (
            normalize_assessment(item.get("assessment")),
            len(item.get("supporting_evidence") or []),
            len(item.get("conflicting_evidence") or []),
        ),
        default=None,
    )
    strongest_dimension = max(
        (item for item in dimension_records if item.get("dimension") != "evidence_confidence"),
        key=lambda item: (
            {"insufficient_evidence": 0, "weak": 1, "mixed": 2, "reasonably_strong": 3, "strong": 4}.get(normalize_assessment(item.get("assessment")), 0),
            len(item.get("supporting_evidence") or []),
            len(item.get("conflicting_evidence") or []),
        ),
        default=None,
    )

    summary_payload = {
        "schema_version": MANAGEMENT_QUALITY_SCHEMA_VERSION,
        "generator_version": MANAGEMENT_QUALITY_GENERATOR_VERSION,
        "company_slug": company,
        "latest_period": latest_period,
        "overall_view": overall_view,
        "overall_direction": overall_direction,
        "strongest_dimension": strongest_dimension.get("dimension") if strongest_dimension else "",
        "weakest_dimension": weakest_dimension.get("dimension") if weakest_dimension else "",
        "what_strengthened_conviction": conviction_lists["what_strengthened_conviction"],
        "what_weakened_conviction": conviction_lists["what_weakened_conviction"],
        "what_remains_unproven": conviction_lists["what_remains_unproven"],
        "major_turning_points": turning_points,
        "evidence_confidence": evidence_confidence,
        "investor_implication": _investor_implication(overall_view, overall_direction),
        "unresolved_questions": _build_unresolved_questions(dimension_lookup),
        "generated_at": _utc_now(),
    }
    summary_payload["interpretation"] = {
        "conclusion": f"Management quality is {overall_view.replace('_', ' ')} and the trajectory is {overall_direction.replace('_', ' ')}.",
        "what_changed": [item.get("summary") for item in turning_points[:3] if item.get("summary")],
        "why_it_matters": _investor_implication(overall_view, overall_direction),
        "economic_mechanism": "Management quality matters because execution, capital allocation, candor, and risk handling determine whether the company converts plans into durable per-share value.",
        "thesis_impact": (
            "strengthens"
            if overall_view in {"strong", "reasonably_strong"} and overall_direction == "improving"
            else "weakens"
            if overall_view == "weak" or overall_direction == "deteriorating"
            else "neutral"
            if overall_view == "mixed"
            else "unresolved"
        ),
        "positive_evidence": [item.get("summary") for item in conviction_lists["what_strengthened_conviction"] if item.get("summary")],
        "negative_evidence": [item.get("summary") for item in conviction_lists["what_weakened_conviction"] if item.get("summary")],
        "unresolved": [item for item in _build_unresolved_questions(dimension_lookup)[:3] if item],
        "what_to_watch": [item.get("summary") for item in turning_points[:3] if item.get("summary")],
        "confidence": evidence_confidence,
    }

    dimensions_payload = {
        "schema_version": MANAGEMENT_QUALITY_SCHEMA_VERSION,
        "generator_version": MANAGEMENT_QUALITY_GENERATOR_VERSION,
        "company_slug": company,
        "latest_period": latest_period,
        "dimensions": dimension_records,
        "generated_at": _utc_now(),
    }

    evidence_payload = {
        "schema_version": MANAGEMENT_QUALITY_SCHEMA_VERSION,
        "generator_version": MANAGEMENT_QUALITY_GENERATOR_VERSION,
        "company_slug": company,
        "latest_period": latest_period,
        "evidence_count": len(evidence_items),
        "evidence_items": evidence_items,
        "turning_points": turning_points,
        "generated_at": _utc_now(),
    }

    dependencies = []
    for name, path in {
        "management_commitments": company_root / "company_memory" / "management_commitments" / "management_commitments.json",
        "management_progression": company_root / "company_memory" / "management_progression" / "management_progression.json",
        "projects": company_root / "company_memory" / "projects" / "projects_registry.json",
        "capacity": company_root / "company_memory" / "capacity" / "capacity_registry.json",
        "risks": company_root / "company_memory" / "risks" / "risk_registry.json",
        "management_commentary": company_root / "company_memory" / "management_commentary" / "commentary_themes.json",
        "capital_allocation_outcomes": company_root / "company_memory" / "capital_allocation_outcomes" / "capital_allocation_outcomes.json",
    }.items():
        dependencies.append({"name": name, "generated_at": _load_company_payload(path).get("generated_at")})
    lineage_report = validate_lineage(artifact_generated_at=summary_payload["generated_at"], dependencies=dependencies)
    validation_payload = _build_validation(summary_payload, dimensions_payload, evidence_payload, lineage_report=lineage_report, upstream_validation=validation_upstream_status)
    manifest_payload = build_management_quality_manifest(
        company_slug=company,
        generated_at=_utc_now(),
        source_files_considered=[
            "company_memory/management_commitments/management_commitments.json",
            "company_memory/management_progression/management_progression.json",
            "company_memory/projects/projects_registry.json",
            "company_memory/capacity/capacity_registry.json",
            "company_memory/risks/risk_registry.json",
            "company_memory/management_commentary/commentary_themes.json",
            "company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json",
            "company_memory/financials/investor_financial_modules/owner_earnings_bridge.json",
            "company_memory/financials/investor_financial_modules/per_share_compounding_analysis.json",
            "company_memory/financials/financial_truth_pack.json",
        ],
        source_files_found=[key for key, value in source_stream_counts.items() if value],
        source_files_missing=[key for key in ("management_commitments", "management_progression", "projects", "capacity", "risks", "management_commentary", "capital_allocation_outcomes", "owner_earnings", "per_share_compounding", "financial_truth") if not source_stream_counts.get(key)],
        dimension_count=len(dimension_records),
        evidence_count=len(evidence_items),
        turning_point_count=len(turning_points),
        overall_view=overall_view,
        overall_direction=overall_direction,
        validation_status=validation_payload["status"],
        limitations=_limitations(source_stream_counts, evidence_confidence),
    )
    manifest_payload["lineage_validation"] = lineage_report
    manifest_payload["upstream_validation"] = upstream_validation
    manifest_payload["quarantined_optional_sources"] = quarantined_optional_sources

    return {
        "management_quality_summary.json": summary_payload,
        "management_quality_dimensions.json": dimensions_payload,
        "management_quality_evidence.json": evidence_payload,
        "management_quality_validation.json": validation_payload,
        "management_quality_manifest.json": manifest_payload,
    }


def _limitations(source_stream_counts: Dict[str, int], evidence_confidence: Dict[str, Any]) -> List[str]:
    limitations: List[str] = []
    if not source_stream_counts.get("capital_allocation_outcomes"):
        limitations.append("Capital-allocation outcomes were not available.")
    if not source_stream_counts.get("risks"):
        limitations.append("Risk-evolution evidence was sparse or missing.")
    if evidence_confidence.get("level") in {"low", "insufficient"}:
        limitations.append("The evidence base is thin, so the synthesis should be read cautiously.")
    return limitations


def _build_unresolved_questions(dimension_lookup: Dict[str, Dict[str, Any]]) -> List[str]:
    questions: List[str] = []
    if dimension_lookup.get("execution_discipline", {}).get("assessment") in {"mixed", "weak", "insufficient_evidence"}:
        questions.append("Where did commitments or projects fail to translate into delivery?")
    if dimension_lookup.get("capital_allocation_discipline", {}).get("assessment") in {"mixed", "weak", "insufficient_evidence"}:
        questions.append("Which capital deployments are still not proving their economic worth?")
    if dimension_lookup.get("owner_alignment", {}).get("assessment") in {"mixed", "weak", "insufficient_evidence"}:
        questions.append("Are per-share economics improving fast enough to justify continued reinvestment?")
    if dimension_lookup.get("risk_handling", {}).get("assessment") in {"mixed", "weak", "insufficient_evidence"}:
        questions.append("Are recurring risks being addressed early or only after they become visible?")
    if dimension_lookup.get("candor_and_consistency", {}).get("assessment") in {"mixed", "weak", "insufficient_evidence"}:
        questions.append("Has management explanation stayed aligned with later evidence?")
    if dimension_lookup.get("adaptability", {}).get("assessment") in {"mixed", "weak", "insufficient_evidence"}:
        questions.append("When evidence changed, did management adapt quickly and transparently enough?")
    return questions[:7]


def _investor_implication(overall_view: str, overall_direction: str) -> str:
    if overall_view == "strong":
        return "Management credibility and execution appear strong enough to support conviction."
    if overall_view == "reasonably_strong":
        return "Management quality looks broadly supportive of the thesis, with a few open edges."
    if overall_view == "mixed":
        return "The evidence is mixed, so conviction should stay selective and evidence-led."
    if overall_view == "weak":
        return "Management quality weakens conviction until execution and capital discipline improve."
    return "There is not yet enough evidence to change conviction with confidence."


class ManagementQualityBuilder:
    def __init__(self, company: str, companies_root: Path | str = Path("companies")) -> None:
        self.company = company
        self.companies_root = Path(companies_root)
        self.company_root = self.companies_root / company
        self.output_dir = get_management_quality_dir(company)

    def build(self) -> Dict[str, Path]:
        payloads = build_management_quality_payloads(company=self.company, company_root=self.company_root)
        written = {
            "management_quality_summary.json": payloads["management_quality_summary.json"],
            "management_quality_dimensions.json": payloads["management_quality_dimensions.json"],
            "management_quality_evidence.json": payloads["management_quality_evidence.json"],
            "management_quality_validation.json": payloads["management_quality_validation.json"],
            "management_quality_manifest.json": payloads["management_quality_manifest.json"],
        }
        return {
            filename: write_json_file(self.output_dir / filename, payload)
            for filename, payload in written.items()
        }


def build_management_quality(company: str, companies_root: Path | str = Path("companies")) -> Dict[str, Path]:
    return ManagementQualityBuilder(company=company, companies_root=companies_root).build()


def write_management_quality(*, company: str, company_root: Path, output_dir: Path) -> Dict[str, Path]:
    payloads = build_management_quality_payloads(company=company, company_root=company_root)
    return {
        filename: write_json_file(output_dir / filename, payload)
        for filename, payload in payloads.items()
    }
