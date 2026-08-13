from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .answer_cards import build_answer_cards, build_question_catalog_view
from .business_journey import build_business_journey
from .contracts import ASK_INTRINSICIQ_SCHEMA_VERSION, CompanyResearchView, empty_business_journey
from .financial_visuals import build_financial_visual_summaries
from .loader import load_company_memory_sources
from .manifest import build_manifest
from .paths import get_answer_cards_path, get_business_journey_path, get_company_research_view_path, get_financial_visual_summaries_path, get_manifest_path, get_uncertainty_map_path, get_validation_report_path
from .paths import get_products_services_path
from .products_services import build_products_services
from .sanitizer import sanitize_public_payload
from .uncertainty_mapper import build_uncertainty_map, summarize_uncertainty_for_view
from .validator import build_validation_report, validate_answer_cards_payload, validate_business_journey_payload, validate_company_research_view, validate_financial_visual_summaries_payload, validate_products_services_payload, validate_uncertainty_map_payload
from .writer import write_json_file


def generate_ask_intrinsiciq_view(company_slug: str, *, force: bool = False) -> Dict[str, Any]:
    generated_at = _now_iso()
    source_bundle = load_company_memory_sources(company_slug)
    company_identity = _build_company_identity(company_slug, source_bundle)
    business_journey_payload, business_journey_diagnostics = build_business_journey(
        source_bundle,
        company_slug=company_slug,
        generated_at=generated_at,
    )
    products_services_payload, products_services_diagnostics = build_products_services(
        source_bundle,
        business_journey_payload=business_journey_payload,
        company_slug=company_slug,
        generated_at=generated_at,
    )
    financial_visual_summaries_payload, financial_visual_summaries_diagnostics = build_financial_visual_summaries(
        source_bundle,
        company_slug=company_slug,
        generated_at=generated_at,
    )
    uncertainty_map_payload, uncertainty_map_diagnostics = build_uncertainty_map(
        source_bundle,
        business_journey_payload=business_journey_payload,
        products_services_payload=products_services_payload,
        company_slug=company_slug,
        generated_at=generated_at,
    )
    answer_cards_payload, answer_cards_diagnostics = build_answer_cards(
        source_bundle,
        business_journey_payload=business_journey_payload,
        products_services_payload=products_services_payload,
        financial_visual_summaries_payload=financial_visual_summaries_payload,
        uncertainty_map_payload=uncertainty_map_payload,
        company_slug=company_slug,
        generated_at=generated_at,
    )
    categories = build_question_catalog_view(answer_cards_payload)
    coverage = _build_coverage(source_bundle, business_journey_payload, products_services_payload, answer_cards_payload, categories)
    public_view: CompanyResearchView = {
        "schemaVersion": ASK_INTRINSICIQ_SCHEMA_VERSION,
        "company": company_identity,
        "coverage": coverage,
        "categories": categories,
        "businessJourney": _build_business_journey_view_model(business_journey_payload),
        "productsAndServices": _build_products_services_view_model(products_services_payload),
        "financialVisuals": _build_financial_visuals_view_model(financial_visual_summaries_payload),
        "generatedAt": generated_at,
        "sourceState": {
            "contentStatus": _content_status(business_journey_payload, products_services_payload, answer_cards_payload),
            "sourceMode": "deterministic_skeleton",
            "summary": "This release provides a curated deterministic research set with answer cards, compact financial visuals, and mapped uncertainty notes built from existing company-memory evidence.",
            "foundSourceCount": len(source_bundle.get("source_files_found", [])),
            "missingSourceCount": len(source_bundle.get("source_files_missing", [])),
            "uncertaintySummary": summarize_uncertainty_for_view(uncertainty_map_payload),
            "sourceFreshness": _build_source_freshness(source_bundle, generated_at),
        },
    }
    freshness_status = str((public_view.get("sourceState") or {}).get("sourceFreshness", {}).get("freshnessStatus") or "").lower()
    if freshness_status == "stale":
        public_view["sourceState"]["contentStatus"] = "stale"
    public_view = sanitize_public_payload(public_view)
    errors = validate_company_research_view(public_view)
    errors.extend(validate_business_journey_payload(business_journey_payload))
    errors.extend(validate_products_services_payload(products_services_payload))
    errors.extend(validate_financial_visual_summaries_payload(financial_visual_summaries_payload))
    errors.extend(validate_uncertainty_map_payload(uncertainty_map_payload))
    errors.extend(
        validate_answer_cards_payload(
            answer_cards_payload,
            products_services_payload=products_services_payload,
            financial_visual_ids=[str(item.get("id") or "") for item in financial_visual_summaries_payload.get("visuals", []) or []],
        )
    )
    warnings = _build_warnings(source_bundle)
    validation_report = build_validation_report(
        generated_at=generated_at,
        outputs_validated=["company_research_view.json", "business_journey.json", "products_services.json", "answer_cards.json", "financial_visual_summaries.json", "uncertainty_map.json"],
        errors=errors,
        warnings=warnings,
    )
    generation_status = "partial" if not errors else "fail"
    limitations: List[str] = []
    if int((financial_visual_summaries_payload.get("coverage_summary") or {}).get("unavailable") or 0) > 0:
        limitations.append("Some financial visual candidates remain unavailable because the current evidence is too thin to support them responsibly.")
    if str(uncertainty_map_payload.get("coverage_status") or "") != "supported":
        limitations.append("The uncertainty map could not be fully established from the available evidence.")
    manifest = build_manifest(
        company_slug=company_slug,
        generated_at=generated_at,
        source_bundle=source_bundle,
        outputs_written=[
            str(get_company_research_view_path(company_slug).name),
            str(get_business_journey_path(company_slug).name),
            str(get_products_services_path(company_slug).name),
            str(get_answer_cards_path(company_slug).name),
            str(get_financial_visual_summaries_path(company_slug).name),
            str(get_uncertainty_map_path(company_slug).name),
            str(get_manifest_path(company_slug).name),
            str(get_validation_report_path(company_slug).name),
        ],
        validation_status=validation_report["status"],
        generation_status=generation_status,
        limitations=limitations,
    )
    write_json_file(get_business_journey_path(company_slug), business_journey_payload, force=True)
    write_json_file(get_products_services_path(company_slug), products_services_payload, force=True)
    write_json_file(get_answer_cards_path(company_slug), answer_cards_payload, force=True)
    write_json_file(get_financial_visual_summaries_path(company_slug), financial_visual_summaries_payload, force=True)
    write_json_file(get_uncertainty_map_path(company_slug), uncertainty_map_payload, force=True)
    write_json_file(get_company_research_view_path(company_slug), public_view, force=True)
    write_json_file(get_manifest_path(company_slug), manifest, force=True)
    write_json_file(get_validation_report_path(company_slug), validation_report, force=True)
    return {
        "business_journey": business_journey_payload,
        "business_journey_diagnostics": business_journey_diagnostics,
        "products_services": products_services_payload,
        "products_services_diagnostics": products_services_diagnostics,
        "financial_visual_summaries": financial_visual_summaries_payload,
        "financial_visual_summaries_diagnostics": financial_visual_summaries_diagnostics,
        "uncertainty_map": uncertainty_map_payload,
        "uncertainty_map_diagnostics": uncertainty_map_diagnostics,
        "answer_cards": answer_cards_payload,
        "answer_cards_diagnostics": answer_cards_diagnostics,
        "company_research_view": public_view,
        "manifest": manifest,
        "validation_report": validation_report,
        "source_bundle": source_bundle,
    }


