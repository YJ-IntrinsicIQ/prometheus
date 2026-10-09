import sys
sys.path.insert(0, '/Users/yogesh/finance-ai-lab')

from knowledge.financials.extractor import (
    _trim_table_text, _strip_column_headers, _split_rows,
    _extract_periods, _expected_value_count, _is_number_token,
    _should_skip_label, _normalize_label, _share_capital_column_plan
)

text = """Equity Share Capital Numbers* Amount Numbers* Amount As at March 31, 2025 Issued, subscribed and fully paid up Equity shares of Rs.2 each 55983969 11.20 55983969 11.20"""

trimmed = _trim_table_text(text, "share_capital")
print("=== TRIMMED ===")
print(trimmed)

stripped = _strip_column_headers(trimmed)
print("\n=== STRIPPED ===")
print(stripped)

periods = _extract_periods(trimmed)
print("\n=== PERIODS ===")
print(periods)

tokens = stripped.split()
print("\n=== TOKENS ===")
for i, t in enumerate(tokens):
    print(f"  [{i}] {t:>15} -> number: {_is_number_token(t)}")

expected = _expected_value_count(tokens, periods)
print(f"\n=== EXPECTED VALUES: {expected} ===")

rows, warnings, rejected = _split_rows(stripped, "share_capital")
print("\n=== ROWS ===")
for label, values in rows:
    print(f"  {label}: {values}")

print("\n=== WARNINGS ===")
for w in warnings:
    print(f"  {w}")

print("\n=== REJECTED ===")
for r in rejected[:20]:
    print(f"  {r}")

# Check column plan
plan = _share_capital_column_plan(trimmed, 4)
print("\n=== COLUMN PLAN ===")
print(plan)