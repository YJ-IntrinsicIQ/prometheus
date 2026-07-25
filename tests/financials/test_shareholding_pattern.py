from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge.financials.shareholding import extract_shareholding_pattern, write_shareholding_pattern


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _normalized_entry(
    field: str,
    *,
    value_original: str = "",
    unit_original: str = "%",
    period: str = "March 31, 2025",
    artifact: str = "normalized_fundamentals.json",
    confidence: str = "high",
):
    return {
        "canonical_field": field,
        "value_crore": None,
        "value_original": value_original,
        "unit_original": unit_original,
        "basis": "consolidated",
        "period": period,
        "source_line_item": field,
        "source_page": 1,
        "source_artifact": artifact,
        "confidence": confidence,
        "warnings": [],
    }


def _normalized_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "shareholding_pattern": {
            "promoter_holding": _normalized_entry("promoter_holding", value_original="54.20"),
            "pledged_promoter_holding": _normalized_entry("pledged_promoter_holding", value_original="1.20"),
            "fii_holding": _normalized_entry("fii_holding", value_original="8.10"),
            "dii_holding": _normalized_entry("dii_holding", value_original="6.40"),
            "mutual_fund_holding": _normalized_entry("mutual_fund_holding", value_original="5.00"),
            "public_holding": _normalized_entry("public_holding", value_original="45.80"),
            "others": _normalized_entry("others", value_original="3.30"),
        },
    }


def _raw_row(line_item_raw: str, current: str, previous: str | None = None, *, page: int = 4, unit_hint: str = "%", value_type: str = ""):
    values = [{"period": "March 31, 2025", "value_raw": current, "unit_hint": unit_hint, "currency_hint": "", "value_crore": None, "value_type": value_type}]
    if previous is not None:
        values.append({"period": "March 31, 2024", "value_raw": previous, "unit_hint": unit_hint, "currency_hint": "", "value_crore": None, "value_type": value_type})
    return {
        "statement_type": "shareholding_pattern",
        "table_type": "shareholding_pattern",
        "basis": "consolidated",
        "line_item_raw": line_item_raw,
        "values": values,
        "source_artifact": "raw_financial_tables.json",
        "page": page,
        "chunk_id": f"chunk-{page}",
        "confidence": "high",
        "warnings": [],
    }


def _raw_payload(rows):
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "tables": {
            "shareholding_pattern": rows,
        },
        "warnings": [],
        "limitations": [],
    }


