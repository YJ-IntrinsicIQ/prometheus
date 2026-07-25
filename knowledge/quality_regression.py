from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from knowledge.artifact_audit import run_company_artifact_audit


DIMENSIONS = [
    "artifact_completeness",
    "evidence_hygiene",
    "business_identity_consistency",
    "capital_allocation_taxonomy",
    "management_context_routing",
    "pcim_freshness",
    "llm_cost_hygiene",
    "panel_readiness",
]

CHECK_TO_DIMENSIONS = {
    "raw_docs": "artifact_completeness",
    "discovery_output": "artifact_completeness",
    "extraction_output": "artifact_completeness",
    "cleaned_output": "artifact_completeness",
    "year_intelligence_output": "artifact_completeness",
    "company_level_artifact": "artifact_completeness",
    "panel_artifact": "panel_readiness",
    "multi_year_coverage": "pcim_freshness",
    "coverage_limits": "artifact_completeness",
    "evidence_hygiene": "evidence_hygiene",
    "business_identity_consistency": "business_identity_consistency",
    "capital_allocation_taxonomy": "capital_allocation_taxonomy",
    "management_context_routing": "management_context_routing",
    "pcim_freshness": "pcim_freshness",
    "llm_cost_hygiene": "llm_cost_hygiene",
    "panel_readiness": "panel_readiness",
}

DIMENSION_RECOMMENDATIONS = {
    "artifact_completeness": "Backfill missing canonical artifacts before relying on downstream quality scores.",
    "evidence_hygiene": "Tighten cleaned-output validation and remove leaked raw payload fields.",
    "business_identity_consistency": "Realign downstream artifacts to business_classification as the only authoritative DNA source.",
    "capital_allocation_taxonomy": "Review cleaned capital allocation outputs and keep non-deployment items out of true deployment groups.",
    "management_context_routing": "Separate company-controlled actions from external context before summary-layer promotion.",
    "pcim_freshness": "Rebuild multi-year memory and PCIM so company-level intelligence matches current yearly artifacts.",
    "llm_cost_hygiene": "Review input-pack manifests for missing manifests, prompt budget overruns, and forbidden payload leakage.",
    "panel_readiness": "Regenerate panel/committee artifacts only after evidence grounding and brief QA issues are resolved.",
}

