#!/usr/bin/env python3
"""Trace PAT through the pipeline for Tanla FY22 and Ujjivan FY22"""
import sys
import json
from pathlib import Path

sys.path.insert(0, "/Users/yogesh/finance-ai-lab")

from knowledge.financials.line_item_mapper import map_line_item
from knowledge.financials.extractor import extract_financial_tables
from knowledge.financials.normalizer import normalize_financial_tables
from knowledge.financials.extraction_schema import FinancialExtractionResult

# Test 1: Line item mapper for Tanla FY22 PAT
print("=" * 80)
print("TEST 1: Line item mapper - Tanla FY22 PAT candidates")
print("=" * 80)

tanla_pat_labels = [
    ("IX. Profit for the year (VII-VIII)", "profit_and_loss"),
    ("IX. Profit before tax (VII - VIII)", "profit_and_loss"),
    ("XI. Profit for the year (IX - X)", "profit_and_loss"),
]

for label, table_type in tanla_pat_labels:
    matches = map_line_item(table_type=table_type, line_item_raw=label)
    print(f"\nLabel: {label}")
    print(f"Table: {table_type}")
    for m in matches:
        print(f"  -> {m.canonical_section}.{m.canonical_field} (score={m.score}, confidence={m.confidence}, reason={m.reason})")

# Test 2: Line item mapper for Ujjivan FY22 PAT candidates
print("\n" + "=" * 80)
print("TEST 2: Line item mapper - Ujjivan FY22 PAT candidates")
print("=" * 80)

ujjivan_pat_labels = [
    ("A. CASH FLOW FROM OPERATING ACTIVITIES Net Profit/(Loss) after taxation", "cash_flow"),
    ("Net Profit/(Loss) before taxation", "cash_flow"),
    ("Net Profit (5-6-8-9)", "balance_sheet"),
    ("Profit /loss for the year", "profit_and_loss"),
]

for label, table_type in ujjivan_pat_labels:
    matches = map_line_item(table_type=table_type, line_item_raw=label)
    print(f"\nLabel: {label}")
    print(f"Table: {table_type}")
    for m in matches:
        print(f"  -> {m.canonical_section}.{m.canonical_field} (score={m.score}, confidence={m.confidence}, reason={m.reason})")

# Test 3: Full extraction for Tanla FY22
print("\n" + "=" * 80)
print("TEST 3: Full extraction - Tanla FY22")
print("=" * 80)

tanla_raw_path = Path("/Users/yogesh/finance-ai-lab/companies/tanla/fy22/financials/raw_financial_tables.json")
tanla_discovery_path = Path("/Users/yogesh/finance-ai-lab/companies/tanla/fy22/financials/financial_discovery.json")

if tanla_raw_path.exists() and tanla_discovery_path.exists():
    result = extract_financial_tables(
        company="tanla",
        year="fy22",
        chunk_path=Path("/Users/yogesh/finance-ai-lab/companies/tanla/fy22/extracted/clean_chunks.json"),
        discovery_path=tanla_discovery_path,
    )

    print(f"\nExtraction result tables: {list(result.tables.keys())}")
    for table_type, rows in result.tables.items():
        if rows:
            print(f"\n{table_type}: {len(rows)} rows")
            for row in rows:
                label = row.line_item_raw
                if any(kw in label.lower() for kw in ['profit', 'pat', 'profit for', 'profit after', 'profit before']):
                    print(f"  {label} -> basis={row.basis}")
                    for v in row.values:
                        print(f"    period={v.period} value_crore={v.value_crore} value_type={v.value_type}")

# Test 4: Full extraction for Ujjivan FY22
print("\n" + "=" * 80)
print("TEST 4: Full extraction - Ujjivan FY22")
print("=" * 80)

ujjivan_raw_path = Path("/Users/yogesh/finance-ai-lab/companies/ujjivan/fy22/financials/raw_financial_tables.json")
ujjivan_discovery_path = Path("/Users/yogesh/finance-ai-lab/companies/ujjivan/fy22/financials/financial_discovery.json")

if ujjivan_raw_path.exists() and ujjivan_discovery_path.exists():
    result = extract_financial_tables(
        company="ujjivan",
        year="fy22",
        chunk_path=Path("/Users/yogesh/finance-ai-lab/companies/ujjivan/fy22/extracted/clean_chunks.json"),
        discovery_path=ujjivan_discovery_path,
    )

    print(f"\nExtraction result tables: {list(result.tables.keys())}")
    for table_type, rows in result.tables.items():
        if rows:
            print(f"\n{table_type}: {len(rows)} rows")
            for row in rows:
                label = row.line_item_raw
                if any(kw in label.lower() for kw in ['profit', 'pat', 'profit for', 'profit after', 'profit before']):
                    print(f"  {label} -> basis={row.basis}")
                    for v in row.values:
                        print(f"    period={v.period} value_crore={v.value_crore} value_type={v.value_type}")

# Test 5: Normalization for Tanla FY22
print("\n" + "=" * 80)
print("TEST 5: Normalization - Tanla FY22")
print("=" * 80)

try:
    payload = normalize_financial_tables(
        company="tanla",
        year="fy22",
        raw_tables_path=tanla_raw_path,
    )
    pat = payload["profit_and_loss"]["pat"]
    print(f"\nPAT entry:")
    print(f"  value_crore: {pat['value_crore']}")
    print(f"  value_original: {pat['value_original']}")
    print(f"  basis: {pat['basis']}")
    print(f"  period: {pat['period']}")
    print(f"  source_line_item: {pat['source_line_item']}")
    print(f"  confidence: {pat['confidence']}")
    print(f"  source_section_type: {pat['source_section_type']}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# Test 6: Normalization for Ujjivan FY22
print("\n" + "=" * 80)
print("TEST 6: Normalization - Ujjivan FY22")
print("=" * 80)

try:
    payload = normalize_financial_tables(
        company="ujjivan",
        year="fy22",
        raw_tables_path=ujjivan_raw_path,
    )
    pat = payload["profit_and_loss"]["pat"]
    print(f"\nPAT entry:")
    print(f"  value_crore: {pat['value_crore']}")
    print(f"  value_original: {pat['value_original']}")
    print(f"  basis: {pat['basis']}")
    print(f"  period: {pat['period']}")
    print(f"  source_line_item: {pat['source_line_item']}")
    print(f"  confidence: {pat['confidence']}")
    print(f"  source_section_type: {pat['source_section_type']}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()