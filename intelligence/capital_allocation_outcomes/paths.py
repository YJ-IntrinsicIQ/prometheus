from __future__ import annotations

from pathlib import Path


def get_capital_allocation_outcomes_dir(company_slug: str) -> Path:
    return Path("companies") / company_slug / "company_memory" / "capital_allocation_outcomes"


def get_capital_allocation_outcomes_path(company_slug: str) -> Path:
    return get_capital_allocation_outcomes_dir(company_slug) / "capital_allocation_outcomes.json"


def get_capital_allocation_timelines_path(company_slug: str) -> Path:
    return get_capital_allocation_outcomes_dir(company_slug) / "capital_allocation_timelines.json"


def get_capital_allocation_assessments_path(company_slug: str) -> Path:
    return get_capital_allocation_outcomes_dir(company_slug) / "capital_allocation_assessments.json"


def get_capital_allocation_validation_path(company_slug: str) -> Path:
    return get_capital_allocation_outcomes_dir(company_slug) / "capital_allocation_validation.json"


def get_capital_allocation_manifest_path(company_slug: str) -> Path:
    return get_capital_allocation_outcomes_dir(company_slug) / "capital_allocation_manifest.json"