OVERALL_CAP_RULES = [
    ("business identity conflict", 60),
    ("latest_business_view.business_dnas does not match", 60),
    ("source_chunk leakage detected in pcim_v1.json", 60),
    ("source_chunk leaked into", 60),
    ("PCIM source manifest freshness status: fail", 65),
    ("non-deployment item cannot be grouped as true_capital_deployment", 70),
    ("committee brief QA failed", 65),
    ("Malformed JSON", 50),
    ("Panel artifacts exist but pcim_v1.json is missing or malformed", 50),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _status_order(status: str) -> int:
    return {"pass": 0, "warning": 1, "fail": 2}.get(str(status or "pass"), 0)


def _merge_status(current: str, incoming: str) -> str:
    return incoming if _status_order(incoming) > _status_order(current) else current


def discover_companies(companies_root: Path | str = Path("companies")) -> List[str]:
    root = Path(companies_root)
    if not root.exists():
        return []
    return [
        path.name
        for path in sorted(root.iterdir())
        if path.is_dir() and not path.name.startswith(".")
    ]


def parse_company_selector(selector: str, *, companies_root: Path | str = Path("companies")) -> List[str]:
    if selector.strip().lower() == "all":
        return discover_companies(companies_root)
    requested = [item.strip() for item in selector.split(",") if item.strip()]
    return list(dict.fromkeys(requested))


def _audit_payload_for_company(
    company: str,
    *,
    companies_root: Path | str,
) -> Dict[str, Any]:
    outputs = run_company_artifact_audit(company, companies_root=companies_root, fix_safe=False)
    payload = _load_json(outputs["company_artifact_audit.json"])
    return payload if isinstance(payload, dict) else {}


def _score_dimension(
    checks: Sequence[Dict[str, Any]],
    *,
    dimension: str,
    include_panel: bool,
    panel_exists: bool,
) -> int:
    if dimension == "panel_readiness" and not include_panel and not panel_exists:
        return 100

    relevant = [
        check for check in checks
        if CHECK_TO_DIMENSIONS.get(check.get("check_name")) == dimension
    ]
    if not relevant:
        return 100 if dimension != "panel_readiness" or not include_panel else 70

    score = 100
    for check in relevant:
        status = str(check.get("status") or "pass")
        if status == "fail":
            score -= 35
        elif status == "warning":
            score -= 12
    if dimension == "artifact_completeness":
        missing_count = sum(
            1
            for check in relevant
            if str(check.get("message") or "").startswith("Missing artifact:")
        )
        score -= min(20, missing_count * 4)
    if dimension == "panel_readiness" and include_panel and not panel_exists:
        score = min(score, 70)
    return max(0, min(100, score))


def _apply_overall_caps(
    overall_score: int,
    *,
    checks: Sequence[Dict[str, Any]],
    critical_failures: Sequence[str],
) -> int:
    messages = [str(item) for item in critical_failures] + [str(check.get("message") or "") for check in checks]
    cap = 100
    for check in checks:
        check_name = str(check.get("check_name") or "")
        status = str(check.get("status") or "")
        message = str(check.get("message") or "")
        if check_name == "business_identity_consistency" and status == "fail":
            cap = min(cap, 60)
        if check_name == "pcim_freshness" and status == "fail":
            cap = min(cap, 65)
        if check_name == "capital_allocation_taxonomy" and status == "fail":
            cap = min(cap, 70)
        if check_name == "panel_readiness" and "committee brief QA failed" in message:
            cap = min(cap, 65)
        if check_name == "panel_readiness" and "pcim_v1.json is missing or malformed" in message:
            cap = min(cap, 50)
        if check_name == "evidence_hygiene" and "source_chunk leakage detected in pcim_v1.json" in message:
            cap = min(cap, 60)
        if check_name == "llm_cost_hygiene" and "source_chunk leaked into" in message:
            cap = min(cap, 60)
    for needle, max_score in OVERALL_CAP_RULES:
        if any(needle in message for message in messages):
            cap = min(cap, max_score)
    return min(overall_score, cap)


def _recommendations_for_company(
    *,
    dimension_scores: Dict[str, int],
    payload: Dict[str, Any],
) -> List[str]:
    recommendations: List[str] = list(payload.get("recommendations", []) or [])
    for dimension, score in dimension_scores.items():
        if score < 75:
            recommendation = DIMENSION_RECOMMENDATIONS[dimension]
            if recommendation not in recommendations:
                recommendations.append(recommendation)
    return recommendations[:8]


def _company_score(
    payload: Dict[str, Any],
    *,
    include_panel: bool,
) -> Dict[str, Any]:
    checks = list(payload.get("checks", []) or [])
    artifacts_checked = [str(item) for item in payload.get("artifacts_checked", []) or []]
    panel_exists = any("/investor_panel/" in item or item.endswith("investor_panel") for item in artifacts_checked)
    dimension_scores = {
        dimension: _score_dimension(
            checks,
            dimension=dimension,
            include_panel=include_panel,
            panel_exists=panel_exists,
        )
        for dimension in DIMENSIONS
    }
    overall_score = round(sum(dimension_scores.values()) / len(dimension_scores))
    overall_score = _apply_overall_caps(
        overall_score,
        checks=checks,
        critical_failures=list(payload.get("critical_failures", []) or []),
    )
    status = str(payload.get("status") or "pass")
    if overall_score < 60:
        status = "fail"
    elif overall_score < 75 and status == "pass":
        status = "warning"
    return {
        "company": payload.get("company"),
        "status": status,
        "years_detected": list(payload.get("years_detected", []) or []),
        "overall_score": overall_score,
        "dimension_scores": dimension_scores,
        "critical_failures": list(payload.get("critical_failures", []) or []),
        "warnings": list(payload.get("warnings", []) or []),
        "recommended_next_actions": _recommendations_for_company(
            dimension_scores=dimension_scores,
            payload=payload,
        ),
    }


def _score_status(score: int) -> str:
    if score >= 90:
        return "strong"
    if score >= 75:
        return "usable with warnings"
    if score >= 60:
        return "needs cleanup"
    return "unreliable"


def _build_weakest_layers(scores: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    layer_map: Dict[str, Dict[str, Any]] = {}
    for score in scores:
        company = str(score.get("company") or "")
        for dimension, value in (score.get("dimension_scores") or {}).items():
            if value >= 75:
                continue
            entry = layer_map.setdefault(
                dimension,
                {
                    "layer": dimension,
                    "issue_count": 0,
                    "affected_companies": [],
                    "recommended_fix": DIMENSION_RECOMMENDATIONS[dimension],
                },
            )
            entry["issue_count"] += 1
            if company and company not in entry["affected_companies"]:
                entry["affected_companies"].append(company)
    return sorted(layer_map.values(), key=lambda item: (-item["issue_count"], item["layer"]))


def _score_by_company(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {str(item.get("company") or ""): item for item in payload.get("scores", []) or []}


def _compare_scorecards(current: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(previous, dict):
        return {
            "baseline_available": False,
            "companies_improved": [],
            "companies_worsened": [],
            "new_failures": [],
            "resolved_failures": [],
            "recurring_warnings": [],
        }
    current_scores = _score_by_company(current)
    previous_scores = _score_by_company(previous)
    improved: List[str] = []
    worsened: List[str] = []
    new_failures: List[str] = []
    resolved_failures: List[str] = []
    recurring_warnings: List[str] = []

    companies = sorted(set(current_scores) | set(previous_scores))
    for company in companies:
        now = current_scores.get(company, {})
        old = previous_scores.get(company, {})
        now_score = int(now.get("overall_score") or 0)
        old_score = int(old.get("overall_score") or 0)
        if now and old:
            if now_score > old_score:
                improved.append(company)
            elif now_score < old_score:
                worsened.append(company)
        now_failures = set(now.get("critical_failures", []) or [])
        old_failures = set(old.get("critical_failures", []) or [])
        for item in sorted(now_failures - old_failures):
            new_failures.append(f"{company}: {item}")
        for item in sorted(old_failures - now_failures):
            resolved_failures.append(f"{company}: {item}")
        now_warnings = set(now.get("warnings", []) or [])
        old_warnings = set(old.get("warnings", []) or [])
        for item in sorted(now_warnings & old_warnings):
            recurring_warnings.append(f"{company}: {item}")

    return {
        "baseline_available": True,
        "companies_improved": improved,
        "companies_worsened": worsened,
        "new_failures": new_failures,
        "resolved_failures": resolved_failures,
        "recurring_warnings": recurring_warnings,
    }


def render_quality_scorecard_markdown(payload: Dict[str, Any]) -> str:
    comparison = payload.get("trend_comparison") or {}
    lines = [
        "# Prometheus Quality Regression Report",
        "",
        f"- Generated at: `{payload.get('generated_at', '')}`",
        f"- Overall status: `{payload.get('overall_status', '')}`",
        f"- Companies evaluated: {len(payload.get('companies_evaluated', []))}",
        "",
        "## Company Score Table",
        "",
        "| Company | Status | Score | Tier | Years |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for score in payload.get("scores", []):
        lines.append(
            f"| {score['company']} | {score['status']} | {score['overall_score']} | "
            f"{_score_status(score['overall_score'])} | {', '.join(score.get('years_detected', [])) or 'None'} |"
        )

    lines.extend(["", "## Weakest Layers", ""])
    weakest = payload.get("weakest_layers", []) or []
    if weakest:
        for item in weakest:
            lines.append(
                f"- `{item['layer']}`: {item['issue_count']} issue(s) across "
                f"{', '.join(item.get('affected_companies', []))}. {item['recommended_fix']}"
            )
    else:
        lines.append("- No recurring weak layers were detected.")

    lines.extend(["", "## Critical Failures", ""])
    criticals = []
    for score in payload.get("scores", []):
        for failure in score.get("critical_failures", []):
            criticals.append(f"- {score['company']}: {failure}")
    lines.extend(criticals or ["- No critical failures recorded."])

    lines.extend(["", "## Recently Resolved Issues", ""])
    lines.extend([f"- {item}" for item in comparison.get("resolved_failures", [])] or ["- No resolved failures recorded."])

    lines.extend(["", "## Regression Warnings", ""])
    regression_items = [f"- {item}" for item in comparison.get("new_failures", []) + comparison.get("recurring_warnings", [])]
    lines.extend(regression_items or ["- No new regression warnings recorded."])

    lines.extend(["", "## Recommended Next Engineering Tasks", ""])
    suggested: List[str] = []
    for item in weakest[:5]:
        recommendation = item.get("recommended_fix")
        if recommendation and recommendation not in suggested:
            suggested.append(recommendation)
    for score in payload.get("scores", []):
        for action in score.get("recommended_next_actions", []):
            if action not in suggested:
                suggested.append(action)
    lines.extend([f"- {item}" for item in suggested[:10]] or ["- No additional engineering tasks suggested."])
    lines.append("")
    return "\n".join(lines)


def _archive_previous_scorecard(reports_dir: Path, baseline: Dict[str, Any]) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = reports_dir / f"prometheus_quality_scorecard.{timestamp}.json"
    _write_json(archive_path, baseline)


def run_quality_regression(
    *,
    companies: Sequence[str],
    companies_root: Path | str = Path("companies"),
    reports_root: Path | str = Path("reports") / "quality",
    include_panel: bool = False,
) -> Dict[str, Path]:
    companies_root = Path(companies_root)
    reports_dir = Path(reports_root)
    current_path = reports_dir / "prometheus_quality_scorecard.json"
    previous_path = reports_dir / "prometheus_quality_scorecard.previous.json"
    baseline = _load_json(current_path)
    if isinstance(baseline, dict):
        _archive_previous_scorecard(reports_dir, baseline)
        _write_json(previous_path, baseline)
    else:
        baseline = _load_json(previous_path)

    scores: List[Dict[str, Any]] = []
    statuses = {"pass": 0, "warning": 0, "fail": 0}
    overall_status = "pass"

    for company in companies:
        audit_payload = _audit_payload_for_company(company, companies_root=companies_root)
        if not audit_payload:
            continue
        score = _company_score(audit_payload, include_panel=include_panel)
        scores.append(score)
        statuses[score["status"]] += 1
        overall_status = _merge_status(overall_status, score["status"])

    payload = {
        "generated_at": _now_iso(),
        "companies_evaluated": [score["company"] for score in scores],
        "overall_status": overall_status,
        "summary": {
            "companies_total": len(scores),
            "pass": statuses["pass"],
            "warning": statuses["warning"],
            "fail": statuses["fail"],
        },
        "scores": scores,
        "weakest_layers": _build_weakest_layers(scores),
        "trend_comparison": _compare_scorecards({"scores": scores}, baseline),
    }

    json_path = _write_json(current_path, payload)
    md_path = _write_text(reports_dir / "prometheus_quality_scorecard.md", render_quality_scorecard_markdown(payload))
    return {
        "prometheus_quality_scorecard.json": json_path,
        "prometheus_quality_scorecard.md": md_path,
    }
