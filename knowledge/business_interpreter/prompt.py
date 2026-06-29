from __future__ import annotations

from typing import Any


def build_prompt(company_memory: Any) -> str:
    return f"""You are an expert business analyst.

Your task is to interpret the supplied Company Memory into a Business Blueprint.

Rules:

- Use ONLY the supplied Company Memory.
- Never invent facts.
- Never make unsupported assumptions.
- If information is insufficient, express lower confidence rather than guessing.
- Keep all summaries concise and objective.
- Return VALID JSON ONLY.
- Do NOT include markdown.
- Do NOT include explanations outside the JSON.
- Do NOT generate Business DNAs.
- Do NOT generate Question Modules.
- Do NOT generate Discovery Profiles.
- Do NOT generate Extraction Profiles.

Return exactly this JSON structure:

{{
  "metadata": {{
    "company": "",
    "version": "",
    "generated_at": "",
    "confidence": 0.0
  }},
  "business_understanding": {{
    "business_summary": "",
    "business_model": "",
    "value_creation": "",
    "competitive_position": ""
  }},
  "business_characteristics": [
    {{
      "name": "",
      "confidence": 0.0
    }}
  ],
  "reasoning": [
    ""
  ]
}}

Company Memory:

{company_memory.to_dict() if hasattr(company_memory, "to_dict") else str(company_memory)}
"""