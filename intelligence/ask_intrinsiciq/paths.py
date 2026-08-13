from __future__ import annotations

from pathlib import Path


def get_ask_intrinsiciq_dir(company_slug: str) -> Path:
    return Path("companies") / company_slug / "company_memory" / "ask_intrinsiciq"


def get_company_research_view_path(company_slug: str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug) / "company_research_view.json"


def get_business_journey_path(company_slug: str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug) / "business_journey.json"


def get_products_services_path(company_slug: str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug) / "products_services.json"


def get_answer_cards_path(company_slug: str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug) / "answer_cards.json"


def get_financial_visual_summaries_path(company_slug: str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug) / "financial_visual_summaries.json"


def get_uncertainty_map_path(company_slug: str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug) / "uncertainty_map.json"


def get_manifest_path(company_slug: str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug) / "ask_intrinsiciq_manifest.json"


def get_validation_report_path(company_slug: str) -> Path:
    return get_ask_intrinsiciq_dir(company_slug) / "ask_intrinsiciq_validation_report.json"
