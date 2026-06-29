QUERIES = [
    "capacity expansion",
    "capacity increase",
    "new manufacturing facility",
    "new plant",
    "greenfield project",
    "brownfield expansion",
    "industrial land",
    "commercial production",
    "commissioned",
]

POSITIVE_PATTERNS = [
    "projects in progress",
    "projects temporarily suspended",
    "manufacturing facility",
    "industrial land",
    "commissioned",
    "commercial production",
    "greenfield",
    "brownfield",
    "capacity expansion",
    "capacity increase",
    "new plant",
    "new facility",
]

NEGATIVE_PATTERNS = [
    "balance sheet",
    "total assets",
    "equity and liabilities",
    "trade receivables",
    "cash and cash equivalents",
    "current liabilities",
    "property, plant and equipment",
    "opening stock",
    "closing stock",
    "raw materials consumption",
    "cost of material consumed",
    "trade payable",
    "trade receivable",
    "inventories",
    "equity share capital",
]

PROMPT = """
You are an expert annual report analyst.

Extract business projects from the text.

A project can be:

- manufacturing facility
- plant expansion
- capacity expansion
- CWIP project
- solar project
- technology initiative
- R&D initiative
- strategic infrastructure project

Return JSON only.

Format:

{
  "projects": [
    {
      "project_name": "",
      "description": "",
      "location": "",
      "status": ""
    }
  ]
}

If no project exists return:

{
  "projects": []
}

Never invent information.
"""
