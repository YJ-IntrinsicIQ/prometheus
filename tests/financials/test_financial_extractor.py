import json
from pathlib import Path

import pytest

from knowledge.financials.extractor import extract_financial_tables, write_financial_extraction
from knowledge.financials.extraction_schema import FinancialExtractionResult
from knowledge.financials.extractor import _parse_discovery, build_financial_extraction_readiness
from knowledge.financials.discovery import discover_financial_sections
from knowledge.financials.line_item_mapper import map_line_item


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


def test_profit_and_loss_continuation_extracts_owner_attributable_pat(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    output_path = tmp_path / "raw_financial_tables.json"
    chunks = [
        {
            "chunk_id": "CHK-PNL-1",
            "page": 186,
            "text": (
                "Consolidated Statement of Profit and Loss for the year ended March 31, 2025 "
                "` in Million Particulars Notes Year ended March 31, 2025 Year ended March 31, 2024 "
                "Revenue from operations 30 328,375.0 290,659.1 Other income 31 6,359.8 10,254.9 "
                "Total income 334,734.8 300,914.0 Profit before tax 50,095.9 38,102.0"
            ),
            "metadata": {},
        },
        {
            "chunk_id": "CHK-PNL-2",
            "page": 186,
            "text": (
                "Total tax expense 49 8,228.0 6,008.8 "
                "Profit for the year before non-controlling interests 41,719.6 32,078.6 "
                "Non-controlling interests 71 4,070.3 5,424.4 "
                "Profit for the year attributable to owners of the Company 37,649.3 26,654.2"
            ),
            "metadata": {},
        },
        {
            "chunk_id": "CHK-PNL-3",
            "page": 187,
            "text": (
                "Consolidated Statement of Profit and Loss for the year ended March 31, 2025 "
                "Other comprehensive income 21,208.3 16,799.9 Earnings per equity share Basic 15.7 11.1"
            ),
            "metadata": {},
        },
    ]
    _write_chunks(chunk_path, chunks)
    discovery = discover_financial_sections(company="acme", year="fy25", chunk_path=chunk_path)
    _write_json(discovery_path, discovery.to_dict())

    result = write_financial_extraction(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
        output_path=output_path,
    )

    rows = result.tables["profit_and_loss"]
    owner_pat = next(row for row in rows if row.line_item_raw == "Profit for the year attributable to owners of the Company")
    assert owner_pat.basis == "consolidated"
    assert owner_pat.is_primary_statement is True
    assert owner_pat.values[0].period == "March 31, 2025"
    assert owner_pat.values[0].value_crore == 3764.93
    pre_nci_row = next(row for row in rows if row.line_item_raw == "Profit for the year before non-controlling interests")
    assert all(
        match.canonical_field != "profit_and_loss.pat"
        for match in map_line_item(table_type="profit_and_loss", line_item_raw=pre_nci_row.line_item_raw)
    )


def test_balance_sheet_continuation_preserves_total_assets_from_tail_titled_chunk(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    output_path = tmp_path / "raw_financial_tables.json"
    chunks = [
        {
            "chunk_id": "CHK-BS-1",
            "page": 184,
            "text": (
                "Consolidated Balance Sheet as at March 31, 2025 ` in Million "
                "Particulars Notes As at March 31, 2025 As at March 31, 2024 "
                "ASSETS (1) Non-current assets "
                "(a) Property, plant and equipment 3 105,674.3 100,274.2 "
                "Total non-current assets 365,983.0 336,246.2"
            ),
            "metadata": {},
        },
        {
            "chunk_id": "CHK-BS-2",
            "page": 184,
            "text": (
                "(2) Current assets (a) Inventories 11 78,749.9 78,859.8 "
                "(b) Financial assets (i) Trade receivables 12 120,000.0 110,000.0 "
                "Total current assets 316,541.6 310,691.9 "
                "TOTAL ASSETS 682,524.6 646,938.1 "
                "Consolidated Balance Sheet"
            ),
            "metadata": {},
        },
        {
            "chunk_id": "CHK-BS-3",
            "page": 185,
            "text": (
                "Consolidated Balance Sheet as at March 31, 2025 ` in Million "
                "Particulars Notes As at March 31, 2025 As at March 31, 2024 "
                "EQUITY AND LIABILITIES Equity Share capital 19 2,399.3 2,399.3 "
                "Other equity 20 450,245.2 411,691.3 "
                "Total equity 491,246.9 447,226.0 "
                "Total liabilities 191,277.7 199,712.1 "
                "TOTAL EQUITY AND LIABILITIES 682,524.6 646,938.1"
            ),
            "metadata": {},
        },
    ]
    _write_chunks(chunk_path, chunks)
    discovery = discover_financial_sections(company="acme", year="fy25", chunk_path=chunk_path)
    _write_json(discovery_path, discovery.to_dict())

    result = write_financial_extraction(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
        output_path=output_path,
    )

    rows = result.tables["balance_sheet"]
    total_assets = next(row for row in rows if row.line_item_raw == "TOTAL ASSETS")
    assert total_assets.basis == "consolidated"
    assert total_assets.source_section_type == "primary_balance_sheet_statement"
    assert total_assets.is_primary_statement is True
    assert total_assets.chunk_id == "CHK-BS-2"
    assert total_assets.values[0].period == "March 31, 2025"
    assert total_assets.values[0].value_crore == 68252.46

    total_equity_liabilities = next(row for row in rows if row.line_item_raw == "TOTAL EQUITY AND LIABILITIES")
    assert total_equity_liabilities.chunk_id == "CHK-BS-3"


def test_balance_sheet_note_total_assets_does_not_become_primary_statement(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    output_path = tmp_path / "raw_financial_tables.json"
    note_text = (
        "Note 52 Financial instruments ` in Million As at March 31, 2025 As at March 31, 2024 "
        "Total Assets by fair value level 100.0 90.0 Total liabilities by fair value level 40.0 35.0"
    )
    primary_text = (
        "Consolidated Balance Sheet as at March 31, 2025 ` in Million "
        "Particulars Notes As at March 31, 2025 As at March 31, 2024 "
        "ASSETS Cash and bank balances 10 1,000.0 900.0 "
        "TOTAL ASSETS 1,000.0 900.0 EQUITY AND LIABILITIES "
        "Total equity 600.0 550.0 Total liabilities 400.0 350.0 "
        "TOTAL EQUITY AND LIABILITIES 1,000.0 900.0"
    )
    _write_chunks(
        chunk_path,
        [
            {"chunk_id": "CHK-NOTE", "page": 250, "text": note_text, "metadata": {}},
            {"chunk_id": "CHK-PRIMARY", "page": 180, "text": primary_text, "metadata": {}},
        ],
    )
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "financial_note": [_candidate("financial_note", "CHK-NOTE", 250, note_text)],
                "primary_balance_sheet_statement": [
                    _candidate("primary_balance_sheet_statement", "CHK-PRIMARY", 180, primary_text)
                ],
            }
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    primary_total_assets = [
        row
        for row in result.tables["balance_sheet"]
        if row.line_item_raw == "TOTAL ASSETS" and row.is_primary_statement
    ]
    assert primary_total_assets
    assert primary_total_assets[0].chunk_id == "CHK-PRIMARY"
    note_rows = [row for row in result.tables["balance_sheet"] if row.chunk_id == "CHK-NOTE"]
    assert all(not row.is_primary_statement for row in note_rows)


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

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    readiness_payload = build_financial_extraction_readiness(_parse_discovery(discovery_path), result)
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


def test_tail_titled_cash_flow_continuation_extracts_real_rows_without_footer_cfo(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    output_path = tmp_path / "raw_financial_tables.json"
    context_text = (
        "` in Million Particulars Year ended March 31, 2025 Year ended March 31, 2024 "
        "Consolidated Statement of Cash Flow"
    )
    tail_text = (
        "Payments for purchase of property, plant and equipment (including capital work-in-progress) "
        "(21,285.8) (22,018.1) Cash and cash equivalents at the end of the year 102,687.7 92,856.5 "
        "Consolidated Statement of Cash Flow for the year ended March 31, 2025"
    )
    _write_chunks(
        chunk_path,
        [
            {"chunk_id": "CHK-CF-CONTEXT", "page": 229, "text": context_text, "metadata": {}},
            {"chunk_id": "CHK-CF-TAIL", "page": 230, "text": tail_text, "metadata": {}},
        ],
    )

    discovery = discover_financial_sections(company="acme", year="fy25", chunk_path=chunk_path)
    _write_json(discovery_path, discovery.to_dict())

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    cash_rows = result.tables["cash_flow"]
    purchase = next(row for row in cash_rows if "purchase of property" in row.line_item_raw.lower())
    assert purchase.basis == "consolidated"
    assert purchase.values[0].period == "March 31, 2025"
    assert purchase.values[0].unit_hint == "million"
    assert purchase.values[0].value_crore == -2128.58
    assert not any("statement of cash flow for the year ended march" in row.line_item_raw.lower() for row in cash_rows)


def test_cash_flow_assembly_prefers_complete_unit_span_over_basis_only_tail(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    header_text = (
        "` in Million Particulars Year ended March 31, 2025 Year ended March 31, 2024 "
        "A. Cash flow from operating activities Profit before tax 137,521.3 110,878.9 "
        "Operating profit before working capital changes 148,724.9 126,422.9 "
        "(Increase) / Decrease in trade receivables (16,020.5) 3,528.9"
    )
    continuation_text = (
        "(Increase) / Decrease in other assets (593.2) (3,839.0) "
        "Cash generated from operations 145,489.3 137,044.2 "
        "Net Income tax (paid) / refund received (4,768.4) (15,694.4) "
        "Net cash generated from / (used in) operating activities (A) 140,720.9 121,349.8 "
        "B. Cash flow from investing activities "
        "Payments for purchase of property, plant and equipment (21,285.8) (22,018.1) "
        "Net cash flow from / (used in) investing activities (B) (53,061.6) (6,902.0)"
    )
    tail_text = (
        "Dividend paid (36,139.7) (28,981.7) "
        "Net cash flow from / (used in) financing activities (C) (79,058.2) (67,101.6) "
        "Cash and cash equivalents at the end of the year 102,687.7 92,856.5 "
        "Consolidated Statement of Cash Flow for the year ended March 31, 2025"
    )
    _write_chunks(
        chunk_path,
        [
            {"chunk_id": "CHK-CF-HEAD", "page": 230, "text": header_text, "metadata": {}},
            {"chunk_id": "CHK-CF-MID", "page": 230, "text": continuation_text, "metadata": {}},
            {"chunk_id": "CHK-CF-TAIL", "page": 230, "text": tail_text, "metadata": {}},
        ],
    )
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "primary_cash_flow_statement": [
                    {**_candidate("primary_cash_flow_statement", "CHK-CF-HEAD", 230, header_text), "basis": "unknown"},
                    {**_candidate("primary_cash_flow_statement", "CHK-CF-MID", 230, continuation_text), "basis": "unknown"},
                    {**_candidate("primary_cash_flow_statement", "CHK-CF-TAIL", 230, tail_text), "basis": "consolidated"},
                ]
            }
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    cfo = next(row for row in result.tables["cash_flow"] if "net cash generated from / (used in) operating activities" in row.line_item_raw.lower())
    capex = next(row for row in result.tables["cash_flow"] if "purchase of property" in row.line_item_raw.lower())
    assert cfo.basis == "consolidated"
    assert cfo.values[0].unit_hint == "million"
    assert cfo.values[0].value_crore == 14072.09
    assert capex.values[0].unit_hint == "million"
    assert capex.values[0].value_crore == -2128.58


def test_wrapped_primary_cash_capex_row_survives_cash_flow_extraction(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "` in Million Particulars Year ended March 31, 2023 Year ended March 31, 2022 "
        "A. Cash flow from operating activities Profit before tax 94,084.3 44,813.2 "
        "Net cash generated from operating activities (A) 49,593.3 89,845.4 "
        "B. Cash flow from investing activities "
        "Payments for purchase of property, plant and equipment (including capital work-in- "
        "progress, other intangible assets and intangible assets under development) "
        "(20,855.8) (14,950.4) "
        "Proceeds from disposal of property, plant and equipment and other intangible assets 210.1 606.1 "
        "Purchase of investments Others (218,087.4) (241,353.5) "
        "Net cash used in investing activities (B) (79,436.8) (57,247.4) "
        "Consolidated Cash Flow Statement for the year ended March 31, 2023"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-SUN-CF", "page": 210, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "primary_cash_flow_statement": [
                    {**_candidate("primary_cash_flow_statement", "CHK-SUN-CF", 210, text), "basis": "consolidated"}
                ]
            }
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy23",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    capex = next(row for row in result.tables["cash_flow"] if "payments for purchase of property" in row.line_item_raw.lower())
    assert capex.basis == "consolidated"
    assert capex.source_section_type == "primary_cash_flow_statement"
    assert capex.is_primary_statement is True
    assert capex.values[0].period == "March 31, 2023"
    assert capex.values[0].value_crore == -2085.58
    assert capex.values[1].period == "March 31, 2022"
    assert capex.values[1].value_crore == -1495.04


def test_primary_statement_assembly_prefers_consolidated_over_slightly_longer_standalone(tmp_path):
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    standalone_text = (
        "STANDALONE STATEMENT OF PROFIT AND LOSS ` in Million "
        "Particulars Year ended March 31, 2025 Year ended March 31, 2024 "
        "Revenue from operations 1,000.0 900.0 Other income 50.0 40.0 Total income 1,050.0 940.0 "
        "Employee benefits expense 100.0 90.0 Other expenses 200.0 180.0 Finance costs 10.0 8.0 "
        "Depreciation and amortisation expense 20.0 18.0 Total expenses 330.0 296.0 "
        "Profit before tax 720.0 644.0 Current tax 100.0 90.0 Deferred tax 20.0 10.0 "
        "Total tax expense 120.0 100.0 Profit for the year 600.0 544.0"
    )
    consolidated_text = (
        "CONSOLIDATED STATEMENT OF PROFIT AND LOSS ` in Million "
        "Particulars Year ended March 31, 2025 Year ended March 31, 2024 "
        "Revenue from operations 3,000.0 2,700.0 Other income 100.0 90.0 Total income 3,100.0 2,790.0 "
        "Employee benefits expense 300.0 280.0 Other expenses 500.0 460.0 Total expenses 800.0 740.0 "
        "Profit before tax 2,300.0 2,050.0 Total tax expense 400.0 350.0 "
        "Profit for the year attributable to owners of the Company 1,900.0 1,700.0"
    )
    _write_chunks(
        chunk_path,
        [
            {"chunk_id": "CHK-STANDALONE-PL", "page": 10, "text": standalone_text, "metadata": {}},
            {"chunk_id": "CHK-CONSOLIDATED-PL", "page": 20, "text": consolidated_text, "metadata": {}},
        ],
    )
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "primary_profit_and_loss_statement": [
                    {**_candidate("primary_profit_and_loss_statement", "CHK-STANDALONE-PL", 10, standalone_text), "basis": "standalone"},
                    {**_candidate("primary_profit_and_loss_statement", "CHK-CONSOLIDATED-PL", 20, consolidated_text), "basis": "consolidated"},
                ]
            }
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy25",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    revenue = next(row for row in result.tables["profit_and_loss"] if row.line_item_raw == "Revenue from operations")
    pat = next(row for row in result.tables["profit_and_loss"] if "attributable to owners" in row.line_item_raw.lower())
    assert revenue.basis == "consolidated"
    assert revenue.values[0].value_crore == 300.0
    assert pat.basis == "consolidated"
    assert pat.values[0].value_crore == 190.0


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


# ---------------------------------------------------------------------------
# Regression tests — Sun Pharma FY23 fix (2026-08-28)
# Covers: wrapped rows, cross-chunk assembly, note vs primary ranking,
# basis/period isolation, semantic mapping, and no-hardcoding invariants.
# ---------------------------------------------------------------------------


def test_wrapped_revenue_row_roman_numeral_prefix(tmp_path):
    """Roman-numeral-prefixed revenue label extracted from primary P&L."""
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    output_path = tmp_path / "raw_financial_tables.json"
    text = (
        "Consolidated Statement of Profit and Loss for the year ended March 31, 2023 "
        "` in Million Particulars Notes Year ended March 31, 2023 Year ended March 31, 2022 "
        "(I) Revenue from operations 30 438,856.8 385,246.7 "
        "(II) Other income 31 4,988.9 7,197.2 "
        "(III) Total income (I+II) 443,845.7 392,443.9 "
        "(XII) Profit before tax (X-XI) 94,084.3 44,813.2 "
        "(XIV) Profit for the year attributable to owners of the Company (XII-XIII) 84,735.8 41,611.0"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-PL-ROMAN", "page": 207, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "primary_profit_and_loss_statement": [
                    {**_candidate("primary_profit_and_loss_statement", "CHK-PL-ROMAN", 207, text), "basis": "consolidated"}
                ]
            }
        ),
    )

    result = write_financial_extraction(
        company="acme",
        year="fy23",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
        output_path=output_path,
    )

    rows = result.tables["profit_and_loss"]
    # Extractor may strip the "(I)" roman-numeral prefix when normalising revenue labels
    revenue = next(r for r in rows if "Revenue from operations" in r.line_item_raw)
    assert revenue.basis == "consolidated"
    assert revenue.is_primary_statement is True
    assert revenue.values[0].period == "March 31, 2023"
    assert revenue.values[0].value_crore == pytest.approx(43885.68, rel=1e-3)

    pat = next(r for r in rows if "attributable to owners of the Company" in r.line_item_raw)
    assert pat.basis == "consolidated"
    assert pat.is_primary_statement is True
    assert pat.values[0].value_crore == pytest.approx(8473.58, rel=1e-3)


