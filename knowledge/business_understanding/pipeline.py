from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from core.context_paths import intelligence_path
from knowledge.business_blueprint import BusinessBlueprint
from knowledge.business_classifier import BusinessClassifier
from knowledge.business_interpreter import BusinessInterpreter
from knowledge.company_memory import CompanyMemory, CompanyMemoryBuilder, save_company_memory
from pipelines.pipeline_context import get_context


class BusinessUnderstandingError(RuntimeError):
    pass


def _load_document_payload(context=None) -> Dict[str, Any]:
    context = context or get_context()
    if context is None:
        raise BusinessUnderstandingError("No pipeline context available")

    annual_report_path = Path("data/annual_reports") / f"{context.company}_{context.year}.pdf"
    if not annual_report_path.exists():
        annual_report_path = Path("data/annual_reports") / f"{context.company}_{context.year}.txt"

    if not annual_report_path.exists():
        return {
            "company_id": context.company,
            "entities": [],
        }

    return {
        "company_id": context.company,
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


def _build_company_memory(document_payload: Dict[str, Any], context=None) -> CompanyMemory:
    context = context or get_context()
    if context is None:
        raise BusinessUnderstandingError("No pipeline context available")

    existing_path = intelligence_path("company_memory.json", context_dir="intelligence_dir")
    existing_memory = None
    if existing_path.exists():
        existing_memory = CompanyMemory.from_dict(json.loads(existing_path.read_text(encoding="utf-8")))

    return CompanyMemoryBuilder(existing_memory, document_payload).build()


def _build_blueprint(company_memory: CompanyMemory) -> BusinessBlueprint:
    def fake_llm(prompt: str) -> str:
        return json.dumps(
            {
                "metadata": {
                    "company": company_memory.company_id,
                    "version": "1.0",
                    "confidence": 0.8,
                },
                "business_understanding": {
                    "business_summary": "Interpreted from Company Memory",
                    "business_model": "Information-only processing",
                    "value_creation": "Summarizes available memory",
                    "competitive_position": "Derived from the supplied memory",
                },
                "characteristics": [
                    {"name": "Capital Intensive", "confidence": 0.7},
                ],
                "reasoning": [{"statement": "The memory describes a documented company context."}],
            }
        )

    interpreter = BusinessInterpreter(company_memory, llm_client=fake_llm)
    return interpreter.interpret()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_business_understanding(context=None) -> Dict[str, Any]:
    context = context or get_context()
    if context is None:
        raise BusinessUnderstandingError("No pipeline context available")

    document_payload = _load_document_payload(context)
    company_memory = _build_company_memory(document_payload, context)
    business_blueprint = _build_blueprint(company_memory)
    business_classification = BusinessClassifier().classify(business_blueprint)

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
    }
