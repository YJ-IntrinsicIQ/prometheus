QUERIES = [
    "capital allocation",
    "capital expenditure",
    "capex",
    "equity issuance",
    "debt financing",
    "loan conversion",
    "buyback",
    "dividend",
    "cash deployment",
    "investment",
    "acquisition",
    "joint venture",
    "subsidiary investment",
]

POSITIVE_PATTERNS = [
    "capital expenditure",
    "capex",
    "loan",
    "borrowings",
    "debt",
    "equity shares",
    "preferential allotment",
    "investment",
    "joint venture",
    "subsidiary",
    "dividend",
    "buyback",
    "capital work in progress",
    "industrial land",
    "manufacturing facility",
]

NEGATIVE_PATTERNS = [
    "audit report",
    "reasonable assurance",
    "financial statements",
    "opening stock",
    "closing stock",
    "inventories",
    "trade receivable",
    "trade payable",
]

PROMPT = """
You are a world-class capital allocation analyst.

Extract capital allocation decisions.

Examples:

- Equity issuance
- Debt raised
- Debt repayment
- Buyback
- Dividend
- Acquisition
- Subsidiary investment
- Joint venture
- Capex spending
- Land acquisition
- Manufacturing facility investment

Return JSON:

{
  "capital_allocations": [
    {
      "action": "",
      "category": "",
      "amount": "",
      "purpose": ""
    }
  ]
}

Rules:

- Never invent numbers.
- Ignore accounting notes.
- Ignore generic disclosures.
- Extract only actual capital allocation decisions.

Return valid JSON only.
"""
