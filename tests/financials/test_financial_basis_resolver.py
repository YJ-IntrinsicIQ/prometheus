from __future__ import annotations

import json
from pathlib import Path

from knowledge.financials.basis_resolver import build_financial_basis_resolution, write_financial_basis_resolution


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _clean_chunks_payload(chunks):
    return {"chunks": chunks}


def _chunk(page: int, text: str, chunk_id: str) -> dict:
    return {"page": page, "chunk_id": chunk_id, "text": text}


def _discovery_item(section_type: str, page: int, text_excerpt: str, basis: str = "unknown") -> dict:
    return {
        "section_type": section_type,
        "source_artifact": "annual_report.pdf",
        "page": page,
        "chunk_id": f"{section_type}-{page}",
        "text_excerpt": text_excerpt,
        "confidence": "high",
        "reasoning": "synthetic discovery",
        "signals": [],
        "basis": basis,
    }


def _discovery_payload(items):
    sections = {
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
    for item in items:
        sections[item["section_type"]].append(item)
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "source_documents": ["annual_report.pdf"],
        "sections": sections,
        "warnings": [],
        "limitations": [],
    }


def _raw_row(table_type: str, line_item_raw: str, page: int, basis: str = "unknown") -> dict:
    return {
        "statement_type": table_type,
        "table_type": table_type,
        "basis": basis,
        "line_item_raw": line_item_raw,
        "values": [{"period": "FY25", "value_raw": "100", "unit_hint": "crores", "currency_hint": "INR", "value_crore": 100.0}],
        "source_artifact": "annual_report.pdf",
        "page": page,
        "chunk_id": f"{table_type}-{page}",
        "confidence": "high",
        "warnings": [],
    }


def _raw_payload(rows):
    tables = {
        "profit_and_loss": [],
        "balance_sheet": [],
        "cash_flow": [],
        "statement_of_changes_in_equity": [],
        "share_capital": [],
        "reserves": [],
        "borrowings": [],
        "fixed_assets": [],
        "revenue": [],
        "tax": [],
        "eps": [],
        "dividend": [],
        "corporate_actions": [],
        "shareholding_pattern": [],
        "investment_schedule": [],
        "lease_note": [],
        "management_discussion_financial_summary": [],
    }
    for row in rows:
        tables[row["table_type"]].append(row)
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "source_documents": ["annual_report.pdf"],
        "tables": tables,
        "rejections": [],
        "warnings": [],
        "limitations": [],
    }


def _entry(section_name: str, field_name: str, page: int, line_item: str, basis: str = "unknown") -> dict:
    statement_type = "profit_and_loss" if section_name == "profit_and_loss" else "balance_sheet"
    return {
        "canonical_field": field_name,
        "value_type": "monetary",
        "value_crore": 100.0,
        "value_original": "100",
        "unit_original": "crores",
        "basis": basis,
        "period": "FY25",
        "source_line_item": line_item,
        "source_page": page,
        "source_artifact": "annual_report.pdf",
        "confidence": "high",
        "warnings": [],
        "derived": False,
        "formula": "",
        "inputs_used": {},
        "value_per_share": None,
        "value_shares": None,
        "crore_shares": None,
        "raw_number": None,
        "capex_abs_crore": None,
        "sign_convention": "",
        "current": {},
        "comparatives": [],
        "source_value_type": "monetary",
        "source_raw_number": None,
        "statement_type": statement_type,
        "source_section_type": statement_type,
        "table_confidence": "high",
        "is_primary_statement": True,
    }


