import json
from pathlib import Path

import pytest

from knowledge.financials.extractor import extract_financial_tables, write_financial_extraction
from knowledge.financials.extraction_schema import FinancialExtractionResult
from knowledge.financials.extractor import _parse_discovery, build_financial_extraction_readiness


ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_chunks(path: Path, chunks) -> None:
    _write_json(path, {"chunks": chunks})


def _discovery_payload(*, company="acme", year="fy25", sections=None):
    base_sections = {
        "primary_profit_and_loss_statement": [],
        "primary_balance_sheet_statement": [],
        "primary_cash_flow_statement": [],
        "statement_of_changes_in_equity": [],
        "financial_note": [],
        "accounting_policy": [],
        "auditor_report": [],
        "management_discussion_financial_summary": [],
        "share_capital_note": [],
        "eps_note": [],
        "dividend_note": [],
        "shareholding_note": [],
        "corporate_action_note": [],
        "irrelevant_financial_text": [],
    }
    if sections:
        for key, value in sections.items():
            base_sections[key] = value
    return {
        "company": company,
        "year": year,
        "generated_at": "2026-07-16T00:00:00Z",
        "source_documents": ["clean_chunks.json"],
        "sections": base_sections,
        "warnings": [],
        "limitations": [],
    }


def _candidate(section_type: str, chunk_id: str, page: int, excerpt: str, confidence="high"):
    return {
        "section_type": section_type,
        "source_artifact": "clean_chunks.json",
        "page": page,
        "chunk_id": chunk_id,
        "text_excerpt": excerpt[:200],
        "confidence": confidence,
        "reasoning": "synthetic test candidate",
        "signals": ["heading:test", "numeric_density"],
    }


def _load_real_ujjivan_financials(year: str):
    base = ROOT / "companies" / "ujjivan" / year / "financials"
    discovery = _parse_discovery(base / "financial_discovery.json")
    result = FinancialExtractionResult.from_dict(json.loads((base / "raw_financial_tables.json").read_text(encoding="utf-8")))
    return discovery, result


def test_profit_and_loss_table_extraction(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    output_path = tmp_path / "raw_financial_tables.json"
    text = (
        "Statement of Profit and Loss (All figures are in INR Crores unless specifically stated otherwise) "
        "Particulars Notes No For the year ended March 31, 2025 For the year ended March 31, 2024 "
        "Revenue from operations 23 519.80 453.45 Other income 24 46.03 9.22 Total income 565.83 462.67 "
        "Profit before tax 242.19 164.83 Profit for the year 181.69 123.99"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-001", "page": 10, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"primary_profit_and_loss_statement": [_candidate("primary_profit_and_loss_statement", "CHK-001", 10, text)]}
        ),
    )

    result = write_financial_extraction(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
        output_path=output_path,
    )

    assert output_path.exists()
    rows = result.tables["profit_and_loss"]
    labels = [row.line_item_raw for row in rows]
    assert "Revenue from operations" in labels
    revenue_row = next(row for row in rows if row.line_item_raw == "Revenue from operations")
    assert revenue_row.values[0].period == "March 31, 2025"
    assert revenue_row.values[0].value_raw == "519.80"
    assert revenue_row.values[0].value_crore == 519.8
    assert revenue_row.values[0].value_type == "monetary"
    assert revenue_row.basis == "unknown"
    assert revenue_row.is_primary_statement is True


def test_profit_and_loss_table_extraction_recognizes_year_ended_periods(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    output_path = tmp_path / "raw_financial_tables.json"
    text = (
        "Tanla Annual Report 2021-22 Consolidated Financial Statements "
        "Particulars Note Year ended March 31, 2022 Year ended March 31, 2021 "
        "Revenue from operations 27 3,20,597.33 2,34,146.55 "
        "Profit before tax 67,411.84 41,475.42 "
        "Total tax expense (X) 13,483.93 5,861.67 "
        "Profit for the year (IX - X) 53,927.91 35,613.75"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-002-ENDED", "page": 194, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"primary_profit_and_loss_statement": [_candidate("primary_profit_and_loss_statement", "CHK-002-ENDED", 194, text)]}
        ),
    )

    result = write_financial_extraction(
        company="acme",
        year="fy22",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
        output_path=output_path,
    )

    rows = result.tables["profit_and_loss"]
    revenue_row = next(row for row in rows if row.line_item_raw == "Revenue from operations")
    pat_row = next(row for row in rows if row.line_item_raw == "Profit for the year (IX - X)")
    assert revenue_row.values[0].period == "March 31, 2022"
    assert pat_row.values[0].period == "March 31, 2022"


