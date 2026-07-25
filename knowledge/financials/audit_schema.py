from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


ALLOWED_AUDIT_STATUS = {"pass", "warning", "fail"}
ALLOWED_AUDIT_SCOPE = {"year", "company_memory"}
ALLOWED_AUDIT_CHECK_STATUS = {"pass", "warning", "fail"}


@dataclass
class FinancialAuditCheck:
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
class FinancialAuditReport:
    company: str
    scope: str
    generated_at: str
    status: str
    year: Optional[str] = None
    hard_failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checks: List[FinancialAuditCheck] = field(default_factory=list)
    required_artifacts: List[str] = field(default_factory=list)
    present_artifacts: List[str] = field(default_factory=list)
    missing_artifacts: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "scope": self.scope,
            "generated_at": self.generated_at,
            "status": self.status,
            "hard_failures": list(self.hard_failures),
            "warnings": list(self.warnings),
            "checks": [check.to_dict() for check in self.checks],
            "required_artifacts": list(self.required_artifacts),
            "present_artifacts": list(self.present_artifacts),
            "missing_artifacts": list(self.missing_artifacts),
            "limitations": list(self.limitations),
        }


def validate_financial_audit_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial audit report must be an object"]

    for key in (
        "company",
        "scope",
        "generated_at",
        "status",
        "hard_failures",
        "warnings",
        "checks",
        "required_artifacts",
        "present_artifacts",
        "missing_artifacts",
        "limitations",
    ):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")

    if payload.get("scope") is not None and payload.get("scope") not in ALLOWED_AUDIT_SCOPE:
        errors.append(f"invalid scope: {payload.get('scope')}")
    if payload.get("status") is not None and payload.get("status") not in ALLOWED_AUDIT_STATUS:
        errors.append(f"invalid status: {payload.get('status')}")

    for list_key in (
        "hard_failures",
        "warnings",
        "required_artifacts",
        "present_artifacts",
        "missing_artifacts",
        "limitations",
    ):
        if list_key in payload and not isinstance(payload.get(list_key), list):
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
            if item.get("status") not in ALLOWED_AUDIT_CHECK_STATUS:
                errors.append(f"checks[{index}].status must be pass|warning|fail")
            if not item.get("details"):
                errors.append(f"checks[{index}].details is required")

    return errors