def _normalized_payload(entries):
    payload = {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "preferred_basis": "unknown",
        "basis_confidence": "low",
        "basis_manifest": {
            "preferred_basis": "unknown",
            "basis_options_available": [],
            "selected_basis_reason": "unknown",
            "basis_confidence": "low",
            "field_basis_selection": [],
            "basis_warnings": ["standalone/consolidated basis is unclear"],
        },
        "profit_and_loss": {},
        "balance_sheet": {},
        "cash_flow": {},
        "share_data": {},
        "corporate_actions": {},
        "shareholding_pattern": {},
        "warnings": [],
        "limitations": [],
        "unmapped_rows": [],
    }
    for section_name, field_name, page, line_item, basis in entries:
        payload[section_name][field_name] = _entry(section_name, field_name, page, line_item, basis)
    return payload


def _truth_report_payload(warnings=None, unresolved=None):
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "contradictions_found": [],
        "resolved_contradictions": [],
        "unresolved_contradictions": list(unresolved or []),
        "false_missing_warnings": [],
        "unreliable_metrics": [],
        "invalid_metrics": [],
        "usable_metrics": [],
        "downstream_blockers": [],
        "warnings": list(warnings or []),
    }


def _setup_financial_root(tmp_path: Path) -> Path:
    return tmp_path / "companies" / "acme" / "fy25" / "financials"


def test_direct_standalone_statement_title_near_table_resolves_high_confidence(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(financial_root.parent / "extracted" / "clean_chunks.json", _clean_chunks_payload([_chunk(10, "Standalone Statement of Profit and Loss", "c1")]))
    _write_json(financial_root / "financial_discovery.json", _discovery_payload([_discovery_item("primary_profit_and_loss_statement", 10, "Standalone Statement of Profit and Loss")]))
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("profit_and_loss", "Revenue from operations", 10)]))
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload([("profit_and_loss", "revenue", 10, "Revenue from operations", "unknown")]))

    report = write_financial_basis_resolution(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        output_path=financial_root / "financial_basis_resolution.json",
    )
    normalized = json.loads((financial_root / "normalized_fundamentals.json").read_text(encoding="utf-8"))

    assert report.resolved_basis == "standalone"
    assert report.confidence == "high"
    assert normalized["profit_and_loss"]["revenue"]["basis"] == "standalone"
    assert normalized["preferred_basis"] == "standalone"


def test_direct_consolidated_statement_title_near_table_resolves_high_confidence(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(financial_root.parent / "extracted" / "clean_chunks.json", _clean_chunks_payload([_chunk(12, "Consolidated Balance Sheet", "c2")]))
    _write_json(financial_root / "financial_discovery.json", _discovery_payload([_discovery_item("primary_balance_sheet_statement", 12, "Consolidated Balance Sheet")]))
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("balance_sheet", "Total assets", 12)]))
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload([("balance_sheet", "total_assets", 12, "Total assets", "unknown")]))

    report = build_financial_basis_resolution(company="acme", year="fy25", financial_root=financial_root)

    assert report.resolved_basis == "consolidated"
    assert report.confidence == "high"


def test_no_subsidiaries_and_no_consolidated_required_resolves_standalone(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(
        financial_root.parent / "extracted" / "clean_chunks.json",
        _clean_chunks_payload([_chunk(3, "The company has no subsidiaries and consolidated financial statements are not required.", "c3")]),
    )
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("profit_and_loss", "Revenue from operations", 10)]))
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload([("profit_and_loss", "revenue", 10, "Revenue from operations", "unknown")]))

    report = build_financial_basis_resolution(company="acme", year="fy25", financial_root=financial_root)

    assert report.resolved_basis == "standalone"
    assert report.confidence in {"medium", "high"}


def test_subsidiaries_exist_but_standalone_table_extracted_keeps_field_standalone_with_warning(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(
        financial_root.parent / "extracted" / "clean_chunks.json",
        _clean_chunks_payload([_chunk(2, "The company has subsidiaries and associates.", "c4"), _chunk(10, "Standalone Statement of Profit and Loss", "c5")]),
    )
    _write_json(financial_root / "financial_discovery.json", _discovery_payload([_discovery_item("primary_profit_and_loss_statement", 10, "Standalone Statement of Profit and Loss")]))
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("profit_and_loss", "Revenue from operations", 10, basis="standalone")]))
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload([("profit_and_loss", "revenue", 10, "Revenue from operations", "unknown")]))

    report = write_financial_basis_resolution(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        output_path=financial_root / "financial_basis_resolution.json",
    )
    normalized = json.loads((financial_root / "normalized_fundamentals.json").read_text(encoding="utf-8"))

    assert normalized["profit_and_loss"]["revenue"]["basis"] == "standalone"
    assert any("Subsidiary evidence exists" in warning for warning in report.warnings)


