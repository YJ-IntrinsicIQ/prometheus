from __future__ import annotations

from pathlib import Path

OUTPUT_FILE_NAMES = {
    "company_research_view": "company_research_view.json",
    "business_journey": "business_journey.json",
    "products_services": "products_services.json",
    "answer_cards": "answer_cards.json",
    "financial_visual_summaries": "financial_visual_summaries.json",
    "uncertainty_map": "uncertainty_map.json",
    "manifest": "ask_intrinsiciq_manifest.json",
    "validation_report": "ask_intrinsiciq_validation_report.json",
}


def logical_ask_intrinsiciq_dir(company_slug: str) -> Path:
    """The label recorded inside manifests. It is never used for file I/O."""
    return Path("companies") / company_slug / "company_memory" / "ask_intrinsiciq"


def get_ask_intrinsiciq_dir(company_slug: str, companies_root: Path | str) -> Path:
    """Always under the explicit companies_root (no default, no fallback to ./companies)."""
    return Path(companies_root) / company_slug / "company_memory" / "ask_intrinsiciq"


def get_company_research_view_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug, companies_root) / OUTPUT_FILE_NAMES["company_research_view"]


def get_business_journey_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug, companies_root) / OUTPUT_FILE_NAMES["business_journey"]


def get_products_services_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug, companies_root) / OUTPUT_FILE_NAMES["products_services"]


def get_answer_cards_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug, companies_root) / OUTPUT_FILE_NAMES["answer_cards"]


def get_financial_visual_summaries_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug, companies_root) / OUTPUT_FILE_NAMES["financial_visual_summaries"]


def get_uncertainty_map_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug, companies_root) / OUTPUT_FILE_NAMES["uncertainty_map"]


def get_manifest_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug, companies_root) / OUTPUT_FILE_NAMES["manifest"]


def get_validation_report_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug, companies_root) / OUTPUT_FILE_NAMES["validation_report"]
