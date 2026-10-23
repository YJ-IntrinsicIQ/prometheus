from __future__ import annotations

from pathlib import Path


def logical_management_quality_dir(company: str) -> Path:
    """The label recorded inside manifests. It is never used for file I/O."""
    return Path("companies") / company / "company_memory" / "management_quality"


def get_management_quality_dir(company: str, companies_root: Path | str) -> Path:
    """Always under the explicit companies_root (no default, no fallback to ./companies)."""
    return Path(companies_root) / company / "company_memory" / "management_quality"


def get_management_quality_summary_path(company: str, companies_root: Path | str) -> Path:
    return get_management_quality_dir(company, companies_root) / "management_quality_summary.json"


def get_management_quality_dimensions_path(company: str, companies_root: Path | str) -> Path:
    return get_management_quality_dir(company, companies_root) / "management_quality_dimensions.json"


def get_management_quality_evidence_path(company: str, companies_root: Path | str) -> Path:
    return get_management_quality_dir(company, companies_root) / "management_quality_evidence.json"


def get_management_quality_validation_path(company: str, companies_root: Path | str) -> Path:
    return get_management_quality_dir(company, companies_root) / "management_quality_validation.json"


def get_management_quality_manifest_path(company: str, companies_root: Path | str) -> Path:
    return get_management_quality_dir(company, companies_root) / "management_quality_manifest.json"
