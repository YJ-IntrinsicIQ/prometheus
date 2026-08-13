from __future__ import annotations

from pathlib import Path


def get_commentary_dir(company_slug: str) -> Path:
    return Path("companies") / company_slug / "company_memory" / "management_commentary"


def get_commentary_themes_path(company_slug: str) -> Path:
    return get_commentary_dir(company_slug) / "commentary_themes.json"


def get_commentary_timelines_path(company_slug: str) -> Path:
    return get_commentary_dir(company_slug) / "commentary_timelines.json"


def get_commentary_assessments_path(company_slug: str) -> Path:
    return get_commentary_dir(company_slug) / "commentary_assessments.json"


def get_commentary_validation_path(company_slug: str) -> Path:
    return get_commentary_dir(company_slug) / "commentary_validation.json"


def get_commentary_manifest_path(company_slug: str) -> Path:
    return get_commentary_dir(company_slug) / "commentary_manifest.json"

