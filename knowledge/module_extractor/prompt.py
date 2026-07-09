from __future__ import annotations

from typing import Any


def build_prompt(module: Any, chunks: Any) -> str:
    questions = getattr(module, "questions", [])

    question_lines = []
    for question in questions:
        question_lines.append(
            f"- {question.id}: {question.question}"
        )

    chunk_lines = []
    for index, chunk in enumerate(chunks, start=1):
        if isinstance(chunk, dict):
            chunk_id = chunk.get("chunk_id", f"chunk_{index}")
            text = chunk.get("text", "")
        else:
            chunk_id = getattr(chunk, "chunk_id", f"chunk_{index}")
            text = getattr(chunk, "text", "")

        chunk_lines.append(
            f"[{chunk_id}]\n{text}\n"
        )

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

{chr(10).join(chunk_lines) if chunk_lines else "None"}

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