from __future__ import annotations

from knowledge.financials.corporate_action_schema import CorporateActionItem
from knowledge.financials.share_count_adjuster import build_share_count_summary


def _entry(value_original="", value_crore=None):
    return {
        "value_original": value_original,
        "value_crore": value_crore,
    }


def _normalized_payload():
    return {
        "profit_and_loss": {
            "eps_basic": _entry("10.00"),
            "eps_diluted": _entry("9.50"),
        },
        "share_data": {
            "face_value": _entry("10"),
            "shares_outstanding": _entry("12000000"),
            "weighted_avg_shares": _entry("11800000"),
            "diluted_shares": _entry("12100000"),
        },
        "balance_sheet": {
            "equity_share_capital": _entry(value_crore=12.0),
        },
    }


def test_build_share_count_summary_from_normalized_payload():
    summary, warnings = build_share_count_summary(
        normalized_payload=_normalized_payload(),
        actions=[],
    )
    assert summary.closing_shares == 12000000.0
    assert summary.weighted_avg_shares == 11800000.0
    assert summary.diluted_shares == 12100000.0
    assert summary.face_value == 10.0
    assert warnings == []


def test_build_share_count_summary_flags_missing_share_counts():
    payload = _normalized_payload()
    payload["share_data"]["weighted_avg_shares"]["value_original"] = ""
    payload["share_data"]["diluted_shares"]["value_original"] = ""

    _, warnings = build_share_count_summary(
        normalized_payload=payload,
        actions=[],
    )
    assert "EPS exists but weighted average shares are missing" in warnings
    assert "diluted shares missing" in warnings


def test_build_share_count_summary_captures_events_and_comparability():
    actions = [
        CorporateActionItem(
            action_type="bonus_issue",
            year="fy25",
            ratio="1:1",
            impact_on_share_count="increase",
            impact_on_eps_comparability="yes",
            source_line_item="Bonus issue in the ratio of 1:1",
            source_page=12,
            source_artifact="raw_financial_tables.json",
            confidence="high",
        ),
        CorporateActionItem(
            action_type="buyback",
            year="fy25",
            impact_on_share_count="decrease",
            impact_on_eps_comparability="yes",
            source_line_item="Buyback of equity shares",
            source_page=13,
            source_artifact="raw_financial_tables.json",
            confidence="medium",
        ),
    ]
    summary, warnings = build_share_count_summary(
        normalized_payload=_normalized_payload(),
        actions=actions,
    )
    assert len(summary.share_count_events) == 2
    assert "bonus_issue may affect per-share comparability" in warnings
    assert "buyback may affect per-share comparability" in warnings