def test_financial_note_revenue_routes_to_canonical_revenue_statement_type(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = "Financial Details FY 2024-25 Revenue from Operations 100.00 90.00"
    _write_chunks(chunk_path, [{"chunk_id": "CHK-REV-NOTE", "page": 72, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(sections={"financial_note": [_candidate("financial_note", "CHK-REV-NOTE", 72, text)]}),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = next(row for row in result.tables["revenue"] if "revenue from operations" in row.line_item_raw.lower())
    assert row.statement_type == "revenue"
    assert row.source_section_type == "financial_note"


def test_financial_note_eps_routes_to_canonical_eps_statement_type(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = "Financial Details EPS (Basic) (`) FY 2024-25 EPS (Basic) (`) 1.23 0.98"
    _write_chunks(chunk_path, [{"chunk_id": "CHK-EPS-NOTE", "page": 72, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(sections={"eps_note": [_candidate("eps_note", "CHK-EPS-NOTE", 72, text)]}),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = next(row for row in result.tables["eps"] if "eps (basic)" in row.line_item_raw.lower())
    assert row.statement_type == "eps"
    assert row.source_section_type == "eps_note"


def test_financial_note_paid_up_capital_routes_to_share_capital(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Section B: Financial Details of the Bank "
        "1. Paid up Capital (`) 19,28,31,42,050 "
        "2. Total Turnover (`) 31,26,07,35,251.63 "
        "3. Total profit after taxes (`) 4,14,59,04,537.08"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-PAID-UP-NOTE", "page": 105, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(sections={"financial_note": [_candidate("financial_note", "CHK-PAID-UP-NOTE", 105, text)]}),
    )

    result = extract_financial_tables(
        company="ujjivan",
        year="fy22",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = next(row for row in result.tables["share_capital"] if "paid up capital" in row.line_item_raw.lower())
    assert row.statement_type == "share_capital"
    assert row.values[0].value_crore == 1928.314205


def test_financial_note_balance_sheet_mix_routes_to_balance_sheet(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Management Message Business Segment Review As on March 31, 2022 (` in 000's) "
        "Revenue 2,821,324 27,692,669 746,743 31,260,736 "
        "Segment Assets 61,766,622 161,706,653 8,436,055 231,909,331 "
        "Unallocated Assets 4,135,311 13 "
        "Total Assets 236,044,642 14 "
        "Segment Liabilities 54,498,992 142,679,793 7,443,443 204,622,228 "
        "Unallocated Liabilities 3,648,737 16 "
        "Capital Employed 7,267,650 19,026,881 992,612 27,287,144 "
        "Unallocated Capital Employed 486,533 18"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-BS-MIX", "page": 133, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(sections={"financial_note": [_candidate("financial_note", "CHK-BS-MIX", 133, text)]}),
    )

    result = extract_financial_tables(
        company="ujjivan",
        year="fy22",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = next(row for row in result.tables["balance_sheet"] if row.line_item_raw == "Total Assets")
    assert row.statement_type == "balance_sheet"
    assert row.values[0].unit_hint == "thousands"
    assert row.values[0].value_crore == 23604.4642


def test_processing_units_prose_does_not_mask_monetary_revenue(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Business Segment Review Performance of the Year World of Ujjivan Banking as a separate sub-segment "
        "of Retail Banking Segment will be implemented by the Bank based on the decision of the DBU Working Group. "
        "C) Corporate/ Whole Sale Banking: The Wholesale Banking Segment provides loans to Corporates and Financial "
        "Institutions. Revenues of the wholesale banking segment consist of interest earned on loans made to customers. "
        "The principal expenses of the segment consist of interest expense on funds borrowed from external sources and "
        "other internal segments, premises expenses, personnel costs, other direct overheads and allocated expenses of "
        "delivery channels, specialist product groups, processing units and support groups. "
        "As on March 31, 2023 (₹ in 000’s) Part A: Business segments SR. NO Business Segments Treasury Retail Banking "
        "Corporate/ Wholesale Banking Total Particulars March 31, 2023 March 31, 2023 March 31, 2023 March 31, 2023 "
        "1 Revenue 4,580,462 42,026,566 934,828 47,541,856 2 Unallocated Revenue - - - - 3 (less) Inter Segment Revenue "
        "- - - - 4 Total Income (1+2-3) 4,580,462 42,026,566 934,828 47,541,856 11 Segment Assets 109,030,727 "
        "210,307,562 11,031,412 330,369,701 13 Total Assets 333,168,775"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-BS-REV", "page": 315, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(sections={"financial_note": [_candidate("financial_note", "CHK-BS-REV", 315, text)]}),
    )

    result = extract_financial_tables(
        company="ujjivan",
        year="fy23",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = next(row for row in result.tables["balance_sheet"] if row.line_item_raw == "Revenue")
    assert row.values[0].unit_hint == "thousands"
    assert row.values[0].value_type == "monetary"
    assert row.values[0].value_crore == 458.0462


def test_paid_up_capital_balance_sheet_schedule_row_is_preserved(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Schedules forming part of the Balance Sheet as at March 31, 2022 (` in 000's) "
        "Particulars As on March 31, 2022 As on March 31, 2021 "
        "SCHEDULE -1 CAPITAL "
        "Authorized Capital 2,300,000,000 Equity Shares of ` 10 each 23,000,000 23,000,000 "
        "Issued, Subscribed and Called up Capital 1,728,314,205 (Previous Year: 1,728,314,205) "
        "Equity Shares of ` 10 each 17,283,142 17,283,142 "
        "200,000,000 11% Preference Shares (Perpetual Non-Cumulative Non-Convertible) of ` 10 each 2,000,000 2,000,000 "
        "19,283,142 19,283,142 Paid up Capital 1,728,314,205 (Previous Year: 1,728,314,205) "
        "Equity Shares of ` 10 each 17,283,142 17,283,142 "
        "200,000,000 11% Preference Shares (Perpetual Non-Cumulative Non-Convertible) of ` 10 each 2,000,000 2,000,000 "
        "TOTAL 19,283,142 19,283,142 "
        "SCHEDULE -2 RESERVES AND SURPLUS I. Statutory Reserves Closing balance 205,131 205,131"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-CAPITAL", "page": 115, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"primary_balance_sheet_statement": [_candidate("primary_balance_sheet_statement", "CHK-CAPITAL", 115, text)]}
        ),
    )

    result = extract_financial_tables(
        company="ujjivan",
        year="fy22",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = next(
        row
        for row in result.tables["balance_sheet"]
        if "paid up capital" in row.line_item_raw.lower() or "called up capital" in row.line_item_raw.lower()
    )
    assert row.statement_type == "balance_sheet"
    assert row.values[0].value_crore is not None


def test_balance_sheet_table_extraction_recognizes_numeric_as_at_periods(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Standalone Balance Sheet (All figures are in INR Crores unless specifically stated otherwise) "
        "Particulars Notes No As at 31/03/2025 As at 31/03/2024 "
        "Property, plant and equipment 4 120.57 91.24 Capital work in progress 5a 7.18 1.35 "
        "Total Assets 1,691.77 1,434.94 Equity Share capital 15 11.20 11.20 Total Liabilities 367.56 267.86"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-002-NUM", "page": 12, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"primary_balance_sheet_statement": [_candidate("primary_balance_sheet_statement", "CHK-002-NUM", 12, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    rows = result.tables["balance_sheet"]
    total_assets = next(row for row in rows if row.line_item_raw == "Total Assets")
    assert [value.period for value in total_assets.values[:2]] == ["31/03/2025", "31/03/2024"]
    assert total_assets.values[0].value_crore == 1691.77
    assert total_assets.values[0].value_type == "monetary"


def test_paid_up_capital_summary_row_prefers_rupees_over_page_level_crores(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "SECTION B: FINANCIAL DETAILS OF THE BANK Sr. No. Particulars Details "
        "1. Paid-up Capital (`) 19,28,31,42,050 "
        "2. Total Turnover (`) 2,806.07 Crore "
        "3. Total profit after taxes (`) 8.30 Crores"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-PAID-UP", "page": 105, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"primary_balance_sheet_statement": [_candidate("primary_balance_sheet_statement", "CHK-PAID-UP", 105, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy21",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = next(row for row in result.tables["balance_sheet"] if "paid-up capital" in row.line_item_raw.lower())
    assert row.values[0].unit_hint == "INR"
    assert row.values[0].value_crore == 1928.314205


def test_share_capital_note_monetary_rows_use_lakh_context(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "The break-up of Basel II capital funds as at March 31, 2021 was as follows: "
        "(₹ in Lakhs) Description Amount Core Equity Tier I Capital - Instruments and Reserves "
        "Directly issued qualifying common share capital plus related stock surplus (share premium) 1,72,831 "
        "Retained earnings 1,26,992 "
        "Investment Fluctuation Reserve 2,051 "
        "A CET1 capital before regulatory adjustments 2,99,824"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-LAKHS", "page": 53, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"share_capital_note": [_candidate("share_capital_note", "CHK-LAKHS", 53, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy21",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    retained = next(row for row in result.tables["share_capital"] if row.line_item_raw == "Retained earnings")
    reserve = next(row for row in result.tables["share_capital"] if row.line_item_raw == "Investment Fluctuation Reserve")
    assert retained.values[0].unit_hint == "lakhs"
    assert retained.values[0].value_crore == 1269.92
    assert reserve.values[0].value_crore == 20.51


def test_mixed_unit_table_keeps_monetary_rows_in_declared_crores(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Reconciliation of estimated income tax Particulars For the Year ended 31st March 2022 "
        "Profit before tax 127.38 74.52 Enacted income tax rate 25.168% 25.168% "
        "Depreciation allowance under IT Act (0.26) 0.01 "
        "(All figures are in INR Crores unless specifically stated otherwise)"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-MIXED", "page": 82, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "primary_profit_and_loss_statement": [
                    _candidate("primary_profit_and_loss_statement", "CHK-MIXED", 82, text)
                ]
            }
        ),
    )

    result = extract_financial_tables(
        company="acme", year="fy22", chunk_path=chunk_path, discovery_path=discovery_path
    )

    pbt = next(row for row in result.tables["profit_and_loss"] if row.line_item_raw == "Profit before tax")
    tax_rate = next(row for row in result.tables["profit_and_loss"] if row.line_item_raw == "Enacted income tax rate")
    depreciation = next(
        row for row in result.tables["profit_and_loss"] if row.line_item_raw == "Depreciation allowance under IT Act"
    )
    assert (pbt.values[0].unit_hint, pbt.values[0].value_type, pbt.values[0].value_crore) == (
        "crores", "monetary", 127.38
    )
    assert (tax_rate.values[0].unit_hint, tax_rate.values[0].value_type, tax_rate.values[0].value_crore) == (
        "%", "percentage", None
    )
    assert (depreciation.values[0].unit_hint, depreciation.values[0].value_type, depreciation.values[0].value_crore) == (
        "crores", "monetary", -0.26
    )


def test_current_liabilities_text_does_not_imply_crores_unit(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Particulars Note As at March 31, 2024 As at March 31, 2023 "
        "Current liabilities Trade payables 54,838.87 53,670.80 "
        "Other current liabilities 1,689.77 2,033.50 "
        "Total current liabilities 1,00,582.60 81,949.56 "
        "Total Liabilities 1,06,719.70 89,508.97 "
        "TOTAL EQUITY AND LIABILITIES 3,00,897.93 2,41,258.32"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-CURRENT-NO-UNIT", "page": 290, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"financial_note": [_candidate("financial_note", "CHK-CURRENT-NO-UNIT", 290, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy24",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = next(row for row in result.tables["balance_sheet"] if row.line_item_raw == "Total Liabilities")
    assert row.values[0].unit_hint == ""
    assert row.values[0].value_crore is None


def test_balance_sheet_table_extraction(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Standalone Balance Sheet (All figures are in INR Crores unless specifically stated otherwise) "
        "Particulars Notes No As at March 31, 2025 As at March 31, 2024 "
        "Property, plant and equipment 4 120.57 91.24 Capital work in progress 5a 7.18 1.35 "
        "Total Assets 1,691.77 1,434.94 Equity Share capital 15 11.20 11.20 Total Liabilities 367.56 267.86"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-002", "page": 12, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"primary_balance_sheet_statement": [_candidate("primary_balance_sheet_statement", "CHK-002", 12, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    rows = result.tables["balance_sheet"]
    assert any(row.line_item_raw == "Property, plant and equipment" for row in rows)
    assert all(row.basis == "standalone" for row in rows)


def test_balance_sheet_generic_total_is_labeled_only_at_assets_equity_boundary(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Balance Sheet (All figures are in INR Crores) Particulars "
        "Property, plant and equipment 44.16 29.21 Current assets 519.85 261.32 "
        "TOTAL 706.67 328.60 EQUITY AND LIABILITIES Equity Share capital 10.38 1.70 "
        "Other Equity 564.13 206.23"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-BS", "page": 59, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            company="acme",
            year="fy22",
            sections={
                "primary_balance_sheet_statement": [
                    _candidate("primary_balance_sheet_statement", "CHK-BS", 59, text)
                ]
            },
        ),
    )

    result = extract_financial_tables(
        company="acme", year="fy22", chunk_path=chunk_path, discovery_path=discovery_path
    )

    total_assets = next(row for row in result.tables["balance_sheet"] if row.line_item_raw == "Total Assets")
    assert total_assets.values[0].value_raw == "706.67"


def test_balance_sheet_generic_subtotal_is_not_reclassified(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Balance Sheet (All figures are in INR Crores) Particulars "
        "Non-current assets 100.00 90.00 TOTAL 100.00 90.00 "
        "Current assets 200.00 180.00 Total Assets 300.00 270.00 "
        "Equity Share capital 50.00 50.00 Total Liabilities 250.00 220.00"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-SUB", "page": 10, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "primary_balance_sheet_statement": [
                    _candidate("primary_balance_sheet_statement", "CHK-SUB", 10, text)
                ]
            }
        ),
    )

    result = extract_financial_tables(
        company="acme", year="fy25", chunk_path=chunk_path, discovery_path=discovery_path
    )
    labels = [row.line_item_raw for row in result.tables["balance_sheet"]]
    assert labels.count("Total Assets") == 1
    assert "TOTAL" in labels


def test_balance_sheet_readiness_accepts_equity_plus_reserves_path(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    output_path = tmp_path / "raw_financial_tables.json"
    text = (
        "Standalone Balance Sheet (All figures are in INR Crores unless specifically stated otherwise) "
        "Particulars As at March 31, 2025 As at March 31, 2024 Total Assets 300.00 270.00 "
        "Equity Share capital 50.00 50.00 Retained earnings 25.00 20.00 "
        "Investment Fluctuation Reserve 5.00 4.00"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-EQ", "page": 12, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"primary_balance_sheet_statement": [_candidate("primary_balance_sheet_statement", "CHK-EQ", 12, text)]}
        ),
    )

    result = write_financial_extraction(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
        output_path=output_path,
    )

    readiness_payload = json.loads((tmp_path / "financial_extraction_readiness.json").read_text(encoding="utf-8"))
    assert readiness_payload["status"] == "READY"
    report = next(item for item in readiness_payload["candidate_reports"] if item["section_type"] == "primary_balance_sheet_statement")
    assert report["selected"] is True
    assert "balance_sheet.reserves" in report["matched_fields"]
    assert any(row.line_item_raw == "Retained earnings" for row in result.tables["balance_sheet"])


@pytest.mark.parametrize(
    "year",
    ["fy21", "fy22", "fy23"],
)
def test_real_ujjivan_balance_sheet_artifacts_keep_total_assets(year):
    discovery, result = _load_real_ujjivan_financials(year)

    readiness = build_financial_extraction_readiness(discovery, result)
    report = next(item for item in readiness["candidate_reports"] if item["section_type"] == "primary_balance_sheet_statement")

    assert readiness["status"] == "READY"
    assert report["selected"] is True
    assert "balance_sheet.total_assets" in report["matched_fields"]
    assert any(row.line_item_raw == "Total Assets" for row in result.tables["balance_sheet"])


def test_cash_flow_table_extraction_with_negative_values(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Cash Flow Statement (All figures are in INR Millions unless specifically stated otherwise) "
        "Particulars For the year ended March 31, 2025 For the year ended March 31, 2024 "
        "Net Profit before tax 242.19 164.83 Purchase of investments (393.10) (82.00) "
        "Net cash generated from operating activities 139.38 (17.24)"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-003", "page": 18, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"primary_cash_flow_statement": [_candidate("primary_cash_flow_statement", "CHK-003", 18, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    purchase_row = next(row for row in result.tables["cash_flow"] if row.line_item_raw == "Purchase of investments")
    assert purchase_row.values[0].value_raw == "(393.10)"
    assert purchase_row.values[0].value_crore == -39.31


def test_multi_year_columns_are_preserved(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Revenue note (All figures are in INR Crores) "
        "Particulars FY23 FY24 FY25 Revenue from operations 200.00 250.00 300.00 Other income 10.00 12.00 15.00"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-004", "page": 25, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"financial_note": [_candidate("financial_note", "CHK-004", 25, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    revenue_row = next(row for row in result.tables["revenue"] if row.line_item_raw == "Revenue from operations")
    assert [value.period for value in revenue_row.values] == ["FY23", "FY24", "FY25"]


def test_shareholding_pattern_keeps_non_monetary_values(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Shareholding Pattern Particulars FY24 FY25 Promoter holding 54.20% 53.80% "
        "Public holding 45.80% 46.20%"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-005", "page": 31, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"shareholding_note": [_candidate("shareholding_note", "CHK-005", 31, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = next(row for row in result.tables["shareholding_pattern"] if row.line_item_raw == "Promoter holding")
    assert row.values[0].value_crore is None
    assert row.values[0].unit_hint == "%"
    assert row.values[0].value_type == "percentage"


def test_unknown_basis_fallback_and_warning(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Particulars Notes No As at March 31, 2025 As at March 31, 2024 "
        "Borrowings 17 200.00 180.00"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-006", "page": 40, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"financial_note": [_candidate("financial_note", "CHK-006", 40, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = result.tables["borrowings"][0]
    assert row.basis == "unknown"
    assert "basis unclear" in row.warnings


def test_malformed_discovery_handling(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    _write_chunks(chunk_path, [{"chunk_id": "CHK-007", "page": 1, "text": "x", "metadata": {}}])
    _write_json(discovery_path, {"company": "acme"})

    with pytest.raises(RuntimeError, match="requires a valid discovery artifact"):
        extract_financial_tables(
            company="acme",
            year="fy25",
            chunk_path=chunk_path,
            discovery_path=discovery_path,
        )


def test_no_company_specific_behavior(tmp_path):
    text = Path("knowledge/financials/extractor.py").read_text(encoding="utf-8").lower()
    assert "datapatterns" not in text
    assert "polymatech" not in text
    assert "tanla" not in text
    assert "tips" not in text


def test_accounting_policy_candidate_is_not_extracted(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = "Summary of significant accounting policies Revenue is recognised in the statement of profit and loss when earned."
    _write_chunks(chunk_path, [{"chunk_id": "CHK-008", "page": 41, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"accounting_policy": [_candidate("accounting_policy", "CHK-008", 41, text)]}
        ),
    )

    with pytest.raises(RuntimeError, match="found no extractable financial rows"):
        extract_financial_tables(
            company="acme",
            year="fy25",
            chunk_path=chunk_path,
            discovery_path=discovery_path,
        )


def test_auditor_report_candidate_is_not_extracted(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = "Independent Auditor's Report Our opinion on the balance sheet and statement of profit and loss."
    _write_chunks(chunk_path, [{"chunk_id": "CHK-009", "page": 42, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"auditor_report": [_candidate("auditor_report", "CHK-009", 42, text)]}
        ),
    )

    with pytest.raises(RuntimeError, match="found no extractable financial rows"):
        extract_financial_tables(
            company="acme",
            year="fy25",
            chunk_path=chunk_path,
            discovery_path=discovery_path,
        )


def test_investment_schedule_rows_do_not_go_to_profit_and_loss(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Notes to the financial statements Investments Particulars March 31, 2025 March 31, 2024 "
        "Current investments in mutual funds 125.00 90.00"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-010", "page": 43, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"financial_note": [_candidate("financial_note", "CHK-010", 43, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    assert result.tables["profit_and_loss"] == []
    assert result.tables["investment_schedule"]


def test_eps_per_share_not_converted_to_crore(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Earnings per share Particulars March 31, 2025 March 31, 2024 "
        "Basic earnings per share 32.45 23.80"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-011", "page": 44, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"eps_note": [_candidate("eps_note", "CHK-011", 44, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = result.tables["eps"][0]
    assert row.values[0].value_crore is None
    assert row.values[0].value_type == "per_share"


def test_share_capital_numbers_amount_columns_are_typed_separately(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Equity Share Capital "
        "Particulars Numbers Amount Numbers Amount "
        "As at March 31, 2025 As at March 31, 2024 "
        "Issued, subscribed and paid-up equity shares of Rs.2 each "
        "78750000 15.75 70000000 14.00"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-013", "page": 46, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"share_capital_note": [_candidate("share_capital_note", "CHK-013", 46, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = next(row for row in result.tables["share_capital"] if "paid-up equity shares" in row.line_item_raw.lower())
    assert [value.period for value in row.values] == [
        "March 31, 2025",
        "March 31, 2025",
        "March 31, 2024",
        "March 31, 2024",
    ]
    assert [value.value_type for value in row.values] == [
        "share_count",
        "monetary",
        "share_count",
        "monetary",
    ]
    assert row.values[0].unit_hint == "shares"
    assert row.values[0].value_crore is None
    assert row.values[1].value_type == "monetary"
    assert row.values[1].value_crore == 15.75


def test_share_capital_numbers_amount_columns_still_type_correctly_without_period_headers(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Equity Share Capital Numbers* Amount Numbers* Amount As at March 31, 2025 "
        "Issued, subscribed and fully paid up Equity shares of Rs.2 each "
        "55983969 11.20 55983969 11.20"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-014", "page": 47, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"share_capital_note": [_candidate("share_capital_note", "CHK-014", 47, text)]}
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    row = next(row for row in result.tables["share_capital"] if "fully paid up equity shares" in row.line_item_raw.lower())
    assert [value.value_type for value in row.values] == ["share_count", "monetary", "share_count", "monetary"]
    assert row.values[0].unit_hint == "shares"
    assert row.values[0].value_crore is None
    assert row.values[1].value_crore == 11.2


def test_rejected_rows_are_written_to_rejection_audit(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    output_path = tmp_path / "raw_financial_tables.json"
    text = (
        "Statement of Profit and Loss Particulars March 31, 2025 March 31, 2024 "
        "Revenue from operations 500.00 420.00 March 10.00 11.00"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-012", "page": 45, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={"primary_profit_and_loss_statement": [_candidate("primary_profit_and_loss_statement", "CHK-012", 45, text)]}
        ),
    )

    with pytest.raises(RuntimeError, match="FINANCIAL_EXTRACTION_NOT_READY"):
        write_financial_extraction(
            company="acme",
            year="fy25",
            chunk_path=chunk_path,
            discovery_path=discovery_path,
            output_path=output_path,
        )

    rejection_payload = json.loads((tmp_path / "financial_extraction_rejections.json").read_text(encoding="utf-8"))
    assert rejection_payload["rejections"]
    readiness_payload = json.loads((tmp_path / "financial_extraction_readiness.json").read_text(encoding="utf-8"))
    assert readiness_payload["status"] == "BLOCKED"
    assert "profit_and_loss.pat" in " ".join(readiness_payload["blocking_reasons"])