def test_wrapped_pat_row_roman_numeral_prefix_maps_to_pat(tmp_path):
    """Long Roman-numeral PAT label maps to profit_and_loss.pat, not a sub-metric."""
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    text = (
        "Consolidated Statement of Profit and Loss ` in Million "
        "Particulars Year ended March 31, 2023 Year ended March 31, 2022 "
        "(I) Revenue from operations 300,000.0 270,000.0 "
        "(X) Profit for the year before non-controlling interests 80,000.0 60,000.0 "
        "(XI) Non-controlling interests 5,000.0 4,000.0 "
        "(XII) Profit for the year attributable to owners of the Company (X-XI) 75,000.0 56,000.0"
    )
    _write_chunks(chunk_path, [{"chunk_id": "CHK-PAT-ROMAN", "page": 50, "text": text, "metadata": {}}])
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "primary_profit_and_loss_statement": [
                    {**_candidate("primary_profit_and_loss_statement", "CHK-PAT-ROMAN", 50, text), "basis": "consolidated"}
                ]
            }
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy23",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    rows = result.tables["profit_and_loss"]
    # map_line_item returns canonical_field as a bare name ("pat"), not "profit_and_loss.pat"
    pat_rows = [
        r for r in rows
        if any(m.canonical_field == "pat" for m in map_line_item(table_type="profit_and_loss", line_item_raw=r.line_item_raw))
    ]
    assert pat_rows, "Expected at least one row mapped to profit_and_loss.pat"
    assert all(r.is_primary_statement for r in pat_rows)

    # Pre-NCI profit must NOT be mapped to pat
    pre_nci = next(r for r in rows if "before non-controlling interests" in r.line_item_raw.lower())
    assert all(
        m.canonical_field != "pat"
        for m in map_line_item(table_type="profit_and_loss", line_item_raw=pre_nci.line_item_raw)
    )


