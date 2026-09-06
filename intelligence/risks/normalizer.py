"""Risk normalization and deduplication logic."""

from __future__ import annotations

import re
import hashlib
from typing import Any, Dict, Optional, Tuple

from knowledge.company_memory.guardrails import (
    assess_progression_materiality,
    build_semantic_quality,
    classify_business_relevance,
    resolve_period_status,
    semantic_validation,
)


def _compact_lower(text: Any) -> str:
    """Normalize text: lowercase, strip, single spaces."""
    if not isinstance(text, str):
        return ""
    return " ".join(text.lower().strip().split())


def _normalize_risk_name(name: str) -> str:
    """Normalize a risk name for consistency."""
    if not name:
        return ""
    
    # Remove common risk prefixes/suffixes
    text = _compact_lower(name)
    text = re.sub(r"^(risk|potential|possible|potential risk|residual risk)\s*of\s+", "", text)
    text = re.sub(r"\s+(risk|risks|concern|concern|exposure)$", "", text)
    text = re.sub(r"^(the|a|an)\s+", "", text)
    
    return text.strip()


def _extract_risk_mechanism(description: str) -> str:
    """Extract the core risk mechanism from a description."""
    if not description:
        return ""
    
    # Look for causal phrases
    text = _compact_lower(description)
    
    # Extract first clause or sentence
    for delimiter in [" if ", " because ", " due to ", " resulting in ", "."]:
        parts = text.split(delimiter)
        if len(parts) > 1:
            return parts[0].strip()
    
    # Default: first 20 words
    words = text.split()
    return " ".join(words[:20]).strip()


def _compute_dedup_key(
    risk_name: str,
    affected_area: Optional[str],
    first_period: str,
) -> str:
    """Compute a deterministic deduplication key for risks."""
    name_norm = _normalize_risk_name(risk_name)
    area_norm = _compact_lower(affected_area or "")
    
    # Create a canonical key
    return f"{name_norm}|{area_norm}|{first_period}".lower().strip()


def _similarity_score(
    text_a: str,
    text_b: str,
    min_common_tokens: int = 3,
) -> float:
    """Score similarity between two risk descriptions (0.0 to 1.0)."""
    if not text_a or not text_b:
        return 0.0
    
    tokens_a = set(_compact_lower(text_a).split())
    tokens_b = set(_compact_lower(text_b).split())
    
    if not tokens_a or not tokens_b:
        return 0.0
    
    common = tokens_a & tokens_b
    if len(common) < min_common_tokens:
        return 0.0
    
    total = len(tokens_a | tokens_b)
    return len(common) / total if total > 0 else 0.0


def normalize_candidate(
    candidate: Dict[str, Any],
    company_slug: str,
) -> Dict[str, Any]:
    """Normalize a raw risk candidate into canonical form."""
    digest = hashlib.sha256(str(candidate.get("risk_name") or candidate.get("value") or "").encode("utf-8")).hexdigest()[:16]
    risk_id = candidate.get("risk_id") or f"risk_{digest}"
    risk_name = candidate.get("risk_name") or candidate.get("value") or ""
    category = candidate.get("category") or candidate.get("risk_category") or "other"
    
    # Normalize name
    normalized_name = _normalize_risk_name(risk_name)
    
    # Extract mechanism
    mechanism = _extract_risk_mechanism(candidate.get("description", risk_name))
    full_text = " ".join(
        str(part or "").strip()
        for part in (
            risk_name,
            candidate.get("description"),
            mechanism,
            candidate.get("category"),
            candidate.get("source_artifact"),
        )
        if str(part or "").strip()
    )
    relevance = classify_business_relevance(full_text, module_name="risks", actor_type="", source_kind=str(candidate.get("source_artifact") or ""))
    period_resolution = resolve_period_status(
        source_year=candidate.get("source_year", ""),
        text=full_text,
        explicit_year=candidate.get("source_year", ""),
    )
    progression_materiality = assess_progression_materiality(
        full_text,
        module_name="risks",
        relevance_status=str(relevance.get("status") or "ambiguous"),
        period_status=str(period_resolution.get("status") or "AMBIGUOUS"),
        status_text=candidate.get("current_status", ""),
        relevance_outcome=str(relevance.get("outcome") or ""),
    )
    semantic_flags = semantic_validation(
        module_name="risks",
        relevance=relevance,
        period=period_resolution,
        materiality=progression_materiality,
    )

    return {
        "risk_id": risk_id,
        "risk_name": risk_name,
        "normalized_name": normalized_name,
        "risk_category": category,
        "affected_area": candidate.get("affected_area"),
        "first_observed_period": candidate.get("source_year", ""),
        "latest_period": candidate.get("source_year", ""),
        "current_status": candidate.get("current_status", "unable_to_verify"),
        "risk_mechanism": mechanism,
        "confidence": {
            "level": candidate.get("confidence", {}).get("level", "low")
            if isinstance(candidate.get("confidence"), dict)
            else "low",
            "basis": [f"source artifact: {candidate.get('source_artifact', '')}"],
            "limitations": [],
        },
        "evidence_status": candidate.get("evidence_status", "direct"),
        "source_references": [
            {
                "artifact": candidate.get("source_artifact", ""),
                "year": candidate.get("source_year", ""),
                "item_id": candidate.get("source_item_id", ""),
            }
        ],
        "semantic_relevance": relevance,
        "period_resolution": period_resolution,
        "progression_materiality": progression_materiality,
        "semantic_validation": semantic_flags,
        "semantic_quality": build_semantic_quality(
            classification="RISK",
            relevance=relevance,
            period=period_resolution,
            materiality=progression_materiality,
            evidence_confidence=candidate.get("confidence") or "medium",
        ),
        # Canonical evolution identity and trajectory — passed through unchanged
        "evo_trajectory": candidate.get("evo_trajectory"),
        "evo_canonical_id": candidate.get("evo_canonical_id"),
        "evo_severity_by_year": candidate.get("evo_severity_by_year") or {},
        "evo_latest_severity": candidate.get("evo_latest_severity"),
    }


