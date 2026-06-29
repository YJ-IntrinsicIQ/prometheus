QUERIES = [
    "business risks",
    "key risks",
    "operational risks",
    "industry risks",
    "supply chain risks",
    "execution risks",
    "regulatory risks",
    "technology risks",
    "competition risk",
    "customer concentration risk",
    "foreign exchange risk",
    "litigation risk",
    "business challenges",
    "industry challenges",
    "supply chain challenges",
    "technology challenges",
    "competitive pressures",
    "customer concentration",
    "raw material dependence",
    "execution challenges",
    "regulatory changes affecting business",
]

POSITIVE_PATTERNS = [
    "challenge",
    "headwind",
    "dependency",
    "competition",
    "competitive",
    "customer concentration",
    "supplier dependency",
    "raw material",
    "technology change",
    "execution",
    "regulatory changes",
    "market demand",
]

NEGATIVE_PATTERNS = [
    "audit report",
    "reasonable assurance",
    "financial statements",
    "going concern",
    "board meeting",
    "notice of meeting",
    "share capital",
    "opening stock",
    "closing stock",
    "inventories",
    "credit risk",
    "liquidity risk",
    "market risk",
    "interest rate risk",
    "foreign currency risk",
    "cash flow forecasting",
    "sensitivity analysis",
    "trade receivables",
    "financial instruments",
]

PROMPT = """
You are a forensic business analyst.

Extract business risks mentioned in the text.

Examples:

- customer concentration
- technology disruption
- supply chain dependence
- execution challenges
- regulatory risk
- foreign exchange exposure
- litigation
- competition
- raw material dependence

Return JSON:

{
  "risks": [
    {
      "risk": "",
      "category": "",
      "severity": ""
    }
  ]
}

Rules:

- Extract only genuine business risks.
- Ignore accounting disclosures.
- Ignore audit procedures.
- Ignore generic boilerplate.
- Never invent information.

Return only valid JSON.
"""