def _build_company_identity(company_slug: str, source_bundle: Dict[str, Any]) -> Dict[str, Any]:
    pcim = ((source_bundle.get("sources") or {}).get("pcim") or {}).get("payload") or {}
    identity_manifest = pcim.get("business_identity_manifest") or {}
    company_name = str(pcim.get("company") or company_slug.replace("-", " ").title()).strip()
    industry = _first_nonempty(
        identity_manifest.get("primary_sector"),
        identity_manifest.get("industry"),
        "",
    )
    description = _first_nonempty(
        identity_manifest.get("business_summary"),
        ((pcim.get("business_understanding") or {}).get("business_summary")),
        "A concise company description is not yet available in this release.",
    )
    periods = _extract_reporting_periods(source_bundle)
    return {
        "companySlug": company_slug,
        "companyName": company_name,
        "displayName": company_name,
        "reportingPeriodsCovered": periods,
        "primaryIndustry": str(industry or ""),
        "shortDescription": str(description or ""),
    }


def _build_coverage(
    source_bundle: Dict[str, Any],
    business_journey_payload: Dict[str, Any],
    products_services_payload: Dict[str, Any],
    answer_cards_payload: Dict[str, Any],
    categories: List[Dict[str, Any]],
) -> Dict[str, Any]:
    found_count = len(source_bundle.get("source_files_found", []))
    summary = "Curated Ask IntrinsicIQ answers are available, but the overall research set is still incomplete."
    if found_count == 0:
        summary = "No upstream research sources were available, so only an empty shell could be prepared."
    coverage_summary = answer_cards_payload.get("coverage_summary") or {}
    evidence_status = "missing"
    if (
        business_journey_payload.get("coverage_status") == "supported"
        or products_services_payload.get("coverage_status") == "supported"
        or int(coverage_summary.get("supported") or 0) > 0
    ):
        evidence_status = "direct"
    elif (
        business_journey_payload.get("coverage_status") == "partial"
        or products_services_payload.get("coverage_status") == "partial"
        or int(coverage_summary.get("partially_supported") or 0) > 0
    ):
        evidence_status = "partial"
    return {
        "availableCategoryIds": [str(category.get("id") or "") for category in categories if str(category.get("id") or "").strip()],
        "sourcedAnswerCount": int(coverage_summary.get("supported") or 0),
        "partiallySupportedAnswerCount": int(coverage_summary.get("partially_supported") or 0),
        "unsupportedAnswerCount": int(coverage_summary.get("not_supported") or 0),
        "unavailableAnswerCount": int(coverage_summary.get("unavailable") or 0),
        "evidenceStatus": evidence_status,
        "summary": summary,
    }


