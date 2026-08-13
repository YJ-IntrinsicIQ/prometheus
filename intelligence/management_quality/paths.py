from __future__ import annotations

from pathlib import Path


def get_management_quality_dir(company: str) -> Path:
    return Path("companies") / company / "company_memory" / "management_quality"


def get_management_quality_summary_path(company: str) -> Path:
    return get_management_quality_dir(company) / "management_quality_summary.json"


def get_management_quality_dimensions_path(company: str) -> Path:
    return get_management_quality_dir(company) / "management_quality_dimensions.json"


def get_management_quality_evidence_path(company: str) -> Path:
    return get_management_quality_dir(company) / "management_quality_evidence.json"


def get_management_quality_validation_path(company: str) -> Path:
    return get_management_quality_dir(company) / "management_quality_validation.json"


def get_management_quality_manifest_path(company: str) -> Path:
    return get_management_quality_dir(company) / "management_quality_manifest.json"

