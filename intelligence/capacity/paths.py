from __future__ import annotations

from pathlib import Path


def logical_capacity_dir(company_slug: str) -> Path:
    """The label recorded inside manifests ("companies/<slug>/company_memory/capacity"). It is never used for file I/O."""
    return Path("companies") / company_slug / "company_memory" / "capacity"


def get_capacity_dir(company_slug: str, companies_root: Path | str) -> Path:
    """Always under the explicit companies_root (no default, no fallback to ./companies)."""
    return Path(companies_root) / company_slug / "company_memory" / "capacity"


def get_capacity_registry_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_capacity_dir(company_slug, companies_root) / "capacity_registry.json"


def get_capacity_timelines_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_capacity_dir(company_slug, companies_root) / "capacity_timelines.json"


def get_capacity_assessments_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_capacity_dir(company_slug, companies_root) / "capacity_assessments.json"


def get_capacity_validation_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_capacity_dir(company_slug, companies_root) / "capacity_validation.json"


def get_capacity_manifest_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_capacity_dir(company_slug, companies_root) / "capacity_manifest.json"
