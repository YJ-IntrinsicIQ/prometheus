from __future__ import annotations

from typing import Any

from knowledge.ai.input_packs import build_llm_input_pack, render_llm_input_pack


def build_input_pack(module: Any, chunks: Any, *, business_context: dict | None = None) -> dict:
    questions = []
    for question in getattr(module, "questions", []) or []:
        questions.append(
            {
                "question_id": question.id,
                "question": question.question,
            }
        )

    normalized_chunks = []
    for index, chunk in enumerate(chunks or [], start=1):
        if isinstance(chunk, dict):
            chunk_id = chunk.get("chunk_id", f"chunk_{index}")
            text = chunk.get("text", "")
            retrieval_score = chunk.get("retrieval_score", 0.0)
            metadata = dict(chunk.get("metadata") or {})
            evidence_ids = list(chunk.get("evidence_ids") or metadata.get("evidence_ids") or [])
            evidence_quality = dict(chunk.get("evidence_quality") or metadata.get("evidence_quality") or {})
            page = chunk.get("page", metadata.get("page"))
            year = chunk.get("year", metadata.get("year"))
        else:
            chunk_id = getattr(chunk, "chunk_id", f"chunk_{index}")
            text = getattr(chunk, "text", "")
            retrieval_score = getattr(chunk, "retrieval_score", 0.0)
            metadata = dict(getattr(chunk, "metadata", {}) or {})
            evidence_ids = list(metadata.get("evidence_ids") or [])
            evidence_quality = dict(metadata.get("evidence_quality") or {})
            page = metadata.get("page")
            year = metadata.get("year")
        normalized_chunks.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "retrieval_score": retrieval_score,
                "page": page,
                "year": year,
                "evidence_ids": evidence_ids,
                "evidence_quality": evidence_quality,
            }
        )

    business_dnas = []
    if isinstance(business_context, dict):
        business_dnas = [
            str(item).strip()
            for item in business_context.get("business_dnas", []) or []
            if str(item).strip()
        ]

    return build_llm_input_pack(
        stage="business_intelligence",
        purpose="Answer module-specific investor questions using only retrieved evidence chunks.",
        company="",
        year=None,
        facts=[
            {
                "module_id": getattr(module, "module_id", ""),
                "module_name": getattr(module, "module_name", ""),
                "business_dnas": business_dnas,
            }
        ],
        selected_input={
            "module": {
                "module_id": getattr(module, "module_id", ""),
                "module_name": getattr(module, "module_name", ""),
            },
            "questions": questions,
            "chunks": normalized_chunks,
        },
        source_artifacts=["retrieval_chunks"],
        pack_name=f"{getattr(module, 'module_id', 'module')}_input_pack",
    )


def build_prompt(module: Any, chunks: Any, llm_input_pack: dict | None = None) -> str:
    questions = getattr(module, "questions", [])

    question_lines = []
    for question in questions:
        question_lines.append(
            f"- {question.id}: {question.question}"
        )

    llm_input_pack = llm_input_pack or build_input_pack(module, chunks)

    return f"""You are a senior investment analyst.

Your responsibility is to answer investor questions using ONLY the supplied evidence.

Do NOT summarize the document.

Instead:

- Synthesize information across ALL relevant chunks.
- Combine related evidence into one coherent answer.
- Prioritize information that could materially affect an investor's understanding of the business.
- Ignore trivial operational details unless they directly answer the question.
- If multiple chunks describe the same event, merge them into one answer.
- If the supplied evidence contains conflicting information, report the conflict instead of choosing one side.
- Never speculate.
- Never use outside knowledge.
- Never invent facts.

Rules

- Use ONLY the supplied chunks.
- Every answer must reference supporting chunk IDs.
- If evidence is insufficient, answer exactly "Not Found".
- Return VALID JSON ONLY.
- Do not include Markdown.
- Do not include explanations outside JSON.

Module

ID: {getattr(module, "module_id", "")}

Name: {getattr(module, "module_name", "")}

Questions

{chr(10).join(question_lines) if question_lines else "None"}

Evidence

{render_llm_input_pack(llm_input_pack, include_policy=False)}

Return EXACTLY this JSON:

{{
  "module_id": "",
  "module_name": "",
  "answers": [
    {{
      "question_id": "",
      "question": "",
      "direct_answer": "",
      "supporting_points": [
        ""
      ],
      "primary_evidence": [
        ""
      ],
      "secondary_evidence": [
        ""
      ],
      "confidence": 0.0,
      "status": "FOUND"
    }}
  ]
}}

Status must be one of:

FOUND
NOT_FOUND
UNCERTAIN

Confidence must be between 0.0 and 1.0.

The response must be valid JSON and nothing else.
"""
