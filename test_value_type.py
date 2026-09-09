# Direct copy of _value_type function for testing
def _value_type(current, line_item_raw):
    if isinstance(current, dict):
        explicit = str(current.get("value_type", "") or "").strip().lower()
        if explicit:
            # Cross-check: if explicit says "percentage" but raw_number is clearly a share count (large magnitude),
            # trust the magnitude. Percentages are typically < 100; share counts are millions/billions.
            raw_number = current.get("raw_number")
            if explicit == "percentage" and isinstance(raw_number, (int, float)) and raw_number > 1000:
                return "share_count"
            if explicit == "share_count" and isinstance(raw_number, (int, float)) and raw_number < 100:
                return "percentage"
            return explicit
        unit = str(current.get("unit_hint", "") or "").strip().lower()
        if unit in {"%", "percent", "percentage"}:
            # Double-check magnitude for percentage-labeled values
            raw_number = current.get("raw_number")
            if isinstance(raw_number, (int, float)) and raw_number > 1000:
                return "share_count"
            return "percentage"
        if unit in {"shares", "units"}:
            return "share_count"
    lowered = str(line_item_raw or "").lower()
    if "shareholders" in lowered and "total" in lowered:
        return "share_count"
    if "shares held" in lowered or "number of shares" in lowered:
        return "share_count"
    return "percentage"

# Test case: promoter row with share count in first column
current = {
    'value_type': 'percentage',
    'unit_hint': '%',
    'raw_number': 1307134535.0,
    'value_raw': '1,307,134,535',
    'period': 'March 31, 2023'
}
line_item_raw = 'No. of Shares Percentage 1. Indian Promoters and Persons acting in Concert'

result = _value_type(current, line_item_raw)
print(f'Result: {result}')

# Test case: percentage column
current2 = {
    'value_type': 'percentage',
    'unit_hint': '%',
    'raw_number': 54.48,
    'value_raw': '54.48',
    'period': 'PERIOD_COLUMN_UNRESOLVED'
}
result2 = _value_type(current2, line_item_raw)
print(f'Result2: {result2}')

# Test case: unit_hint only (no explicit value_type)
current3 = {
    'unit_hint': '%',
    'raw_number': 1307134535.0,
    'value_raw': '1,307,134,535',
}
result3 = _value_type(current3, line_item_raw)
print(f'Result3: {result3}')