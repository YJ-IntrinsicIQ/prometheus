from __future__ import annotations

from pathlib import Path


def get_projects_dir(company_slug: str) -> Path:
    return Path("companies") / company_slug / "company_memory" / "projects"


def get_projects_registry_path(company_slug: str) -> Path:
    return get_projects_dir(company_slug) / "projects_registry.json"


def get_project_timelines_path(company_slug: str) -> Path:
    return get_projects_dir(company_slug) / "project_timelines.json"


def get_project_assessments_path(company_slug: str) -> Path:
    return get_projects_dir(company_slug) / "project_assessments.json"


def get_projects_validation_path(company_slug: str) -> Path:
    return get_projects_dir(company_slug) / "projects_validation.json"


def get_projects_manifest_path(company_slug: str) -> Path:
    return get_projects_dir(company_slug) / "projects_manifest.json"

