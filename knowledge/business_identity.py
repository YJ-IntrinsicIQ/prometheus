from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional

from knowledge.business_blueprint import BusinessBlueprint, BusinessDNA
from knowledge.business_classifier import Registry
from knowledge.question_engine import QuestionRegistry


LOW_CONFIDENCE_WARNING_THRESHOLD = 0.45


def _coerce_blueprint(blueprint: BusinessBlueprint | Dict[str, Any] | None) -> Optional[BusinessBlueprint]:
    if blueprint is None:
        return None
    if isinstance(blueprint, BusinessBlueprint):
        return blueprint
    if isinstance(blueprint, dict):
        return BusinessBlueprint.from_dict(blueprint)
    raise TypeError("blueprint must be a BusinessBlueprint, dict, or None")


def _blueprint_dna_names(blueprint: Optional[BusinessBlueprint]) -> List[str]:
    if blueprint is None:
        return []
    return [item.name for item in blueprint.dnas if item.name]


def align_blueprint_with_classification(
    blueprint: BusinessBlueprint,
    classification: Dict[str, Any],
) -> BusinessBlueprint:
    official_dnas = [
        str(dna).strip()
        for dna in classification.get("business_dnas", [])
        if str(dna).strip()
    ]
    confidence = classification.get("confidence")
    try:
        dna_confidence = float(confidence) if confidence is not None else blueprint.metadata.confidence
    except (TypeError, ValueError):
        dna_confidence = blueprint.metadata.confidence

    return replace(
        blueprint,
        dnas=[
            BusinessDNA(name=dna, confidence=dna_confidence)
            for dna in official_dnas
        ],
        dnas_source="business_classification",
    )


def build_business_identity_manifest(
    blueprint: BusinessBlueprint | Dict[str, Any] | None,
    classification: Dict[str, Any] | None,
    *,
    blueprint_source: str = "business_blueprint.json",
    official_source: str = "business_classification.json",
    require_classification: bool = True,
) -> Dict[str, Any]:
    blueprint_obj = _coerce_blueprint(blueprint)
    classification = classification if isinstance(classification, dict) else {}
    warnings: List[str] = []
    failures: List[str] = []

    business_dnas = classification.get("business_dnas", [])
    if require_classification and not classification:
        failures.append("business_classification.json is required for official Business DNA.")
        business_dnas = []

    if business_dnas and not isinstance(business_dnas, list):
        failures.append("business_classification.business_dnas must be a list.")
        business_dnas = []

    official_dnas = [
        str(dna).strip()
        for dna in business_dnas
        if str(dna).strip()
    ]
    allowed_dnas = set(Registry().allowed_dnas())
    invalid_dnas = [dna for dna in official_dnas if dna not in allowed_dnas]
    if invalid_dnas:
        failures.append(f"Selected Business DNAs are not allowed by the registry: {invalid_dnas}")

    rationale = classification.get("rationale", [])
    evidence_used = classification.get("evidence_used", [])
    rejected_dnas = classification.get("rejected_dnas", [])
    if official_dnas and not rationale:
        failures.append("Selected Business DNAs require non-empty classification.rationale.")
    if official_dnas and not evidence_used:
        failures.append("Selected Business DNAs require non-empty classification.evidence_used.")

    registry = QuestionRegistry()
    expected_modules = [module.module_id for module in registry.modules_for_dnas(official_dnas)]
    actual_modules = classification.get("question_modules", [])
    if actual_modules and not isinstance(actual_modules, list):
        failures.append("business_classification.question_modules must be a list.")
        actual_modules = []
    if official_dnas and expected_modules and not actual_modules:
        failures.append("question_modules is missing for selected Business DNAs with known module mappings.")
    if official_dnas and not expected_modules:
        warnings.append("Selected Business DNAs have no question-module mapping in the registry.")

    blueprint_dnas = _blueprint_dna_names(blueprint_obj)
    blueprint_dnas_source = getattr(blueprint_obj, "dnas_source", None) if blueprint_obj is not None else None
    if blueprint_dnas:
        if blueprint_dnas_source != "business_classification" and blueprint_dnas != official_dnas:
            failures.append(
                "business_blueprint.dnas conflicts with business_classification.business_dnas."
            )
        elif blueprint_dnas_source == "business_classification" and blueprint_dnas != official_dnas:
            failures.append(
                "Mirrored business_blueprint.dnas does not match official business_classification.business_dnas."
            )

    candidate_signals: List[Dict[str, Any]] = []
    if blueprint_obj is not None:
        candidate_signals = [
            signal.to_dict()
            for signal in blueprint_obj.candidate_dna_signals
            if signal.name
        ]
    if not candidate_signals and classification:
        warnings.append("business_blueprint has no candidate_dna_signals.")

    confidence = classification.get("confidence")
    try:
        confidence_value = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_value = None
    if confidence_value is not None and confidence_value < LOW_CONFIDENCE_WARNING_THRESHOLD and evidence_used:
        warnings.append("Classification confidence is low relative to the evidence supplied.")

    if not official_dnas and rejected_dnas and rationale:
        warnings.append("No official Business DNAs were selected; classification explains rejection explicitly.")

    status = "pass"
    if failures:
        status = "fail"
    elif warnings:
        status = "warning"

    return {
        "official_dna_source": official_source,
        "blueprint_source": blueprint_source,
        "official_business_dnas": official_dnas,
        "blueprint_candidate_dna_signals": candidate_signals,
        "classification_confidence": confidence_value,
        "conflict_status": status,
        "warnings": warnings,
        "failures": failures,
    }


def ensure_business_identity_contract(
    blueprint: BusinessBlueprint | Dict[str, Any] | None,
    classification: Dict[str, Any] | None,
    *,
    blueprint_source: str = "business_blueprint.json",
    official_source: str = "business_classification.json",
    require_classification: bool = True,
) -> Dict[str, Any]:
    manifest = build_business_identity_manifest(
        blueprint,
        classification,
        blueprint_source=blueprint_source,
        official_source=official_source,
        require_classification=require_classification,
    )
    if manifest["failures"]:
        raise ValueError("; ".join(manifest["failures"]))
    return manifest