def test_revenue_and_pat_split_across_adjacent_chunks(tmp_path):
    """P&L split across two chunks: revenue in chunk-1, PAT in chunk-2; assembly extracts both."""
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    output_path = tmp_path / "raw_financial_tables.json"
    chunk1_text = (
        "Consolidated Statement of Profit and Loss ` in Crores "
        "Particulars Year ended March 31, 2023 Year ended March 31, 2022 "
        "Revenue from operations 50,000.0 45,000.0 "
        "Other income 500.0 400.0 Total income 50,500.0 45,400.0 "
        "Total expenses 40,000.0 36,000.0 Profit before tax 10,500.0 9,400.0"
    )
    chunk2_text = (
        "Tax expense 2,000.0 1,800.0 "
        "Profit for the year 8,500.0 7,600.0 "
        "Non-controlling interests 200.0 150.0 "
        "Profit for the year attributable to owners of the Company 8,300.0 7,450.0"
    )
    _write_chunks(
        chunk_path,
        [
            {"chunk_id": "CHK-PL-A", "page": 100, "text": chunk1_text, "metadata": {}},
            {"chunk_id": "CHK-PL-B", "page": 100, "text": chunk2_text, "metadata": {}},
        ],
    )
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "primary_profit_and_loss_statement": [
                    {**_candidate("primary_profit_and_loss_statement", "CHK-PL-A", 100, chunk1_text), "basis": "consolidated"},
                    {**_candidate("primary_profit_and_loss_statement", "CHK-PL-B", 100, chunk2_text), "basis": "consolidated"},
                ]
            }
        ),
    )

    result = write_financial_extraction(
        company="acme",
        year="fy23",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
        output_path=output_path,
    )

    rows = result.tables["profit_and_loss"]
    revenue = next(r for r in rows if r.line_item_raw == "Revenue from operations")
    assert revenue.values[0].value_crore == pytest.approx(50000.0)

    pat_row = next(
        r for r in rows if "attributable to owners of the Company" in r.line_item_raw
    )
    assert pat_row.values[0].value_crore == pytest.approx(8300.0)
    assert pat_row.is_primary_statement is True


