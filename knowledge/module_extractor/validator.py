from __future__ import annotations

from typing import Any, Dict, List

from .schema import ModuleAnswer, ModuleExtractionResult


class ValidationError(ValueError):
    pass


VALID_STATUSES = {
    "FOUND",
    "NOT_FOUND",
    "UNCERTAIN",
}


def _validate_string_list(
    value: Any,
    field_name: str,
    index: int,
) -> List[str]:
    if not isinstance(value, list):
        raise ValidationError(
            f"answers[{index}].{field_name} must be a list"
        )

    if not all(
        isinstance(item, str) and item.strip()
        for item in value
    ):
        raise ValidationError(
            f"answers[{index}].{field_name} must contain non-empty strings"
        )

    return list(value)


def validate_module_extraction_payload(
    payload: Dict[str, Any],
) -> ModuleExtractionResult:

    if not isinstance(payload, dict):
        raise ValidationError("payload must be an object")

    module_id = payload.get("module_id")
    module_name = payload.get("module_name")
    answers = payload.get("answers")

    if not isinstance(module_id, str) or not module_id.strip():
        raise ValidationError("module_id is required")

    if not isinstance(module_name, str) or not module_name.strip():
        raise ValidationError("module_name is required")

    if not isinstance(answers, list) or not answers:
        raise ValidationError("answers must be a non-empty list")

    seen_question_ids = set()
    normalized_questions = set()

    validated_answers: List[ModuleAnswer] = []

    for index, item in enumerate(answers):

        if not isinstance(item, dict):
            raise ValidationError(
                f"answers[{index}] must be an object"
            )

        question_id = item.get("question_id")
        question = item.get("question")

        direct_answer = item.get("direct_answer")
        if direct_answer is None:
            direct_answer = item.get("answer")

        supporting_points = item.get("supporting_points")

        primary_evidence = item.get("primary_evidence")

        secondary_evidence = item.get("secondary_evidence")

        confidence = item.get("confidence")

        status = item.get("status")

        if not isinstance(question_id, str) or not question_id.strip():
            raise ValidationError(
                f"answers[{index}].question_id is required"
            )

        if question_id in seen_question_ids:
            raise ValidationError(
                f"duplicate question_id: {question_id}"
            )

        seen_question_ids.add(question_id)

        if not isinstance(question, str) or not question.strip():
            raise ValidationError(
                f"answers[{index}].question is required"
            )

        normalized_question = question.strip().lower()

        if normalized_question in normalized_questions:
            raise ValidationError(
                f"duplicate question text: {question}"
            )

        normalized_questions.add(normalized_question)

        if not isinstance(direct_answer, str):
            raise ValidationError(
                f"answers[{index}].direct_answer must be a string"
            )

        if supporting_points is None:
            supporting_points = item.get("supporting_chunk_ids") or []
        supporting_points = _validate_string_list(
            supporting_points,
            "supporting_points",
            index,
        )

        if primary_evidence is None:
            primary_evidence = []
        primary_evidence = _validate_string_list(
            primary_evidence,
            "primary_evidence",
            index,
        )

        if secondary_evidence is None:
            secondary_evidence = []
        secondary_evidence = _validate_string_list(
            secondary_evidence,
            "secondary_evidence",
            index,
        )

        if (
            not isinstance(confidence, (int, float))
            or not 0 <= float(confidence) <= 1
        ):
            raise ValidationError(
                f"answers[{index}].confidence must be between 0 and 1"
            )

        if status not in VALID_STATUSES:
            raise ValidationError(
                f"answers[{index}].status is invalid"
            )

        validated_answers.append(
            ModuleAnswer(
                question_id=question_id,
                question=question,
                direct_answer=direct_answer,
                supporting_points=supporting_points,
                primary_evidence=primary_evidence,
                secondary_evidence=secondary_evidence,
                confidence=float(confidence),
                status=status,
            )
        )

    return ModuleExtractionResult(
        module_id=module_id,
        module_name=module_name,
        answers=validated_answers,
    )