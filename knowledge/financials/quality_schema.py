from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


ALLOWED_QUALITY_STATUS = {"pass", "warning", "fail"}
ALLOWED_OVERALL_FINANCIAL_QUALITY = {
    "strong",
    "adequate",
    "mixed",
    "weak",
    "insufficient_data",
}
ALLOWED_SECTION_QUALITY = {"strong", "adequate", "mixed", "weak", "insufficient_data"}
ALLOWED_SECTION_CONFIDENCE = {"high", "medium", "low", "missing"}


@dataclass
class QualitySection:
    status: str
    summary: str
    signals: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "signals": list(self.signals),
            "warnings": list(self.warnings),
            "metrics": dict(self.metrics),
        }


@dataclass
class FinancialQualitySummary:
    company: str
    generated_at: str
    years_covered: List[str]
    status: str
    overall_financial_quality: str
    growth_quality: QualitySection
    margin_quality: QualitySection
    return_on_capital_quality: QualitySection
    cash_conversion_quality: QualitySection
    balance_sheet_strength: QualitySection
    working_capital_quality: QualitySection
    dilution_and_corporate_action_quality: QualitySection
    ownership_quality: QualitySection
    red_flags: List[str] = field(default_factory=list)
    positive_signals: List[str] = field(default_factory=list)
    missing_data: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "generated_at": self.generated_at,
            "years_covered": list(self.years_covered),
            "status": self.status,
            "overall_financial_quality": self.overall_financial_quality,
            "growth_quality": self.growth_quality.to_dict(),
            "margin_quality": self.margin_quality.to_dict(),
            "return_on_capital_quality": self.return_on_capital_quality.to_dict(),
            "cash_conversion_quality": self.cash_conversion_quality.to_dict(),
            "balance_sheet_strength": self.balance_sheet_strength.to_dict(),
            "working_capital_quality": self.working_capital_quality.to_dict(),
            "dilution_and_corporate_action_quality": self.dilution_and_corporate_action_quality.to_dict(),
            "ownership_quality": self.ownership_quality.to_dict(),
            "red_flags": list(self.red_flags),
            "positive_signals": list(self.positive_signals),
            "missing_data": list(self.missing_data),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


@dataclass
class DeterministicFinancialQualitySection:
    assessment: str
    confidence: str
    evidence_metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "assessment": self.assessment,
            "confidence": self.confidence,
            "evidence_metrics": dict(self.evidence_metrics),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }
        if self.highlights:
            payload["highlights"] = list(self.highlights)
        if self.summary:
            payload["summary"] = self.summary
        return payload


@dataclass
class YearFinancialQualitySummary:
    company: str
    year: str
    generated_at: str
    status: str
    basis_used: str
    sections: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    source_artifacts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        rendered_sections: Dict[str, Any] = {}
        for key, value in self.sections.items():
            if isinstance(value, DeterministicFinancialQualitySection):
                rendered_sections[key] = value.to_dict()
            else:
                rendered_sections[key] = value
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "status": self.status,
            "basis_used": self.basis_used,
            "sections": rendered_sections,
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "source_artifacts": list(self.source_artifacts),
        }


def _validate_legacy_financial_quality_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial quality summary payload must be an object"]

    for key in (
        "company",
        "generated_at",
        "years_covered",
        "status",
        "overall_financial_quality",
        "growth_quality",
        "margin_quality",
        "return_on_capital_quality",
        "cash_conversion_quality",
        "balance_sheet_strength",
        "working_capital_quality",
        "dilution_and_corporate_action_quality",
        "ownership_quality",
        "red_flags",
        "positive_signals",
        "missing_data",
        "warnings",
        "limitations",
    ):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")

    if payload.get("status") is not None and payload.get("status") not in ALLOWED_QUALITY_STATUS:
        errors.append(f"invalid status: {payload.get('status')}")
    if (
        payload.get("overall_financial_quality") is not None
        and payload.get("overall_financial_quality") not in ALLOWED_OVERALL_FINANCIAL_QUALITY
    ):
        errors.append(
            f"invalid overall_financial_quality: {payload.get('overall_financial_quality')}"
        )

    for list_key in ("years_covered", "red_flags", "positive_signals", "missing_data", "warnings", "limitations"):
        if list_key in payload and not isinstance(payload.get(list_key), list):
            errors.append(f"{list_key} must be a list")

    for section_name in (
        "growth_quality",
        "margin_quality",
        "return_on_capital_quality",
        "cash_conversion_quality",
        "balance_sheet_strength",
        "working_capital_quality",
        "dilution_and_corporate_action_quality",
        "ownership_quality",
    ):
        section = payload.get(section_name)
        if not isinstance(section, dict):
            errors.append(f"{section_name} must be an object")
            continue
        for key in ("status", "summary", "signals", "warnings", "metrics"):
            if key not in section:
                errors.append(f"{section_name} missing required field: {key}")
        if section.get("status") not in ALLOWED_SECTION_QUALITY:
            errors.append(f"{section_name}.status invalid: {section.get('status')}")
        if "signals" in section and not isinstance(section.get("signals"), list):
            errors.append(f"{section_name}.signals must be a list")
        if "warnings" in section and not isinstance(section.get("warnings"), list):
            errors.append(f"{section_name}.warnings must be a list")
        if "metrics" in section and not isinstance(section.get("metrics"), dict):
            errors.append(f"{section_name}.metrics must be an object")

    return errors