def test_note_dense_expense_rows_do_not_outrank_pl_with_semantic_hints(tmp_path):
    """A note table with many expense rows (no revenue/PAT semantics) loses to a proper P&L."""
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    # Dense expense-only note — many rows, no semantic hint keywords
    note_text = (
        "` in Million Year ended March 31, 2023 Year ended March 31, 2022 "
        "Salaries wages and bonus 6,551.5 6,535.3 "
        "Staff welfare 226.0 255.3 "
        "Professional and consultancy 6,882.2 8,554.4 "
        "Consumables 1,200.0 1,100.0 "
        "Depreciation on R&D assets 800.0 750.0 "
        "Power and fuel 400.0 380.0 "
        "Repairs and maintenance 300.0 290.0 "
        "Lab expenses 950.0 900.0 "
        "Clinical trials 2,100.0 1,980.0 "
        "Others 500.0 480.0 "
        "Total R&D expenditure 19,909.7 20,225.0"
    )
    # Compact P&L — fewer rows but contains canonical semantic hints
    pl_text = (
        "Consolidated Statement of Profit and Loss ` in Million "
        "Particulars Year ended March 31, 2023 Year ended March 31, 2022 "
        "Revenue from operations 438,856.8 385,246.7 "
        "Other income 4,988.9 7,197.2 "
        "Total expenses 344,772.5 340,433.7 "
        "Profit before tax 94,084.3 44,813.2 "
        "Tax expense 9,348.5 3,202.2 "
        "Profit for the year attributable to owners of the Company 84,735.8 41,611.0"
    )
    _write_chunks(
        chunk_path,
        [
            {"chunk_id": "CHK-NOTE-RD", "page": 244, "text": note_text, "metadata": {}},
            {"chunk_id": "CHK-PL-REAL", "page": 207, "text": pl_text, "metadata": {}},
        ],
    )
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "primary_profit_and_loss_statement": [
                    {**_candidate("primary_profit_and_loss_statement", "CHK-NOTE-RD", 244, note_text), "basis": "consolidated"},
                    {**_candidate("primary_profit_and_loss_statement", "CHK-PL-REAL", 207, pl_text), "basis": "consolidated"},
                ]
            }
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy23",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    pl_rows = result.tables["profit_and_loss"]
    revenue = next((r for r in pl_rows if r.line_item_raw == "Revenue from operations"), None)
    assert revenue is not None, "Revenue from operations must be present from the real P&L"
    assert revenue.values[0].value_crore == pytest.approx(43885.68, rel=1e-3)

    # Expense-only note rows like "Salaries wages and bonus" must not appear in primary P&L
    primary_labels = {r.line_item_raw for r in pl_rows if r.is_primary_statement}
    assert "Salaries wages and bonus" not in primary_labels