def _year_label(period: str) -> str:
    """Extract numeric year from a period string."""
    if not period:
        return ""
    match = re.search(r"(\d{2,4})", period)
    return match.group(1) if match else ""


def deduplicate_risks(
    candidates: list[Dict[str, Any]],
    similarity_threshold: float = 0.6,
) -> Tuple[list[Dict[str, Any]], list[Tuple[str, str]]]:
    """
    Deduplicate risks using deterministic rules.
    
    Returns:
        (deduplicated_risks, merge_log) where merge_log contains (kept_id, merged_id)
    """
    if not candidates:
        return [], []
    
    # Group by canonical mechanism name. Source taxonomies frequently assign
    # different categories to the same economic risk wording.
    groups: Dict[str, list[Dict[str, Any]]] = {}
    
    for candidate in candidates:
        normalized = _normalize_risk_name(candidate.get("risk_name", ""))
        key = normalized.lower()
        
        if key not in groups:
            groups[key] = []
        groups[key].append(candidate)
    
    # Merge within groups using similarity
    result = []
    merge_log = []
    
    for group in groups.values():
        if len(group) == 1:
            result.append(group[0])
            continue
        
        # Sort by first observed period
        sorted_group = sorted(
            group,
            key=lambda x: (_year_label(x.get("first_observed_period", "")), x.get("risk_id", "")),
        )
        
        # Keep first, merge others
        primary = sorted_group[0]
        for secondary in sorted_group[1:]:
            score = _similarity_score(
                primary.get("risk_name", ""),
                secondary.get("risk_name", ""),
            )
            
            if score >= similarity_threshold:
                # Merge: keep primary, record merge
                merge_log.append((primary.get("risk_id", ""), secondary.get("risk_id", "")))
                
                # Update primary with latest period and evidence
                if secondary.get("first_observed_period"):
                    primary_year = _year_label(primary.get("first_observed_period", ""))
                    secondary_year = _year_label(secondary.get("first_observed_period", ""))
                    if secondary_year and (not primary_year or secondary_year < primary_year):
                        primary["first_observed_period"] = secondary.get("first_observed_period")
                
                if secondary.get("latest_period"):
                    secondary_year = _year_label(secondary.get("latest_period", ""))
                    primary_year = _year_label(primary.get("latest_period", ""))
                    if secondary_year and (not primary_year or secondary_year > primary_year):
                        primary["latest_period"] = secondary.get("latest_period")
                
                # Merge source references
                if secondary.get("source_references"):
                    if not primary.get("source_references"):
                        primary["source_references"] = []
                    primary["source_references"].extend(secondary.get("source_references", []))

                # Propagate evolution trajectory if primary lacks it
                for _tf in ("evo_trajectory", "evo_canonical_id", "evo_severity_by_year", "evo_latest_severity"):
                    if not primary.get(_tf) and secondary.get(_tf):
                        primary[_tf] = secondary[_tf]
            else:
                # Keep as separate risk
                result.append(secondary)
        
        result.append(primary)
    
    return result, merge_log
