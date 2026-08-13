from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


ALLOWED_FACT_BASIS = {"standalone", "consolidated", "unknown", "not_applicable"}
ALLOWED_FACT_CONFIDENCE = {"high", "medium", "low", "missing", "invalid", "unreliable"}
ALLOWED_AVAILABILITY_STATUS = {
    "present_direct",
    "present_derived",
    "partial",
    "missing",
    "invalid",
    "unreliable",
    "not_applicable",
}
ALLOWED_RECONCILIATION_STATUS = {"pass", "warning", "fail", "unknown", "not_applicable"}
ALLOWED_FINANCIAL_TRUTH_STATUS = {"pass", "warning", "partial", "invalid"}
ALLOWED_ARTIFACT_QUARANTINE_STATUS = {
    "usable",
    "usable_with_warnings",
    "partial",
    "quarantined",
    "invalid",
    "missing",
}


@dataclass
class FinancialFact:
    metric_id: str
    metric_name: str
    fiscal_year: str
    period: str
    value: float | None
    unit: str
    basis: str
    source_statement: str
    source_artifact: str
    source_line_item: str
    source_page: int | None
    confidence: str
    availability_status: str
    derived: bool = False
    formula: str = ""
    inputs_used: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reconciliation_status: str = "unknown"
    usable_downstream: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "metric_name": self.metric_name,
            "fiscal_year": self.fiscal_year,
            "period": self.period,
            "value": self.value,
            "unit": self.unit,
            "basis": self.basis,
            "source_statement": self.source_statement,
            "source_artifact": self.source_artifact,
            "source_line_item": self.source_line_item,
            "source_page": self.source_page,
            "confidence": self.confidence,
            "availability_status": self.availability_status,
            "derived": self.derived,
            "formula": self.formula,
            "inputs_used": list(self.inputs_used),
            "warnings": list(self.warnings),
            "reconciliation_status": self.reconciliation_status,
            "usable_downstream": self.usable_downstream,
            "notes": list(self.notes),
        }


@dataclass
class FinancialTruthReconciliationReport:
    company: str
    year: str
    generated_at: str
    contradictions_found: List[str] = field(default_factory=list)
    resolved_contradictions: List[str] = field(default_factory=list)
    unresolved_contradictions: List[str] = field(default_factory=list)
    false_missing_warnings: List[str] = field(default_factory=list)
    unreliable_metrics: List[str] = field(default_factory=list)
    invalid_metrics: List[str] = field(default_factory=list)
    usable_metrics: List[str] = field(default_factory=list)
    downstream_blockers: List[str] = field(default_factory=list)
    warning_normalizations: List[Dict[str, Any]] = field(default_factory=list)
    invalid_artifact_findings: List[Dict[str, Any]] = field(default_factory=list)
    quarantined_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    resolved_false_warnings: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "contradictions_found": list(self.contradictions_found),
            "resolved_contradictions": list(self.resolved_contradictions),
            "unresolved_contradictions": list(self.unresolved_contradictions),
            "false_missing_warnings": list(self.false_missing_warnings),
            "unreliable_metrics": list(self.unreliable_metrics),
            "invalid_metrics": list(self.invalid_metrics),
            "usable_metrics": list(self.usable_metrics),
            "downstream_blockers": list(self.downstream_blockers),
            "warning_normalizations": list(self.warning_normalizations),
            "invalid_artifact_findings": list(self.invalid_artifact_findings),
            "quarantined_artifacts": list(self.quarantined_artifacts),
            "resolved_false_warnings": list(self.resolved_false_warnings),
            "warnings": list(self.warnings),
        }