def test_associates_jv_nci_profit_not_mapped_to_pat():
    """Share-of-profit rows and NCI map to their own fields, not profit_and_loss.pat."""
    # canonical_field is a bare name (e.g. "pat", "share_of_profit_associates")
    checks = [
        ("Share of profit of associates", {"share_of_profit_associates"}),
        ("Share of profit of joint ventures", {"share_of_profit_jv"}),
        ("Non-controlling interests", {"non_controlling_interests"}),
        ("Profit for the year before non-controlling interests", set()),  # must NOT hit pat
    ]
    for label, expected_fields in checks:
        matches = map_line_item(table_type="profit_and_loss", line_item_raw=label)
        fields = {m.canonical_field for m in matches}
        # None of these should map to pat
        assert "pat" not in fields, (
            f"'{label}' must not map to profit_and_loss.pat (got {fields})"
        )
        for ef in expected_fields:
            assert ef in fields, f"'{label}' expected to map to {ef} (got {fields})"


def test_period_labeled_candidate_preferred_over_unlabeled(tmp_path):
    """Assembly prefers a candidate with explicit period column headers over an unlabeled one."""
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    # No period headers — just bare numbers
    unlabeled_text = (
        "Consolidated Statement of Profit and Loss ` in Crores "
        "Revenue from operations 50,000.0 45,000.0 "
        "Profit for the year attributable to owners 8,000.0 7,200.0"
    )
    # Properly period-labeled
    labeled_text = (
        "Consolidated Statement of Profit and Loss ` in Crores "
        "Particulars Year ended March 31, 2023 Year ended March 31, 2022 "
        "Revenue from operations 55,000.0 49,000.0 "
        "Profit for the year attributable to owners of the Company 9,000.0 8,100.0"
    )
    _write_chunks(
        chunk_path,
        [
            {"chunk_id": "CHK-UNLABELED", "page": 10, "text": unlabeled_text, "metadata": {}},
            {"chunk_id": "CHK-LABELED", "page": 20, "text": labeled_text, "metadata": {}},
        ],
    )
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "primary_profit_and_loss_statement": [
                    {**_candidate("primary_profit_and_loss_statement", "CHK-UNLABELED", 10, unlabeled_text), "basis": "consolidated"},
                    {**_candidate("primary_profit_and_loss_statement", "CHK-LABELED", 20, labeled_text), "basis": "consolidated"},
                ]
            }
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy23",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    pl_rows = result.tables["profit_and_loss"]
    revenue = next(r for r in pl_rows if "Revenue from operations" in r.line_item_raw)
    # Period-labeled candidate has revenue=55000; unlabeled has 50000
    assert revenue.values[0].value_crore == pytest.approx(55000.0), (
        "Period-labeled candidate should be preferred (revenue=55000, not 50000)"
    )
    assert revenue.values[0].period == "March 31, 2023"