def _extract_reporting_periods(source_bundle: Dict[str, Any]) -> List[str]:
    pcim = ((source_bundle.get("sources") or {}).get("pcim") or {}).get("payload") or {}
    years = pcim.get("available_years") or []
    if isinstance(years, list):
        return [str(year) for year in years if str(year).strip()]
    truth_pack = ((source_bundle.get("sources") or {}).get("financial_truth_pack") or {}).get("payload") or {}
    covered = truth_pack.get("years_covered") or []
    if isinstance(covered, list):
        return [str(year) for year in covered if str(year).strip()]
    return []


def _build_warnings(source_bundle: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    if source_bundle.get("source_files_missing"):
        warnings.append("Some upstream company-memory sources were unavailable during generation.")
    return warnings


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_source_freshness(source_bundle: Dict[str, Any], generated_at: str) -> Dict[str, Any]:
    source_records = source_bundle.get("sources") or {}
    loaded_sources: List[Dict[str, Any]] = []
    stale_sources: List[str] = []
    latest_generated_at: datetime | None = None
    latest_file_mtime: datetime | None = None
    generated_time = _parse_iso(generated_at)

    for source_name, record in source_records.items():
        if not isinstance(record, dict):
            continue
        if str(record.get("status") or "").lower() != "loaded":
            continue
        source_generated_at = _parse_iso(record.get("generated_at"))
        file_mtime = _parse_iso(record.get("file_mtime"))
        loaded_sources.append(
            {
                "sourceName": source_name,
                "generatedAt": record.get("generated_at") or "",
                "fileMtime": record.get("file_mtime") or "",
            }
        )
        if source_generated_at and (latest_generated_at is None or source_generated_at > latest_generated_at):
            latest_generated_at = source_generated_at
        if file_mtime and (latest_file_mtime is None or file_mtime > latest_file_mtime):
            latest_file_mtime = file_mtime
        if generated_time and source_generated_at and source_generated_at > generated_time:
            stale_sources.append(source_name)
        if generated_time and file_mtime and file_mtime > generated_time:
            stale_sources.append(source_name)

    freshness_status = "fresh"
    if stale_sources:
        freshness_status = "stale"
    elif source_bundle.get("source_files_missing"):
        freshness_status = "partial"
    elif not loaded_sources:
        freshness_status = "unavailable"

    return {
        "freshnessStatus": freshness_status,
        "checkedAt": generated_at,
        "latestSourceGeneratedAt": latest_generated_at.replace(microsecond=0).isoformat().replace("+00:00", "Z") if latest_generated_at else "",
        "latestSourceModifiedAt": latest_file_mtime.replace(microsecond=0).isoformat().replace("+00:00", "Z") if latest_file_mtime else "",
        "loadedSources": loaded_sources,
        "staleSources": sorted(set(stale_sources)),
    }


def _build_business_journey_view_model(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_stages = list(payload.get("stages", []) or [])
    if payload.get("historical_stages"):
        raw_stages = list(payload.get("historical_stages") or [])
        current_state = payload.get("current_state") or {}
        if current_state:
            raw_stages.append(
                {
                    "id": current_state.get("id", ""),
                    "period_label": current_state.get("period_label", ""),
                    "title": current_state.get("title", ""),
                    "simple_description": current_state.get("description", ""),
                    "significance": current_state.get("why_it_matters", ""),
                    "evidence_status": current_state.get("evidence_status", "missing"),
                    "display_order": len(raw_stages) + 1,
                }
            )
    stages = []
    for item in raw_stages:
        stages.append(
            {
                "id": item.get("id", ""),
                "periodLabel": item.get("period_label", ""),
                "title": item.get("title", ""),
                "simpleDescription": item.get("simple_description", ""),
                "significance": item.get("significance", ""),
                "evidenceStatus": item.get("evidence_status", "missing"),
                "displayOrder": item.get("display_order", 0),
            }
        )
    return {
        "summary": payload.get("summary") or empty_business_journey()["summary"],
        "stages": stages,
        "currentDirection": payload.get("current_direction") or "Historical evolution is not yet established from the available evidence.",
        "openQuestions": list(payload.get("open_questions", []) or []),
    }


def _build_products_services_view_model(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    groups = []
    for group in payload.get("groups", []) or []:
        items = []
        for item in group.get("items", []) or []:
            items.append(
                {
                    "id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "simpleExplanation": item.get("simple_explanation", ""),
                    "customerType": item.get("customer_type", ""),
                    "roleInBusiness": item.get("role_in_business", ""),
                    "revenueContributionStatus": item.get("revenue_contribution_status", "unknown"),
                    "revenueContribution": item.get("revenue_contribution"),
                    "evidenceStatus": item.get("evidence_status", "missing"),
                    "displayOrder": item.get("display_order", 0),
                }
            )
        groups.append(
            {
                "id": group.get("id", ""),
                "title": group.get("title", ""),
                "description": group.get("description", ""),
                "items": items,
            }
        )
    return groups


def _build_financial_visuals_view_model(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    visuals = []
    for item in payload.get("visuals", []) or []:
        visuals.append(
            {
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "subtitle": item.get("subtitle", ""),
                "visualType": item.get("visual_type", "status"),
                "unit": item.get("unit", ""),
                "series": item.get("series", []),
                "interpretation": item.get("interpretation", ""),
                "precisionNote": item.get("precision_note"),
                "evidenceStatus": item.get("evidence_status", "missing"),
            }
        )
    return visuals


def _content_status(
    business_journey_payload: Dict[str, Any],
    products_services_payload: Dict[str, Any],
    answer_cards_payload: Dict[str, Any],
) -> str:
    statuses = {
        business_journey_payload.get("coverage_status"),
        products_services_payload.get("coverage_status"),
    }
    coverage_summary = answer_cards_payload.get("coverage_summary") or {}
    if int(coverage_summary.get("supported") or 0) > 0 or int(coverage_summary.get("partially_supported") or 0) > 0:
        return "partial"
    if "supported" in statuses:
        return "partial"
    if "partial" in statuses:
        return "partial"
    return "incomplete"


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