def test_both_standalone_and_consolidated_tables_can_coexist(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(
        financial_root.parent / "extracted" / "clean_chunks.json",
        _clean_chunks_payload([_chunk(10, "Standalone Statement of Profit and Loss", "c6"), _chunk(20, "Consolidated Balance Sheet", "c7")]),
    )
    _write_json(
        financial_root / "financial_discovery.json",
        _discovery_payload(
            [
                _discovery_item("primary_profit_and_loss_statement", 10, "Standalone Statement of Profit and Loss"),
                _discovery_item("primary_balance_sheet_statement", 20, "Consolidated Balance Sheet"),
            ]
        ),
    )
    _write_json(
        financial_root / "raw_financial_tables.json",
        _raw_payload(
            [
                _raw_row("profit_and_loss", "Revenue from operations", 10, basis="standalone"),
                _raw_row("balance_sheet", "Total assets", 20, basis="consolidated"),
            ]
        ),
    )
    _write_json(
        financial_root / "normalized_fundamentals.json",
        _normalized_payload(
            [
                ("profit_and_loss", "revenue", 10, "Revenue from operations", "unknown"),
                ("balance_sheet", "total_assets", 20, "Total assets", "unknown"),
            ]
        ),
    )

    report = write_financial_basis_resolution(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        output_path=financial_root / "financial_basis_resolution.json",
    )
    normalized = json.loads((financial_root / "normalized_fundamentals.json").read_text(encoding="utf-8"))

    assert report.resolved_basis == "unknown"
    assert any("Both standalone and consolidated basis appear" in warning for warning in report.warnings)
    assert normalized["preferred_basis"] == "mixed"
    assert normalized["profit_and_loss"]["revenue"]["basis"] == "standalone"
    assert normalized["balance_sheet"]["total_assets"]["basis"] == "consolidated"


def test_preferred_basis_comes_from_resolved_fields_not_global_document_hint(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(
        financial_root.parent / "extracted" / "clean_chunks.json",
        _clean_chunks_payload(
            [
                _chunk(1, "Consolidated financial statements overview", "global-consolidated"),
                _chunk(10, "Standalone Statement of Profit and Loss", "standalone-pnl"),
            ]
        ),
    )
    _write_json(
        financial_root / "financial_discovery.json",
        _discovery_payload(
            [
                _discovery_item("primary_profit_and_loss_statement", 10, "Standalone Statement of Profit and Loss"),
            ]
        ),
    )
    _write_json(
        financial_root / "raw_financial_tables.json",
        _raw_payload(
            [
                _raw_row("profit_and_loss", "Revenue from operations", 10, basis="unknown"),
                _raw_row("profit_and_loss", "Profit for the year", 10, basis="unknown"),
            ]
        ),
    )
    _write_json(
        financial_root / "normalized_fundamentals.json",
        _normalized_payload(
            [
                ("profit_and_loss", "revenue", 10, "Revenue from operations", "unknown"),
                ("profit_and_loss", "pat", 10, "Profit for the year", "unknown"),
            ]
        ),
    )

    write_financial_basis_resolution(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        output_path=financial_root / "financial_basis_resolution.json",
    )
    normalized = json.loads((financial_root / "normalized_fundamentals.json").read_text(encoding="utf-8"))

    assert normalized["profit_and_loss"]["revenue"]["basis"] == "standalone"
    assert normalized["profit_and_loss"]["pat"]["basis"] == "standalone"
    assert normalized["preferred_basis"] == "standalone"


def test_global_basis_does_not_set_preferred_when_fields_remain_unknown(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(
        financial_root.parent / "extracted" / "clean_chunks.json",
        _clean_chunks_payload(
            [
                _chunk(1, "Consolidated financial statements overview", "global-consolidated"),
                _chunk(10, "Operating table without a nearby reporting basis", "field-table"),
            ]
        ),
    )
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("profit_and_loss", "Revenue from operations", 10)]))
    normalized = _normalized_payload([("profit_and_loss", "revenue", 10, "Revenue from operations", "unknown")])
    normalized["preferred_basis"] = "consolidated"
    normalized["basis_manifest"]["preferred_basis"] = "consolidated"
    _write_json(financial_root / "normalized_fundamentals.json", normalized)

    write_financial_basis_resolution(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        output_path=financial_root / "financial_basis_resolution.json",
    )
    normalized = json.loads((financial_root / "normalized_fundamentals.json").read_text(encoding="utf-8"))

    assert normalized["profit_and_loss"]["revenue"]["basis"] == "unknown"
    assert normalized["preferred_basis"] == "unknown"