def test_standalone_candidate_not_used_when_consolidated_present(tmp_path):
    """When both standalone and consolidated P&Ls are discovered, consolidated values are used."""
    chunk_path = tmp_path / "clean_chunks.json"
    discovery_path = tmp_path / "financial_discovery.json"
    standalone_text = (
        "STANDALONE STATEMENT OF PROFIT AND LOSS ` in Crores "
        "Particulars Year ended March 31, 2023 Year ended March 31, 2022 "
        "Revenue from operations 10,000.0 9,000.0 "
        "Profit for the year 1,500.0 1,300.0"
    )
    consolidated_text = (
        "CONSOLIDATED STATEMENT OF PROFIT AND LOSS ` in Crores "
        "Particulars Year ended March 31, 2023 Year ended March 31, 2022 "
        "Revenue from operations 50,000.0 45,000.0 "
        "Profit for the year attributable to owners of the Company 8,000.0 7,000.0"
    )
    _write_chunks(
        chunk_path,
        [
            {"chunk_id": "CHK-SA-PL", "page": 10, "text": standalone_text, "metadata": {}},
            {"chunk_id": "CHK-CONSOL-PL", "page": 20, "text": consolidated_text, "metadata": {}},
        ],
    )
    _write_json(
        discovery_path,
        _discovery_payload(
            sections={
                "primary_profit_and_loss_statement": [
                    {**_candidate("primary_profit_and_loss_statement", "CHK-SA-PL", 10, standalone_text), "basis": "standalone"},
                    {**_candidate("primary_profit_and_loss_statement", "CHK-CONSOL-PL", 20, consolidated_text), "basis": "consolidated"},
                ]
            }
        ),
    )

    result = extract_financial_tables(
        company="acme",
        year="fy23",
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )

    pl_rows = [r for r in result.tables["profit_and_loss"] if r.is_primary_statement]
    assert all(r.basis == "consolidated" for r in pl_rows), (
        "All primary P&L rows must be consolidated when consolidated candidate is available"
    )
    revenue = next(r for r in pl_rows if "Revenue from operations" in r.line_item_raw)
    # Consolidated revenue is 50000, standalone is 10000
    assert revenue.values[0].value_crore == pytest.approx(50000.0)


