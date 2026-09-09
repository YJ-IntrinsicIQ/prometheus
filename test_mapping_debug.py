from knowledge.financials.line_item_mapper import map_line_item

test_items = [
    "(IX) Profit for the year before share of profit/(loss) of associates and joint venture (VII-VIII)",
    "(X) Share of profit/(loss) of associates (net of tax)",
    "(XI) Share of profit/(loss) of joint venture (net of tax)",
    "(XIII) Non-controlling interests",
    "(XIV) Profit for the year attributable to owners of the Company (XII-XIII)",
    "(VII) Profit before tax (V-VI)",
    "(V) Profit before exceptional items and tax (III-IV)",
]

for item in test_items:
    print(f"Testing: {item}")
    result = map_line_item(table_type="profit_and_loss", line_item_raw=item)
    for r in result:
        print(f"  -> {r.canonical_field} (score={r.score}, conf={r.confidence}, reason={r.reason})")
    print()
