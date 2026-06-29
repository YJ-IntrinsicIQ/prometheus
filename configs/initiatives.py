QUERIES = [
    "technology initiatives",
    "automation initiatives",
    "research and development initiatives",
    "digital transformation",
    "innovation projects",
    "sustainability initiatives",
    "process improvement",
    "manufacturing excellence",
    "technology adoption",
    "collaboration with research institutions"
]

POSITIVE_PATTERNS = [
    "implemented",
    "adopted",
    "developed",
    "launched",
    "introduced",
    "deployed",
    "commissioned",
    "installed",
    "upgraded",
    "expanded",
    "piloted",
    "collaboration",
    "automation",
    "robotics",
    "digital twin",
    "predictive maintenance",
    "iot",
    "research",
    "innovation"
]

NEGATIVE_PATTERNS = [
    "will implement",
    "plans to",
    "expects to",
    "future expansion",
    "roadmap",
    "target by",
    "audit report",
    "financial statements",
    "reasonable assurance"
]

PROMPT = """
You are an expert business analyst.

Extract management initiatives that have already been executed.

Examples:
- AI-driven predictive maintenance implementation
- Digital twin deployment
- Collaboration with IIT Madras
- Precision automation adoption

Do NOT extract:
- future plans
- promises
- targets
- aspirations

Return JSON:

{
  "initiatives": [
    {
      "initiative": "",
      "category": "",
      "status": "",
      "benefit": ""
    }
  ]
}

Return only valid JSON.
"""