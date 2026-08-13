from knowledge.failure_learning import (
    CORE_LESSONS,
    FAILURE_CLASS_REGISTRY,
    INCIDENTS,
    INCIDENT_TAXONOMY,
    validate_failure_class_registry,
    validate_failure_learning_registry,
)


def test_failure_learning_registry_is_self_consistent():
    validation = validate_failure_learning_registry()

    assert validation["status"] == "pass"
    assert validation["date"] == "2026-08-09"
    assert validation["incident_count"] == 22
    assert validation["taxonomy_count"] == len(INCIDENT_TAXONOMY)
    assert not validation["issues"]


def test_failure_learning_covers_confirmed_and_hypothesis_root_causes():
    statuses = {incident["root_cause_status"] for incident in INCIDENTS}

    assert statuses == {"CONFIRMED", "HYPOTHESIS"}
    assert any("OCR" in safeguard or "OCR" in requirement for incident in INCIDENTS for safeguard in incident["durable_safeguards"] for requirement in incident["regression_requirements"])  # noqa: E501


def test_failure_learning_core_lessons_are_present():
    assert len(CORE_LESSONS) >= 5
    assert any("stage success" in lesson.lower() for lesson in CORE_LESSONS)
    assert any("provider" in lesson.lower() for lesson in CORE_LESSONS)


def test_failure_class_registry_captures_period_resolution_unsupported():
    validation = validate_failure_class_registry()

    assert validation["status"] == "pass"
    assert validation["failure_class_count"] == 5
    assert not validation["issues"]
    assert FAILURE_CLASS_REGISTRY[0]["failure_class"] == "PERIOD_RESOLUTION_UNSUPPORTED"
    assert "risks" in FAILURE_CLASS_REGISTRY[0]["affected_modules"]
    assert any(
        entry["failure_class"] == "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION"
        and entry["severity"] == "PRODUCTION BLOCKER"
        for entry in FAILURE_CLASS_REGISTRY
    )
