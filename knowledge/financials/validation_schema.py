from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


ALLOWED_VALIDATION_STATUS = {"pass", "warning", "fail"}
ALLOWED_BASIS_CHECKED = {"standalone", "consolidated", "mixed", "unknown"}
ALLOWED_CHECK_STATUS = {"pass", "warning", "fail"}


@dataclass
class ValidationCheck:
    check_name: str
    status: str
    details: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status,
            "details": self.details,
        }


@dataclass
class FinancialValidationReport:
    company: str
    year: str
    generated_at: str
    status: str
    basis_checked: str
    hard_failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checks: List[ValidationCheck] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    suspicious_values: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "status": self.status,
            "basis_checked": self.basis_checked,
            "hard_failures": list(self.hard_failures),
            "warnings": list(self.warnings),
            "checks": [check.to_dict() for check in self.checks],
            "missing_fields": list(self.missing_fields),
            "suspicious_values": list(self.suspicious_values),
            "limitations": list(self.limitations),
        }


def validate_financial_validation_report_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial validation report must be an object"]
    for key in ("company", "year", "generated_at"):
        if not payload.get(key):
            errors.append(f"{key} is required")
    if payload.get("status") not in ALLOWED_VALIDATION_STATUS:
        errors.append("status must be pass|warning|fail")
    if payload.get("basis_checked") not in ALLOWED_BASIS_CHECKED:
        errors.append("basis_checked must be standalone|consolidated|mixed|unknown")

    for list_key in ("hard_failures", "warnings", "missing_fields", "suspicious_values", "limitations"):
        if not isinstance(payload.get(list_key), list):
            errors.append(f"{list_key} must be a list")

    checks = payload.get("checks")
    if not isinstance(checks, list):
        errors.append("checks must be a list")
    else:
        for index, item in enumerate(checks):
            if not isinstance(item, dict):
                errors.append(f"checks[{index}] must be an object")
                continue
            if not item.get("check_name"):
                errors.append(f"checks[{index}].check_name is required")
            if item.get("status") not in ALLOWED_CHECK_STATUS:
                errors.append(f"checks[{index}].status must be pass|warning|fail")
            if not item.get("details"):
                errors.append(f"checks[{index}].details is required")

    return errors
