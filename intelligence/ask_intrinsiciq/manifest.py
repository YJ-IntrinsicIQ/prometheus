from __future__ import annotations

from typing import Any, Dict

from .contracts import ASK_INTRINSICIQ_GENERATOR_VERSION
from .paths import (
    get_answer_cards_path,
    get_ask_intrinsiciq_dir,
    get_business_journey_path,
    get_company_research_view_path,
    get_financial_visual_summaries_path,
    get_products_services_path,
    get_uncertainty_map_path,
)


def build_manifest(*, company_slug: str, generated_at: str, source_bundle: Dict[str, Any], outputs_written: list[str], validation_status: str, generation_status: str, limitations: list[str]) -> Dict[str, Any]:
    return {
        "schema_version": "ask_intrinsiciq_manifest.v1",
        "company_slug": company_slug,
        "generated_at": generated_at,
        "generator_version": ASK_INTRINSICIQ_GENERATOR_VERSION,
        "output_directory": str(get_ask_intrinsiciq_dir(company_slug)),
        "source_files_considered": list(source_bundle.get("source_files_considered", [])),
        "source_files_found": list(source_bundle.get("source_files_found", [])),
        "source_files_missing": list(source_bundle.get("source_files_missing", [])),
        "outputs_written": outputs_written,
        "outputs_planned": [
            str(get_company_research_view_path(company_slug).name),
            str(get_business_journey_path(company_slug).name),
            str(get_products_services_path(company_slug).name),
            str(get_answer_cards_path(company_slug).name),
            str(get_financial_visual_summaries_path(company_slug).name),
            str(get_uncertainty_map_path(company_slug).name),
            "ask_intrinsiciq_manifest.json",
            "ask_intrinsiciq_validation_report.json",
        ],
        "validation_status": validation_status,
        "generation_status": generation_status,
        "limitations": limitations,
    }
