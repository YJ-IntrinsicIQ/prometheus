#!/usr/bin/env python3
"""
Standalone manual verification tool for the Business Interpreter.

This is diagnostic only. It loads the real tips/2024 company_memory.json,
runs BusinessInterpreter through the real AI layer using Groq, prints
diagnostics, and writes business_blueprint.generated.json without touching the
production business_blueprint.json artifact.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from knowledge.ai import get_llm  # noqa: E402
from knowledge.ai.schema import AIResponse  # noqa: E402
from knowledge.business_blueprint import BusinessBlueprint  # noqa: E402
from knowledge.business_interpreter import BusinessInterpreter  # noqa: E402
from knowledge.company_memory import load_company_memory  # noqa: E402


COMPANY = "tips"
YEAR = "2024"
INTELLIGENCE_DIR = ROOT / "companies" / COMPANY / YEAR / "intelligence"
MEMORY_PATH = INTELLIGENCE_DIR / "company_memory.json"
GENERATED_BLUEPRINT_PATH = INTELLIGENCE_DIR / "business_blueprint.generated.json"
DEBUG_DIR = ROOT / "debug"

PLACEHOLDER_VALUES = {
    "placeholder",
    "tbd",
    "todo",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "not available",
    "not applicable",
    "to be determined",
}


@dataclass
class CapturedAI:
    prompt: Optional[str] = None
    raw_response: Optional[str] = None
    response: Optional[AIResponse] = None


def main() -> int:
    print_header("BUSINESS INTERPRETER VERIFICATION")
    print(f"Company: {COMPANY}")
    print(f"Year: {YEAR}")

    try:
        load_local_env()
        memory = load_real_company_memory()
        llm = get_llm(provider="groq")
        ai = CapturedAI()

        def ai_adapter(prompt: str) -> str:
            ai.prompt = prompt
            ai.response = llm.generate(
                prompt=prompt,
                response_schema={"type": "object"},
            )
            ai.raw_response = ai.response.text
            return ai.response.text

        try:
            blueprint = BusinessInterpreter(memory, llm_client=ai_adapter).interpret()
        except Exception as exc:
            if ai.response is not None:
                print_ai(ai.response)
            print_interpreter_failure(exc, ai)
            return 1

        if ai.response is None:
            raise RuntimeError("AI layer did not return a response")

        write_blueprint(blueprint)
        print_ai(ai.response)
        print_blueprint(blueprint)

        failures = validate_result(blueprint, ai.response, llm)
        print_validation(failures)
        return 1 if failures else 0
    except Exception as exc:
        print_section("Validation")
        print(f"FAIL: {exc}")
        return 1


def load_real_company_memory():
    memory = load_company_memory(MEMORY_PATH)
    if memory is None:
        raise FileNotFoundError(f"Missing company memory: {MEMORY_PATH}")
    return memory


def load_local_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def write_blueprint(blueprint: BusinessBlueprint) -> None:
    GENERATED_BLUEPRINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_BLUEPRINT_PATH.write_text(
        json.dumps(blueprint.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def write_debug_artifacts(ai: CapturedAI) -> Dict[str, Path]:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifacts: Dict[str, Path] = {}

    if ai.prompt is not None:
        path = unique_debug_path(timestamp, "interpreter_prompt", ".txt")
        path.write_text(ai.prompt, encoding="utf-8")
        artifacts["Prompt"] = path

    if ai.raw_response is not None:
        path = unique_debug_path(timestamp, "interpreter_raw_response", ".txt")
        path.write_text(ai.raw_response, encoding="utf-8")
        artifacts["Raw Response"] = path

        parsed = try_parse_json(ai.raw_response)
        if parsed is not None:
            parsed_path = unique_debug_path(timestamp, "interpreter_parsed", ".json")
            parsed_path.write_text(
                json.dumps(parsed, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            artifacts["Parsed JSON"] = parsed_path

    return artifacts


def unique_debug_path(timestamp: str, stem: str, suffix: str) -> Path:
    path = DEBUG_DIR / f"{timestamp}_{stem}{suffix}"
    if not path.exists():
        return path

    index = 2
    while True:
        candidate = DEBUG_DIR / f"{timestamp}_{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def try_parse_json(raw_response: str) -> Optional[Any]:
    try:
        return json.loads(raw_response)
    except (TypeError, json.JSONDecodeError):
        return None


def print_interpreter_failure(exc: Exception, ai: CapturedAI) -> None:
    artifacts = write_debug_artifacts(ai)
    parsed = try_parse_json(ai.raw_response) if ai.raw_response is not None else None
    missing_fields = find_missing_fields(parsed)
    extra_fields = find_extra_fields(parsed)
    schema_errors = find_schema_errors(parsed, exc)

    print_section("Validation")
    print("Validation Error")
    print(str(exc))
    print()
    print("Missing Fields")
    print_items(missing_fields)
    print()
    print("Extra Fields")
    print_items(extra_fields)
    print()
    print("Schema Errors")
    print_items(schema_errors)
    print()
    print("Debug Artifacts")
    if artifacts:
        for label, path in artifacts.items():
            print(f"{label}: {path}")
    else:
        print("None")


def find_missing_fields(parsed: Optional[Any]) -> List[str]:
    if not isinstance(parsed, dict):
        return ["<root JSON object>"]

    missing: List[str] = []
    required = {
        "metadata": ["company", "version", "generated_at", "confidence"],
        "business_understanding": [
            "business_summary",
            "business_model",
            "value_creation",
            "competitive_position",
        ],
    }

    for section, fields in required.items():
        section_value = parsed.get(section)
        if not isinstance(section_value, dict):
            missing.append(section)
            continue
        for field in fields:
            if field not in section_value or section_value.get(field) in ("", None):
                missing.append(f"{section}.{field}")

    characteristics = parsed.get("characteristics")
    if characteristics is None and "business_characteristics" in parsed:
        missing.append("characteristics")
    elif not isinstance(characteristics, list) or not characteristics:
        missing.append("characteristics")
    else:
        for index, item in enumerate(characteristics):
            if not isinstance(item, dict):
                missing.append(f"characteristics[{index}].name")
                missing.append(f"characteristics[{index}].confidence")
                continue
            if item.get("name") in ("", None):
                missing.append(f"characteristics[{index}].name")
            if item.get("confidence") in ("", None):
                missing.append(f"characteristics[{index}].confidence")

    reasoning = parsed.get("reasoning")
    if not isinstance(reasoning, list) or not reasoning:
        missing.append("reasoning")
    else:
        for index, item in enumerate(reasoning):
            if isinstance(item, dict) and item.get("statement") in ("", None):
                missing.append(f"reasoning[{index}].statement")
            elif isinstance(item, str) and not item.strip():
                missing.append(f"reasoning[{index}]")

    return missing


def find_extra_fields(parsed: Optional[Any]) -> List[str]:
    if not isinstance(parsed, dict):
        return []

    extras: List[str] = []
    allowed_top_level = {
        "metadata",
        "business_understanding",
        "characteristics",
        "dnas",
        "reasoning",
    }
    allowed_nested = {
        "metadata": {"company", "version", "generated_at", "confidence"},
        "business_understanding": {
            "business_summary",
            "business_model",
            "value_creation",
            "competitive_position",
        },
    }

    for key, value in parsed.items():
        if key not in allowed_top_level:
            extras.append(key)
        if key in allowed_nested and isinstance(value, dict):
            for nested_key in value:
                if nested_key not in allowed_nested[key]:
                    extras.append(f"{key}.{nested_key}")

    for list_key in ("characteristics", "dnas"):
        items = parsed.get(list_key)
        if isinstance(items, list):
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                for key in item:
                    if key not in {"name", "confidence"}:
                        extras.append(f"{list_key}[{index}].{key}")

    return extras


def find_schema_errors(parsed: Optional[Any], exc: Exception) -> List[str]:
    errors = [str(exc)]
    if parsed is None:
        errors.append("Raw response is not valid JSON")
        return errors
    if not isinstance(parsed, dict):
        errors.append("Parsed response is not a JSON object")
        return errors

    metadata = parsed.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        errors.append("metadata must be an object")
    elif isinstance(metadata, dict):
        confidence = metadata.get("confidence")
        if confidence is not None and not isinstance(confidence, (int, float)):
            errors.append("metadata.confidence must be numeric")

    understanding = parsed.get("business_understanding")
    if understanding is not None and not isinstance(understanding, dict):
        errors.append("business_understanding must be an object")

    characteristics = parsed.get("characteristics")
    if characteristics is not None and not isinstance(characteristics, list):
        errors.append("characteristics must be a list")
    elif isinstance(characteristics, list):
        for index, item in enumerate(characteristics):
            if not isinstance(item, dict):
                errors.append(f"characteristics[{index}] must be an object")
                continue
            confidence = item.get("confidence")
            if confidence is not None and not isinstance(confidence, (int, float)):
                errors.append(f"characteristics[{index}].confidence must be numeric")

    reasoning = parsed.get("reasoning")
    if reasoning is not None and not isinstance(reasoning, list):
        errors.append("reasoning must be a list")

    return dedupe(errors)


def dedupe(items: List[str]) -> List[str]:
    seen = set()
    unique = []
    for item in items:
        if item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def print_items(items: List[str]) -> None:
    if not items:
        print("None")
        return
    for item in items:
        print(f"- {item}")


def print_header(title: str) -> None:
    print("=" * 50)
    print(title)
    print("=" * 50)
    print()


def print_section(title: str) -> None:
    print("-" * 50)
    print()
    print(title)
    print()


def print_ai(response: AIResponse) -> None:
    print_section("AI")
    print(f"Provider: {response.provider}")
    print(f"Model: {response.model}")
    print(f"Latency: {response.latency_ms:.2f}ms")
    print(f"Prompt Tokens: {response.prompt_tokens}")
    print(f"Completion Tokens: {response.completion_tokens}")
    print(f"Total Tokens: {response.total_tokens}")


def print_blueprint(blueprint: BusinessBlueprint) -> None:
    understanding = blueprint.business_understanding

    print_section("Business Blueprint")
    print("Business Summary")
    print(understanding.business_summary)
    print()
    print("Business Model")
    print(understanding.business_model)
    print()
    print("Value Creation")
    print(understanding.value_creation)
    print()
    print("Competitive Position")
    print(understanding.competitive_position)
    print()
    print("Characteristics")
    for characteristic in blueprint.characteristics:
        print(f"- {characteristic.name} (confidence: {characteristic.confidence:.2f})")
    print()
    print("Reasoning")
    for item in blueprint.reasoning:
        print(f"- {item.statement}")
    print()
    print("Confidence")
    print(f"{blueprint.metadata.confidence:.2f}")
    print()
    print(f"Saved: {GENERATED_BLUEPRINT_PATH}")


def validate_result(blueprint: BusinessBlueprint, response: AIResponse, llm) -> List[str]:
    failures: List[str] = []
    understanding = blueprint.business_understanding

    required_fields = {
        "Business Summary": understanding.business_summary,
        "Business Model": understanding.business_model,
        "Value Creation": understanding.value_creation,
        "Competitive Position": understanding.competitive_position,
    }
    for name, value in required_fields.items():
        if not is_non_placeholder(value):
            failures.append(f"{name} is empty or placeholder")

    if not blueprint.characteristics:
        failures.append("At least one characteristic is required")
    if not blueprint.reasoning:
        failures.append("At least one reasoning statement is required")

    for characteristic in blueprint.characteristics:
        if not is_non_placeholder(characteristic.name):
            failures.append("Characteristic contains a placeholder value")
        if characteristic.name.strip().lower() == "capital intensive":
            failures.append('Characteristic contains hardcoded "Capital Intensive" output')

    for item in blueprint.reasoning:
        if not is_non_placeholder(item.statement):
            failures.append("Reasoning contains a placeholder value")
        if item.statement.strip().lower() == "capital intensive":
            failures.append('Reasoning contains hardcoded "Capital Intensive" output')

    if response.provider.strip().lower() != "groq":
        failures.append(f"Expected Groq provider, got {response.provider}")
    if llm.__class__.__name__.lower() == "mockprovider":
        failures.append("fake_llm/mock provider was used")
    if "mock" in response.provider.strip().lower() or "mock" in response.model.strip().lower():
        failures.append("fake_llm/mock response metadata detected")

    return failures


def is_non_placeholder(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return False
    return normalized not in PLACEHOLDER_VALUES and "placeholder" not in normalized


def print_validation(failures: List[str]) -> None:
    print_section("Validation")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return

    print("PASS")


if __name__ == "__main__":
    raise SystemExit(main())
