from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .constants import (
    DEFAULT_BLUEPRINT_VERSION,
    DEFAULT_BUSINESS_MODEL,
    DEFAULT_BUSINESS_SUMMARY,
    DEFAULT_COMPETITIVE_POSITION,
    DEFAULT_CONFIDENCE,
    DEFAULT_VALUE_CREATION,
)


@dataclass
class Metadata:
    company: str
    version: str = DEFAULT_BLUEPRINT_VERSION
    generated_at: Optional[str] = None
    confidence: float = DEFAULT_CONFIDENCE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "version": self.version,
            "generated_at": self.generated_at,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Metadata":
        return cls(
            company=payload.get("company", ""),
            version=payload.get("version", DEFAULT_BLUEPRINT_VERSION),
            generated_at=payload.get("generated_at"),
            confidence=float(payload.get("confidence", DEFAULT_CONFIDENCE)),
        )


@dataclass
class BusinessUnderstanding:
    business_summary: str = DEFAULT_BUSINESS_SUMMARY
    business_model: str = DEFAULT_BUSINESS_MODEL
    value_creation: str = DEFAULT_VALUE_CREATION
    competitive_position: str = DEFAULT_COMPETITIVE_POSITION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_summary": self.business_summary,
            "business_model": self.business_model,
            "value_creation": self.value_creation,
            "competitive_position": self.competitive_position,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "BusinessUnderstanding":
        return cls(
            business_summary=payload.get("business_summary", DEFAULT_BUSINESS_SUMMARY),
            business_model=payload.get("business_model", DEFAULT_BUSINESS_MODEL),
            value_creation=payload.get("value_creation", DEFAULT_VALUE_CREATION),
            competitive_position=payload.get("competitive_position", DEFAULT_COMPETITIVE_POSITION),
        )


@dataclass
class BusinessCharacteristic:
    name: str
    confidence: float = DEFAULT_CONFIDENCE

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "confidence": self.confidence}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "BusinessCharacteristic":
        return cls(
            name=payload.get("name", ""),
            confidence=float(payload.get("confidence", DEFAULT_CONFIDENCE)),
        )


@dataclass
class BusinessDNA:
    name: str
    confidence: float = DEFAULT_CONFIDENCE

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "confidence": self.confidence}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "BusinessDNA":
        return cls(
            name=payload.get("name", ""),
            confidence=float(payload.get("confidence", DEFAULT_CONFIDENCE)),
        )


@dataclass
class ReasoningStatement:
    statement: str

    def to_dict(self) -> Dict[str, Any]:
        return {"statement": self.statement}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ReasoningStatement":
        return cls(statement=payload.get("statement", ""))


def _normalize_reasoning_item(item: Union[str, Dict[str, Any], ReasoningStatement]) -> ReasoningStatement:
    if isinstance(item, ReasoningStatement):
        return item
    if isinstance(item, str):
        return ReasoningStatement(statement=item)
    if isinstance(item, dict):
        return ReasoningStatement.from_dict(item)
    return ReasoningStatement(statement=str(item))


@dataclass
class BusinessBlueprint:
    metadata: Metadata
    business_understanding: BusinessUnderstanding = field(default_factory=BusinessUnderstanding)
    characteristics: List[BusinessCharacteristic] = field(default_factory=list)
    dnas: List[BusinessDNA] = field(default_factory=list)
    reasoning: List[ReasoningStatement] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "business_understanding": self.business_understanding.to_dict(),
            "characteristics": [item.to_dict() for item in self.characteristics],
            "dnas": [item.to_dict() for item in self.dnas],
            "reasoning": [item.to_dict() for item in self.reasoning],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "BusinessBlueprint":
        return cls(
            metadata=Metadata.from_dict(payload.get("metadata", {})),
            business_understanding=BusinessUnderstanding.from_dict(payload.get("business_understanding", {})),
            characteristics=[BusinessCharacteristic.from_dict(item) for item in payload.get("characteristics", [])],
            dnas=[BusinessDNA.from_dict(item) for item in payload.get("dnas", [])],
            reasoning=[_normalize_reasoning_item(item) for item in payload.get("reasoning", [])],
        )
