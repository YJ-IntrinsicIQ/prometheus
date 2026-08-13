from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .financial_memory_truth import build_financial_memory_manifest, build_financial_truth_pack
from .quality_schema import (
    DeterministicFinancialQualitySection,
    FinancialQualitySummary,
    QualitySection,
    YearFinancialQualitySummary,
    validate_financial_quality_payload,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _trend_series(payload: Dict[str, Any], container: str, metric: str) -> List[Dict[str, Any]]:
    section = payload.get(container, {})
    item = section.get(metric, {}) if isinstance(section, dict) else {}
    series = item.get("series", []) if isinstance(item, dict) else []
    return series if isinstance(series, list) else []


def _growth_points(payload: Dict[str, Any], metric: str) -> List[Dict[str, Any]]:
    section = payload.get("growth_summary", {})
    items = section.get(metric, []) if isinstance(section, dict) else []
    return items if isinstance(items, list) else []


def _timeline(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = payload.get("corporate_actions_timeline", [])
    return items if isinstance(items, list) else []


def _latest_value(series: Sequence[Dict[str, Any]]) -> Optional[float]:
    for item in reversed(series):
        value = item.get("value")
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _first_value(series: Sequence[Dict[str, Any]]) -> Optional[float]:
    for item in series:
        value = item.get("value")
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _delta(series: Sequence[Dict[str, Any]]) -> Optional[float]:
    first = _first_value(series)
    latest = _latest_value(series)
    if first is None or latest is None:
        return None
    return latest - first


def _latest_growth(points: Sequence[Dict[str, Any]]) -> Optional[float]:
    for item in reversed(points):
        value = item.get("growth_percent")
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _quality_from_scores(strengths: int, weaknesses: int, *, insufficient: bool = False) -> str:
    if insufficient:
        return "insufficient_data"
    if strengths >= 2 and weaknesses == 0:
        return "strong"
    if strengths >= 1 and weaknesses == 0:
        return "adequate"
    if weaknesses >= 2 and strengths == 0:
        return "weak"
    if strengths == 0 and weaknesses == 1:
        return "weak"
    return "mixed"


def _section(summary: str, status: str, signals=None, warnings=None, metrics=None) -> QualitySection:
    return QualitySection(
        status=status,
        summary=summary,
        signals=list(signals or []),
        warnings=list(warnings or []),
        metrics=dict(metrics or {}),
    )


def _build_growth_quality(payload: Dict[str, Any], years: Sequence[str]) -> Tuple[QualitySection, List[str], List[str], List[str]]:
    positives: List[str] = []
    red_flags: List[str] = []
    missing: List[str] = []
    warnings: List[str] = []
    revenue_growth = _latest_growth(_growth_points(payload, "revenue"))
    pat_growth = _latest_growth(_growth_points(payload, "pat"))
    eps_growth = _latest_growth(_growth_points(payload, "eps_basic"))
    bvps_growth = _latest_growth(_growth_points(payload, "book_value_per_share"))
    revenue_series = _trend_series(payload, "metric_trends", "revenue")
    pat_series = _trend_series(payload, "metric_trends", "pat")
    share_count_series = _trend_series(payload, "per_share_trends", "share_count")

    if len(years) < 2:
        _append_unique(missing, "multi-year growth history unavailable")
        return _section(
            "Only one year of data is available, so trend quality cannot be judged confidently.",
            "insufficient_data",
            warnings=["only one financial year available"],
            metrics={
                "revenue_growth": revenue_growth,
                "pat_growth": pat_growth,
                "eps_growth": eps_growth,
                "book_value_per_share_growth": bvps_growth,
            },
        ), positives, red_flags, missing

    strengths = 0
    weaknesses = 0
    if revenue_growth is None:
        _append_unique(missing, "revenue growth missing")
    elif revenue_growth > 12:
        strengths += 1
        _append_unique(positives, "Revenue growth is healthy.")
    elif revenue_growth < 0:
        weaknesses += 1
        _append_unique(red_flags, "Revenue declined.")

    if pat_growth is None:
        _append_unique(missing, "PAT growth missing")
    elif pat_growth > 12:
        strengths += 1
        _append_unique(positives, "PAT growth is healthy.")
    elif pat_growth < 0:
        weaknesses += 1
        _append_unique(red_flags, "PAT declined.")

    if eps_growth is None:
        _append_unique(missing, "EPS growth missing")
    if bvps_growth is None:
        _append_unique(missing, "book value per share growth missing")

    if pat_growth is not None and eps_growth is not None and pat_growth > eps_growth + 10:
        weaknesses += 1
        _append_unique(red_flags, "Per-share growth is lagging absolute profit growth.")
        _append_unique(warnings, "PAT growth outpaced EPS growth by a wide margin")

    share_count_delta = _delta(share_count_series)
    if share_count_delta is not None and share_count_delta > 0:
        _append_unique(warnings, "share count increased across the observed period")

    status = _quality_from_scores(strengths, weaknesses)
    summary = "Growth quality is mixed."
    if status == "strong":
        summary = "Growth quality looks strong across the observed period."
    elif status == "adequate":
        summary = "Growth quality looks broadly adequate."
    elif status == "weak":
        summary = "Growth quality looks weak."
    return _section(
        summary,
        status,
        signals=positives,
        warnings=warnings,
        metrics={
            "revenue_growth": revenue_growth,
            "pat_growth": pat_growth,
            "eps_growth": eps_growth,
            "book_value_per_share_growth": bvps_growth,
            "share_count_change": share_count_delta,
            "revenue_points": len(revenue_series),
            "pat_points": len(pat_series),
        },
    ), positives, red_flags, missing


def _build_margin_quality(payload: Dict[str, Any], years: Sequence[str]) -> Tuple[QualitySection, List[str], List[str], List[str]]:
    positives: List[str] = []
    red_flags: List[str] = []
    missing: List[str] = []
    warnings: List[str] = []
    opm_series = _trend_series(payload, "margin_trends", "opm")
    ebitda_series = _trend_series(payload, "margin_trends", "ebitda_margin")
    npm_series = _trend_series(payload, "margin_trends", "npm")
    if len(years) < 2 or (not opm_series and not ebitda_series and not npm_series):
        _append_unique(missing, "margin trend history unavailable")
        return _section(
            "Margin quality cannot be judged well with the current trend coverage.",
            "insufficient_data",
            warnings=["margin history missing or incomplete"],
            metrics={"opm_change": None, "ebitda_margin_change": None, "npm_change": None},
        ), positives, red_flags, missing

    opm_change = _delta(opm_series)
    ebitda_change = _delta(ebitda_series)
    npm_change = _delta(npm_series)
    strengths = 0
    weaknesses = 0
    for label, change in (("OPM", opm_change), ("EBITDA margin", ebitda_change), ("NPM", npm_change)):
        if change is None:
            _append_unique(missing, f"{label} trend missing")
            continue
        if change > 1.0:
            strengths += 1
            _append_unique(positives, f"{label} improved.")
        elif change < -1.0:
            weaknesses += 1
            _append_unique(red_flags, f"{label} deteriorated.")
    status = _quality_from_scores(strengths, weaknesses)
    summary = "Margin quality is mixed."
    if status == "strong":
        summary = "Margins improved across the observed period."
    elif status == "adequate":
        summary = "Margins are stable to improving."
    elif status == "weak":
        summary = "Margins weakened across the observed period."
    return _section(
        summary,
        status,
        signals=positives,
        warnings=warnings,
        metrics={"opm_change": opm_change, "ebitda_margin_change": ebitda_change, "npm_change": npm_change},
    ), positives, red_flags, missing


def _build_return_quality(payload: Dict[str, Any], years: Sequence[str]) -> Tuple[QualitySection, List[str], List[str], List[str]]:
    positives: List[str] = []
    red_flags: List[str] = []
    missing: List[str] = []
    roe_series = _trend_series(payload, "return_trends", "roe")
    roce_series = _trend_series(payload, "return_trends", "roce")
    roa_series = _trend_series(payload, "return_trends", "roa")
    if len(years) < 2 or (not roe_series and not roce_series and not roa_series):
        _append_unique(missing, "return-on-capital trend history unavailable")
        return _section(
            "Return quality cannot be judged well with the current trend coverage.",
            "insufficient_data",
            warnings=["ROE/ROCE/ROA history missing or incomplete"],
            metrics={"roe_change": None, "roce_change": None, "roa_change": None},
        ), positives, red_flags, missing

    roe_change = _delta(roe_series)
    roce_change = _delta(roce_series)
    roa_change = _delta(roa_series)
    strengths = 0
    weaknesses = 0
    if roce_change is None:
        _append_unique(missing, "ROCE unavailable")
    elif roce_change > 1.0:
        strengths += 1
        _append_unique(positives, "ROCE improved.")
    elif roce_change < -1.0:
        weaknesses += 1
        _append_unique(red_flags, "ROCE weakened.")
    if roe_change is not None and roe_change > 1.0:
        strengths += 1
    elif roe_change is not None and roe_change < -1.0:
        weaknesses += 1
    if roa_change is not None and roa_change < -1.0:
        weaknesses += 1
    status = _quality_from_scores(strengths, weaknesses)
    summary = "Return quality is mixed."
    if status == "strong":
        summary = "Returns on capital are improving."
    elif status == "adequate":
        summary = "Returns on capital look acceptable."
    elif status == "weak":
        summary = "Returns on capital look weak or deteriorating."
    return _section(
        summary,
        status,
        signals=positives,
        warnings=[],
        metrics={"roe_change": roe_change, "roce_change": roce_change, "roa_change": roa_change},
    ), positives, red_flags, missing


def _build_cash_conversion_quality(payload: Dict[str, Any], years: Sequence[str]) -> Tuple[QualitySection, List[str], List[str], List[str]]:
    positives: List[str] = []
    red_flags: List[str] = []
    missing: List[str] = []
    warnings: List[str] = []
    cfo_pat_series = _trend_series(payload, "cash_conversion_trends", "cfo_to_pat")
    fcf_pat_series = _trend_series(payload, "cash_conversion_trends", "fcf_to_pat")
    fcf_series = _trend_series(payload, "cash_conversion_trends", "fcf")
    capex_series = _trend_series(payload, "cash_conversion_trends", "capex")
    dividend_series = _trend_series(payload, "per_share_trends", "dividend_per_share")

    cfo_pat = _latest_value(cfo_pat_series)
    fcf_pat = _latest_value(fcf_pat_series)
    latest_fcf = _latest_value(fcf_series)
    latest_capex = _latest_value(capex_series)
    latest_dividend = _latest_value(dividend_series)

    if cfo_pat is None:
        _append_unique(missing, "CFO/PAT missing")
    if latest_fcf is None:
        _append_unique(missing, "FCF missing")
    if len(years) < 2:
        _append_unique(warnings, "only one financial year available")
    if cfo_pat is None and latest_fcf is None:
        return _section(
            "Cash conversion quality is hard to judge because CFO/FCF coverage is incomplete.",
            "insufficient_data",
            warnings=warnings,
            metrics={"cfo_to_pat": cfo_pat, "fcf_to_pat": fcf_pat, "fcf": latest_fcf, "capex": latest_capex},
        ), positives, red_flags, missing

    strengths = 0
    weaknesses = 0
    if cfo_pat is not None and cfo_pat >= 100:
        strengths += 1
        _append_unique(positives, "Operating cash flow is backing reported profit.")
    elif cfo_pat is not None and cfo_pat < 80:
        weaknesses += 1
        _append_unique(red_flags, "Operating cash flow is weak relative to profit.")
    if fcf_pat is not None and fcf_pat >= 50:
        strengths += 1
        _append_unique(positives, "Free cash flow conversion looks healthy.")
    elif fcf_pat is not None and fcf_pat < 0:
        weaknesses += 1
        _append_unique(red_flags, "Free cash flow conversion is negative.")
    if latest_dividend is not None and (latest_fcf is None or latest_fcf <= 0):
        weaknesses += 1
        _append_unique(red_flags, "Dividend is not clearly backed by free cash flow.")
        _append_unique(warnings, "dividend is present without positive FCF support")
    status = _quality_from_scores(strengths, weaknesses, insufficient=(cfo_pat is None and fcf_pat is None))
    summary = "Cash conversion quality is mixed."
    if status == "strong":
        summary = "Cash conversion looks strong."
    elif status == "adequate":
        summary = "Cash conversion looks broadly adequate."
    elif status == "weak":
        summary = "Cash conversion looks weak."
    return _section(
        summary,
        status,
        signals=positives,
        warnings=warnings,
        metrics={"cfo_to_pat": cfo_pat, "fcf_to_pat": fcf_pat, "fcf": latest_fcf, "capex": latest_capex},
    ), positives, red_flags, missing


def _build_balance_sheet_strength(payload: Dict[str, Any]) -> Tuple[QualitySection, List[str], List[str], List[str]]:
    positives: List[str] = []
    red_flags: List[str] = []
    missing: List[str] = []
    debt_series = _trend_series(payload, "balance_sheet_trends", "total_debt")
    debt_equity_series = _trend_series(payload, "balance_sheet_trends", "debt_to_equity")
    net_debt_series = _trend_series(payload, "balance_sheet_trends", "net_debt")
    cash_series = _trend_series(payload, "balance_sheet_trends", "cash_and_equivalents")
    reserves_series = _trend_series(payload, "balance_sheet_trends", "reserves")

    debt_change = _delta(debt_series)
    debt_equity = _latest_value(debt_equity_series)
    net_debt = _latest_value(net_debt_series)
    cash_balance = _latest_value(cash_series)
    reserves_change = _delta(reserves_series)

    strengths = 0
    weaknesses = 0
    if debt_change is not None and debt_change < 0:
        strengths += 1
        _append_unique(positives, "Debt has reduced across the observed period.")
    elif debt_change is not None and debt_change > 0:
        weaknesses += 1
        _append_unique(red_flags, "Debt has risen across the observed period.")
    if debt_equity is None:
        _append_unique(missing, "debt-to-equity missing")
    elif debt_equity > 100:
        weaknesses += 1
        _append_unique(red_flags, "Leverage is elevated.")
    elif debt_equity < 50:
        strengths += 1
        _append_unique(positives, "Leverage looks moderate.")
    if net_debt is not None and net_debt < 0:
        strengths += 1
        _append_unique(positives, "Net cash position is supportive.")
    if reserves_change is not None and reserves_change > 0:
        strengths += 1
    status = _quality_from_scores(strengths, weaknesses, insufficient=(not debt_series and debt_equity is None))
    summary = "Balance sheet strength is mixed."
    if status == "strong":
        summary = "Balance sheet strength looks healthy."
    elif status == "adequate":
        summary = "Balance sheet strength looks adequate."
    elif status == "weak":
        summary = "Balance sheet strength looks weak."
    return _section(
        summary,
        status,
        signals=positives,
        warnings=[],
        metrics={
            "debt_change": debt_change,
            "debt_to_equity": debt_equity,
            "net_debt": net_debt,
            "cash_balance": cash_balance,
            "reserves_change": reserves_change,
        },
    ), positives, red_flags, missing


def _build_working_capital_quality(payload: Dict[str, Any]) -> Tuple[QualitySection, List[str], List[str], List[str]]:
    positives: List[str] = []
    red_flags: List[str] = []
    missing: List[str] = []
    warnings: List[str] = []
    receivables_series = _trend_series(payload, "cash_conversion_trends", "receivables")
    inventory_series = _trend_series(payload, "cash_conversion_trends", "inventory")
    ccc_series = _trend_series(payload, "cash_conversion_trends", "cash_conversion_cycle")
    receivable_days_series = _trend_series(payload, "cash_conversion_trends", "receivable_days")
    revenue_series = _trend_series(payload, "metric_trends", "revenue")

    if not receivables_series and not inventory_series and not ccc_series:
        _append_unique(missing, "working capital trend data missing")
        return _section(
            "Working-capital quality cannot be judged with the current data.",
            "insufficient_data",
            warnings=[],
            metrics={},
        ), positives, red_flags, missing

    strengths = 0
    weaknesses = 0
    receivables_growth_abs = _delta(receivables_series)
    revenue_growth_abs = _delta(revenue_series)
    ccc_change = _delta(ccc_series)
    receivable_days_change = _delta(receivable_days_series)
    if receivables_growth_abs is not None and revenue_growth_abs is not None and receivables_growth_abs > revenue_growth_abs:
        weaknesses += 1
        _append_unique(red_flags, "Receivables are growing faster than revenue.")
        _append_unique(warnings, "receivables growth is outpacing revenue growth")
    if ccc_change is not None and ccc_change < 0:
        strengths += 1
        _append_unique(positives, "Cash conversion cycle improved.")
    elif ccc_change is not None and ccc_change > 5:
        weaknesses += 1
        _append_unique(red_flags, "Cash conversion cycle worsened.")
    if receivable_days_change is not None and receivable_days_change > 5:
        weaknesses += 1
    status = _quality_from_scores(strengths, weaknesses)
    summary = "Working-capital quality is mixed."
    if status == "strong":
        summary = "Working-capital pressure looks controlled."
    elif status == "adequate":
        summary = "Working-capital quality looks acceptable."
    elif status == "weak":
        summary = "Working-capital pressure looks elevated."
    return _section(
        summary,
        status,
        signals=positives,
        warnings=warnings,
        metrics={
            "receivables_change": receivables_growth_abs,
            "revenue_change": revenue_growth_abs,
            "cash_conversion_cycle_change": ccc_change,
            "receivable_days_change": receivable_days_change,
        },
    ), positives, red_flags, missing


def _build_dilution_quality(payload: Dict[str, Any]) -> Tuple[QualitySection, List[str], List[str], List[str]]:
    positives: List[str] = []
    red_flags: List[str] = []
    missing: List[str] = []
    warnings: List[str] = []
    share_count_series = _trend_series(payload, "per_share_trends", "share_count")
    eps_basic_growth = _latest_growth(_growth_points(payload, "eps_basic"))
    pat_growth = _latest_growth(_growth_points(payload, "pat"))
    timeline = _timeline(payload)
    share_count_change = _delta(share_count_series)

    action_types = [str(item.get("action_type", "")) for item in timeline if isinstance(item, dict)]
    if "qip" in action_types or "preferential_issue" in action_types:
        _append_unique(red_flags, "Dilution-linked corporate actions are present.")
        _append_unique(warnings, "QIP or preferential issuance affects comparability")
    if "buyback" in action_types:
        _append_unique(positives, "Buyback activity is present.")
    if any(action in action_types for action in ("stock_split", "bonus_issue")):
        _append_unique(warnings, "Split or bonus issue affects per-share comparability")
    if share_count_change is not None and share_count_change > 0:
        _append_unique(red_flags, "Share count has increased.")
    if pat_growth is not None and eps_basic_growth is not None and eps_basic_growth + 5 < pat_growth:
        _append_unique(red_flags, "EPS growth is lagging PAT growth, which may indicate dilution.")
        _append_unique(warnings, "per-share growth lags profit growth")
    status = _quality_from_scores(len(positives), len(red_flags), insufficient=(not timeline and share_count_change is None))
    summary = "Dilution and corporate-action quality is mixed."
    if status == "strong":
        summary = "Corporate-action signals are not creating obvious dilution pressure."
    elif status == "weak":
        summary = "Dilution and comparability risks need attention."
    elif status == "insufficient_data":
        summary = "Dilution quality cannot be judged with the current data."
    return _section(
        summary,
        status,
        signals=positives,
        warnings=warnings,
        metrics={"share_count_change": share_count_change, "action_types": action_types},
    ), positives, red_flags, missing


def _build_ownership_quality(payload: Dict[str, Any]) -> Tuple[QualitySection, List[str], List[str], List[str]]:
    positives: List[str] = []
    red_flags: List[str] = []
    missing: List[str] = []
    promoter_series = _trend_series(payload, "ownership_trends", "promoter_holding")
    pledge_series = _trend_series(payload, "ownership_trends", "pledged_promoter_holding")
    fii_series = _trend_series(payload, "ownership_trends", "fii_holding")
    public_series = _trend_series(payload, "ownership_trends", "public_holding")

    if not promoter_series and not pledge_series and not fii_series and not public_series:
        _append_unique(missing, "ownership data missing")
        return _section(
            "Ownership quality cannot be judged with the current data.",
            "insufficient_data",
            warnings=[],
            metrics={},
        ), positives, red_flags, missing

    promoter_change = _delta(promoter_series)
    pledge_latest = _latest_value(pledge_series)
    fii_change = _delta(fii_series)
    public_change = _delta(public_series)
    strengths = 0
    weaknesses = 0
    if promoter_change is not None and promoter_change >= 0:
        strengths += 1
        _append_unique(positives, "Promoter holding is stable to improving.")
    if pledge_latest is not None and pledge_latest > 0:
        weaknesses += 1
        _append_unique(red_flags, "Pledged promoter shares create ownership risk.")
    if fii_change is not None and fii_change > 0:
        strengths += 1
        _append_unique(positives, "Foreign institutional ownership has improved.")
    if public_change is not None and public_change > 10:
        _append_unique(warnings, "public float has shifted materially")
    status = _quality_from_scores(strengths, weaknesses)
    summary = "Ownership quality is mixed."
    if status == "strong":
        summary = "Ownership signals look supportive."
    elif status == "weak":
        summary = "Ownership quality has clear risk signals."
    return _section(
        summary,
        status,
        signals=positives,
        warnings=[],
        metrics={
            "promoter_holding_change": promoter_change,
            "pledged_promoter_holding_latest": pledge_latest,
            "fii_holding_change": fii_change,
            "public_holding_change": public_change,
        },
    ), positives, red_flags, missing


def _overall_quality(sections: Sequence[QualitySection]) -> str:
    statuses = [section.status for section in sections]
    if statuses.count("insufficient_data") >= 5:
        return "insufficient_data"
    strongs = statuses.count("strong")
    weaks = statuses.count("weak")
    if strongs >= 4 and weaks == 0:
        return "strong"
    if weaks >= 4 and strongs == 0:
        return "weak"
    if strongs >= 2 and weaks <= 1:
        return "adequate"
    return "mixed"


def _build_legacy_financial_quality_summary(*, company: str, trends_path: Path) -> FinancialQualitySummary:
    if not trends_path.exists():
        raise RuntimeError(f"financial_quality requires financial_trends.json: {trends_path}")
    trends = _load_json(trends_path)
    years = trends.get("years_covered", [])
    if not isinstance(years, list):
        years = []

    revenue_series = _trend_series(trends, "metric_trends", "revenue")
    pat_series = _trend_series(trends, "metric_trends", "pat")
    if not revenue_series and not pat_series:
        raise RuntimeError("financial_quality requires revenue or PAT data in financial_trends")

    growth_quality, g_pos, g_red, g_missing = _build_growth_quality(trends, years)
    margin_quality, m_pos, m_red, m_missing = _build_margin_quality(trends, years)
    return_quality, r_pos, r_red, r_missing = _build_return_quality(trends, years)
    cash_quality, c_pos, c_red, c_missing = _build_cash_conversion_quality(trends, years)
    balance_quality, b_pos, b_red, b_missing = _build_balance_sheet_strength(trends)
    working_quality, w_pos, w_red, w_missing = _build_working_capital_quality(trends)
    dilution_quality, d_pos, d_red, d_missing = _build_dilution_quality(trends)
    ownership_quality, o_pos, o_red, o_missing = _build_ownership_quality(trends)

    company_root = trends_path.parents[2]
    manifest = build_financial_memory_manifest(company=company, company_root=company_root)
    truth_pack = build_financial_truth_pack(company=company, company_root=company_root)

    positive_signals: List[str] = []
    red_flags: List[str] = []
    missing_data: List[str] = []
    precise_missing_data: List[str] = []
    unreliable_data: List[str] = []
    invalid_or_quarantined_data: List[str] = []
    warnings: List[str] = [str(item) for item in trends.get("warnings", [])] if isinstance(trends.get("warnings"), list) else []
    limitations: List[str] = [str(item) for item in trends.get("limitations", [])] if isinstance(trends.get("limitations"), list) else []

    for group in (g_pos, m_pos, r_pos, c_pos, b_pos, w_pos, d_pos, o_pos):
        for item in group:
            _append_unique(positive_signals, item)
    for group in (g_red, m_red, r_red, c_red, b_red, w_red, d_red, o_red):
        for item in group:
            _append_unique(red_flags, item)
    for group in (g_missing, m_missing, r_missing, c_missing, b_missing, w_missing, d_missing, o_missing):
        for item in group:
            _append_unique(missing_data, item)

    truth_by_group = {
        "usable_current": truth_pack.get("usable_current_metrics", []),
        "usable_derived": truth_pack.get("usable_derived_metrics", []),
        "precise_missing": truth_pack.get("precise_missing_metrics", []),
        "unreliable": truth_pack.get("unreliable_metrics", []),
        "invalid": truth_pack.get("invalid_or_quarantined_metrics", []),
    }
    for item in truth_by_group["precise_missing"]:
        if isinstance(item, dict):
            _append_unique(precise_missing_data, str(item.get("metric_name") or item.get("metric_id") or "missing metric"))
    for item in truth_by_group["unreliable"]:
        if isinstance(item, dict):
            _append_unique(unreliable_data, str(item.get("metric_name") or item.get("metric_id") or "unreliable metric"))
    for item in truth_by_group["invalid"]:
        if isinstance(item, dict):
            _append_unique(invalid_or_quarantined_data, str(item.get("metric_name") or item.get("metric_id") or "invalid metric"))

    for section in (
        growth_quality,
        margin_quality,
        return_quality,
        cash_quality,
        balance_quality,
        working_quality,
        dilution_quality,
        ownership_quality,
    ):
        for warning in section.warnings:
            _append_unique(warnings, warning)

    for blocked in truth_pack.get("financial_warnings_blocked_downstream", []) if isinstance(truth_pack.get("financial_warnings_blocked_downstream"), list) else []:
        if not isinstance(blocked, dict):
            continue
        original_warning = str(blocked.get("original_warning") or "")
        normalized_warning = str(blocked.get("normalized_warning") or "")
        metric = str(blocked.get("affected_metric") or "")
        lowered = original_warning.lower()
        if original_warning and original_warning in warnings:
            warnings = [item for item in warnings if item != original_warning]
        if normalized_warning:
            _append_unique(warnings, normalized_warning)
        if metric == "fcf":
            missing_data = [item for item in missing_data if "fcf" not in item.lower()]
        if metric == "cfo_to_pat":
            missing_data = [item for item in missing_data if "cfo/pat" not in item.lower()]
        if metric in {"payables", "payable_days"}:
            missing_data = [item for item in missing_data if "payables" not in item.lower()]
        if metric == "roe":
            missing_data = [item for item in missing_data if "roe" not in item.lower()]
        if metric == "roce":
            missing_data = [item for item in missing_data if "roce" not in item.lower()]
        if metric == "closing_shares":
            missing_data = [item for item in missing_data if "share count missing" not in item.lower()]
            _append_unique(warnings, "Closing shares exist, but weighted-average shares are missing." if any("weighted" in str(x).lower() for x in precise_missing_data) else "Share-count interpretation is partial.")
        if "ownership" in lowered and invalid_or_quarantined_data:
            missing_data = [item for item in missing_data if "ownership" not in item.lower()]
            _append_unique(warnings, "Ownership data invalid/quarantined.")

    overall = _overall_quality(
        [
            growth_quality,
            margin_quality,
            return_quality,
            cash_quality,
            balance_quality,
            working_quality,
            dilution_quality,
            ownership_quality,
        ]
    )
    status = "pass"
    if red_flags or warnings or missing_data:
        status = "warning"
    if not revenue_series and not pat_series:
        status = "fail"

    current_year = str(years[-1]) if years else ""
    current_year_snapshot = {
        "year": current_year,
        "single_year_snapshot": len(years) == 1,
        "usable_metrics": [item.get("metric_id") for item in truth_by_group["usable_current"] if isinstance(item, dict) and item.get("fiscal_year") == current_year][:12],
        "derived_metrics": [item.get("metric_id") for item in truth_by_group["usable_derived"] if isinstance(item, dict) and item.get("fiscal_year") == current_year][:12],
    }
    multi_year_trend_quality = {
        "insufficient_comparable_periods": len(years) < 2,
        "years_covered": [str(year) for year in years],
        "status": "single_year_snapshot" if len(years) == 1 else "multi_year_available",
    }
    profitability_quality = margin_quality
    debt_quality = _section(
        "Debt quality is constrained by reconciliation and leverage context." if unreliable_data else "Debt quality reflects the available leverage evidence.",
        "weak" if any("debt" in item.lower() for item in unreliable_data) else balance_quality.status,
        signals=[],
        warnings=[item for item in warnings if "debt" in item.lower()],
        metrics={"unreliable_debt": any("debt" in item.lower() for item in unreliable_data)},
    )
    per_share_quality = dilution_quality
    capital_allocation_quality = _section(
        "Capital-allocation quality reflects capex, FCF, dividend, and comparability evidence.",
        "mixed" if any("capex" in item.lower() or "fcf" in item.lower() for item in warnings + missing_data) else "adequate",
        signals=[],
        warnings=[item for item in warnings if any(token in item.lower() for token in ("capex", "fcf", "dividend", "share"))],
        metrics={},
    )

    report = FinancialQualitySummary(
        company=company,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        years_covered=[str(year) for year in years],
        status=status,
        overall_financial_quality=overall,
        current_year_snapshot=current_year_snapshot,
        multi_year_trend_quality=multi_year_trend_quality,
        growth_quality=growth_quality,
        profitability_quality=profitability_quality,
        margin_quality=margin_quality,
        return_on_capital_quality=return_quality,
        cash_conversion_quality=cash_quality,
        balance_sheet_strength=balance_quality,
        debt_quality=debt_quality,
        working_capital_quality=working_quality,
        per_share_quality=per_share_quality,
        dilution_and_corporate_action_quality=dilution_quality,
        ownership_quality=ownership_quality,
        capital_allocation_quality=capital_allocation_quality,
        red_flags=red_flags,
        positive_signals=positive_signals,
        missing_data=missing_data,
        precise_missing_data=precise_missing_data,
        unreliable_data=unreliable_data,
        invalid_or_quarantined_data=invalid_or_quarantined_data,
        warnings=warnings,
        limitations=limitations,
    )
    validation_errors = validate_financial_quality_payload(report.to_dict())
    if validation_errors:
        raise ValueError("Invalid financial quality payload: " + "; ".join(validation_errors))
    return report


def _write_legacy_financial_quality_summary(*, company: str, trends_path: Path, output_path: Path) -> FinancialQualitySummary:
    report = _build_legacy_financial_quality_summary(company=company, trends_path=trends_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report


def _load_optional_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = _load_json(path)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _section_entry(payload: Dict[str, Any], section: str, field: str) -> Dict[str, Any]:
    section_payload = payload.get(section, {})
    return section_payload.get(field, {}) if isinstance(section_payload, dict) else {}


def _entry_value(entry: Dict[str, Any]) -> Optional[float]:
    if not isinstance(entry, dict):
        return None
    for key in ("value_crore", "value_per_share", "crore_shares", "raw_number", "value"):
        value = entry.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _ratio_value(payload: Dict[str, Any], name: str) -> Optional[float]:
    ratios = payload.get("ratios", {})
    item = ratios.get(name, {}) if isinstance(ratios, dict) else {}
    value = item.get("value") if isinstance(item, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def _growth_metric(payload: Dict[str, Any], name: str) -> Dict[str, Any]:
    growth_metrics = payload.get("growth_metrics", {})
    return growth_metrics.get(name, {}) if isinstance(growth_metrics, dict) else {}


def _margin_metric(payload: Dict[str, Any], name: str) -> Dict[str, Any]:
    margin_changes = payload.get("margin_changes", {})
    return margin_changes.get(name, {}) if isinstance(margin_changes, dict) else {}


def _metric_value(payload: Dict[str, Any], name: str) -> Optional[float]:
    item = _growth_metric(payload, name)
    value = item.get("growth_percent") if isinstance(item, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def _change_value(payload: Dict[str, Any], name: str) -> Optional[float]:
    item = _growth_metric(payload, name)
    value = item.get("absolute_change") if isinstance(item, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def _margin_change_value(payload: Dict[str, Any], name: str) -> Optional[float]:
    item = _margin_metric(payload, name)
    value = item.get("absolute_change") if isinstance(item, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def _section_confidence(metric_count: int, *, hard_failure: bool = False, warnings: Sequence[str] = ()) -> str:
    if hard_failure:
        return "low"
    if metric_count >= 4 and not warnings:
        return "high"
    if metric_count >= 2:
        return "medium"
    if metric_count == 1:
        return "low"
    return "missing"


def _build_year_section(
    *,
    assessment: str,
    evidence_metrics: Dict[str, Any],
    warnings: Sequence[str] = (),
    limitations: Sequence[str] = (),
    highlights: Sequence[str] = (),
    summary: str = "",
    hard_failure: bool = False,
) -> DeterministicFinancialQualitySection:
    metric_count = sum(1 for value in evidence_metrics.values() if value not in (None, "", [], {}))
    return DeterministicFinancialQualitySection(
        assessment=assessment,
        confidence=_section_confidence(metric_count, hard_failure=hard_failure, warnings=warnings),
        evidence_metrics=evidence_metrics,
        warnings=[str(item) for item in warnings],
        limitations=[str(item) for item in limitations],
        highlights=[str(item) for item in highlights],
        summary=summary,
    )


def _reconciliation_check(payload: Dict[str, Any], field_name: str) -> Dict[str, Any]:
    checks = payload.get("checks", {})
    return checks.get(field_name, {}) if isinstance(checks, dict) else {}


def _check_failed(payload: Dict[str, Any], field_name: str) -> bool:
    check = _reconciliation_check(payload, field_name)
    return bool(isinstance(check, dict) and check.get("hard_failure"))


def _clean_source_artifacts(*payloads: Dict[str, Any]) -> List[str]:
    artifacts: List[str] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        artifact = payload.get("source_artifact")
        if isinstance(artifact, str) and artifact:
            _append_unique(artifacts, artifact)
        for key, value in payload.items():
            if isinstance(value, dict):
                nested = value.get("source_artifact")
                if isinstance(nested, str) and nested:
                    _append_unique(artifacts, nested)
        source_artifacts = payload.get("source_artifacts")
        if isinstance(source_artifacts, list):
            for item in source_artifacts:
                if isinstance(item, str) and item:
                    _append_unique(artifacts, item)
    return artifacts


def _build_fail_year_summary(
    *,
    company: str,
    year: str,
    basis_used: str,
    warnings: Sequence[str],
    limitations: Sequence[str],
    missing_data: Sequence[str],
    source_artifacts: Sequence[str],
) -> YearFinancialQualitySummary:
    empty = _build_year_section(
        assessment="insufficient_data",
        evidence_metrics={},
        warnings=warnings,
        limitations=limitations,
        summary="Financial quality could not be assessed because required input artifacts are missing or malformed.",
        hard_failure=True,
    )
    sections = {
        "growth_quality": empty,
        "margin_quality": empty,
        "return_on_capital_quality": empty,
        "cash_conversion_quality": empty,
        "balance_sheet_strength": empty,
        "working_capital_pressure": empty,
        "capital_allocation_signals": empty,
        "per_share_quality": empty,
        "ownership_signal_quality": empty,
        "dividend_quality": empty,
        "red_flags": [],
        "missing_data": list(missing_data),
        "investor_questions": ["Which required financial artifacts are missing or malformed for this year?"],
    }
    return YearFinancialQualitySummary(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status="fail",
        basis_used=basis_used or "unknown",
        sections=sections,
        warnings=[str(item) for item in warnings],
        limitations=[str(item) for item in limitations],
        source_artifacts=[str(item) for item in source_artifacts],
    )


def _build_year_financial_quality_summary(*, company: str, year: str, financial_root: Path) -> YearFinancialQualitySummary:
    normalized = _load_optional_json(financial_root / "normalized_fundamentals.json")
    reconciliation = _load_optional_json(financial_root / "financial_reconciliation_report.json")
    validation = _load_optional_json(financial_root / "financial_validation_report.json")
    ratios = _load_optional_json(financial_root / "financial_ratios.json")
    growth = _load_optional_json(financial_root / "financial_growth.json")
    corporate_actions = _load_optional_json(financial_root / "corporate_actions.json")
    shareholding = _load_optional_json(financial_root / "shareholding_pattern.json")
    audit = _load_optional_json(financial_root / "financial_audit_report.json")

    basis_used = (
        str(ratios.get("basis_used") or "")
        or str(growth.get("basis_used") or "")
        or str(validation.get("basis_checked") or "")
        or "unknown"
    )

    missing_required: List[str] = []
    warnings: List[str] = []
    limitations: List[str] = []
    source_artifacts = [
        "normalized_fundamentals.json",
        "financial_reconciliation_report.json",
        "financial_validation_report.json",
        "financial_ratios.json",
        "financial_growth.json",
        "corporate_actions.json",
    ]
    if shareholding:
        source_artifacts.append("shareholding_pattern.json")
    if audit:
        source_artifacts.append("financial_audit_report.json")

    required_payloads = {
        "normalized_fundamentals.json": normalized,
        "financial_reconciliation_report.json": reconciliation,
        "financial_validation_report.json": validation,
        "financial_ratios.json": ratios,
        "financial_growth.json": growth,
        "corporate_actions.json": corporate_actions,
    }
    for name, payload in required_payloads.items():
        if not payload:
            missing_required.append(f"{name} missing or malformed")

    if missing_required:
        return _build_fail_year_summary(
            company=company,
            year=year,
            basis_used=basis_used,
            warnings=["Required financial artifacts are incomplete for deterministic quality assessment."],
            limitations=list(missing_required),
            missing_data=list(missing_required),
            source_artifacts=source_artifacts,
        )

    revenue = _section_entry(normalized, "profit_and_loss", "revenue")
    pat = _section_entry(normalized, "profit_and_loss", "pat")
    cfo = _section_entry(normalized, "cash_flow", "cfo")
    capex = _section_entry(normalized, "cash_flow", "capex")
    dividends_paid = _section_entry(normalized, "cash_flow", "dividends_paid")
    total_debt = _section_entry(normalized, "balance_sheet", "total_debt")
    cash = _section_entry(normalized, "balance_sheet", "cash_and_equivalents")
    share_count = _section_entry(normalized, "share_data", "shares_outstanding")
    weighted_avg_shares = _section_entry(normalized, "share_data", "weighted_avg_shares")

    revenue_growth = _metric_value(growth, "revenue")
    pat_growth = _metric_value(growth, "pat")
    eps_growth = _metric_value(growth, "eps_basic")
    ebitda_growth = _metric_value(growth, "ebitda")
    ebit_growth = _metric_value(growth, "ebit")
    bvps_growth = _metric_value(growth, "book_value_per_share")
    receivables_growth = _metric_value(growth, "receivables")
    inventory_growth = _metric_value(growth, "inventory")
    payables_growth = _metric_value(growth, "payables")
    debt_growth = _metric_value(growth, "total_debt")

    opm = _ratio_value(ratios, "opm")
    ebitda_margin = _ratio_value(ratios, "ebitda_margin")
    ebit_margin = _ratio_value(ratios, "ebit_margin")
    npm = _ratio_value(ratios, "npm")
    gross_margin = _ratio_value(ratios, "gross_margin")
    opm_change = _margin_change_value(growth, "opm")
    ebitda_margin_change = _margin_change_value(growth, "ebitda_margin")
    ebit_margin_change = _margin_change_value(growth, "ebit_margin")
    npm_change = _margin_change_value(growth, "npm")
    gross_margin_change = _margin_change_value(growth, "gross_margin")

    roe = _ratio_value(ratios, "roe")
    roce = _ratio_value(ratios, "roce")
    roa = _ratio_value(ratios, "roa")
    debt_to_equity = _ratio_value(ratios, "debt_to_equity")
    net_debt = _ratio_value(ratios, "net_debt")
    cfo_to_pat = _ratio_value(ratios, "cfo_to_pat")
    fcf = _ratio_value(ratios, "fcf")
    fcf_to_pat = _ratio_value(ratios, "fcf_to_pat")
    fcf_margin = _ratio_value(ratios, "fcf_margin")
    receivable_days = _ratio_value(ratios, "receivable_days")
    inventory_days = _ratio_value(ratios, "inventory_days")
    payable_days = _ratio_value(ratios, "payable_days")
    cash_conversion_cycle = _ratio_value(ratios, "cash_conversion_cycle")
    eps_basic = _ratio_value(ratios, "eps_basic")
    dividend_per_share = _ratio_value(ratios, "dividend_per_share")
    payout_ratio = _ratio_value(ratios, "payout_ratio")
    book_value_per_share = _ratio_value(ratios, "book_value_per_share")

    core_hard_failures = [str(item) for item in reconciliation.get("hard_failures", []) if isinstance(item, str)]
    audit_hard_failures = [str(item) for item in audit.get("hard_failures", []) if isinstance(item, str)]
    if validation.get("status") == "fail":
        _append_unique(warnings, "Financial validation reported hard failures.")
    for item in reconciliation.get("warnings", []) if isinstance(reconciliation.get("warnings"), list) else []:
        _append_unique(warnings, str(item))
    for item in validation.get("warnings", []) if isinstance(validation.get("warnings"), list) else []:
        _append_unique(warnings, str(item))
    for item in ratios.get("warnings", []) if isinstance(ratios.get("warnings"), list) else []:
        _append_unique(warnings, str(item))
    for item in growth.get("warnings", []) if isinstance(growth.get("warnings"), list) else []:
        _append_unique(warnings, str(item))
    for item in corporate_actions.get("warnings", []) if isinstance(corporate_actions.get("warnings"), list) else []:
        _append_unique(warnings, str(item))
    for item in audit.get("warnings", []) if isinstance(audit.get("warnings"), list) else []:
        _append_unique(warnings, str(item))

    if _entry_value(capex) is None:
        _append_unique(limitations, "capex missing; free cash flow quality is only partially observable")
    if _entry_value(share_count) is None and _entry_value(weighted_avg_shares) is None:
        _append_unique(limitations, "share count missing; per-share analysis is limited")
    if payable_days is None:
        _append_unique(limitations, "payables unavailable; cash conversion cycle may be incomplete")

    red_flags: List[str] = []
    missing_data: List[str] = []
    investor_questions: List[str] = []

    growth_highlights: List[str] = []
    growth_warnings: List[str] = []
    growth_assessment = "insufficient_data"
    if revenue_growth is None or pat_growth is None:
        _append_unique(missing_data, "core growth metrics incomplete")
        growth_warnings.append("Revenue or PAT growth is missing.")
    else:
        if revenue_growth >= 15 and pat_growth >= 15 and (eps_growth is None or eps_growth >= 10):
            growth_assessment = "strong"
            growth_highlights.append("Revenue, PAT, and per-share growth are moving in the right direction.")
        elif revenue_growth > 0 and pat_growth > 0:
            growth_assessment = "improving"
            growth_highlights.append("Revenue and PAT are both growing.")
        elif revenue_growth >= 0 or pat_growth >= 0:
            growth_assessment = "mixed"
        else:
            growth_assessment = "weak"
        if revenue_growth is not None and pat_growth is not None and pat_growth > revenue_growth + 5:
            growth_highlights.append("PAT is growing faster than revenue, which can indicate operating leverage.")
        if eps_growth is not None and pat_growth is not None and eps_growth + 5 < pat_growth:
            growth_warnings.append("EPS growth is lagging PAT growth, which can indicate dilution or share-count drag.")
        if cfo_to_pat is not None and cfo_to_pat < 0.7 and revenue_growth is not None and revenue_growth > 0:
            growth_warnings.append("Revenue growth is not converting cleanly into cash flow.")
    growth_section = _build_year_section(
        assessment=growth_assessment,
        evidence_metrics={
            "revenue_growth_percent": revenue_growth,
            "pat_growth_percent": pat_growth,
            "eps_growth_percent": eps_growth,
            "ebitda_growth_percent": ebitda_growth,
            "ebit_growth_percent": ebit_growth,
            "book_value_per_share_growth_percent": bvps_growth,
        },
        warnings=growth_warnings,
        limitations=[item for item in limitations if "share count" in item],
        highlights=growth_highlights,
        summary="Deterministic read on growth quality from revenue, profit, and per-share progression.",
        hard_failure=bool(core_hard_failures),
    )

    margin_highlights: List[str] = []
    margin_warnings: List[str] = []
    margin_assessment = "insufficient_data"
    margin_changes = [value for value in (gross_margin_change, ebitda_margin_change, ebit_margin_change, opm_change, npm_change) if value is not None]
    if margin_changes:
        improving = sum(1 for value in margin_changes if value > 1.0)
        compressing = sum(1 for value in margin_changes if value < -1.0)
        if improving >= 2 and compressing == 0:
            margin_assessment = "strong"
            margin_highlights.append("Multiple margin lines expanded year over year.")
        elif improving >= 1 and compressing == 0:
            margin_assessment = "improving"
        elif compressing >= 2:
            margin_assessment = "weak"
            margin_warnings.append("Margins are compressing across multiple levels.")
        else:
            margin_assessment = "mixed"
        if opm is not None and opm >= 20:
            margin_highlights.append("Operating margin is currently strong.")
        if npm is not None and npm < 5:
            margin_warnings.append("Net margin remains thin.")
    else:
        _append_unique(missing_data, "margin trend data incomplete")
    margin_section = _build_year_section(
        assessment=margin_assessment,
        evidence_metrics={
            "gross_margin": gross_margin,
            "ebitda_margin": ebitda_margin,
            "ebit_margin": ebit_margin,
            "opm": opm,
            "npm": npm,
            "gross_margin_change_pp": gross_margin_change,
            "ebitda_margin_change_pp": ebitda_margin_change,
            "ebit_margin_change_pp": ebit_margin_change,
            "opm_change_pp": opm_change,
            "npm_change_pp": npm_change,
        },
        warnings=margin_warnings,
        limitations=[] if margin_changes else ["prior-year margin comparatives unavailable"],
        highlights=margin_highlights,
        summary="Margin quality assessment from current ratios and year-over-year margin changes.",
        hard_failure=bool(core_hard_failures),
    )

    roc_highlights: List[str] = []
    roc_warnings: List[str] = []
    roc_assessment = "insufficient_data"
    if roce is not None or roe is not None or roa is not None:
        if roce is not None and roce >= 18:
            roc_assessment = "strong"
            roc_highlights.append("ROCE is strong.")
        elif ((roce is not None and roce >= 10) or (roe is not None and roe >= 12)):
            roc_assessment = "acceptable"
        else:
            roc_assessment = "weak"
        if roce is not None and roe is not None and roce > roe:
            roc_highlights.append("ROCE exceeds ROE, which can point to stronger operating efficiency than leverage-driven returns.")
        if _check_failed(reconciliation, "total_debt") or _check_failed(reconciliation, "net_worth"):
            roc_assessment = "distorted"
            roc_warnings.append("Capital structure inputs carry reconciliation risk.")
    else:
        _append_unique(missing_data, "return on capital metrics missing")
    roc_section = _build_year_section(
        assessment=roc_assessment,
        evidence_metrics={"roe": roe, "roce": roce, "roa": roa},
        warnings=roc_warnings,
        limitations=[] if roce is not None or roe is not None else ["ROE/ROCE/ROA unavailable"],
        highlights=roc_highlights,
        summary="Return-on-capital quality from ROE, ROCE, and ROA without new ratio math.",
        hard_failure=_check_failed(reconciliation, "total_debt") or _check_failed(reconciliation, "net_worth"),
    )

    cash_highlights: List[str] = []
    cash_warnings: List[str] = []
    cash_assessment = "insufficient_data"
    cfo_value = _entry_value(cfo)
    pat_value = _entry_value(pat)
    if cfo_to_pat is not None:
        if cfo_to_pat > 1:
            cash_assessment = "strong"
            cash_highlights.append("Operating cash flow is stronger than reported PAT.")
        elif cfo_to_pat >= 0.7:
            cash_assessment = "acceptable"
        else:
            cash_assessment = "weak"
            cash_warnings.append("Operating cash conversion is weak relative to PAT.")
    elif cfo_value is None:
        _append_unique(missing_data, "CFO missing")
    if cfo_value is not None and pat_value is not None and cfo_value < 0 and pat_value > 0:
        _append_unique(red_flags, "PAT is positive while CFO is negative.")
        cash_warnings.append("Negative operating cash flow alongside positive reported profit is a red flag.")
    if fcf is None:
        if _entry_value(capex) is None:
            _append_unique(missing_data, "FCF unavailable because capex is missing")
            cash_warnings.append("FCF is missing because capex is not clearly captured.")
        else:
            _append_unique(missing_data, "FCF missing")
    elif fcf_to_pat is not None and fcf_to_pat < 0:
        cash_warnings.append("Free cash flow conversion is negative.")
    cash_section = _build_year_section(
        assessment=cash_assessment,
        evidence_metrics={
            "cfo_to_pat": cfo_to_pat,
            "fcf": fcf,
            "fcf_to_pat": fcf_to_pat,
            "fcf_margin": fcf_margin,
            "cfo_value_crore": cfo_value,
            "pat_value_crore": pat_value,
        },
        warnings=cash_warnings,
        limitations=[item for item in limitations if "capex" in item],
        highlights=cash_highlights,
        summary="Cash conversion quality from CFO, FCF, and conversion ratios.",
        hard_failure=bool(core_hard_failures),
    )

    balance_highlights: List[str] = []
    balance_warnings: List[str] = []
    balance_assessment = "insufficient_data"
    if net_debt is not None or debt_to_equity is not None:
        if net_debt is not None and net_debt < 0:
            balance_assessment = "net_cash"
            balance_highlights.append("Net debt is negative, indicating a net cash position.")
        elif debt_to_equity is not None and debt_to_equity <= 0.5:
            balance_assessment = "low_leverage"
        elif debt_to_equity is not None and debt_to_equity <= 1.0:
            balance_assessment = "moderate_leverage"
        else:
            balance_assessment = "high_leverage"
            balance_warnings.append("Leverage is elevated.")
        if _check_failed(reconciliation, "total_debt"):
            balance_warnings.append("Debt mapping has reconciliation failures.")
    else:
        _append_unique(missing_data, "balance-sheet leverage metrics missing")
    balance_section = _build_year_section(
        assessment=balance_assessment,
        evidence_metrics={
            "net_debt": net_debt,
            "debt_to_equity": debt_to_equity,
            "cash_and_equivalents_crore": _entry_value(cash),
            "total_debt_crore": _entry_value(total_debt),
        },
        warnings=balance_warnings,
        limitations=[] if net_debt is not None or debt_to_equity is not None else ["debt/cash metrics unavailable"],
        highlights=balance_highlights,
        summary="Balance-sheet strength from leverage, debt, and cash indicators.",
        hard_failure=_check_failed(reconciliation, "total_debt"),
    )

    wc_highlights: List[str] = []
    wc_warnings: List[str] = []
    wc_assessment = "insufficient_data"
    if receivable_days is not None or inventory_days is not None or payable_days is not None or cash_conversion_cycle is not None:
        wc_assessment = "stable"
        if receivables_growth is not None and revenue_growth is not None and receivables_growth > revenue_growth + 10:
            wc_assessment = "weak"
            wc_warnings.append("Receivables are growing much faster than revenue.")
            _append_unique(red_flags, "Receivables are growing materially faster than revenue.")
        if inventory_growth is not None and revenue_growth is not None and inventory_growth > revenue_growth + 10:
            wc_assessment = "weak"
            wc_warnings.append("Inventory is building faster than revenue.")
            _append_unique(red_flags, "Inventory is growing materially faster than revenue.")
        if payable_days is None:
            wc_warnings.append("Payables are missing, which prevents a full cash-conversion view.")
        if cash_conversion_cycle is not None and cash_conversion_cycle > 120:
            wc_warnings.append("Cash conversion cycle is high.")
        if receivable_days is not None and receivable_days > 90:
            wc_warnings.append("Receivable days are high.")
        if not wc_warnings:
            wc_highlights.append("Working-capital signals do not show an immediate strain.")
    else:
        _append_unique(missing_data, "working-capital metrics missing")
    working_section = _build_year_section(
        assessment=wc_assessment,
        evidence_metrics={
            "receivable_days": receivable_days,
            "inventory_days": inventory_days,
            "payable_days": payable_days,
            "cash_conversion_cycle": cash_conversion_cycle,
            "receivables_growth_percent": receivables_growth,
            "inventory_growth_percent": inventory_growth,
            "payables_growth_percent": payables_growth,
            "revenue_growth_percent": revenue_growth,
        },
        warnings=wc_warnings,
        limitations=[item for item in limitations if "payables" in item],
        highlights=wc_highlights,
        summary="Working-capital pressure from days metrics and growth comparisons.",
        hard_failure=_check_failed(reconciliation, "receivables") or _check_failed(reconciliation, "payables"),
    )

    capital_highlights: List[str] = []
    capital_warnings: List[str] = []
    capital_assessment = "insufficient_data"
    actions = corporate_actions.get("actions", []) if isinstance(corporate_actions.get("actions"), list) else []
    action_types = [str(item.get("action_type", "")) for item in actions if isinstance(item, dict)]
    if _entry_value(capex) is not None or actions or fcf is not None:
        capital_assessment = "mixed"
        if _entry_value(capex) is not None:
            capital_highlights.append("Capex is captured for the year.")
        else:
            capital_warnings.append("Capex is missing, limiting reinvestment analysis.")
        if fcf is not None and fcf > 0:
            capital_highlights.append("Free cash flow is positive.")
            if capital_assessment == "mixed":
                capital_assessment = "stable"
        if "buyback" in action_types:
            capital_highlights.append("Buyback activity is present.")
        if "qip" in action_types or "preferential_issue" in action_types or "rights_issue" in action_types:
            capital_warnings.append("Equity issuance activity affects capital-allocation interpretation.")
    else:
        _append_unique(missing_data, "capital-allocation evidence limited")
    capital_section = _build_year_section(
        assessment=capital_assessment,
        evidence_metrics={
            "capex_crore": _entry_value(capex),
            "fcf_crore": fcf,
            "dividends_paid_crore": _entry_value(dividends_paid),
            "action_types": action_types,
        },
        warnings=capital_warnings,
        limitations=[item for item in limitations if "capex" in item],
        highlights=capital_highlights,
        summary="Capital-allocation signals from capex, free cash flow, dividends, and corporate actions.",
        hard_failure=bool(core_hard_failures),
    )

    per_share_highlights: List[str] = []
    per_share_warnings: List[str] = []
    per_share_assessment = "insufficient_data"
    if eps_basic is not None or book_value_per_share is not None:
        per_share_assessment = "stable"
        if eps_growth is not None and eps_growth > 0:
            per_share_highlights.append("EPS is growing.")
            per_share_assessment = "improving"
        if _entry_value(share_count) is None and _entry_value(weighted_avg_shares) is None:
            per_share_warnings.append("Share count is missing, so per-share comparability is limited.")
        if corporate_actions.get("per_share_comparability_warnings"):
            per_share_warnings.extend(
                str(item) for item in corporate_actions.get("per_share_comparability_warnings", []) if isinstance(item, str)
            )
    else:
        _append_unique(missing_data, "per-share metrics missing")
    per_share_section = _build_year_section(
        assessment=per_share_assessment,
        evidence_metrics={
            "eps_basic": eps_basic,
            "eps_growth_percent": eps_growth,
            "book_value_per_share": book_value_per_share,
            "book_value_per_share_growth_percent": bvps_growth,
            "shares_outstanding": _entry_value(share_count),
            "weighted_avg_shares": _entry_value(weighted_avg_shares),
        },
        warnings=per_share_warnings,
        limitations=[item for item in limitations if "share count" in item],
        highlights=per_share_highlights,
        summary="Per-share quality from EPS, BVPS, and share-count coverage.",
        hard_failure=_check_failed(reconciliation, "shares_outstanding"),
    )

    ownership_highlights: List[str] = []
    ownership_warnings: List[str] = []
    ownership_assessment = "insufficient_data"
    if shareholding:
        ownership_assessment = "stable"
        items = shareholding.get("items", [])
        promoter = next((item.get("holding_percent") for item in items if isinstance(item, dict) and item.get("holder_category") == "promoter_holding_percent"), None)
        pledge = next((item.get("holding_percent") for item in items if isinstance(item, dict) and item.get("holder_category") == "pledged_promoter_holding_percent"), None)
        institutional = next((item.get("holding_percent") for item in items if isinstance(item, dict) and item.get("holder_category") == "institutional_holding_percent"), None)
        if isinstance(promoter, (int, float)):
            ownership_highlights.append(f"Promoter holding is {promoter:.2f}%.")
        if isinstance(pledge, (int, float)) and pledge > 0:
            ownership_assessment = "weak"
            ownership_warnings.append("Promoter pledge creates ownership risk.")
        if isinstance(institutional, (int, float)):
            ownership_highlights.append(f"Institutional holding is {institutional:.2f}%.")
    else:
        _append_unique(missing_data, "shareholding pattern missing")
        ownership_warnings.append("Ownership pattern is unavailable for this year.")
    ownership_section = _build_year_section(
        assessment=ownership_assessment,
        evidence_metrics={
            "shareholding_status": shareholding.get("status"),
            "ownership_summary": shareholding.get("ownership_summary", {}),
        },
        warnings=ownership_warnings,
        limitations=[] if shareholding else ["shareholding data unavailable"],
        highlights=ownership_highlights,
        summary="Ownership quality from promoter, pledge, and institutional holding signals.",
        hard_failure=False,
    )

    dividend_highlights: List[str] = []
    dividend_warnings: List[str] = []
    dividend_assessment = "insufficient_data"
    if dividend_per_share is not None or _entry_value(dividends_paid) is not None:
        dividend_assessment = "stable"
        if dividend_per_share is not None:
            dividend_highlights.append("Dividend per share is available.")
        if payout_ratio is not None:
            dividend_highlights.append("Payout ratio is available.")
        if fcf is None:
            dividend_warnings.append("Dividend funding quality is uncertain because FCF is unavailable.")
        elif fcf < 0:
            dividend_warnings.append("Dividend is not backed by positive free cash flow.")
            _append_unique(red_flags, "Dividend appears unsupported by positive free cash flow.")
    else:
        _append_unique(missing_data, "dividend data unavailable")
    dividend_section = _build_year_section(
        assessment=dividend_assessment,
        evidence_metrics={
            "dividends_paid_crore": _entry_value(dividends_paid),
            "dividend_per_share": dividend_per_share,
            "payout_ratio": payout_ratio,
            "fcf_crore": fcf,
        },
        warnings=dividend_warnings,
        limitations=[item for item in limitations if "capex" in item],
        highlights=dividend_highlights,
        summary="Dividend quality from dividend cash, per-share payout, and free-cash-flow support.",
        hard_failure=False,
    )

    for failure in core_hard_failures:
        _append_unique(red_flags, failure)
    for failure in audit_hard_failures:
        _append_unique(red_flags, failure)

    if debt_growth is not None and debt_growth > 20 and cfo_to_pat is not None and cfo_to_pat < 0.7:
        _append_unique(red_flags, "Debt is rising sharply while cash conversion is weak.")
    if share_count.get("source_line_item") in (None, "") and _entry_value(weighted_avg_shares) is None:
        _append_unique(missing_data, "share count unavailable for per-share analysis")

    for limitation in limitations:
        if "capex" in limitation:
            _append_unique(investor_questions, "Why is capex missing or not clearly disclosed?")
        if "share count" in limitation:
            _append_unique(investor_questions, "What is the reliable current share count and weighted average share base?")
        if "payables" in limitation:
            _append_unique(investor_questions, "Can trade payables be verified to complete the cash-conversion picture?")
    for warning in growth_warnings + cash_warnings + balance_warnings + wc_warnings + capital_warnings + per_share_warnings + ownership_warnings + dividend_warnings:
        lowered = warning.lower()
        if "receivable" in lowered:
            _append_unique(investor_questions, "Why are receivable days elevated or receivables growing faster than revenue?")
        if "inventory" in lowered:
            _append_unique(investor_questions, "What explains the inventory build-up?")
        if "dividend" in lowered:
            _append_unique(investor_questions, "Is the dividend sustainably funded by operating cash flow and free cash flow?")
        if "qip" in lowered or "issuance" in lowered or "share count" in lowered:
            _append_unique(investor_questions, "What was the exact share-count impact of equity issuance or related capital actions?")
        if "basis" in lowered:
            _append_unique(investor_questions, "Should these numbers be read on a standalone or consolidated basis?")

    status = "pass"
    if core_hard_failures or validation.get("status") == "fail" or missing_required:
        status = "fail"
    elif warnings or limitations or missing_data or red_flags:
        status = "warning"

    report = YearFinancialQualitySummary(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status=status,
        basis_used=basis_used or "unknown",
        sections={
            "growth_quality": growth_section,
            "margin_quality": margin_section,
            "return_on_capital_quality": roc_section,
            "cash_conversion_quality": cash_section,
            "balance_sheet_strength": balance_section,
            "working_capital_pressure": working_section,
            "capital_allocation_signals": capital_section,
            "per_share_quality": per_share_section,
            "ownership_signal_quality": ownership_section,
            "dividend_quality": dividend_section,
            "red_flags": red_flags,
            "missing_data": missing_data,
            "investor_questions": investor_questions,
        },
        warnings=warnings,
        limitations=limitations,
        source_artifacts=source_artifacts,
    )
    validation_errors = validate_financial_quality_payload(report.to_dict())
    if validation_errors:
        raise ValueError("Invalid year financial quality payload: " + "; ".join(validation_errors))
    return report


def build_financial_quality_summary(
    *,
    company: str,
    trends_path: Path | None = None,
    financial_root: Path | None = None,
    year: str | None = None,
) -> FinancialQualitySummary | YearFinancialQualitySummary:
    if trends_path is not None:
        return _build_legacy_financial_quality_summary(company=company, trends_path=trends_path)
    if financial_root is None or not year:
        raise RuntimeError("financial_quality requires either trends_path or financial_root/year")
    return _build_year_financial_quality_summary(company=company, year=year, financial_root=financial_root)


def write_financial_quality_summary(
    *,
    company: str,
    output_path: Path,
    trends_path: Path | None = None,
    financial_root: Path | None = None,
    year: str | None = None,
) -> FinancialQualitySummary | YearFinancialQualitySummary:
    if trends_path is not None:
        return _write_legacy_financial_quality_summary(
            company=company,
            trends_path=trends_path,
            output_path=output_path,
        )
    report = build_financial_quality_summary(
        company=company,
        financial_root=financial_root,
        year=year,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report
