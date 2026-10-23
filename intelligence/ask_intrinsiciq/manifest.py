from __future__ import annotations

from typing import Any, Dict

from .contracts import ASK_INTRINSICIQ_GENERATOR_VERSION
from .paths import OUTPUT_FILE_NAMES, logical_ask_intrinsiciq_dir


def build_manifest(*, company_slug: str, generated_at: str, source_bundle: Dict[str, Any], outputs_written: list[str], validation_status: str, generation_status: str, limitations: list[str]) -> Dict[str, Any]:
    return {
        "schema_version": "ask_intrinsiciq_manifest.v1",
        "company_slug": company_slug,
        "generated_at": generated_at,
        "generator_version": ASK_INTRINSICIQ_GENERATOR_VERSION,
        "output_directory": str(logical_ask_intrinsiciq_dir(company_slug)),
        "source_files_considered": list(source_bundle.get("source_files_considered", [])),
        "source_files_found": list(source_bundle.get("source_files_found", [])),
        "source_files_missing": list(source_bundle.get("source_files_missing", [])),
        "outputs_written": outputs_written,
        "outputs_planned": [
            OUTPUT_FILE_NAMES["company_research_view"],
            OUTPUT_FILE_NAMES["business_journey"],
            OUTPUT_FILE_NAMES["products_services"],
            OUTPUT_FILE_NAMES["answer_cards"],
            OUTPUT_FILE_NAMES["financial_visual_summaries"],
            OUTPUT_FILE_NAMES["uncertainty_map"],
            "ask_intrinsiciq_manifest.json",
            "ask_intrinsiciq_validation_report.json",
        ],
        "validation_status": validation_status,
        "generation_status": generation_status,
        "limitations": limitations,
    }
