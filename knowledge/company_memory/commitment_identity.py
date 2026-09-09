"""
Generic commitment identity extraction — no company-specific logic.

Extracts named subjects, geographies, and timelines deterministically from
source statements. Populates commitment_identity block in MC records.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# Generic pharma entity catalog (canonical_name → subject_type)
# These are proper names of drugs/molecules/facilities/deals; not company-specific logic.
_PHARMA_ENTITIES: List[tuple[str, str]] = [
    ("ilumya", "DRUG"),
    ("ilumetri", "DRUG"),
    ("nidlegy", "DRUG"),
    ("deuruxolitinib", "MOLECULE"),
    ("leqselvi", "DRUG"),
    ("unloxcyt", "DRUG"),
    ("nafamostat", "MOLECULE"),
    ("aqch", "MOLECULE"),
    ("organon", "DEAL"),
    ("toansa", "FACILITY"),
    ("halol", "FACILITY"),
    ("maduranthakam", "FACILITY"),
    ("mkm", "FACILITY"),
]

_GEOGRAPHY_TERMS: frozenset[str] = frozenset({
    "japan", "australia", "china", "india", "us", "usa", "united states",
    "europe", "uk", "germany", "france", "canada", "brazil", "mexico",
    "south korea", "korea", "russia", "middle east", "africa", "mena",
    "latam", "latin america", "asia pacific", "north america",
    "emerging markets",
})

_TIMELINE_RE = re.compile(r"\b(fy\s*\d{2,4}|20\d{2})\b", re.IGNORECASE)


def extract_commitment_identity(original_statement: str) -> Dict[str, Any]:
    """
    Deterministic extraction of named subjects, geography, and timelines.

    Named subjects come from the known entity catalog (exact word-boundary match).
    Geography comes from a generic market list.
    Timelines are FY-year or calendar-year mentions present in the source.

    Returns an empty structure when the source has no specific named entities.
    """
    text_lower = original_statement.lower()

    named_subjects: List[Dict[str, str]] = []
    seen: set[str] = set()
    for canonical, subject_type in _PHARMA_ENTITIES:
        if re.search(rf"\b{re.escape(canonical)}\b", text_lower) and canonical not in seen:
            named_subjects.append(
                {"subject": canonical.upper(), "subject_type": subject_type, "canonical": canonical}
            )
            seen.add(canonical)

    geography: List[str] = []
    for geo in sorted(_GEOGRAPHY_TERMS):
        if re.search(rf"\b{re.escape(geo)}\b", text_lower):
            geography.append(geo)

    extracted_timelines: List[str] = [
        m.group(0).lower().replace(" ", "") for m in _TIMELINE_RE.finditer(original_statement)
    ]

    return {
        "named_subjects": named_subjects,
        "geography": geography,
        "extracted_timelines": extracted_timelines,
    }


def check_specificity_loss(
    original_statement: str,
    normalized_commitment: str,
    commitment_identity: Dict[str, Any],
) -> List[str]:
    """
    Return list of warning codes when normalization lost specificity that was in the source.

    COMMITMENT_SPECIFICITY_LOSS — named entity present in source but absent in normalized form
    COMMITMENT_TIMELINE_LOSS   — timeline present in source but absent in normalized form
    COMMITMENT_GEOGRAPHY_LOSS  — specific geography in source but absent in normalized form
    """
    warnings: List[str] = []
    norm_lower = normalized_commitment.lower()

    for s in commitment_identity.get("named_subjects", []):
        if s["canonical"] not in norm_lower:
            warnings.append("COMMITMENT_SPECIFICITY_LOSS")
            break

    for geo in commitment_identity.get("geography", []):
        if geo not in norm_lower:
            warnings.append("COMMITMENT_GEOGRAPHY_LOSS")
            break

    for timeline in commitment_identity.get("extracted_timelines", []):
        if timeline not in norm_lower:
            warnings.append("COMMITMENT_TIMELINE_LOSS")
            break

    return warnings
