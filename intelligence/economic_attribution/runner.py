"""CLI runner for economic attribution intelligence (ENG-135).

Usage:
    python -m intelligence.economic_attribution.runner <company_slug>

Reads from canonical company-memory sources; writes economic_attribution_intelligence.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .builder import build_economic_attribution_intelligence
from .paths import get_economic_attribution_dir, get_economic_attribution_path


def run(company_slug: str) -> Path:
    base = Path("companies") / company_slug / "company_memory"
    cao_path = base / "capital_allocation_outcomes" / "capital_allocation_outcomes.json"
    mp_path = base / "management_progression" / "management_progression.json"
    gold_risk_path = base / "gold" / "risk_evolution_timeline.json"
    ftp_path = base / "financial_truth_pack.json"

    result = build_economic_attribution_intelligence(cao_path, mp_path, gold_risk_path, ftp_path)

    out_dir = get_economic_attribution_dir(company_slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = get_economic_attribution_path(company_slug)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

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
    manifest_path = out_dir / "economic_attribution_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else "sun_pharma"
    path = run(slug)
    print(f"Written: {path}")
