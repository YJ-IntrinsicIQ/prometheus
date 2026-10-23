"""Fixture support for tests whose synthetic company carries financial evidence (a PCIM with financial sections, a truth pack): financial evidence is only usable when it is recorded against
the company's fact registries (knowledge.financials.authority_gate), so such a fixture gets the minimal registry and the record a real build would have written."""
import json
from pathlib import Path

from knowledge.financials.authority_gate import bind_company


def _minimal_registry(year="fy25"):
    fact = {"metric_id": "revenue", "metric_name": "Revenue", "fiscal_year": year, "period": year, "value": 100.0, "unit": "INR crore", "basis": "consolidated", "source_statement": "profit_and_loss",
            "source_line_item": "Revenue from operations", "source_page": 1, "availability_status": "present_direct", "usable_downstream": True, "derived": False}
    return {"available_facts": [fact], "derived_facts": [], "partial_facts": [], "missing_facts": [], "invalid_facts": [], "unreliable_facts": []}


def vouch(company_dir: Path, output_root: Path | None = None) -> None:
    company_dir = Path(company_dir)
    years = [p.name for p in sorted(company_dir.glob("fy*")) if (p / "financials").is_dir()] or ["fy25"]
    for year in years:
        registry = company_dir / year / "financials" / "financial_fact_registry.json"
        if not registry.exists():
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_text(json.dumps(_minimal_registry(year)), encoding="utf-8")
    bind_company(company_dir, output_root=output_root or company_dir.parent)


def save_vouched(path: Path, payload) -> None:
    """Write a financial artifact of a fixture company and record it (the equivalent of the pipeline's guarded write)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    company_dir = path.parent
    while company_dir.name != "company_memory" and company_dir != company_dir.parent:
        company_dir = company_dir.parent
    vouch(company_dir.parent)