@dataclass
class FinancialFactRegistry:
    company: str
    year: str
    generated_at: str
    source_artifacts_read: List[str] = field(default_factory=list)
    registry_warnings: List[str] = field(default_factory=list)
    available_facts: List[FinancialFact] = field(default_factory=list)
    derived_facts: List[FinancialFact] = field(default_factory=list)
    partial_facts: List[FinancialFact] = field(default_factory=list)
    missing_facts: List[FinancialFact] = field(default_factory=list)
    precise_missing_facts: List[FinancialFact] = field(default_factory=list)
    unreliable_facts: List[FinancialFact] = field(default_factory=list)
    invalid_facts: List[FinancialFact] = field(default_factory=list)
    quarantined_facts: List[FinancialFact] = field(default_factory=list)
    contradiction_summary: Dict[str, Any] = field(default_factory=dict)
    downstream_readiness: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "source_artifacts_read": list(self.source_artifacts_read),
            "registry_warnings": list(self.registry_warnings),
            "available_facts": [fact.to_dict() for fact in self.available_facts],
            "derived_facts": [fact.to_dict() for fact in self.derived_facts],
            "partial_facts": [fact.to_dict() for fact in self.partial_facts],
            "missing_facts": [fact.to_dict() for fact in self.missing_facts],
            "precise_missing_facts": [fact.to_dict() for fact in self.precise_missing_facts],
            "unreliable_facts": [fact.to_dict() for fact in self.unreliable_facts],
            "invalid_facts": [fact.to_dict() for fact in self.invalid_facts],
            "quarantined_facts": [fact.to_dict() for fact in self.quarantined_facts],
            "contradiction_summary": dict(self.contradiction_summary),
            "downstream_readiness": dict(self.downstream_readiness),
        }


@dataclass
class FinancialArtifactQuarantineReport:
    company: str
    fiscal_year: str
    generated_at: str
    artifact_status_by_file: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    quarantined_facts: List[Dict[str, Any]] = field(default_factory=list)
    quarantined_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    usable_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    invalid_reason: List[str] = field(default_factory=list)
    affected_metrics: List[str] = field(default_factory=list)
    downstream_blockers: List[str] = field(default_factory=list)
    recommended_reparse_targets: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "fiscal_year": self.fiscal_year,
            "generated_at": self.generated_at,
            "artifact_status_by_file": dict(self.artifact_status_by_file),
            "quarantined_facts": list(self.quarantined_facts),
            "quarantined_artifacts": list(self.quarantined_artifacts),
            "usable_artifacts": list(self.usable_artifacts),
            "invalid_reason": list(self.invalid_reason),
            "affected_metrics": list(self.affected_metrics),
            "downstream_blockers": list(self.downstream_blockers),
            "recommended_reparse_targets": list(self.recommended_reparse_targets),
            "warnings": list(self.warnings),
        }


