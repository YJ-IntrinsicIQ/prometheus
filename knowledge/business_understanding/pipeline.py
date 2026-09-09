from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.context_paths import intelligence_path
from knowledge.ai import get_llm
from knowledge.ai.input_packs import call_llm_with_input_pack
from knowledge.business_identity import (
    align_blueprint_with_classification,
    ensure_business_identity_contract,
)
from knowledge.business_classifier import BusinessClassifier
from knowledge.business_interpreter import BusinessInterpreter
from knowledge.company_memory import CompanyMemory, CompanyMemoryBuilder, save_company_memory
from pipelines.pipeline_context import get_context


class BusinessUnderstandingError(RuntimeError):
    pass


_CLEAN_ARTIFACT_SPECS = [
    ("clean_projects.json", "project", "project_name"),
    ("clean_promises.json", "promise", "promise"),
    ("clean_risks.json", "risk", "risk"),
    ("clean_capacity.json", "capacity", "capacity_type"),
    ("clean_capital_allocation.json", "capital_allocation", "action"),
    ("clean_initiatives.json", "initiative", "initiative"),
]

_IGNORED_RECORD_FIELDS = {
    "source_chunk",
    "page",
    "distance",
    "confidence",
}


def _load_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []

    return [item for item in payload if isinstance(item, dict)]


