from __future__ import annotations

from typing import Optional

from .schema import DEFAULT_CONFIDENCE, MonetaryValue


UNIT_FACTORS_TO_CRORE = {
    "rupees": 1 / 10_000_000,
    "inr": 1 / 10_000_000,
    "₹": 1 / 10_000_000,
    "thousand": 1 / 10_000,
    "thousands": 1 / 10_000,
    "lakh": 1 / 100,
    "lakhs": 1 / 100,
    "lac": 1 / 100,
    "lacs": 1 / 100,
    "million": 1 / 10,
    "mn": 1 / 10,
    "crore": 1.0,
    "crores": 1.0,
    "cr": 1.0,
    "billion": 100.0,
}


def canonicalize_unit(unit: str) -> str:
    raw = str(unit or "").strip().lower()
    if not raw:
        return ""
    collapsed = raw.replace(".", "").replace(",", " ")
    collapsed = " ".join(collapsed.split())
    if collapsed in UNIT_FACTORS_TO_CRORE:
        return collapsed
    for alias in sorted(UNIT_FACTORS_TO_CRORE, key=len, reverse=True):
        if alias in collapsed:
            return alias
    return collapsed


def convert_to_crore(value: Optional[float], unit: str) -> Optional[float]:
    if value is None:
        return None
    canonical = canonicalize_unit(unit)
    if not canonical:
        raise ValueError("unit is required when value is present")
    factor = UNIT_FACTORS_TO_CRORE.get(canonical)
    if factor is None:
        raise ValueError(f"Unsupported unit for crore normalization: {unit}")
    return round(float(value) * factor, 10)


def build_monetary_value(
    *,
    value_original: Optional[float],
    unit_original: str,
    source_year: str = "",
    source_page: Optional[int] = None,
    source_artifact: str = "",
    confidence: str = DEFAULT_CONFIDENCE,
    notes: Optional[list[str]] = None,
    currency: str = "INR",
) -> MonetaryValue:
    normalized_notes = [str(item) for item in (notes or [])]
    if value_original is None:
        if "missing_value" not in normalized_notes:
            normalized_notes.append("missing_value")
        return MonetaryValue(
            value_original=None,
            unit_original=unit_original,
            value_crore=None,
            currency=currency,
            source_year=source_year,
            source_page=source_page,
            source_artifact=source_artifact,
            confidence=confidence,
            notes=normalized_notes,
        )
    return MonetaryValue(
        value_original=float(value_original),
        unit_original=unit_original,
        value_crore=convert_to_crore(float(value_original), unit_original),
        currency=currency,
        source_year=source_year,
        source_page=source_page,
        source_artifact=source_artifact,
        confidence=confidence,
        notes=normalized_notes,
    )