def test_resolver_does_not_upgrade_unknown_field_to_incompatible_preferred_basis(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(
        financial_root.parent / "extracted" / "clean_chunks.json",
        _clean_chunks_payload([_chunk(10, "Standalone Balance Sheet", "standalone-bs")]),
    )
    _write_json(
        financial_root / "financial_discovery.json",
        _discovery_payload([_discovery_item("primary_balance_sheet_statement", 10, "Standalone Balance Sheet")]),
    )
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("balance_sheet", "Total debt", 10)]))
    normalized = _normalized_payload([("balance_sheet", "total_debt", 10, "Total debt", "unknown")])
    normalized["preferred_basis"] = "consolidated"
    normalized["basis_manifest"]["preferred_basis"] = "consolidated"
    _write_json(financial_root / "normalized_fundamentals.json", normalized)

    write_financial_basis_resolution(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        output_path=financial_root / "financial_basis_resolution.json",
    )
    normalized = json.loads((financial_root / "normalized_fundamentals.json").read_text(encoding="utf-8"))

    assert normalized["balance_sheet"]["total_debt"]["basis"] == "unknown"


def test_resolver_demotes_stale_incompatible_canonical_basis(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(
        financial_root.parent / "extracted" / "clean_chunks.json",
        _clean_chunks_payload([_chunk(10, "Standalone Balance Sheet", "standalone-bs")]),
    )
    _write_json(
        financial_root / "financial_discovery.json",
        _discovery_payload([_discovery_item("primary_balance_sheet_statement", 10, "Standalone Balance Sheet")]),
    )
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("balance_sheet", "Total debt", 10)]))
    normalized = _normalized_payload([("balance_sheet", "total_debt", 10, "Total debt", "standalone")])
    normalized["preferred_basis"] = "consolidated"
    normalized["basis_manifest"]["preferred_basis"] = "consolidated"
    _write_json(financial_root / "normalized_fundamentals.json", normalized)

    write_financial_basis_resolution(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        output_path=financial_root / "financial_basis_resolution.json",
    )
    normalized = json.loads((financial_root / "normalized_fundamentals.json").read_text(encoding="utf-8"))

    assert normalized["balance_sheet"]["total_debt"]["basis"] == "unknown"
    assert normalized["preferred_basis"] == "unknown"


def test_conflicting_basis_evidence_remains_unknown(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(
        financial_root.parent / "extracted" / "clean_chunks.json",
        _clean_chunks_payload([_chunk(10, "Standalone Statement of Profit and Loss Consolidated Statement of Profit and Loss", "c8")]),
    )
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("profit_and_loss", "Revenue from operations", 10)]))
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload([("profit_and_loss", "revenue", 10, "Revenue from operations", "unknown")]))

    report = build_financial_basis_resolution(company="acme", year="fy25", financial_root=financial_root)

    resolution = next(item for item in report.field_resolutions if item.field_path == "profit_and_loss.revenue")
    assert resolution.resolved_basis == "unknown"
    assert resolution.confidence == "low"