def _iter_clean_records(context) -> Iterable[tuple[str, str, str, List[Dict[str, Any]]]]:
    for filename, event_prefix, title_field in _CLEAN_ARTIFACT_SPECS:
        path = context.extracted_dir / filename
        records = _load_json_list(path)
        if records:
            yield filename, event_prefix, title_field, records


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _truncate_text(text: str, limit: int = 240) -> str:
    normalized = (text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _build_event_summary(event_prefix: str, title_field: str, record: Dict[str, Any]) -> str:
    title = _stringify_value(record.get(title_field))
    detail_parts = []

    for key, value in record.items():
        if key in _IGNORED_RECORD_FIELDS or key == title_field:
            continue

        normalized = _stringify_value(value)
        if normalized:
            detail_parts.append(f"{key}: {normalized}")

    summary_prefix = title or event_prefix.replace("_", " ").title()
    if not detail_parts:
        return summary_prefix

    return f"{summary_prefix} - {'; '.join(detail_parts[:3])}"


def _build_event_metadata(filename: str, record: Dict[str, Any], index: int) -> Dict[str, Any]:
    metadata = {
        "artifact_file": filename,
        "artifact_index": index,
    }

    for key, value in record.items():
        if key == "source_chunk":
            continue

        normalized = _stringify_value(value)
        if normalized:
            metadata[key] = _truncate_text(normalized)

    return metadata


def _build_payload_from_clean_artifacts(context) -> Dict[str, Any]:
    events = []

    for filename, event_prefix, title_field, records in _iter_clean_records(context):
        for index, record in enumerate(records, start=1):
            event_type = f"{event_prefix}_{index}"
            evidence_source = f"{filename}#{index}"
            summary = _build_event_summary(event_prefix, title_field, record)
            source_chunk = _stringify_value(record.get("source_chunk"))

            events.append(
                {
                    "event_type": event_type,
                    "summary": summary,
                    "metadata": _build_event_metadata(filename, record, index),
                    "evidence": [
                        {
                            "source": evidence_source,
                            "source_type": "cleaned_artifact",
                            "content": summary,
                            "metadata": {
                                "artifact_file": filename,
                                "artifact_index": index,
                                "page": record.get("page"),
                                "distance": record.get("distance"),
                            },
                        }
                    ],
                }
            )

    if not events:
        return {}

    return {
        "company_id": context.company,
        "metadata": {
            "source": "cleaned_artifacts",
        },
        "entities": [
            {
                "name": context.company.title(),
                "entity_type": "company",
                "metadata": {
                    "source": "cleaned_artifacts",
                    "artifact_files": [
                        filename
                        for filename, _, _ in _CLEAN_ARTIFACT_SPECS
                        if (context.extracted_dir / filename).exists()
                    ],
                },
                "events": events,
            }
        ],
    }


def _build_fallback_document_payload(context) -> Dict[str, Any]:
    from core.inbox_paths import PROCESSED
    _fy = str(context.year).lower()
    _processed = PROCESSED / context.company / _fy / "annual_report"
    annual_report_path = next(
        (p for p in sorted(_processed.glob("*.pdf")) if _processed.exists()), None
    )

    if not annual_report_path or not annual_report_path.exists():
        return {
            "company_id": context.company,
            "entities": [],
        }

    return {
        "company_id": context.company,
        "metadata": {
            "source": "annual_report_stub",
        },
        "entities": [
            {
                "name": context.company.title(),
                "entity_type": "company",
                "events": [
                    {
                        "event_type": "document_loaded",
                        "summary": f"Loaded {annual_report_path.name}",
                        "evidence": [
                            {
                                "source": annual_report_path.name,
                                "source_type": "annual_report",
                                "content": f"Processed {annual_report_path.name}",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _load_document_payload(context=None) -> Dict[str, Any]:
    context = context or get_context()
    if context is None:
        raise BusinessUnderstandingError("No pipeline context available")

    payload = _build_payload_from_clean_artifacts(context)
    if payload:
        return payload

    return _build_fallback_document_payload(context)


def _build_company_memory(document_payload: Dict[str, Any], context=None) -> CompanyMemory:
    context = context or get_context()
    if context is None:
        raise BusinessUnderstandingError("No pipeline context available")

    if document_payload.get("metadata", {}).get("source") == "cleaned_artifacts":
        return CompanyMemoryBuilder(existing_memory=None, new_document=document_payload).build()

    existing_path = intelligence_path("company_memory.json", context_dir="intelligence_dir")
    existing_memory = None
    if existing_path.exists():
        existing_memory = CompanyMemory.from_dict(json.loads(existing_path.read_text(encoding="utf-8")))

    return CompanyMemoryBuilder(existing_memory, document_payload).build()


def _build_business_understanding_bundle(
    company_memory: CompanyMemory,
    *,
    context=None,
) -> Dict[str, Any]:
    llm = get_llm()
    context = context or get_context()
    classifier = BusinessClassifier()
    classification_context = classifier.build_candidate_context(
        company_memory,
        company=context.company if context is not None else company_memory.company_id,
        year=context.year if context is not None else None,
    )

    def ai_adapter(prompt: str, *, llm_input_pack: Optional[Dict[str, Any]] = None) -> str:
        response = call_llm_with_input_pack(
            llm=llm,
            prompt=prompt,
            input_pack=llm_input_pack or {
                "pack_name": "business_understanding_input_pack",
                "stage": "business_understanding",
                "company": context.company if context is not None else company_memory.company_id,
                "year": context.year if context is not None else None,
                "purpose": "Interpret company memory into business blueprint and constrained business classification.",
                "input_policy": {},
                "facts": [],
                "observations": [],
                "evidence_ids": [],
                "limitations": [],
                "metadata": {
                    "source_artifacts": ["company_memory.json"],
                    "source_hashes": [],
                    "tokens_estimated": 1,
                    "chars": 1,
                    "truncation_applied": False,
                    "warnings": [],
                },
            },
            manifest_path=(
                context.intelligence_dir / "business_understanding_llm_call_manifest.json"
                if context is not None
                else None
            ),
            require_source_artifacts=True,
            response_schema={"type": "object"},
        )
        print(f"AI Provider: {response.provider}")
        print(f"AI Model: {response.model}")
        print(f"AI Latency: {response.latency_ms:.2f}ms")
        print(f"AI Prompt tokens: {response.prompt_tokens}")
        print(f"AI Completion tokens: {response.completion_tokens}")
        print(f"AI Total tokens: {response.total_tokens}")
        return response.text

    interpreter = BusinessInterpreter(company_memory, llm_client=ai_adapter)
    interpretation = interpreter.interpret(classification_context=classification_context)
    business_blueprint = interpretation.blueprint
    business_classification = classifier.finalize_classification(
        business_blueprint,
        interpretation.classification,
        company=context.company if context is not None else business_blueprint.metadata.company,
        year=context.year if context is not None else None,
    )
    business_blueprint = align_blueprint_with_classification(
        business_blueprint,
        business_classification,
    )
    business_identity_manifest = ensure_business_identity_contract(
        business_blueprint,
        business_classification,
    )
    return {
        "business_blueprint": business_blueprint,
        "business_classification": business_classification,
        "classification_context": classification_context,
        "business_identity_manifest": business_identity_manifest,
    }


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_business_understanding(context=None) -> Dict[str, Any]:
    context = context or get_context()
    if context is None:
        raise BusinessUnderstandingError("No pipeline context available")

    document_payload = _load_document_payload(context)
    company_memory = _build_company_memory(document_payload, context)
    interpretation_bundle = _build_business_understanding_bundle(
        company_memory,
        context=context,
    )
    business_blueprint = interpretation_bundle["business_blueprint"]
    business_classification = interpretation_bundle["business_classification"]

    memory_path = intelligence_path("company_memory.json", context_dir="intelligence_dir")
    blueprint_path = intelligence_path("business_blueprint.json", context_dir="intelligence_dir")
    classification_path = intelligence_path("business_classification.json", context_dir="intelligence_dir")

    save_company_memory(company_memory, memory_path)
    _write_json(blueprint_path, business_blueprint.to_dict())
    _write_json(classification_path, business_classification)

    return {
        "company_memory": company_memory,
        "business_blueprint": business_blueprint,
        "business_classification": business_classification,
        "classification_context": interpretation_bundle["classification_context"],
        "business_identity_manifest": interpretation_bundle["business_identity_manifest"],
    }
