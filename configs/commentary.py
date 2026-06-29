QUERIES = [
    "management discussion",
    "future outlook",
    "business strategy",
    "growth drivers",
    "competitive advantage",
    "innovation strategy",
    "industry outlook",
    "technology roadmap",
    "strategic initiatives",
    "research and development"
]

POSITIVE_PATTERNS = [
    "strategy",
    "future outlook",
    "growth",
    "competitive advantage",
    "innovation",
    "research",
    "development",
    "roadmap",
    "technology",
    "industry outlook",
    "expansion",
    "long term"
]

NEGATIVE_PATTERNS = [
    "audit report",
    "reasonable assurance",
    "financial statements",
    "opening stock",
    "closing stock",
    "trade receivables",
    "trade payables",
    "market risk",
    "credit risk",
    "liquidity risk"
]

PROMPT = """
You are an expert business analyst.

Extract management commentary.

Focus on:

- strategy
- future outlook
- competitive positioning
- innovation
- industry outlook
- technology direction
- growth initiatives

Return JSON:

{
  "commentary": [
    {
      "theme": "",
      "commentary": "",
      "sentiment": ""
    }
  ]
}

Sentiment must be:
positive
neutral
negative

Do not invent information.

Return only valid JSON.
"""