from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


from knowledge.business_blueprint import DEFAULT_BLUEPRINT_VERSION


def _compact_company_memory(company_memory: Any) -> Any:
    if not hasattr(company_memory, "company_id") or not hasattr(company_memory, "events"):
        return company_memory.to_dict() if hasattr(company_memory, "to_dict") else str(company_memory)

    entities: List[Dict[str, Any]] = []
    for entity in getattr(company_memory, "entities", {}).values():
        entities.append(
            {
                "name": getattr(entity, "name", ""),
                "entity_type": getattr(entity, "entity_type", ""),
                "current_state": (
                    {
                        "status": entity.current_state.status,
                        "summary": entity.current_state.metadata.get("summary"),
                    }
                    if getattr(entity, "current_state", None) is not None
                    else None
                ),
            }
        )

    facts: List[Dict[str, Any]] = []
    for event in sorted(
        getattr(company_memory, "events", {}).values(),
        key=lambda item: getattr(item, "event_type", ""),
    ):
        facts.append(
            {
                "event_type": getattr(event, "event_type", ""),
                "summary": getattr(event, "summary", ""),
            }
        )

    return {
        "company_id": getattr(company_memory, "company_id", ""),
        "entities": entities,
        "facts": facts,
    }


def build_prompt(company_memory: Any, classification_context: Optional[Dict[str, Any]] = None) -> str:
    compact_memory = _compact_company_memory(company_memory)
    classification_context = classification_context or {}
    return f"""You are an expert business analyst.

Your task is to interpret the supplied Company Memory into:
1. a Business Blueprint
2. a constrained Business Classification

Rules:

- Use ONLY the supplied Company Memory.
- Never invent facts.
- Never make unsupported assumptions.
- If information is insufficient, express lower confidence rather than guessing.
- Keep all summaries concise and objective.
- Return VALID JSON ONLY.
- Do NOT include markdown.
- Do NOT include explanations outside the JSON.
- Do NOT omit, rename, or leave blank any required field shown below.
- `business_understanding.business_summary` is REQUIRED and must be a concise, non-empty string.
- Every `confidence` value must be a JSON number between 0 and 1.
- Never write confidence values as words, percentages, fractions, or quoted strings.
- Use simple decimals such as `0.42`, `0.8`, or `1.0`.
- `reasoning` must be an array of objects with a `statement` string field.
- `characteristics` must describe concrete operating, economic, strategic, or industry-specific business traits.
- Prefer company-specific descriptors that help downstream classification.
- Avoid vague generic labels such as `Sustainability`, `Innovation`, `Social Responsibility`, or `Human Resources` unless they are tied to a specific business attribute.
- If a theme is relevant, express it in operating/business terms, for example:
  - `Semiconductor manufacturing`
  - `Export-led expansion via overseas subsidiaries`
  - `Advanced manufacturing automation and digital twin adoption`
  - `Energy-efficiency-led manufacturing optimization`
  - `R&D collaboration with academic institutions`
  - `Capital-intensive manufacturing buildout`
  - `Convertible / debt-funded expansion`
- Good characteristics should usually identify one of:
  - industry positioning
  - manufacturing or operating model
  - expansion pattern
  - technology or automation capability
  - funding/capital structure pattern
  - cost/efficiency operating discipline
- Prefer specific multi-word phrases over abstract single-word labels.
- Include 3 to 6 characteristics when the memory supports them.
- The classification task is constrained to the supplied allowed DNAs and candidate archetypes.
- Choose Business DNAs only from the supplied allowed DNAs.
- Do not infer a DNA from generic words alone such as `technology`, `digital`, `innovation`, `platform`, or `global`.
- Use the supplied negative signals to reject neighboring but wrong archetypes.
- Select only the smallest set of DNAs that is strongly supported by the evidence, with a maximum of 3.
- If a nearby archetype is plausible but unsupported, place it in `classification.rejected_dnas` with a short reason.
- `classification.question_modules`, `classification.discovery_profile`, and `classification.extraction_profile` are NOT part of the response. Local code will derive them deterministically.

Return exactly this JSON structure:

{{
  "metadata": {{
    "company": "",
    "version": "{DEFAULT_BLUEPRINT_VERSION}",
    "generated_at": "",
    "confidence": 0.0
  }},
  "business_understanding": {{
    "business_summary": "",
    "business_model": "",
    "value_creation": "",
    "competitive_position": ""
  }},
  "characteristics": [
    {{
      "name": "",
      "confidence": 0.0
    }}
  ],
  "reasoning": [
    {{
      "statement": ""
    }}
  ],
  "classification": {{
    "selected_dnas": [
      {{
        "name": "",
        "confidence": 0.0,
        "reason": ""
      }}
    ],
    "rejected_dnas": [
      {{
        "name": "",
        "reason": ""
      }}
    ],
    "rationale": [
      ""
    ],
    "evidence_used": [
      ""
    ],
    "confidence": 0.0
  }}
}}

All of the following are required in the final JSON:

- `metadata.company`
- `metadata.version`
- `metadata.generated_at`
- `metadata.confidence`
- `business_understanding.business_summary`
- `business_understanding.business_model`
- `business_understanding.value_creation`
- `business_understanding.competitive_position`
- at least one item in `characteristics`
- at least one item in `reasoning`
- `classification.selected_dnas` may be empty only if none of the allowed DNAs is supported
- every selected DNA must come from the supplied allowed DNAs
- every rejected DNA must include a short reason

Before finalizing your answer, check that:

1. every required field is present
2. no required string field is empty
3. no field names were renamed
4. the response is a single valid JSON object
5. every `confidence` value is a valid JSON number
6. no numeric field uses words or invalid tokens
7. each characteristic is concrete and company-specific rather than generic
8. each selected DNA comes only from the supplied allowed DNAs
9. generic words alone were not used as justification for classification

Classification Context:

{json.dumps(classification_context, indent=2, ensure_ascii=False)}

Company Memory:

{json.dumps(compact_memory, indent=2, ensure_ascii=False)}
"""