def test_extract_shareholding_pattern_uses_normalized_fallback(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(raw_path, _raw_payload([]))

    report = extract_shareholding_pattern(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        normalized_path=normalized_path,
    )

    item_map = {item.holder_category: item for item in report.items}
    assert item_map["promoter_holding_percent"].holding_percent == 54.2
    assert item_map["pledged_promoter_holding_percent"].holding_percent == 1.2
    assert item_map["institutional_holding_percent"].holding_percent == 19.5
    assert report.ownership_summary.promoter_control == "Promoter holding recorded at 54.20%."
    assert report.searched_sections == []


def test_extract_shareholding_pattern_prefers_raw_rows_and_calculates_change(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(
        raw_path,
        _raw_payload(
            [
                _raw_row("Promoter and promoter group", "57.00", "55.50"),
                _raw_row("Foreign institutional investors", "9.50", "8.00"),
                _raw_row("Domestic institutional investors", "7.00", "6.00"),
                _raw_row("Mutual funds", "4.50", "4.20"),
                _raw_row("Public shareholding", "43.00", "44.50"),
            ]
        ),
    )

    report = extract_shareholding_pattern(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        normalized_path=normalized_path,
    )

    item_map = {item.holder_category: item for item in report.items}
    assert item_map["promoter_holding_percent"].holding_percent == 57.0
    assert item_map["promoter_holding_percent"].change_percent == 1.5
    assert item_map["fii_holding_percent"].change_percent == 1.5
    assert any("promoter_holding_percent increased by 1.50 percentage points." == change for change in report.ownership_summary.notable_changes)
    assert "shareholding_pattern" in report.searched_sections


def test_extract_shareholding_pattern_warns_when_categories_do_not_sum_near_100(tmp_path):
    payload = _normalized_payload()
    payload["shareholding_pattern"]["promoter_holding"]["value_original"] = "40.00"
    payload["shareholding_pattern"]["public_holding"]["value_original"] = "35.00"
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    _write_json(normalized_path, payload)
    _write_json(raw_path, _raw_payload([]))

    report = extract_shareholding_pattern(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        normalized_path=normalized_path,
    )

    assert "categories do not sum near 100%" in report.warnings


def test_extract_shareholding_pattern_warns_when_pledge_data_missing(tmp_path):
    payload = _normalized_payload()
    payload["shareholding_pattern"]["pledged_promoter_holding"] = _normalized_entry("pledged_promoter_holding")
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    _write_json(normalized_path, payload)
    _write_json(raw_path, _raw_payload([]))

    report = extract_shareholding_pattern(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        normalized_path=normalized_path,
    )

    assert "promoter pledge data missing" in report.warnings
    assert report.ownership_summary.pledge_risk == "Promoter pledge data unavailable."


def test_extract_shareholding_pattern_warns_when_raw_section_exists_but_no_rows_are_usable(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    _write_json(normalized_path, {"company": "acme", "year": "fy25", "generated_at": "2026-07-17T00:00:00Z", "shareholding_pattern": {}})
    _write_json(raw_path, _raw_payload([_raw_row("Unclassified holders", "", None)]))

    report = extract_shareholding_pattern(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        normalized_path=normalized_path,
    )
    assert report.status == "warning"
    assert any("could not be parsed reliably" in warning for warning in report.warnings)
    assert "shareholding_pattern" in report.searched_sections


def test_write_shareholding_pattern_persists_artifact(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    output_path = tmp_path / "shareholding_pattern.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(raw_path, _raw_payload([]))

    report = write_shareholding_pattern(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        normalized_path=normalized_path,
        output_path=output_path,
    )

    assert output_path.exists()
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["company"] == "acme"
    assert saved["status"] == report.status
    assert output_path.with_name("shareholding_rejections.json").exists()


def test_extract_shareholding_pattern_records_rejection_reasons(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(raw_path, _raw_payload([_raw_row("Unclassified holders", "12.0", None)]))

    report = extract_shareholding_pattern(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        normalized_path=normalized_path,
    )

    assert any("Unclassified shareholding row" in reason for reason in report.rejection_reasons)


def test_shareholding_percentages_remain_percentages(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(raw_path, _raw_payload([_raw_row("Promoter and promoter group", "57.00", "55.50", value_type="percentage")]))

    report = extract_shareholding_pattern(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        normalized_path=normalized_path,
    )
    item = next(item for item in report.items if item.holder_category == "promoter_holding_percent")
    assert item.holding_percent == 57.0
    assert item.shares_held is None


def test_shareholding_shares_held_parsed_correctly(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    _write_json(normalized_path, {"company": "acme", "year": "fy25", "generated_at": "2026-07-17T00:00:00Z", "shareholding_pattern": {}})
    _write_json(raw_path, _raw_payload([_raw_row("Promoter and promoter group", "1200000", None, unit_hint="shares", value_type="share_count")]))

    report = extract_shareholding_pattern(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        normalized_path=normalized_path,
    )
    item = next(item for item in report.items if item.holder_category == "promoter_holding_percent")
    assert item.holding_percent is None
    assert item.shares_held == 1200000.0


def test_pledge_data_separated_from_promoter_holding(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    _write_json(normalized_path, {"company": "acme", "year": "fy25", "generated_at": "2026-07-17T00:00:00Z", "shareholding_pattern": {}})
    _write_json(
        raw_path,
        _raw_payload(
            [
                _raw_row("Promoter and promoter group", "57.00", "55.50", value_type="percentage"),
                _raw_row("Pledged promoter holding", "2.50", "2.00", value_type="percentage"),
            ]
        ),
    )

    report = extract_shareholding_pattern(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        normalized_path=normalized_path,
    )
    item_map = {item.holder_category: item for item in report.items}
    assert item_map["promoter_holding_percent"].holding_percent == 57.0
    assert item_map["pledged_promoter_holding_percent"].holding_percent == 2.5