def _validate_fact_payload(prefix: str, payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    required = (
        "metric_id",
        "metric_name",
        "fiscal_year",
        "period",
        "value",
        "unit",
        "basis",
        "source_statement",
        "source_artifact",
        "source_line_item",
        "source_page",
        "confidence",
        "availability_status",
        "derived",
        "formula",
        "inputs_used",
        "warnings",
        "reconciliation_status",
        "usable_downstream",
        "notes",
    )
    for field in required:
        if field not in payload:
            errors.append(f"{prefix} missing required field: {field}")
    if payload.get("basis") not in ALLOWED_FACT_BASIS:
        errors.append(f"{prefix}.basis must be one of {sorted(ALLOWED_FACT_BASIS)}")
    if payload.get("confidence") not in ALLOWED_FACT_CONFIDENCE:
        errors.append(f"{prefix}.confidence must be one of {sorted(ALLOWED_FACT_CONFIDENCE)}")
    if payload.get("availability_status") not in ALLOWED_AVAILABILITY_STATUS:
        errors.append(f"{prefix}.availability_status must be one of {sorted(ALLOWED_AVAILABILITY_STATUS)}")
    if payload.get("reconciliation_status") not in ALLOWED_RECONCILIATION_STATUS:
        errors.append(f"{prefix}.reconciliation_status must be one of {sorted(ALLOWED_RECONCILIATION_STATUS)}")
    if not isinstance(payload.get("derived"), bool):
        errors.append(f"{prefix}.derived must be boolean")
    if not isinstance(payload.get("usable_downstream"), bool):
        errors.append(f"{prefix}.usable_downstream must be boolean")
    if not isinstance(payload.get("inputs_used"), list):
        errors.append(f"{prefix}.inputs_used must be a list")
    if not isinstance(payload.get("warnings"), list):
        errors.append(f"{prefix}.warnings must be a list")
    if not isinstance(payload.get("notes"), list):
        errors.append(f"{prefix}.notes must be a list")
    return errors


def validate_financial_truth_reconciliation_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    required = (
        "company",
        "year",
        "generated_at",
        "contradictions_found",
        "resolved_contradictions",
        "unresolved_contradictions",
        "false_missing_warnings",
        "unreliable_metrics",
        "invalid_metrics",
        "usable_metrics",
        "downstream_blockers",
        "warning_normalizations",
        "invalid_artifact_findings",
        "quarantined_artifacts",
        "resolved_false_warnings",
        "warnings",
    )
    for field in required:
        if field not in payload:
            errors.append(f"missing required top-level field: {field}")
        elif field not in {"company", "year", "generated_at"} and not isinstance(payload.get(field), list):
            errors.append(f"{field} must be a list")
    return errors


def validate_financial_fact_registry_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial fact registry must be an object"]
    for field in (
        "company",
        "year",
        "generated_at",
        "source_artifacts_read",
        "registry_warnings",
        "available_facts",
        "derived_facts",
        "partial_facts",
        "missing_facts",
        "precise_missing_facts",
        "unreliable_facts",
        "invalid_facts",
        "quarantined_facts",
        "contradiction_summary",
        "downstream_readiness",
    ):
        if field not in payload:
            errors.append(f"missing required top-level field: {field}")
    for field in ("source_artifacts_read", "registry_warnings"):
        if field in payload and not isinstance(payload.get(field), list):
            errors.append(f"{field} must be a list")
    for field in ("available_facts", "derived_facts", "partial_facts", "missing_facts", "precise_missing_facts", "unreliable_facts", "invalid_facts", "quarantined_facts"):
        items = payload.get(field)
        if not isinstance(items, list):
            errors.append(f"{field} must be a list")
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{field}[{index}] must be an object")
                continue
            errors.extend(_validate_fact_payload(f"{field}[{index}]", item))
    contradiction_summary = payload.get("contradiction_summary")
    if contradiction_summary is not None and not isinstance(contradiction_summary, dict):
        errors.append("contradiction_summary must be an object")
    downstream_readiness = payload.get("downstream_readiness")
    if downstream_readiness is not None:
        if not isinstance(downstream_readiness, dict):
            errors.append("downstream_readiness must be an object")
        else:
            if downstream_readiness.get("financial_truth_status") not in ALLOWED_FINANCIAL_TRUTH_STATUS:
                errors.append("downstream_readiness.financial_truth_status must be pass|warning|partial|invalid")
            for list_field in ("usable_metrics", "unreliable_metrics", "invalid_metrics", "quarantined_metrics", "missing_metrics", "downstream_blockers", "warnings"):
                if list_field in downstream_readiness and not isinstance(downstream_readiness.get(list_field), list):
                    errors.append(f"downstream_readiness.{list_field} must be a list")
    return errors


def validate_financial_artifact_quarantine_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial artifact quarantine report must be an object"]
    required = (
        "company",
        "fiscal_year",
        "generated_at",
        "artifact_status_by_file",
        "quarantined_facts",
        "quarantined_artifacts",
        "usable_artifacts",
        "invalid_reason",
        "affected_metrics",
        "downstream_blockers",
        "recommended_reparse_targets",
        "warnings",
    )
    for field in required:
        if field not in payload:
            errors.append(f"missing required top-level field: {field}")
    if "artifact_status_by_file" in payload and not isinstance(payload.get("artifact_status_by_file"), dict):
        errors.append("artifact_status_by_file must be an object")
    for field in (
        "quarantined_facts",
        "quarantined_artifacts",
        "usable_artifacts",
        "invalid_reason",
        "affected_metrics",
        "downstream_blockers",
        "recommended_reparse_targets",
        "warnings",
    ):
        if field in payload and not isinstance(payload.get(field), list):
            errors.append(f"{field} must be a list")
    statuses = payload.get("artifact_status_by_file") or {}
    if isinstance(statuses, dict):
        for artifact_name, item in statuses.items():
            if not isinstance(item, dict):
                errors.append(f"artifact_status_by_file.{artifact_name} must be an object")
                continue
            status = item.get("status")
            if status not in ALLOWED_ARTIFACT_QUARANTINE_STATUS:
                errors.append(
                    f"artifact_status_by_file.{artifact_name}.status must be one of {sorted(ALLOWED_ARTIFACT_QUARANTINE_STATUS)}"
                )
            if "usable_downstream" in item and not isinstance(item.get("usable_downstream"), bool):
                errors.append(f"artifact_status_by_file.{artifact_name}.usable_downstream must be boolean")
    return errors
