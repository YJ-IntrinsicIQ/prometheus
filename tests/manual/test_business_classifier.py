#!/usr/bin/env python3
"""
Manual verification tool for the Business Classification layer.

This script is diagnostic only. It uses real company artifacts for tips/2024
and explains the existing classifier's registry matches without changing
production code or inventing new classification rules.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from knowledge.business_blueprint import BusinessBlueprint  # noqa: E402
from knowledge.business_classifier import BusinessClassifier  # noqa: E402
from knowledge.business_interpreter import BusinessInterpreter, validate_blueprint_payload  # noqa: E402
from knowledge.company_memory import CompanyMemory, load_company_memory  # noqa: E402


COMPANY = "tips"
YEAR = "2024"
INTELLIGENCE_DIR = ROOT / "companies" / COMPANY / YEAR / "intelligence"
MEMORY_PATH = INTELLIGENCE_DIR / "company_memory.json"
BLUEPRINT_PATH = INTELLIGENCE_DIR / "business_blueprint.json"

TIPS_MANUFACTURING_SUPPORT_TERMS = [
    "Plant",
    "Factory",
    "Production",
    "Capacity",
    "Capex",
]


def main() -> int:
    print_header("BUSINESS CLASSIFIER VERIFICATION")
    print(f"Company: {COMPANY}")
    print(f"Year: {YEAR}")

    memory = step_1_load_memory()
    blueprint = step_2_run_business_interpreter(memory)
    classification = step_3_run_business_classifier(blueprint)
    explanations = step_4_explain_dna_selection(memory, blueprint, classification)
    warnings = step_5_sanity_checks(memory, blueprint, classification)
    step_6_final_summary(classification, explanations, warnings)
    return 0


def step_1_load_memory() -> CompanyMemory:
    print_step("STEP 1 - Load company_memory.json")
    try:
        memory = load_company_memory(MEMORY_PATH)
    except Exception as exc:
        fail("STEP 1 - Memory loaded", exc)

    if memory is None:
        fail("STEP 1 - Memory loaded", f"Missing file: {MEMORY_PATH}")

    entity_count = len(memory.entities)
    event_count = len(memory.events)
    evidence_count = len(memory.evidence)

    print(f"Memory loaded: {MEMORY_PATH}")
    print(f"Entity count: {entity_count}")
    print(f"Event count: {event_count}")
    print(f"Evidence count: {evidence_count}")

    if entity_count <= 0 or event_count <= 0 or evidence_count <= 0:
        fail("STEP 1 - Memory loaded", "entity, event, and evidence counts must all be > 0")

    print("PASS: Memory loaded")
    return memory


def step_2_run_business_interpreter(memory: CompanyMemory) -> BusinessBlueprint:
    print_step("STEP 2 - Run Business Interpreter")

    try:
        blueprint = BusinessInterpreter(memory).interpret()
        source = "BusinessInterpreter.interpret()"
    except Exception as exc:
        if not BLUEPRINT_PATH.exists():
            fail("STEP 2 - Business Interpreter", exc)
        print(f"Interpreter execution unavailable: {exc}")
        print(f"Using existing Business Blueprint artifact: {BLUEPRINT_PATH}")
        try:
            blueprint = BusinessBlueprint.from_dict(load_json(BLUEPRINT_PATH))
        except Exception as load_exc:
            fail("STEP 2 - Business Blueprint loaded", load_exc)
        source = "existing business_blueprint.json"

    try:
        blueprint = validate_blueprint_payload(blueprint.to_dict())
    except Exception as exc:
        fail("STEP 2 - Business Interpreter output validation", exc)

    understanding = blueprint.business_understanding
    print(f"Blueprint source: {source}")
    print(f"Business Summary: {understanding.business_summary}")
    print(f"Business Model: {understanding.business_model}")
    print(f"Value Creation: {understanding.value_creation}")
    print(f"Competitive Position: {understanding.competitive_position}")
    print("Characteristics detected:")
    for characteristic in blueprint.characteristics:
        print(f"- {characteristic.name} (confidence: {characteristic.confidence:.2f})")
    print(f"Confidence: {blueprint.metadata.confidence:.2f}")
    print("PASS: Business Interpreter output available")
    return blueprint


def step_3_run_business_classifier(blueprint: BusinessBlueprint) -> Dict[str, Any]:
    print_step("STEP 3 - Run Business Classifier")
    try:
        classification = BusinessClassifier().classify(blueprint)
    except Exception as exc:
        fail("STEP 3 - Business Classifier", exc)

    print_list("Detected Business DNA(s)", classification.get("business_dnas", []))
    print_json("Discovery Profile", classification.get("discovery_profile", {}))
    print_json("Extraction Profile", classification.get("extraction_profile", {}))
    print_list("Question Modules", classification.get("question_modules", []))
    print(f"Report Template: {classification.get('report_template')}")

    if not classification.get("business_dnas"):
        fail("STEP 3 - Business Classifier", "No Business DNA detected")

    print("PASS: Business Classifier returned classification")
    return classification


def step_4_explain_dna_selection(
    memory: CompanyMemory,
    blueprint: BusinessBlueprint,
    classification: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    print_step("STEP 4 - Most Important Section")
    classifier = BusinessClassifier()
    blueprint_characteristics = [item.name for item in blueprint.characteristics]
    explanations: Dict[str, Dict[str, Any]] = {}

    for dna in classification.get("business_dnas", []):
        matching_mappings = [
            mapping
            for mapping in classifier.registry.find_matches(blueprint_characteristics)
            if dna in mapping.get("dnas", [])
        ]
        matched_characteristics = collect_matched_characteristics(
            blueprint.characteristics,
            matching_mappings,
        )
        evidence = collect_evidence(memory, blueprint, matched_characteristics)

        explanations[dna] = {
            "matched_characteristics": matched_characteristics,
            "rules": matching_mappings,
            "evidence": evidence,
            "confidence": max(
                [item["confidence"] for item in matched_characteristics],
                default=None,
            ),
        }

        print(f"Business DNA:\n{dna}")
        print("\nMatched because")
        if matched_characteristics:
            for item in matched_characteristics:
                print(f"- Characteristic: {item['name']} (confidence: {item['confidence']:.2f})")
        else:
            print("Reason unavailable.")

        print("\nRules matched")
        if matching_mappings:
            for mapping in matching_mappings:
                characteristics = mapping.get("characteristics", [])
                print(
                    "- Existing registry rule: match any blueprint characteristic in "
                    f"{characteristics}"
                )
        else:
            print("Reason unavailable.")

        print("\nEvidence used")
        if evidence:
            for snippet in evidence:
                print(f'"{snippet}"')
        else:
            print("Reason unavailable.")

        confidence = explanations[dna]["confidence"]
        if confidence is None:
            print("\nConfidence: Reason unavailable.")
        else:
            print(f"\nConfidence: {confidence:.2f} (matched characteristic confidence)")

    return explanations


def step_5_sanity_checks(
    memory: CompanyMemory,
    blueprint: BusinessBlueprint,
    classification: Dict[str, Any],
) -> List[str]:
    print_step("STEP 5 - Sanity Checks")
    warnings: List[str] = []
    detected_dnas = classification.get("business_dnas", [])

    if COMPANY == "tips" and "Manufacturing" in detected_dnas:
        missing_terms = [
            term
            for term in TIPS_MANUFACTURING_SUPPORT_TERMS
            if not corpus_contains(memory, blueprint, term)
        ]
        if missing_terms:
            warning = (
                "Detected DNA: Manufacturing; but no supporting evidence found for "
                + ", ".join(missing_terms)
            )
            warnings.append(warning)

    if warnings:
        for warning in warnings:
            print("WARNING")
            print(warning)
            print("This is NOT an automatic failure.")
    else:
        print("No sanity warnings.")

    print("PASS: Sanity checks completed")
    return warnings


def step_6_final_summary(
    classification: Dict[str, Any],
    explanations: Dict[str, Dict[str, Any]],
    warnings: Sequence[str],
) -> None:
    print_step("STEP 6 - Final Summary")
    detected_dnas = classification.get("business_dnas", [])
    print_list("Detected DNA(s)", detected_dnas)

    confidences = [
        explanation.get("confidence")
        for explanation in explanations.values()
        if explanation.get("confidence") is not None
    ]
    if confidences:
        print(f"Confidence: {max(confidences):.2f} (matched characteristic confidence)")
    else:
        print("Confidence: Reason unavailable.")

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("Warnings: None")

    if not detected_dnas:
        fail("STEP 6 - Final Summary", "No detected DNA(s)")

    print("PASS: Business classifier verification completed")


def collect_matched_characteristics(characteristics, mappings: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    mapping_names = {
        name.strip().lower()
        for mapping in mappings
        for name in mapping.get("characteristics", [])
        if name and name.strip()
    }
    matched = []
    for characteristic in characteristics:
        if characteristic.name.strip().lower() in mapping_names:
            matched.append({"name": characteristic.name, "confidence": characteristic.confidence})
    return matched


def collect_evidence(
    memory: CompanyMemory,
    blueprint: BusinessBlueprint,
    matched_characteristics: Sequence[Dict[str, Any]],
) -> List[str]:
    terms = [item["name"] for item in matched_characteristics]
    snippets = []

    for statement in blueprint.reasoning:
        text = statement.statement
        if contains_any(text, terms):
            snippets.append(trim(text))

    for event in memory.events.values():
        if contains_any(event.summary, terms):
            snippets.append(trim(event.summary))

    for evidence in memory.evidence.values():
        if evidence.content and contains_any(evidence.content, terms):
            snippets.append(trim(evidence.content))

    return unique(snippets)


def corpus_contains(memory: CompanyMemory, blueprint: BusinessBlueprint, term: str) -> bool:
    return contains_any("\n".join(corpus_texts(memory, blueprint)), [term])


def corpus_texts(memory: CompanyMemory, blueprint: BusinessBlueprint) -> List[str]:
    texts = []
    understanding = blueprint.business_understanding
    texts.extend(
        [
            understanding.business_summary,
            understanding.business_model,
            understanding.value_creation,
            understanding.competitive_position,
        ]
    )
    texts.extend(item.name for item in blueprint.characteristics)
    texts.extend(item.statement for item in blueprint.reasoning)
    texts.extend(entity.name for entity in memory.entities.values())
    texts.extend(event.summary for event in memory.events.values())
    texts.extend(evidence.content or "" for evidence in memory.evidence.values())
    return texts


def contains_any(text: str, terms: Sequence[str]) -> bool:
    normalized = text.lower()
    return any(term.lower() in normalized for term in terms if term)


def unique(items: Sequence[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def trim(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    return normalized[:limit]


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def print_header(title: str) -> None:
    print("=" * 50)
    print(title)
    print("=" * 50)
    print()


def print_step(title: str) -> None:
    print()
    print("-" * 50)
    print(title)
    print("-" * 50)


def print_list(label: str, values: Sequence[Any]) -> None:
    print(f"{label}:")
    if values:
        for value in values:
            print(f"- {value}")
    else:
        print("- None")


def print_json(label: str, payload: Any) -> None:
    print(f"{label}:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def fail(stage: str, detail: Any) -> None:
    print(f"FAIL: {stage}")
    print(f"Failing stage: {stage}")
    print(f"Reason: {detail}")
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
