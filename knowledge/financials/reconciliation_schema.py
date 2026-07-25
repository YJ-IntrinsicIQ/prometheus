from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


ALLOWED_RECONCILIATION_STATUS = {"pass", "warning", "fail"}
ALLOWED_RECONCILIATION_CHECK_STATUS = {"pass", "warning", "fail"}


@dataclass
class ReconciliationFieldCheck:
    field_name: str
    status: str
    hard_failure: bool = False
    reason: str = ""
    source_line_item: str = ""
    source_section_type: str = ""
    statement_type: str = ""
    basis: str = "unknown"
    source_artifacts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "status": self.status,
            "hard_failure": self.hard_failure,
            "reason": self.reason,
            "source_line_item": self.source_line_item,
            "source_section_type": self.source_section_type,
            "statement_type": self.statement_type,
            "basis": self.basis,
            "source_artifacts": list(self.source_artifacts),
            "warnings": list(self.warnings),
        }


@dataclass
class FinancialReconciliationReport:
    company: str
    year: str
    generated_at: str
    status: str
    checks: Dict[str, ReconciliationFieldCheck] = field(default_factory=dict)
    hard_failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "status": self.status,
            "checks": {name: item.to_dict() for name, item in self.checks.items()},
            "hard_failures": list(self.hard_failures),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


def validate_financial_reconciliation_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial reconciliation report must be an object"]
    for key in ("company", "year", "generated_at", "status", "checks", "hard_failures", "warnings", "limitations"):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    status = payload.get("status")
    if status is not None and status not in ALLOWED_RECONCILIATION_STATUS:
        errors.append("status must be pass|warning|fail")
    checks = payload.get("checks")
    if checks is not None and not isinstance(checks, dict):
        errors.append("checks must be an object")
    elif isinstance(checks, dict):
        for field_name, item in checks.items():
            if not isinstance(item, dict):
                errors.append(f"checks.{field_name} must be an object")
                continue
            for required in (
                "field_name",
                "status",
                "hard_failure",
                "reason",
                "source_line_item",
                "source_section_type",
                "statement_type",
                "basis",
                "source_artifacts",
                "warnings",
            ):
                if required not in item:
                    errors.append(f"checks.{field_name} missing required field: {required}")
            if item.get("field_name") != field_name:
                errors.append(f"checks.{field_name}.field_name must equal {field_name}")
            if item.get("status") not in ALLOWED_RECONCILIATION_CHECK_STATUS:
                errors.append(f"checks.{field_name}.status must be pass|warning|fail")
            if not isinstance(item.get("hard_failure"), bool):
                errors.append(f"checks.{field_name}.hard_failure must be boolean")
            if not isinstance(item.get("source_artifacts"), list):
                errors.append(f"checks.{field_name}.source_artifacts must be a list")
            if not isinstance(item.get("warnings"), list):
                errors.append(f"checks.{field_name}.warnings must be a list")
    for field in ("hard_failures", "warnings", "limitations"):
        if field in payload and not isinstance(payload.get(field), list):
            errors.append(f"{field} must be a list")
    return errors
