from __future__ import annotations

from pathlib import Path


def logical_projects_dir(company_slug: str) -> Path:
    """The label recorded inside manifests ("companies/<slug>/company_memory/projects"). It is never used for file I/O."""
    return Path("companies") / company_slug / "company_memory" / "projects"


def get_projects_dir(company_slug: str, companies_root: Path | str) -> Path:
    """Where the projects bundle is written: always under the explicit companies_root (no default, no fallback to ./companies)."""
    return Path(companies_root) / company_slug / "company_memory" / "projects"


def get_projects_registry_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_projects_dir(company_slug, companies_root) / "projects_registry.json"


def get_project_timelines_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_projects_dir(company_slug, companies_root) / "project_timelines.json"


def get_project_assessments_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_projects_dir(company_slug, companies_root) / "project_assessments.json"


def get_projects_validation_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_projects_dir(company_slug, companies_root) / "projects_validation.json"


def get_projects_manifest_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_projects_dir(company_slug, companies_root) / "projects_manifest.json"
