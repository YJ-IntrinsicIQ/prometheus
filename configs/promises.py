QUERIES = [
    "future plans",
    "management plans",
    "future strategy",
    "commercial production",
    "capacity target",
    "capacity expansion plan",
    "future growth",
    "roadmap",
    "business objective",
    "strategic objective",
    "future facility",
    "planned expansion",
    "target capacity",
    "commissioning timeline",
]

POSITIVE_PATTERNS = [
    "we plan",
    "the company plans",
    "expects to",
    "will commission",
    "commercial production",
    "capacity expansion",
    "target capacity",
    "future growth",
    "strategic objective",
    "roadmap",
    "expansion plan",
    "will establish",
    "intends to",
    "aims to",
]

NEGATIVE_PATTERNS = [
    "balance sheet",
    "cash flow",
    "trade receivables",
    "trade payables",
    "cost of material consumed",
    "inventories",
    "equity share capital",
]

PROMPT = """
You are an expert long-term investor.

Extract management promises.

A promise can be:

- future capacity target
- future expansion plan
- commercial production commitment
- facility construction commitment
- strategic objective
- product launch commitment
- future milestone

Return JSON:

{
  "promises": [
    {
      "promise": "",
      "timeline": "",
      "category": ""
    }
  ]
}

Do not extract historical achievements.

Only future commitments.

Never invent information.
"""