def _validate_year_financial_quality_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["year financial quality summary payload must be an object"]

    for key in (
        "company",
        "year",
        "generated_at",
        "status",
        "basis_used",
        "sections",
        "warnings",
        "limitations",
        "source_artifacts",
    ):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")

    if payload.get("status") is not None and payload.get("status") not in ALLOWED_QUALITY_STATUS:
        errors.append(f"invalid status: {payload.get('status')}")
    if "sections" in payload and not isinstance(payload.get("sections"), dict):
        errors.append("sections must be an object")

    for field in ("warnings", "limitations", "source_artifacts"):
        if field in payload and not isinstance(payload.get(field), list):
            errors.append(f"{field} must be a list")

    sections = payload.get("sections") if isinstance(payload.get("sections"), dict) else {}
    required_sections = (
        "growth_quality",
        "margin_quality",
        "return_on_capital_quality",
        "cash_conversion_quality",
        "balance_sheet_strength",
        "working_capital_pressure",
        "capital_allocation_signals",
        "per_share_quality",
        "ownership_signal_quality",
        "dividend_quality",
        "red_flags",
        "missing_data",
        "investor_questions",
    )
    for section_name in required_sections:
        if section_name not in sections:
            errors.append(f"sections missing required field: {section_name}")

    for section_name in (
        "growth_quality",
        "margin_quality",
        "return_on_capital_quality",
        "cash_conversion_quality",
        "balance_sheet_strength",
        "working_capital_pressure",
        "capital_allocation_signals",
        "per_share_quality",
        "ownership_signal_quality",
        "dividend_quality",
    ):
        section = sections.get(section_name)
        if not isinstance(section, dict):
            errors.append(f"sections.{section_name} must be an object")
            continue
        for key in ("assessment", "confidence", "evidence_metrics", "warnings", "limitations"):
            if key not in section:
                errors.append(f"sections.{section_name} missing required field: {key}")
        confidence = section.get("confidence")
        if confidence is not None and confidence not in ALLOWED_SECTION_CONFIDENCE:
            errors.append(f"sections.{section_name}.confidence invalid: {confidence}")
        if "evidence_metrics" in section and not isinstance(section.get("evidence_metrics"), dict):
            errors.append(f"sections.{section_name}.evidence_metrics must be an object")
        if "warnings" in section and not isinstance(section.get("warnings"), list):
            errors.append(f"sections.{section_name}.warnings must be a list")
        if "limitations" in section and not isinstance(section.get("limitations"), list):
            errors.append(f"sections.{section_name}.limitations must be a list")
        if "highlights" in section and not isinstance(section.get("highlights"), list):
            errors.append(f"sections.{section_name}.highlights must be a list")

    for section_name in ("red_flags", "missing_data", "investor_questions"):
        if section_name in sections and not isinstance(sections.get(section_name), list):
            errors.append(f"sections.{section_name} must be a list")

    return errors


def validate_financial_quality_payload(payload: Dict[str, Any]) -> List[str]:
    if isinstance(payload, dict) and "sections" in payload and "year" in payload:
        return _validate_year_financial_quality_payload(payload)
    return _validate_legacy_financial_quality_payload(payload)
