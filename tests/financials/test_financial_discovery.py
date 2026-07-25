import json
from pathlib import Path
from typing import Optional

import pytest

from core.company_context import CompanyContext
from knowledge.financials.discovery import discover_financial_sections, write_financial_discovery


def _chunk(chunk_id: str, page: Optional[int], text: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "page": page,
        "text": text,
        "metadata": {"document_type": "annual_report"},
    }


def _write_chunks(path: Path, chunks) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "company": "syntheticco",
        "year": "fy25",
        "document_type": "annual_report",
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_profit_and_loss_discovery(tmp_path):
    chunk_path = _write_chunks(
        tmp_path / "clean_chunks.json",
        [
            _chunk(
                "CHK-001",
                120,
                "Statement of Profit and Loss Revenue from operations 520 453 Other income 46 9 Profit before tax 248 164",
            )
        ],
    )

    result = discover_financial_sections(company="syntheticco", year="fy25", chunk_path=chunk_path)

    assert result.sections["primary_profit_and_loss_statement"]
    assert result.sections["primary_profit_and_loss_statement"][0].confidence in {"high", "medium"}


def test_balance_sheet_discovery(tmp_path):
    chunk_path = _write_chunks(
        tmp_path / "clean_chunks.json",
        [
            _chunk(
                "CHK-002",
                121,
                "Balance Sheet Equity share capital 10 Other Equity 840 Total assets 1420 Total liabilities 570",
            )
        ],
    )

    result = discover_financial_sections(company="syntheticco", year="fy25", chunk_path=chunk_path)

    assert result.sections["primary_balance_sheet_statement"]


def test_cash_flow_discovery(tmp_path):
    chunk_path = _write_chunks(
        tmp_path / "clean_chunks.json",
        [
            _chunk(
                "CHK-003",
                122,
                "Cash Flow Statement Net cash from operating activities 210 Net cash from investing activities -120 Net cash from financing activities -20",
            )
        ],
    )

    result = discover_financial_sections(company="syntheticco", year="fy25", chunk_path=chunk_path)

    assert result.sections["primary_cash_flow_statement"]
    assert "cash flow statement was not discovered" not in result.warnings


def test_notes_and_share_capital_discovery(tmp_path):
    chunk_path = _write_chunks(
        tmp_path / "clean_chunks.json",
        [
            _chunk(
                "CHK-004",
                130,
                "Notes forming part of financial statements Note 12 Equity Share Capital authorised share capital issued subscribed and paid-up share capital",
            )
        ],
    )

    result = discover_financial_sections(company="syntheticco", year="fy25", chunk_path=chunk_path)

    assert result.sections["share_capital_note"]


def test_shareholding_pattern_discovery(tmp_path):
    chunk_path = _write_chunks(
        tmp_path / "clean_chunks.json",
        [
            _chunk(
                "CHK-005",
                131,
                "Shareholding Pattern Promoter holding 42.5 Public shareholding 31.0 FII holding 12.0 DII holding 10.0",
            )
        ],
    )

    result = discover_financial_sections(company="syntheticco", year="fy25", chunk_path=chunk_path)

    assert result.sections["shareholding_note"]
    assert "shareholding pattern was not discovered" not in result.warnings


def test_standalone_vs_consolidated_hints(tmp_path):
    chunk_path = _write_chunks(
        tmp_path / "clean_chunks.json",
        [
            _chunk(
                "CHK-006",
                140,
                "Consolidated Balance Sheet Total assets 1400 Total liabilities 900",
            ),
            _chunk(
                "CHK-007",
                141,
                "Standalone Statement of Profit and Loss Revenue from operations 500 Profit after tax 180",
            ),
        ],
    )

    result = discover_financial_sections(company="syntheticco", year="fy25", chunk_path=chunk_path)

    balance_item = result.sections["primary_balance_sheet_statement"][0]
    profit_item = result.sections["primary_profit_and_loss_statement"][0]
    assert "consolidated_hint" in balance_item.signals
    assert balance_item.basis == "consolidated"
    assert balance_item.basis_confidence in {"medium", "high"}
    assert "standalone_hint" in profit_item.signals
    assert profit_item.basis == "standalone"
    assert profit_item.basis_confidence in {"medium", "high"}


def test_accounting_policy_not_classified_as_primary_pl(tmp_path):
    chunk_path = _write_chunks(
        tmp_path / "clean_chunks.json",
        [
            _chunk(
                "CHK-009",
                150,
                "Summary of significant accounting policies Revenue is recognised in the statement of profit and loss when control transfers to the customer.",
            )
        ],
    )

    result = discover_financial_sections(company="syntheticco", year="fy25", chunk_path=chunk_path)

    assert result.sections["accounting_policy"]
    assert not result.sections["primary_profit_and_loss_statement"]


def test_auditor_report_not_classified_as_balance_sheet(tmp_path):
    chunk_path = _write_chunks(
        tmp_path / "clean_chunks.json",
        [
            _chunk(
                "CHK-010",
                151,
                "Independent Auditor's Report Our opinion on the standalone financial statements includes the balance sheet, statement of profit and loss and cash flow statement.",
            )
        ],
    )

    result = discover_financial_sections(company="syntheticco", year="fy25", chunk_path=chunk_path)

    assert result.sections["auditor_report"]
    assert not result.sections["primary_balance_sheet_statement"]


def test_statement_of_changes_in_equity_not_classified_as_pl(tmp_path):
    chunk_path = _write_chunks(
        tmp_path / "clean_chunks.json",
        [
            _chunk(
                "CHK-011",
                152,
                "Statement of Changes in Equity Equity share capital Other equity Balance at April 1, 2024 Profit for the year Dividend paid Balance at March 31, 2025",
            )
        ],
    )

    result = discover_financial_sections(company="syntheticco", year="fy25", chunk_path=chunk_path)

    assert result.sections["statement_of_changes_in_equity"]
    assert not result.sections["primary_profit_and_loss_statement"]


def test_no_company_specific_behavior_in_discovery_module():
    text = Path("knowledge/financials/discovery.py").read_text(encoding="utf-8").lower()

    assert "polymatech" not in text
    assert "tanla" not in text
    assert "tips" not in text


def test_malformed_source_handling(tmp_path):
    path = tmp_path / "clean_chunks.json"
    path.write_text(json.dumps({"invalid": "shape"}), encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported clean_chunks payload shape"):
        discover_financial_sections(company="syntheticco", year="fy25", chunk_path=path)


def test_missing_source_handling(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="syntheticco", year="fy25")
    context.create_directories()
    missing_output = context.financials_dir / "financial_discovery.json"

    with pytest.raises(FileNotFoundError):
        write_financial_discovery(
            company="syntheticco",
            year="fy25",
            chunk_path=context.extracted_dir / "clean_chunks.json",
            output_path=missing_output,
        )


def test_no_sections_discovered_fails(tmp_path):
    chunk_path = _write_chunks(
        tmp_path / "clean_chunks.json",
        [
            _chunk("CHK-008", 10, "This section discusses corporate culture and leadership development only.")
        ],
    )

    with pytest.raises(RuntimeError, match="found no financial sections"):
        discover_financial_sections(company="syntheticco", year="fy25", chunk_path=chunk_path)