def test_no_basis_evidence_found_stays_unknown(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("profit_and_loss", "Revenue from operations", 10)]))
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload([("profit_and_loss", "revenue", 10, "Revenue from operations", "unknown")]))

    report = write_financial_basis_resolution(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        output_path=financial_root / "financial_basis_resolution.json",
    )
    normalized = json.loads((financial_root / "normalized_fundamentals.json").read_text(encoding="utf-8"))

    assert report.resolved_basis == "unknown"
    assert report.confidence == "low"
    assert normalized["profit_and_loss"]["revenue"]["basis"] == "unknown"


def test_weak_distant_hint_does_not_override_direct_table_basis(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(
        financial_root.parent / "extracted" / "clean_chunks.json",
        _clean_chunks_payload([_chunk(1, "Consolidated financial statements discussion", "c9"), _chunk(10, "Standalone Statement of Profit and Loss", "c10")]),
    )
    _write_json(financial_root / "financial_discovery.json", _discovery_payload([_discovery_item("primary_profit_and_loss_statement", 10, "Standalone Statement of Profit and Loss")]))
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("profit_and_loss", "Revenue from operations", 10)]))
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload([("profit_and_loss", "revenue", 10, "Revenue from operations", "unknown")]))

    report = build_financial_basis_resolution(company="acme", year="fy25", financial_root=financial_root)
    resolution = next(item for item in report.field_resolutions if item.field_path == "profit_and_loss.revenue")

    assert resolution.resolved_basis == "standalone"
    assert resolution.confidence == "high"


def test_false_basis_unknown_warning_gets_resolved_only_when_confidence_is_medium_or_high(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(financial_root.parent / "extracted" / "clean_chunks.json", _clean_chunks_payload([_chunk(10, "Standalone Statement of Profit and Loss", "c11")]))
    _write_json(financial_root / "financial_discovery.json", _discovery_payload([_discovery_item("primary_profit_and_loss_statement", 10, "Standalone Statement of Profit and Loss")]))
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("profit_and_loss", "Revenue from operations", 10)]))
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload([("profit_and_loss", "revenue", 10, "Revenue from operations", "unknown")]))
    _write_json(
        financial_root / "financial_truth_reconciliation_report.json",
        _truth_report_payload(
            warnings=["standalone/consolidated basis is unclear"],
            unresolved=["preferred basis unknown"],
        ),
    )

    write_financial_basis_resolution(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        output_path=financial_root / "financial_basis_resolution.json",
    )
    truth_report = json.loads((financial_root / "financial_truth_reconciliation_report.json").read_text(encoding="utf-8"))

    assert truth_report["warning_resolutions"]
    assert not any("preferred basis unknown" == item for item in truth_report["unresolved_contradictions"])


def test_low_confidence_does_not_resolve_basis_warning(tmp_path):
    financial_root = _setup_financial_root(tmp_path)
    _write_json(financial_root / "raw_financial_tables.json", _raw_payload([_raw_row("profit_and_loss", "Revenue from operations", 10)]))
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload([("profit_and_loss", "revenue", 10, "Revenue from operations", "unknown")]))
    _write_json(
        financial_root / "financial_truth_reconciliation_report.json",
        _truth_report_payload(warnings=["basis unclear"]),
    )

    write_financial_basis_resolution(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        output_path=financial_root / "financial_basis_resolution.json",
    )
    truth_report = json.loads((financial_root / "financial_truth_reconciliation_report.json").read_text(encoding="utf-8"))

    assert truth_report.get("warning_resolutions", []) == []
