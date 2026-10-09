import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, '/Users/yogesh/finance-ai-lab')

from knowledge.financials.normalizer import normalize_financial_tables

# Replicate the test data
def _row(table_type, line_item_raw, values, **kwargs):
    normalized_values = []
    for period, value_raw, value_crore in values:
        normalized_values.append({
            "period": period,
            "value_raw": value_raw,
            "unit_hint": "crore",
            "currency_hint": "INR",
            "value_crore": value_crore,
            "value_type": "monetary",
            "raw_number": float(str(value_raw).replace(",", "").strip("()[]")),
        })
    return {
        "statement_type": table_type,
        "table_type": table_type,
        "basis": "unknown",
        "line_item_raw": line_item_raw,
        "values": normalized_values,
        "source_artifact": "clean_chunks.json",
        "page": kwargs.get("page", 1),
        "chunk_id": f"CHK-{kwargs.get('page', 1):03d}",
        "confidence": "medium",
        "source_section_type": table_type,
        "table_confidence": "medium",
        "table_rejection_risk": [],
        "is_primary_statement": table_type in {"profit_and_loss", "balance_sheet", "cash_flow"},
        "warnings": [],
    }

sections = {
    "profit_and_loss": [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2023", "500.00", 500.0)]),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2023", "120.00", 120.0)]),
    ],
    "balance_sheet": [
        _row("balance_sheet", "Total Assets", [("March 31, 2023", "23604.46", 23604.4642)]),
        _row("balance_sheet", "Total Equity", [("March 31, 2023", "600.00", 600.0)]),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2023", "400.00", 400.0)]),
        _row("balance_sheet", "Tax Expenses (including deferred tax)", [("March 31, 2023", "(1,357,681)", -135.7681)], page=316),
    ],
    "cash_flow": [
        _row("cash_flow", "Operating Profit/(Loss) before Working Capital changes", [("March 31, 2023", "15,991,439", 1599.1439)], page=271),
        _row("cash_flow", "Net Profit/(Loss) before taxation", [("March 31, 2023", "14,672,376", 1467.2376)], page=271),
        _row("cash_flow", "A. Cash Flow from Operating Activities Net Profit/(Loss) After taxation", [("March 31, 2023", "10,999,217", 1099.9217)], page=271),
        _row("cash_flow", "Tax adjustment", [("March 31, 2023", "3,673,159", 367.3159)], page=271),
        _row("cash_flow", "Direct Taxes paid (net of refunds)", [("March 31, 2023", "(2,803,717)", -280.3717)], page=271),
    ],
}

payload = {
    "company": "acme",
    "year": "fy23",
    "generated_at": "2026-07-16T00:00:00Z",
    "source_documents": ["clean_chunks.json"],
    "tables": sections,
    "warnings": [],
    "limitations": [],
}

with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump(payload, f)
    temp_path = Path(f.name)

from knowledge.financials.line_item_mapper import map_line_item
from knowledge.financials.normalizer import _entry_rank, _build_normalized_entry

# Debug: check what mappings are returned
print("=== Testing map_line_item ===")
matches1 = map_line_item(table_type="balance_sheet", line_item_raw="Tax Expenses (including deferred tax)")
print("balance_sheet 'Tax Expenses (including deferred tax)':")
for m in matches1:
    print(f"  {m.canonical_section}.{m.canonical_field} score={m.score} confidence={m.confidence}")

matches2 = map_line_item(table_type="cash_flow", line_item_raw="Tax adjustment")
print("cash_flow 'Tax adjustment':")
for m in matches2:
    print(f"  {m.canonical_section}.{m.canonical_field} score={m.score} confidence={m.confidence}")

# Build entries manually to check their ranks
entry_bs = {
    "canonical_field": "tax",
    "source_line_item": "Tax Expenses (including deferred tax)",
    "statement_type": "balance_sheet",
    "source_section_type": "primary_balance_sheet_statement",
    "basis": "unknown",
    "period": "March 31, 2023",
    "is_primary_statement": True,
    "table_confidence": "medium",
    "value_crore": -135.7681,
}

entry_cf = {
    "canonical_field": "tax",
    "source_line_item": "Tax adjustment",
    "statement_type": "cash_flow",
    "source_section_type": "primary_cash_flow_statement",
    "basis": "unknown",
    "period": "March 31, 2023",
    "is_primary_statement": True,
    "table_confidence": "medium",
    "value_crore": 367.3159,
}

print("\n=== Rank comparison ===")
rank_bs = _entry_rank(entry_bs, "2023")
rank_cf = _entry_rank(entry_cf, "2023")
print(f"balance_sheet rank: {rank_bs}")
print(f"cash_flow rank: {rank_cf}")
print(f"cash_flow > balance_sheet: {rank_cf > rank_bs}")

result = normalize_financial_tables(company="ujjivan", year="fy23", raw_tables_path=temp_path)
print("\n=== Result ===")
print("P&L tax:", result["profit_and_loss"].get("tax"))
print("P&L pbt:", result["profit_and_loss"].get("pbt"))
