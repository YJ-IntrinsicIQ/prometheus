from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


ALLOWED_RESOLVED_BASIS = {"standalone", "consolidated", "unknown", "not_applicable"}
ALLOWED_BASIS_RESOLUTION_CONFIDENCE = {"high", "medium", "low"}


@dataclass
class BasisEvidence:
    category: str
    basis: str
    confidence: str
    score: int
    text: str = ""
    source_artifact: str = ""
    page: int | None = None
    chunk_id: str = ""
    proximity: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "basis": self.basis,
            "confidence": self.confidence,
            "score": self.score,
            "text": self.text,
            "source_artifact": self.source_artifact,
            "page": self.page,
            "chunk_id": self.chunk_id,
            "proximity": self.proximity,
        }


@dataclass
class FieldBasisResolution:
    field_path: str
    metric_id: str
    source_line_item: str
    source_page: int | None
    current_basis: str
    resolved_basis: str
    confidence: str
    applied_to_normalized: bool = False
    applied_to_fact_registry: bool = False
    evidence_used: List[Dict[str, Any]] = field(default_factory=list)
    evidence_rejected: List[Dict[str, Any]] = field(default_factory=list)
    basis_conflicts: List[str] = field(default_factory=list)
    reasoning: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_path": self.field_path,
            "metric_id": self.metric_id,
            "source_line_item": self.source_line_item,
            "source_page": self.source_page,
            "current_basis": self.current_basis,
            "resolved_basis": self.resolved_basis,
            "confidence": self.confidence,
            "applied_to_normalized": self.applied_to_normalized,
            "applied_to_fact_registry": self.applied_to_fact_registry,
            "evidence_used": list(self.evidence_used),
            "evidence_rejected": list(self.evidence_rejected),
            "basis_conflicts": list(self.basis_conflicts),
            "reasoning": self.reasoning,
            "warnings": list(self.warnings),
        }


@dataclass
class FinancialBasisResolutionReport:
    company: str
    year: str
    generated_at: str
    resolved_basis: str
    confidence: str
    evidence_used: List[Dict[str, Any]] = field(default_factory=list)
    evidence_rejected: List[Dict[str, Any]] = field(default_factory=list)
    basis_conflicts: List[str] = field(default_factory=list)
    reasoning: str = ""
    source_pages: List[int] = field(default_factory=list)
    source_chunks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    document_basis_summary: Dict[str, Any] = field(default_factory=dict)
    field_resolutions: List[FieldBasisResolution] = field(default_factory=list)
    warning_resolutions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "resolved_basis": self.resolved_basis,
            "confidence": self.confidence,
            "evidence_used": list(self.evidence_used),
            "evidence_rejected": list(self.evidence_rejected),
            "basis_conflicts": list(self.basis_conflicts),
            "reasoning": self.reasoning,
            "source_pages": list(self.source_pages),
            "source_chunks": list(self.source_chunks),
            "warnings": list(self.warnings),
            "document_basis_summary": dict(self.document_basis_summary),
            "field_resolutions": [item.to_dict() for item in self.field_resolutions],
            "warning_resolutions": list(self.warning_resolutions),
        }


def validate_financial_basis_resolution_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial basis resolution must be an object"]
    required = (
        "company",
        "year",
        "generated_at",
        "resolved_basis",
        "confidence",
        "evidence_used",
        "evidence_rejected",
        "basis_conflicts",
        "reasoning",
        "source_pages",
        "source_chunks",
        "warnings",
        "document_basis_summary",
        "field_resolutions",
        "warning_resolutions",
    )
    for field in required:
        if field not in payload:
            errors.append(f"missing required top-level field: {field}")
    if payload.get("resolved_basis") not in ALLOWED_RESOLVED_BASIS:
        errors.append("resolved_basis must be standalone|consolidated|unknown|not_applicable")
    if payload.get("confidence") not in ALLOWED_BASIS_RESOLUTION_CONFIDENCE:
        errors.append("confidence must be high|medium|low")
    for field in ("evidence_used", "evidence_rejected", "basis_conflicts", "source_pages", "source_chunks", "warnings", "field_resolutions", "warning_resolutions"):
        if field in payload and not isinstance(payload.get(field), list):
            errors.append(f"{field} must be a list")
    if "document_basis_summary" in payload and not isinstance(payload.get("document_basis_summary"), dict):
        errors.append("document_basis_summary must be an object")
    return errors
