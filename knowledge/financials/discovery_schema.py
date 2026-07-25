from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


FINANCIAL_DISCOVERY_SECTIONS = (
    "primary_profit_and_loss_statement",
    "primary_balance_sheet_statement",
    "primary_cash_flow_statement",
    "statement_of_changes_in_equity",
    "financial_note",
    "accounting_policy",
    "auditor_report",
    "management_discussion_financial_summary",
    "share_capital_note",
    "eps_note",
    "dividend_note",
    "shareholding_note",
    "corporate_action_note",
    "irrelevant_financial_text",
)

ALLOWED_DISCOVERY_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_DISCOVERY_BASIS = {"standalone", "consolidated", "unknown"}


@dataclass
class DiscoveredSectionItem:
    section_type: str
    source_artifact: str
    page: Optional[int]
    chunk_id: str
    text_excerpt: str
    confidence: str
    reasoning: str
    basis: str = "unknown"
    basis_confidence: str = "low"
    signals: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_type": self.section_type,
            "source_artifact": self.source_artifact,
            "page": self.page,
            "chunk_id": self.chunk_id,
            "text_excerpt": self.text_excerpt,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "basis": self.basis,
            "basis_confidence": self.basis_confidence,
            "signals": list(self.signals),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DiscoveredSectionItem":
        return cls(
            section_type=payload.get("section_type", ""),
            source_artifact=payload.get("source_artifact", ""),
            page=payload.get("page"),
            chunk_id=payload.get("chunk_id", ""),
            text_excerpt=payload.get("text_excerpt", ""),
            confidence=payload.get("confidence", "low"),
            reasoning=payload.get("reasoning", ""),
            basis=payload.get("basis", "unknown"),
            basis_confidence=payload.get("basis_confidence", "low"),
            signals=[str(item) for item in payload.get("signals", [])],
        )


@dataclass
class FinancialDiscoveryResult:
    company: str
    year: str
    generated_at: str
    source_documents: List[str] = field(default_factory=list)
    sections: Dict[str, List[DiscoveredSectionItem]] = field(
        default_factory=lambda: {name: [] for name in FINANCIAL_DISCOVERY_SECTIONS}
    )
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "source_documents": list(self.source_documents),
            "sections": {
                key: [item.to_dict() for item in self.sections.get(key, [])]
                for key in FINANCIAL_DISCOVERY_SECTIONS
            },
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FinancialDiscoveryResult":
        raw_sections = payload.get("sections", {})
        sections = {
            key: [DiscoveredSectionItem.from_dict(item) for item in raw_sections.get(key, [])]
            for key in FINANCIAL_DISCOVERY_SECTIONS
        }
        return cls(
            company=payload.get("company", ""),
            year=payload.get("year", ""),
            generated_at=payload.get("generated_at", ""),
            source_documents=[str(item) for item in payload.get("source_documents", [])],
            sections=sections,
            warnings=[str(item) for item in payload.get("warnings", [])],
            limitations=[str(item) for item in payload.get("limitations", [])],
        )


def validate_financial_discovery_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial discovery payload must be an object"]
    if not payload.get("company"):
        errors.append("company is required")
    if not payload.get("year"):
        errors.append("year is required")
    if not payload.get("generated_at"):
        errors.append("generated_at is required")

    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, dict):
        errors.append("sections must be an object")
        return errors

    for section_name in FINANCIAL_DISCOVERY_SECTIONS:
        items = raw_sections.get(section_name)
        if not isinstance(items, list):
            errors.append(f"sections.{section_name} must be a list")
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"sections.{section_name}[{index}] must be an object")
                continue
            if item.get("confidence") not in ALLOWED_DISCOVERY_CONFIDENCE:
                errors.append(f"sections.{section_name}[{index}].confidence must be high|medium|low")
            if item.get("basis") not in ALLOWED_DISCOVERY_BASIS:
                errors.append(f"sections.{section_name}[{index}].basis must be standalone|consolidated|unknown")
            if item.get("basis_confidence") not in ALLOWED_DISCOVERY_CONFIDENCE:
                errors.append(f"sections.{section_name}[{index}].basis_confidence must be high|medium|low")
            for key in ("section_type", "source_artifact", "chunk_id", "text_excerpt", "reasoning"):
                if not item.get(key):
                    errors.append(f"sections.{section_name}[{index}].{key} is required")

    if not any(raw_sections.get(section_name) for section_name in FINANCIAL_DISCOVERY_SECTIONS):
        errors.append("at least one financial section must be discovered")

    return errors
