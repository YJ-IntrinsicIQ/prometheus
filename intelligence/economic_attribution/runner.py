"""CLI runner for economic attribution intelligence (ENG-135).

Usage:
    python -m intelligence.economic_attribution.runner <company_slug>

Reads from canonical company-memory sources; writes economic_attribution_intelligence.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from typing import Dict

from core.context_paths import guarded_write_text, resolve_output_root, safe_destination

from .builder import build_economic_attribution_intelligence
from .paths import get_economic_attribution_dir, get_economic_attribution_manifest_path, get_economic_attribution_path


def plan_outputs(company_slug: str, companies_root: Path | str, *, authorize_served_write: bool = False) -> Dict[str, Path]:
    """The exact files run() would write. Read-only: nothing is created."""
    root = resolve_output_root(companies_root, authorize_served=authorize_served_write)
    return {
        "economic_attribution_intelligence.json": safe_destination(root, get_economic_attribution_path(company_slug, root)),
        "economic_attribution_manifest.json": safe_destination(root, get_economic_attribution_manifest_path(company_slug, root)),
    }


def run(company_slug: str, companies_root: Path | str, *, authorize_served_write: bool = False) -> Path:
    root = resolve_output_root(companies_root, authorize_served=authorize_served_write)
    base = root / company_slug / "company_memory"
    cao_path = base / "capital_allocation_outcomes" / "capital_allocation_outcomes.json"
    mp_path = base / "management_progression" / "management_progression.json"
    gold_risk_path = base / "gold" / "risk_evolution_timeline.json"
    ftp_path = base / "financial_truth_pack.json"

    result = build_economic_attribution_intelligence(cao_path, mp_path, gold_risk_path, ftp_path)

    out_path = guarded_write_text(root, get_economic_attribution_path(company_slug, root), json.dumps(result, indent=2, ensure_ascii=False))

    manifest = {
        "company": company_slug,
        "generated_at": result["generated_at"],
        "schema_version": result["schema_version"],
        "total_cases": result["attribution_summary"]["total_cases"],
        "directly_attributable": result["attribution_summary"]["directly_attributable"],
        "associated_not_attributable": result["attribution_summary"]["associated_not_attributable"],
        "no_outcome_evidence": result["attribution_summary"]["no_outcome_evidence"],
        "attribution_unknown": result["attribution_summary"]["attribution_unknown"],
    }
    guarded_write_text(root, get_economic_attribution_manifest_path(company_slug, root), json.dumps(manifest, indent=2))
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Economic attribution runner. There is no default company and no default output root.")
    parser.add_argument("company_slug")
    parser.add_argument("--companies-root", required=True, help="absolute output root")
    parser.add_argument("--authorize-served-write", action="store_true", help="required only when the root is the served companies/ tree")
    parser.add_argument("--dry-run", action="store_true", help="print the exact destinations and write nothing")
    args = parser.parse_args()
    if args.dry_run:
        for name, dest in plan_outputs(args.company_slug, args.companies_root, authorize_served_write=args.authorize_served_write).items():
            print(f"{name} -> {dest}")
    else:
        print(f"Written: {run(args.company_slug, args.companies_root, authorize_served_write=args.authorize_served_write)}")
