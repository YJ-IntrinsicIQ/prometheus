QUERIES = [
    "capacity expansion",
    "capacity increase",
    "production capacity",
    "commercial production",
    "manufacturing capacity",
    "new facility",
    "new plant",
    "capacity addition",
    "expansion project",
    "future capacity",
]

POSITIVE_PATTERNS = [
    "capacity",
    "commercial production",
    "new facility",
    "new plant",
    "manufacturing facility",
    "expansion",
    "commissioned",
    "production line",
    "throughput",
    "output",
]

NEGATIVE_PATTERNS = [
    "credit risk",
    "market risk",
    "liquidity risk",
    "audit",
    "financial statements",
    "opening stock",
    "closing stock",
    "inventories",
    "trade receivable",
    "trade payable",
]

PROMPT = """
You are an expert industrial analyst.

Extract capacity expansion information.

Return JSON:

{
  "capacity_expansions": [
    {
      "capacity_type": "",
      "current_capacity": "",
      "target_capacity": "",
      "timeline": "",
      "location": "",
      "status": ""
    }
  ]
}

Examples:

- new plant
- new facility
- commercial production
- manufacturing expansion
- capacity addition

Rules:

- Extract only expansion-related information.
- Ignore accounting disclosures.
- Ignore historical commentary unless linked to expansion.
- Never invent numbers.

Return only valid JSON.
"""
