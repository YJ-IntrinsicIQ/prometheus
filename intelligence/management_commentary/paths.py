from __future__ import annotations

from pathlib import Path


def get_commentary_dir(company_slug: str, companies_root: Path | str) -> Path:
    """Always under the explicit companies_root (no default, no fallback to ./companies)."""
    return Path(companies_root) / company_slug / "company_memory" / "management_commentary"


def get_commentary_themes_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_commentary_dir(company_slug, companies_root) / "commentary_themes.json"


def get_commentary_timelines_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_commentary_dir(company_slug, companies_root) / "commentary_timelines.json"


def get_commentary_assessments_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_commentary_dir(company_slug, companies_root) / "commentary_assessments.json"


def get_commentary_validation_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_commentary_dir(company_slug, companies_root) / "commentary_validation.json"


def get_commentary_manifest_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_commentary_dir(company_slug, companies_root) / "commentary_manifest.json"
