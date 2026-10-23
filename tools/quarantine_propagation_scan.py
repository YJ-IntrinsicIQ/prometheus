"""Does any figure the Financial Fact Registry rejected survive anywhere downstream?

For every company/year of a candidate tree: the rejected figures are the registry's invalid / unreliable facts and the normalized file's `registry_exclusions`. Every other JSON artifact
of the company (CIM, PCIM, financial memory, trends, ratios, growth, quality summary, truth pack, investor modules, capital-allocation outcomes ...) is searched for an object that names the
metric and carries the rejected value for that year. The registry's own records of the rejection (registry, reconciliation, quarantine reports, the exclusion block, the truth pack's
invalid / unreliable lists, raw extraction evidence) are the only places a rejected figure may appear, and only as rejected.

The same figures are also pushed through the investor panel's real metric registry (`_build_financial_metric_registry`) built from the candidate PCIM.

Structural, not textual: a point is judged by its PARENT metric identity (the `metric` field of an ancestor or the metric-named key of a mapping, so `metric_series/total_debt/3` and
`balance_sheet_strength_inputs/metrics/2/series/2` are attributed to their metric) and its fiscal year, never by its number alone; there is no monetary cut-off (every rejected fact is
scanned, small ones included). A point carrying a rejected value is classified:
  leak                    the point carries the rejected value as usable evidence (no unusable flag);
  flagged_diagnostic      the point carries it but says it is unusable (usable_downstream false / invalid / unreliable) - a record of the rejection, not evidence;
  independent_comparative a later year's report states the same number for the earlier year - a separate source, listed for review, not a leak.
A legitimate fact that merely shares the number with a rejected fact of a DIFFERENT metric or year is never reported.

Usage: python3 tools/quarantine_propagation_scan.py <candidate_companies_root> <out.json>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ALLOWED_RECORDS = ("financial_fact_registry.json", "financial_truth_reconciliation_report.json", "financial_artifact_quarantine_report.json", "raw_financial_tables.json",
                   "financial_discovery.json", "financial_extraction_rejections.json", "financial_extraction_readiness.json", "financial_anchor_coverage.json", "clean_chunks_rechunked.json",
                   "clean_chunks.json", "raw_baseline.json", "financial_headline_metrics.json")
REJECTION_LISTS = {"invalid_or_quarantined_metrics", "unreliable_metrics", "registry_exclusions", "invalid_facts", "unreliable_facts", "quarantined_facts", "invalid_metrics",
                   "unreliable_financial_inputs", "invalid_or_quarantined_financial_inputs", "downstream_blockers", "registry_warnings", "withheld_metrics"}


def rejected_figures(companies_root: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for registry_path in sorted(Path(companies_root).glob("*/fy*/financials/financial_fact_registry.json")):
        company, fy = registry_path.parents[2].name, registry_path.parents[1].name
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        for key in ("invalid_facts", "unreliable_facts"):
            for fact in registry.get(key) or []:
                if isinstance(fact.get("value"), (int, float)) and not fact.get("usable_downstream"):
                    out.append({"company": company, "fy": fy, "metric": fact["metric_id"], "value": float(fact["value"]), "line": fact.get("source_line_item"), "why": (fact.get("warnings") or [""])[-1][:160]})
        try:
            normalized = json.loads((registry_path.parent / "normalized_fundamentals.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            normalized = {}
        for metric, record in (normalized.get("registry_exclusions") or {}).items():
            value = (record.get("entry") or {}).get("value_crore")
            if isinstance(value, (int, float)):
                out.append({"company": company, "fy": fy, "metric": metric, "value": float(value), "line": (record.get("entry") or {}).get("source_line_item"), "why": (record.get("reasons") or [""])[-1][:160]})
    seen, unique = set(), []
    for r in out:
        key = (r["company"], r["fy"], r["metric"], round(r["value"], 4))
        if key not in seen:
            seen.add(key); unique.append(r)
    return unique


def _unusable(holder: Dict[str, Any]) -> bool:
    return holder.get("usable_downstream") is False or str(holder.get("availability_status") or "") in {"invalid", "unreliable"} or bool(holder.get("withheld_by_authority")) \
        or str(holder.get("verification_status") or "") == "REJECTED"


def _same(a: float, b: float) -> bool:
    return abs(abs(a) - abs(b)) <= 1e-6 * max(1.0, abs(b)) + 1e-9


def scan(companies_root: Path) -> Dict[str, Any]:
    from knowledge.financials.authority_gate import iter_metric_points, load_company_authority, known_metrics
    rejected = rejected_figures(companies_root)
    leaks: List[Dict[str, Any]] = []
    flagged: List[Dict[str, Any]] = []
    comparatives: List[Dict[str, Any]] = []
    by_company: Dict[str, List[Dict[str, Any]]] = {}
    for r in rejected:
        by_company.setdefault(r["company"], []).append(r)
    artifacts = points = 0
    for company, figures in by_company.items():
        known = known_metrics(load_company_authority(Path(companies_root) / company)) | {f["metric"] for f in figures}
        for path in sorted((Path(companies_root) / company).rglob("*.json")):
            if path.name in ALLOWED_RECORDS or path.name == "authority_manifest.json":
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            artifacts += 1
            rel = str(path.relative_to(companies_root))
            fy_of_path = next((p for p in path.parts if re.fullmatch(r"fy\d\d", p)), "")
            for where, metric, year, holder, key in iter_metric_points(payload, year=fy_of_path, known=frozenset(known)):
                points += 1
                for fig in figures:
                    if metric != fig["metric"] or not _same(float(holder[key]), fig["value"]):
                        continue
                    if (year and year != fig["fy"]) or ("/comparatives" in where and fy_of_path and fy_of_path != fig["fy"]):
                        # a LATER year's report states the same number for the earlier year as its comparative column: a separate source, listed for review
                        comparatives.append({**fig, "artifact": rel, "where": where, "point_year": year})
                        continue
                    record = {**fig, "artifact": rel, "where": where}
                    (flagged if _unusable(holder) else leaks).append(record)
    return {"rejected_figures": len(rejected), "artifacts_scanned": artifacts, "points_examined": points, "leaks": leaks, "flagged_diagnostics": len(flagged),
            "independent_comparatives": comparatives, "rejected": rejected}


def panel_registry_leaks(companies_root: Path) -> Dict[str, Any]:
    """Build the investor panel's REAL financial metric registry from each candidate PCIM and look for any rejected figure in it."""
    from intelligence.investor_panel import runner
    rejected = rejected_figures(companies_root)
    leaks, sizes = [], {}
    for company in sorted({r["company"] for r in rejected} | {p.parent.parent.name for p in Path(companies_root).glob("*/company_memory/pcim_v1.json")}):
        pcim_path = Path(companies_root) / company / "company_memory" / "pcim_v1.json"
        if not pcim_path.exists():
            continue
        pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
        registry = runner._build_financial_metric_registry(pcim, list(pcim.keys()))
        sizes[company] = len(registry)
        for entry in registry:
            for fig in (r for r in rejected if r["company"] == company):
                text = json.dumps(entry, default=str)
                if fig["fy"] in text and fig["metric"] in text.lower() and any(abs(abs(float(v)) - abs(fig["value"])) <= 1e-6 * max(1.0, abs(fig["value"])) for v in [entry.get("value"), entry.get("numeric_value")] if isinstance(v, (int, float))):
                    leaks.append({**fig, "metric_id": entry.get("metric_id")})
    return {"panel_registry_sizes": sizes, "leaks": leaks}


if __name__ == "__main__":
    root = Path(sys.argv[1])
    report = {"scan": scan(root), "panel_registry": panel_registry_leaks(root)}
    Path(sys.argv[2]).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({"rejected": report["scan"]["rejected_figures"], "artifacts": report["scan"]["artifacts_scanned"], "leaks": len(report["scan"]["leaks"]), "panel_leaks": len(report["panel_registry"]["leaks"])}, indent=1))
