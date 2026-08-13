import json
from pathlib import Path

import pytest

from knowledge.financials.extractor import extract_financial_tables, write_financial_extraction


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
