from __future__ import annotations
from pathlib import Path


def get_economic_attribution_dir(company_slug: str) -> Path:
    return Path("companies") / company_slug / "company_memory" / "economic_attribution"


def get_economic_attribution_path(company_slug: str) -> Path:
    return get_economic_attribution_dir(company_slug) / "economic_attribution_intelligence.json"


def get_economic_attribution_manifest_path(company_slug: str) -> Path:
    return get_economic_attribution_dir(company_slug) / "economic_attribution_manifest.json"
