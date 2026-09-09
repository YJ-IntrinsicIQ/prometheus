from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


FINANCIAL_EXTRACTION_TABLES = (
    "profit_and_loss",
    "balance_sheet",
    "cash_flow",
    "statement_of_changes_in_equity",
    "share_capital",
    "reserves",
    "borrowings",
    "fixed_assets",
    "revenue",
    "tax",
    "eps",
    "dividend",
    "corporate_actions",
    "shareholding_pattern",
    "investment_schedule",
    "lease_note",
    "management_discussion_financial_summary",
)

ALLOWED_EXTRACTION_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_TABLE_BASIS = {"standalone", "consolidated", "unknown"}
ALLOWED_VALUE_TYPES = {"monetary", "share_count", "per_share", "percentage", "ratio", "unit_count", "unknown"}


@dataclass
class ExtractedValue:
    period: str
    value_raw: str
    unit_hint: str
    currency_hint: str
    value_crore: Optional[float]
    value_type: str = "unknown"
    raw_number: Optional[float] = None
    # Canonical period role assigned by the quarterly annotation pass.
    # Empty string means "not yet annotated" (annual processing never sets this).
    # Quarterly processing calls knowledge.financials.period_roles.annotate_period_roles().
    period_role: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "period": self.period,
            "value_raw": self.value_raw,
            "unit_hint": self.unit_hint,
            "currency_hint": self.currency_hint,
            "value_crore": self.value_crore,
            "value_type": self.value_type,
            "raw_number": self.raw_number,
        }
        if self.period_role:
            d["period_role"] = self.period_role
        return d

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExtractedValue":
        return cls(
            period=str(payload.get("period", "")),
            value_raw=str(payload.get("value_raw", "")),
            unit_hint=str(payload.get("unit_hint", "")),
            currency_hint=str(payload.get("currency_hint", "")),
            value_crore=payload.get("value_crore"),
            value_type=str(payload.get("value_type", "unknown")),
            period_role=str(payload.get("period_role", "")),
            raw_number=payload.get("raw_number"),
        )


@dataclass
class ExtractedFinancialRow:
    statement_type: str
    table_type: str
    basis: str
    line_item_raw: str
    values: List[ExtractedValue] = field(default_factory=list)
    source_artifact: str = ""
    page: Optional[int] = None
    chunk_id: str = ""
    confidence: str = "low"
    source_section_type: str = ""
    table_confidence: str = "low"
    table_rejection_risk: List[str] = field(default_factory=list)
    is_primary_statement: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "statement_type": self.statement_type,
            "table_type": self.table_type,
            "basis": self.basis,
            "line_item_raw": self.line_item_raw,
            "values": [item.to_dict() for item in self.values],
            "source_artifact": self.source_artifact,
            "page": self.page,
            "chunk_id": self.chunk_id,
            "confidence": self.confidence,
            "source_section_type": self.source_section_type,
            "table_confidence": self.table_confidence,
            "table_rejection_risk": list(self.table_rejection_risk),
            "is_primary_statement": self.is_primary_statement,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExtractedFinancialRow":
        return cls(
            statement_type=str(payload.get("statement_type", "")),
            table_type=str(payload.get("table_type", "")),
            basis=str(payload.get("basis", "unknown")),
            line_item_raw=str(payload.get("line_item_raw", "")),
            values=[ExtractedValue.from_dict(item) for item in payload.get("values", [])],
            source_artifact=str(payload.get("source_artifact", "")),
            page=payload.get("page"),
            chunk_id=str(payload.get("chunk_id", "")),
            confidence=str(payload.get("confidence", "low")),
            source_section_type=str(payload.get("source_section_type", "")),
            table_confidence=str(payload.get("table_confidence", "low")),
            table_rejection_risk=[str(item) for item in payload.get("table_rejection_risk", [])],
            is_primary_statement=bool(payload.get("is_primary_statement", False)),
            warnings=[str(item) for item in payload.get("warnings", [])],
        )


@dataclass
class FinancialExtractionResult:
    company: str
    year: str
    generated_at: str
    source_documents: List[str] = field(default_factory=list)
    tables: Dict[str, List[ExtractedFinancialRow]] = field(
        default_factory=lambda: {name: [] for name in FINANCIAL_EXTRACTION_TABLES}
    )
    rejections: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "source_documents": list(self.source_documents),
            "tables": {
                key: [item.to_dict() for item in self.tables.get(key, [])]
                for key in FINANCIAL_EXTRACTION_TABLES
            },
            "rejections": list(self.rejections),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FinancialExtractionResult":
        raw_tables = payload.get("tables", {})
        tables = {
            key: [ExtractedFinancialRow.from_dict(item) for item in raw_tables.get(key, [])]
            for key in FINANCIAL_EXTRACTION_TABLES
        }
        return cls(
            company=str(payload.get("company", "")),
            year=str(payload.get("year", "")),
            generated_at=str(payload.get("generated_at", "")),
            source_documents=[str(item) for item in payload.get("source_documents", [])],
            tables=tables,
            rejections=[item for item in payload.get("rejections", []) if isinstance(item, dict)],
            warnings=[str(item) for item in payload.get("warnings", [])],
            limitations=[str(item) for item in payload.get("limitations", [])],
        )


def validate_financial_extraction_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial extraction payload must be an object"]
    if not payload.get("company"):
        errors.append("company is required")
    if not payload.get("year"):
        errors.append("year is required")
    if not payload.get("generated_at"):
        errors.append("generated_at is required")

    raw_tables = payload.get("tables")
    if not isinstance(raw_tables, dict):
        errors.append("tables must be an object")
        return errors

    for table_name in FINANCIAL_EXTRACTION_TABLES:
        rows = raw_tables.get(table_name)
        if not isinstance(rows, list):
            errors.append(f"tables.{table_name} must be a list")
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"tables.{table_name}[{index}] must be an object")
                continue
            if row.get("confidence") not in ALLOWED_EXTRACTION_CONFIDENCE:
                errors.append(f"tables.{table_name}[{index}].confidence must be high|medium|low")
            if row.get("table_confidence") not in ALLOWED_EXTRACTION_CONFIDENCE:
                errors.append(f"tables.{table_name}[{index}].table_confidence must be high|medium|low")
            if row.get("basis") not in ALLOWED_TABLE_BASIS:
                errors.append(
                    f"tables.{table_name}[{index}].basis must be standalone|consolidated|unknown"
                )
            for key in ("statement_type", "table_type", "line_item_raw", "source_artifact", "chunk_id", "source_section_type"):
                if not row.get(key):
                    errors.append(f"tables.{table_name}[{index}].{key} is required")
            values = row.get("values")
            if not isinstance(values, list) or not values:
                errors.append(f"tables.{table_name}[{index}].values must be a non-empty list")
                continue
            for value_index, value in enumerate(values):
                if not isinstance(value, dict):
                    errors.append(f"tables.{table_name}[{index}].values[{value_index}] must be an object")
                    continue
                if not value.get("period"):
                    errors.append(f"tables.{table_name}[{index}].values[{value_index}].period is required")
                if not value.get("value_raw"):
                    errors.append(f"tables.{table_name}[{index}].values[{value_index}].value_raw is required")
                if value.get("value_type") not in ALLOWED_VALUE_TYPES:
                    errors.append(
                        f"tables.{table_name}[{index}].values[{value_index}].value_type must be one of {sorted(ALLOWED_VALUE_TYPES)}"
                    )

    if not any(raw_tables.get(table_name) for table_name in FINANCIAL_EXTRACTION_TABLES):
        errors.append("at least one financial row must be extracted")

    return errors
