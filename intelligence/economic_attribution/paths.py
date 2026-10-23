from __future__ import annotations
from pathlib import Path


def get_economic_attribution_dir(company_slug: str, companies_root: Path | str) -> Path:
    """Always under the explicit companies_root (no default, no fallback to ./companies)."""
    return Path(companies_root) / company_slug / "company_memory" / "economic_attribution"


def get_economic_attribution_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_economic_attribution_dir(company_slug, companies_root) / "economic_attribution_intelligence.json"


def get_economic_attribution_manifest_path(company_slug: str, companies_root: Path | str) -> Path:
    return get_economic_attribution_dir(company_slug, companies_root) / "economic_attribution_manifest.json"
