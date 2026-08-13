"""Risk Evolution file paths."""

from __future__ import annotations

from pathlib import Path


def get_risk_dir(company_root: Path | str) -> Path:
    """Get the risk evolution directory for a company."""
    root = Path(company_root)
    return root / "company_memory" / "risks"


def get_risk_registry_path(company_root: Path | str) -> Path:
    """Get the risk registry file path."""
    return get_risk_dir(company_root) / "risk_registry.json"


def get_risk_timelines_path(company_root: Path | str) -> Path:
    """Get the risk timelines file path."""
    return get_risk_dir(company_root) / "risk_timelines.json"


def get_risk_assessments_path(company_root: Path | str) -> Path:
    """Get the risk assessments file path."""
    return get_risk_dir(company_root) / "risk_assessments.json"


def get_risk_validation_path(company_root: Path | str) -> Path:
    """Get the risk validation file path."""
    return get_risk_dir(company_root) / "risk_validation.json"


def get_risk_manifest_path(company_root: Path | str) -> Path:
    """Get the risk manifest file path."""
    return get_risk_dir(company_root) / "risk_manifest.json"