def test_no_company_or_sector_hardcoding_in_extractor_and_discovery():
    """Extractor and discovery source code must not reference specific company names or sectors."""
    import ast

    forbidden = {"sun_pharma", "sunpharma", "pharma", "cipla", "drreddy", "lupin", "zydus"}
    files_to_check = [
        ROOT / "knowledge" / "financials" / "extractor.py",
        ROOT / "knowledge" / "financials" / "discovery.py",
        ROOT / "knowledge" / "financials" / "line_item_mapper.py",
        ROOT / "knowledge" / "financials" / "normalizer.py",
    ]
    for file_path in files_to_check:
        source = file_path.read_text(encoding="utf-8").lower()
        # Strip comments and string literals via AST to avoid false positives on docstrings
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        # Check raw source for company-specific tokens (simple string search)
        for token in forbidden:
            assert token not in source, (
                f"Company-specific token '{token}' found in {file_path.name}. "
                "Extractor and discovery must be company-agnostic."
            )


# ---------------------------------------------------------------------------
# Real-data regression tests (read pre-generated artifacts)
# ---------------------------------------------------------------------------


def test_sun_pharma_fy23_revenue_and_pat_regression():
    """Sun Pharma FY23 normalized fundamentals must contain correct revenue and PAT."""
    fin_dir = ROOT / "companies" / "sun_pharma" / "fy23" / "financials"
    readiness_path = fin_dir / "financial_extraction_readiness.json"
    normalized_path = fin_dir / "normalized_fundamentals.json"

    if not readiness_path.exists() or not normalized_path.exists():
        pytest.skip("Sun Pharma FY23 artifacts not present")

    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["status"] == "READY", (
        f"FY23 readiness gate must be READY, got {readiness['status']}. "
        f"blocking_reasons={readiness.get('blocking_reasons')}"
    )
    assert not readiness.get("blocking_reasons"), (
        f"FY23 must have no blocking reasons, got {readiness['blocking_reasons']}"
    )

    # P&L candidate must match revenue and pat
    pl_candidate = next(
        (c for c in readiness.get("candidate_reports", []) if c["candidate_id"] == "primary_profit_and_loss_statement"),
        None,
    )
    assert pl_candidate is not None
    assert pl_candidate["selected"] is True
    assert "profit_and_loss.revenue" in pl_candidate["matched_fields"]
    assert "profit_and_loss.pat" in pl_candidate["matched_fields"]

    normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    # Locate revenue and pat from normalized output
    pl_section = normalized.get("profit_and_loss", {})
    revenue_entry = pl_section.get("revenue") or {}
    pat_entry = pl_section.get("pat") or {}

    assert revenue_entry, "profit_and_loss.revenue must be present in normalized_fundamentals"
    assert pat_entry, "profit_and_loss.pat must be present in normalized_fundamentals"

    revenue_crore = revenue_entry.get("value_crore")
    pat_crore = pat_entry.get("value_crore")

    assert revenue_crore is not None
    assert pat_crore is not None
    assert pytest.approx(revenue_crore, rel=0.01) == 43885.68, (
        f"FY23 revenue expected ~43,885.68 crore, got {revenue_crore}"
    )
    assert pytest.approx(pat_crore, rel=0.01) == 8473.58, (
        f"FY23 PAT expected ~8,473.58 crore, got {pat_crore}"
    )


@pytest.mark.parametrize("year", ["fy20", "fy22", "fy24", "fy25"])
def test_sun_pharma_existing_years_remain_ready(year):
    """Pre-existing Sun Pharma years must stay READY after the FY23 fix."""
    fin_dir = ROOT / "companies" / "sun_pharma" / year / "financials"
    readiness_path = fin_dir / "financial_extraction_readiness.json"

    if not readiness_path.exists():
        pytest.skip(f"Sun Pharma {year} readiness artifact not present")

    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["status"] == "READY", (
        f"Sun Pharma {year} must still be READY after FY23 fix, "
        f"got {readiness['status']}. blocking={readiness.get('blocking_reasons')}"
    )
