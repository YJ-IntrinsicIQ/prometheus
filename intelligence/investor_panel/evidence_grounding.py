from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


EVIDENCE_VALUE_KEYS = (
    "value",
    "business_summary",
    "business_model",
    "project_name",
    "initiative",
    "promise",
    "risk",
    "action",
    "summary",
    "normalized_promise",
)

MISSING_DATA_KEYWORDS = (
    "not available",
    "not provided",
    "not disclosed",
    "missing",
    "unavailable",
    "lack ",
    "lacks ",
    "lacking ",
    "absence of",
    "insufficient detail",
)

PROMISE_CLAIM_KEYWORDS = (
    "promise",
    "promises",
    "target",
    "targets",
    "guidance",
    "follow-through",
    "follow through",
    "commitment",
    "commitments",
    "roadmap",
)

GOVERNANCE_CLAIM_KEYWORDS = (
    "governance",
    "board",
    "committee",
    "oversight",
    "compliance",
    "regulatory",
    "conduct",
)

INCENTIVE_CLAIM_KEYWORDS = (
    "incentive",
    "compensation",
    "owner-minded",
    "owner minded",
    "alignment",
    "pay",
    "stewardship",
)

HR_CONDUCT_KEYWORDS = (
    "hr",
    "talent",
    "people",
    "conduct",
    "policy",
    "human capital",
)

RISK_EVIDENCE_TERMS = (
    "market risk",
    "liquidity risk",
    "interest rate",
    "foreign exchange",
    "foreign exchange exposure",
    "credit risk",
    "derivative",
    "hedging",
)

CLAIM_RULES = [
    {
        "name": "liquidity",
        "keywords": ["liquidity", "refinancing", "borrowings", "maturity concentration", "maturity profile"],
        "allowed": ["liquidity_risk", "liquidity risk", "debt_borrowing", "borrowings"],
    },
    {
        "name": "interest_rate",
        "keywords": ["interest rate", "interest-rate", "variable rate", "rate sensitivity"],
        "allowed": ["interest_rate_risk", "market risk - interest rate", "interest rate / market risk", "interest rate risk"],
    },
    {
        "name": "foreign_exchange",
        "keywords": ["foreign exchange", "fx", "currency"],
        "allowed": [
            "foreign_exchange_risk",
            "foreign exchange exposure",
            "market risk - foreign currency risk",
            "derivative_hedging_risk",
            "hedging/derivative risk",
        ],
    },
    {
        "name": "credit",
        "keywords": ["credit risk", "receivables", "counterparty"],
        "allowed": ["credit_risk", "credit risk"],
    },
    {
        "name": "regulatory",
        "keywords": ["regulatory", "sebi", "fema", "companies act", "board", "committee", "compliance"],
        "allowed": ["regulatory_risk", "regulatory risk", "fema_compliance_risk", "fema compliance risk"],
    },
    {
        "name": "related_party",
        "keywords": ["related party", "rpt"],
        "allowed": ["related_party_risk", "related party / governance risk"],
    },
    {
        "name": "internal_control",
        "keywords": ["internal control", "weakness"],
        "allowed": ["internal_control_risk", "internal control / operational risk", "risk_management_weakness"],
    },
    {
        "name": "capex",
        "keywords": ["cwip", "capex", "capital work in progress", "capital expenditure"],
        "allowed": ["cwip", "capex", "capital_project", "capex spending (capital work-in-progress)"],
    },
    {
        "name": "share_split",
        "keywords": ["share split", "subdivision"],
        "allowed": [
            "share_split",
            "share split",
            "share subdivision / equity split",
            "share split / equity capital reorganization",
        ],
    },
    {
        "name": "treasury_investment",
        "keywords": ["treasury investment", "debt mutual fund", "short-term investment", "short term investment"],
        "allowed": ["treasury_investment", "debt mutual fund schemes", "short_term_investment"],
    },
]


def normalize_evidence_id(evidence_id: str) -> str:
    value = str(evidence_id or "").strip()
    if not value:
        return value

    match = re.match(
        r"^(ev_fy\d+)_business_classification_(?!json_)([a-z0-9_]+)$",
        value,
    )
    if match:
        year = match.group(1).replace("ev_", "")
        dna = match.group(2)
        return (
            f"{match.group(1)}_business_classification_json_"
            f"business_dna_by_year_{year}_{dna}"
        )

    match = re.match(r"^(ev_fy\d+)_company_intelligence_(?!json_)(.+)$", value)
    if match:
        return f"{match.group(1)}_company_intelligence_json_{match.group(2)}"

    match = re.match(r"^(ev_fy\d+)_management_summary_(?!json_)(.+)$", value)
    if match:
        return f"{match.group(1)}_management_summary_json_{match.group(2)}"
    return value


def _first_present(item: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _extract_category(item: Dict[str, Any]) -> Any:
    category = item.get("category")
    if category not in (None, ""):
        return category
    refs = item.get("evidence_references")
    if isinstance(refs, dict):
        return refs.get("category")
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict) and ref.get("category") not in (None, ""):
                return ref.get("category")
    return None


def _extract_page(item: Dict[str, Any]) -> Any:
    page = _first_present(item, ("page", "source_page"))
    if page is not None:
        return page
    refs = item.get("evidence_references")
    if isinstance(refs, dict):
        return refs.get("page") or refs.get("source_page")
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict) and (ref.get("page") or ref.get("source_page")):
                return ref.get("page") or ref.get("source_page")
    return None


def _entry_text(entry: Dict[str, Any]) -> str:
    parts = [
        entry.get("category"),
        entry.get("canonical_risk"),
        entry.get("canonical_theme"),
        entry.get("signal_type"),
        entry.get("value"),
    ]
    return " ".join(str(part or "").lower() for part in parts)


def _normalize_section_path(path: List[str]) -> str:
    return ".".join(part for part in path if part)


def _canonical_business_classification_alias(evidence_id: str) -> Optional[str]:
    match = re.match(
        r"^(ev_fy\d+)_business_classification_json_business_dna_by_year_(fy\d+)_(.+)$",
        evidence_id,
    )
    if not match or match.group(1).replace("ev_", "") != match.group(2):
        return None
    return f"{match.group(1)}_business_classification_{match.group(3)}"


def _aliases_for_canonical_evidence_id(evidence_id: str) -> List[str]:
    aliases = {evidence_id, normalize_evidence_id(evidence_id)}

    match = re.match(r"^(ev_fy\d+)_company_intelligence_json_(.+)$", evidence_id)
    if match:
        aliases.add(f"{match.group(1)}_company_intelligence_{match.group(2)}")

    business_alias = _canonical_business_classification_alias(evidence_id)
    if business_alias:
        aliases.add(business_alias)

    return [alias for alias in aliases if alias]


def _entry_preference_score(entry: Dict[str, Any]) -> Tuple[int, int]:
    canonical_id = str(entry.get("canonical_evidence_id") or entry.get("evidence_id") or "")
    section_path = str(entry.get("section_path") or "")
    return (
        1 if "_json_business_dna_by_year_" in canonical_id else 0,
        0 if section_path.startswith("multi_year_inputs") else 1,
    )


def build_evidence_lookup(pcim: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    canonical_entries: Dict[str, Dict[str, Any]] = {}

    def register(item: Dict[str, Any], path: List[str]) -> None:
        evidence_ids = item.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            return
        base = {
            "section_path": _normalize_section_path(path),
            "value": _first_present(item, EVIDENCE_VALUE_KEYS),
            "category": _extract_category(item),
            "canonical_risk": item.get("normalized_risk") or item.get("canonical_risk"),
            "canonical_theme": item.get("canonical_theme") or item.get("theme"),
            "signal_type": item.get("signal_type"),
            "source_year": item.get("source_year"),
            "source_artifact": item.get("source_artifact"),
            "source_item_id": item.get("source_item_id"),
            "page": _extract_page(item),
        }
        for evidence_id in evidence_ids:
            if not isinstance(evidence_id, str) or not evidence_id.strip():
                continue
            canonical_id = normalize_evidence_id(evidence_id)
            current = canonical_entries.setdefault(
                canonical_id,
                {
                    "evidence_id": canonical_id,
                    "canonical_evidence_id": canonical_id,
                    "aliases": [],
                },
            )
            for key, value in base.items():
                current.setdefault(key, None)
                if current.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                    current[key] = value

    def walk(value: Any, path: List[str]) -> None:
        if isinstance(value, dict):
            register(value, path)
            for key, nested in value.items():
                if key == "evidence_map":
                    continue
                walk(nested, path + [key])
        elif isinstance(value, list):
            for idx, nested in enumerate(value):
                walk(nested, path + [str(idx)])

    for section, value in pcim.items():
        if section == "evidence_map":
            continue
        walk(value, [section])

    multi_year_map = (pcim.get("multi_year_inputs") or {}).get("evidence_map") or {}
    if isinstance(multi_year_map, dict):
        for evidence_id, metadata in multi_year_map.items():
            if not isinstance(metadata, dict):
                continue
            canonical_id = normalize_evidence_id(evidence_id)
            current = canonical_entries.setdefault(
                canonical_id,
                {
                    "evidence_id": canonical_id,
                    "canonical_evidence_id": canonical_id,
                    "aliases": [],
                },
            )
            current.setdefault("section_path", "multi_year_inputs.evidence_map")
            current.setdefault("category", None)
            current.setdefault("canonical_risk", None)
            current.setdefault("canonical_theme", None)
            current.setdefault("signal_type", None)
            current.setdefault("value", None)
            current["source_year"] = current.get("source_year") or metadata.get("source_year")
            current["source_artifact"] = current.get("source_artifact") or metadata.get("source_artifact")
            current["source_item_id"] = current.get("source_item_id") or metadata.get("source_item_id")
            current["page"] = current.get("page") or metadata.get("source_page")

    lookup: Dict[str, Dict[str, Any]] = {}
    for canonical_id, entry in canonical_entries.items():
        aliases = sorted(set(_aliases_for_canonical_evidence_id(canonical_id)))
        entry["aliases"] = aliases
        for alias in aliases:
            existing = lookup.get(alias)
            if existing is None or _entry_preference_score(entry) >= _entry_preference_score(existing):
                lookup[alias] = entry
    return lookup


def resolve_evidence_id(
    evidence_id: str,
    evidence_lookup: Dict[str, Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], str, bool]:
    original_id = str(evidence_id or "").strip()
    if not original_id:
        return None, None, "", False

    normalized_id = normalize_evidence_id(original_id)
    entry = evidence_lookup.get(original_id) or evidence_lookup.get(normalized_id)
    if entry is None:
        return None, None, normalized_id, normalized_id != original_id
    canonical_id = str(entry.get("canonical_evidence_id") or entry.get("evidence_id") or normalized_id)
    return entry, canonical_id, normalized_id, canonical_id != original_id


def _canonicalize_allowed_ids(
    allowed_evidence_ids: Optional[List[str]],
    evidence_lookup: Dict[str, Dict[str, Any]],
) -> set[str]:
    canonical_allowed: set[str] = set()
    for evidence_id in allowed_evidence_ids or []:
        entry, canonical_id, _, _ = resolve_evidence_id(evidence_id, evidence_lookup)
        if entry is not None and canonical_id:
            canonical_allowed.add(canonical_id)
        else:
            normalized = normalize_evidence_id(evidence_id)
            if normalized:
                canonical_allowed.add(normalized)
    return canonical_allowed


def canonicalize_evidence_ids(
    evidence_ids: List[str],
    evidence_lookup: Dict[str, Dict[str, Any]],
    *,
    allowed_evidence_ids: Optional[List[str]] = None,
) -> List[str]:
    canonical: List[str] = []
    allowed = _canonicalize_allowed_ids(allowed_evidence_ids, evidence_lookup)
    for evidence_id in evidence_ids:
        entry, canonical_id, _, _ = resolve_evidence_id(evidence_id, evidence_lookup)
        resolved = canonical_id if entry is not None else normalize_evidence_id(evidence_id)
        if allowed and resolved not in allowed:
            continue
        if resolved and resolved not in canonical:
            canonical.append(resolved)
    return canonical


def normalize_evidence_ids_with_summary(
    evidence_ids: List[str],
    evidence_lookup: Dict[str, Dict[str, Any]],
    *,
    allowed_evidence_ids: Optional[List[str]] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    canonical: List[str] = []
    allowed = _canonicalize_allowed_ids(allowed_evidence_ids, evidence_lookup)
    replacements: List[Dict[str, str]] = []
    unresolved_ids: List[str] = []

    for evidence_id in evidence_ids:
        original_id = str(evidence_id or "").strip()
        if not original_id:
            continue
        entry, canonical_id, _, was_normalized = resolve_evidence_id(original_id, evidence_lookup)
        if entry is None or not canonical_id:
            if original_id not in unresolved_ids:
                unresolved_ids.append(original_id)
            if original_id not in canonical:
                canonical.append(original_id)
            continue
        if allowed and canonical_id not in allowed:
            if original_id not in unresolved_ids:
                unresolved_ids.append(original_id)
            if original_id not in canonical:
                canonical.append(original_id)
            continue
        if canonical_id not in canonical:
            canonical.append(canonical_id)
        if was_normalized or canonical_id != original_id:
            replacement = {"original_id": original_id, "canonical_id": canonical_id}
            if replacement not in replacements:
                replacements.append(replacement)

    return canonical, {
        "applied": bool(replacements),
        "replacements": replacements,
        "unresolved_ids": unresolved_ids,
    }


def normalize_text_evidence_ids(
    text: str,
    evidence_lookup: Dict[str, Dict[str, Any]],
) -> Tuple[str, List[Dict[str, str]], List[str]]:
    value = str(text or "")
    replacements: List[Dict[str, str]] = []
    unresolved_ids: List[str] = []

    def replace(match: re.Match[str]) -> str:
        original_id = match.group(0)
        entry, canonical_id, _, was_normalized = resolve_evidence_id(original_id, evidence_lookup)
        if entry is None or not canonical_id:
            if original_id not in unresolved_ids:
                unresolved_ids.append(original_id)
            return original_id
        if was_normalized or canonical_id != original_id:
            replacement = {"original_id": original_id, "canonical_id": canonical_id}
            if replacement not in replacements:
                replacements.append(replacement)
        return canonical_id

    normalized = re.sub(r"\bev_[A-Za-z0-9_]+\b", replace, value)
    return normalized, replacements, unresolved_ids


def strip_inline_evidence_prose(text: str) -> Tuple[str, List[str]]:
    value = str(text or "")
    inline_ids = re.findall(r"\bev_[A-Za-z0-9_]+\b", value)
    patterns = [
        r"\(\s*supporting evidence:.*?\)",
        r"\(\s*evidence:.*?\)",
        r"supporting evidence:\s*ev_[A-Za-z0-9_;\- ,:.()]+",
        r"evidence:\s*ev_[A-Za-z0-9_;\- ,:.()]+",
    ]
    cleaned = value
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    return cleaned, inline_ids


def assert_no_source_chunk(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "source_chunk":
                raise ValueError("source_chunk leakage detected in prompt payload")
            assert_no_source_chunk(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_source_chunk(nested)


def validate_prompt_payload(compact_pcim: Dict[str, Any], *, pcim_source: str) -> None:
    assert_no_source_chunk(compact_pcim)
    if "multi_year_inputs" in compact_pcim:
        multi_year_inputs = compact_pcim["multi_year_inputs"] or {}
        if multi_year_inputs and multi_year_inputs.get("available") is not False and "limitations" not in multi_year_inputs:
            raise ValueError("multi_year_inputs.limitations missing from prompt payload")
        if multi_year_inputs and "years_covered" not in multi_year_inputs and multi_year_inputs.get("available") is not False:
            raise ValueError("multi_year_inputs.years_covered missing from prompt payload")
    if "/multi_year/" in pcim_source:
        raise ValueError("Investor panel must load multi_year_inputs from PCIM, not raw multi-year JSON")


def split_claim_text(claim_text: str) -> List[str]:
    text, _ = strip_inline_evidence_prose(claim_text)
    text = text.strip()
    if not text:
        return []

    fragments: List[str] = []
    primary_parts = re.split(r"(?<=[.!?])\s+|;\s+", text)
    for part in primary_parts:
        part = part.strip(" -")
        if not part:
            continue
        secondary_parts = [part]
        if len(_matched_rule_names(part)) > 1 or _is_missing_data_claim(part):
            secondary_parts = re.split(r",\s+(?=(?:but)\b)|\s+but\s+|\s+and\s+", part)
        for secondary in secondary_parts:
            cleaned = secondary.strip(" ,.-")
            if cleaned:
                fragments.append(cleaned)
    return fragments or [text]


def _matched_rule_names(claim_text: str) -> List[str]:
    claim = claim_text.lower()
    return [rule["name"] for rule in CLAIM_RULES if any(keyword in claim for keyword in rule["keywords"])]


def _rule_for_name(name: str) -> Dict[str, Any]:
    for rule in CLAIM_RULES:
        if rule["name"] == name:
            return rule
    raise KeyError(name)


def _is_missing_data_claim(claim_text: str) -> bool:
    claim = claim_text.lower()
    return any(keyword in claim for keyword in MISSING_DATA_KEYWORDS)


def _entry_is_uncertainty_support(entry: Dict[str, Any]) -> bool:
    section_path = str(entry.get("section_path") or "")
    if section_path.startswith("uncertainty_missing_data"):
        return True
    if "uncertainty_notes" in section_path:
        return True
    return False


def _entry_is_business_model_support(entry: Dict[str, Any]) -> bool:
    section_path = str(entry.get("section_path") or "").lower()
    signal_type = str(entry.get("signal_type") or "").lower()
    return (
        "business_model" in section_path
        or "latest_business_view" in section_path
        or "business_summary" in section_path
        or signal_type == "business_model"
    )


def _contains_claim_keyword(claim: str, keyword: str) -> bool:
    if " " in keyword or "-" in keyword:
        return keyword in claim
    return re.search(rf"\b{re.escape(keyword)}\b", claim) is not None


def _claim_mentions_governance(claim_text: str) -> bool:
    claim = str(claim_text or "").lower()
    return any(_contains_claim_keyword(claim, keyword) for keyword in GOVERNANCE_CLAIM_KEYWORDS)


def _claim_mentions_incentives(claim_text: str) -> bool:
    claim = str(claim_text or "").lower()
    return any(_contains_claim_keyword(claim, keyword) for keyword in INCENTIVE_CLAIM_KEYWORDS)


def _claim_mentions_hr_or_conduct(claim_text: str) -> bool:
    claim = str(claim_text or "").lower()
    return any(_contains_claim_keyword(claim, keyword) for keyword in HR_CONDUCT_KEYWORDS)


def _claim_mentions_business_quality(claim_text: str) -> bool:
    claim = str(claim_text or "").lower()
    return any(
        phrase in claim
        for phrase in (
            "business quality",
            "understandable business",
            "understandable",
            "business description",
            "operating model",
            "manufacturing capability",
            "manufacturing capabilities",
            "product capability",
            "differentiation",
            "business model",
            "stewardship",
            "management rationality",
        )
    )


def _claim_demands_strong_moat_support(claim_text: str) -> bool:
    claim = str(claim_text or "").lower()
    return any(
        phrase in claim
        for phrase in (
            "pricing power",
            "customer lock-in",
            "customer lock in",
            "durable competitive advantage",
            "durable moat",
            "strong moat",
            "switching costs",
        )
    )


def _entry_supports_governance(entry: Dict[str, Any]) -> bool:
    haystack = _entry_text(entry)
    return any(
        phrase in haystack
        for phrase in (
            "governance",
            "board governance",
            "regulatory compliance / board governance",
            "regulatory compliance",
            "governance_risk",
            "related_party",
            "internal_control",
            "risk governance",
        )
    )


def _entry_supports_incentives(entry: Dict[str, Any]) -> bool:
    haystack = _entry_text(entry)
    return any(
        phrase in haystack
        for phrase in (
            "equity_incentives",
            "compensation",
            "incentive",
            "owner alignment",
            "related_party_exposure",
        )
    )


def _entry_is_human_capital_support(entry: Dict[str, Any]) -> bool:
    haystack = _entry_text(entry)
    return "human_capital" in haystack or "human capital" in haystack


def _entry_is_risk_evidence(entry: Dict[str, Any]) -> bool:
    haystack = _entry_text(entry)
    return any(term in haystack for term in RISK_EVIDENCE_TERMS)


def _entry_is_promise_support(entry: Dict[str, Any]) -> bool:
    section_path = str(entry.get("section_path") or "").lower()
    source_item_id = str(entry.get("source_item_id") or "").lower()
    signal_type = str(entry.get("signal_type") or "").lower()
    return (
        "promise" in section_path
        or source_item_id.startswith("prom")
        or "promise" in signal_type
    )


def _claim_mentions_promise_context(claim_text: str) -> bool:
    claim = str(claim_text or "").lower()
    return any(keyword in claim for keyword in PROMISE_CLAIM_KEYWORDS)


def _classification_for_claim(claim_text: str, entry: Dict[str, Any]) -> str:
    matched_names = _matched_rule_names(claim_text)
    claim_lower = str(claim_text or "").lower()
    if _is_missing_data_claim(claim_text):
        if _entry_is_uncertainty_support(entry):
            return "pass"
        return "ignore"

    if matched_names and set(matched_names).issubset({"capex", "share_split", "treasury_investment"}) and _entry_is_risk_evidence(entry):
        return "ignore"

    if _entry_is_promise_support(entry) and not _claim_mentions_promise_context(claim_text):
        if matched_names or "downside protection" in claim_lower or "margin" in claim_lower:
            return "ignore"

    if _entry_is_business_model_support(entry):
        if _claim_mentions_business_quality(claim_text):
            if _claim_demands_strong_moat_support(claim_text):
                return "weak_business_model"
            return "pass"
        if "moat" in claim_lower or _claim_demands_strong_moat_support(claim_text):
            return "weak_business_model"

    if _claim_mentions_business_quality(claim_text) and _entry_is_risk_evidence(entry):
        return "ignore"

    if _claim_mentions_governance(claim_text) or _claim_mentions_incentives(claim_text):
        if _entry_is_uncertainty_support(entry) and _is_missing_data_claim(claim_text):
            return "pass"
        if _entry_supports_governance(entry):
            return "pass"
        if _claim_mentions_incentives(claim_text) and _entry_supports_incentives(entry):
            return "pass"
        if _claim_mentions_hr_or_conduct(claim_text) and _entry_is_human_capital_support(entry):
            return "pass"
        if _entry_is_risk_evidence(entry):
            if "oversight" in claim_lower or "risk governance" in claim_lower:
                return "weak_routing"
            return "governance_routing"

    if not matched_names:
        return "generic"

    haystack = _entry_text(entry)
    if not haystack.strip():
        return "weak_metadata"

    for name in matched_names:
        rule = _rule_for_name(name)
        if any(allowed.lower() in haystack for allowed in rule["allowed"]):
            return "pass"

    known_signal = any(
        any(allowed.lower() in haystack for allowed in rule["allowed"]) or any(keyword in haystack for keyword in rule["keywords"])
        for rule in CLAIM_RULES
    )
    if known_signal:
        return "incompatible"
    return "weak_metadata"


def _warning_priority(issue: str) -> int:
    if "not present in PCIM evidence lookup" in issue:
        return 0
    if "only incompatible evidence" in issue:
        return 1
    if "unsupported PCIM section" in issue:
        return 1
    if "normalized" in issue:
        return 2
    if "lacks category metadata" in issue:
        return 3
    return 4


def _warning(
    *,
    claim_location: str,
    claim_text: str,
    evidence_id: Optional[str],
    evidence_entry: Optional[Dict[str, Any]],
    issue: str,
    suggested_action: str,
    normalized_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload = {
        "claim_location": claim_location,
        "claim_text": claim_text,
        "evidence_id": evidence_id,
        "evidence_category": (evidence_entry or {}).get("category")
        or (evidence_entry or {}).get("canonical_risk")
        or (evidence_entry or {}).get("canonical_theme"),
        "issue": issue,
        "suggested_action": suggested_action,
    }
    if normalized_id and normalized_id != evidence_id:
        payload["normalized_id"] = normalized_id
    return payload


def _warning_key(warning: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        warning.get("claim_location"),
        warning.get("issue"),
        warning.get("evidence_id"),
        warning.get("normalized_id"),
    )


def _dedupe_and_limit_warnings(warnings: List[Dict[str, Any]], *, limit: int = 10) -> List[Dict[str, Any]]:
    unique: List[Dict[str, Any]] = []
    seen = set()
    for warning in warnings:
        key = _warning_key(warning)
        if key in seen:
            continue
        seen.add(key)
        unique.append(warning)
    unique.sort(key=lambda item: (_warning_priority(str(item.get("issue") or "")), str(item.get("claim_location") or "")))
    return unique[:limit]


def _append_normalization_summary_warning(
    warnings: List[Dict[str, Any]],
    *,
    claim_location: str,
    claim_text: str,
    normalized_pairs: List[Tuple[str, str]],
) -> None:
    if not normalized_pairs:
        return
    unique_pairs = []
    seen = set()
    for original_id, normalized_id in normalized_pairs:
        key = (original_id, normalized_id)
        if key in seen:
            continue
        seen.add(key)
        unique_pairs.append(key)
    warnings.append(
        {
            "claim_location": claim_location,
            "claim_text": claim_text,
            "evidence_id": unique_pairs[0][0],
            "evidence_category": None,
            "issue": "Evidence ID was normalized during grounding lookup.",
            "suggested_action": "Prefer canonical PCIM evidence IDs in future analyst outputs.",
            "original_ids": [item[0] for item in unique_pairs],
            "normalized_ids": [item[1] for item in unique_pairs],
        }
    )


def _is_material_group(group_name: str) -> bool:
    return group_name in {"key_findings", "red_flags"}


def _group_name_from_location(claim_location: str) -> str:
    return claim_location.split(".", 1)[0]


def _validate_claim_unit(
    *,
    claim_location: str,
    claim_text: str,
    evidence_ids: List[str],
    evidence_lookup: Dict[str, Dict[str, Any]],
    warnings: List[Dict[str, Any]],
    supporting_pcim_sections: List[str],
) -> str:
    group_name = _group_name_from_location(claim_location)
    claim_is_missing_data = _is_missing_data_claim(claim_text)
    strict_rule_names = _matched_rule_names(claim_text)

    resolved_entries = []
    normalized_pairs = []
    missing_ids = []

    for evidence_id in evidence_ids:
        entry, canonical_id, normalized_id, was_normalized = resolve_evidence_id(evidence_id, evidence_lookup)
        if entry is None:
            missing_ids.append((evidence_id, normalized_id))
            continue
        resolved_entries.append((evidence_id, canonical_id or evidence_id, entry))
        if was_normalized:
            normalized_pairs.append((evidence_id, canonical_id or normalized_id))

    for evidence_id, normalized_id in missing_ids:
        warnings.append(
            _warning(
                claim_location=claim_location,
                claim_text=claim_text,
                evidence_id=evidence_id,
                evidence_entry=None,
                issue="Evidence ID is not present in PCIM evidence lookup.",
                suggested_action="Replace with a cited evidence_id that exists in PCIM.",
                normalized_id=normalized_id,
            )
        )

    if missing_ids:
        return "fail"

    if claim_is_missing_data and "uncertainty_missing_data" in supporting_pcim_sections:
        _append_normalization_summary_warning(
            warnings,
            claim_location=claim_location,
            claim_text=claim_text,
            normalized_pairs=normalized_pairs,
        )
        return "warning" if normalized_pairs else "pass"

    compatible = []
    weak_metadata = []
    incompatible = []
    routing_warnings = []
    for evidence_id, normalized_id, entry in resolved_entries:
        classification = _classification_for_claim(claim_text, entry)
        if classification == "pass":
            compatible.append((evidence_id, normalized_id, entry))
        elif classification == "weak_metadata":
            weak_metadata.append((evidence_id, normalized_id, entry))
        elif classification == "weak_business_model":
            weak_metadata.append((evidence_id, normalized_id, entry, "Weak but acceptable support: business-model evidence supports business description, not moat durability."))
        elif classification == "weak_routing":
            weak_metadata.append((evidence_id, normalized_id, entry, "Weak but acceptable support: risk evidence only partially supports governance/oversight framing."))
        elif classification == "governance_routing":
            routing_warnings.append((evidence_id, normalized_id, entry))
        elif classification == "incompatible":
            incompatible.append((evidence_id, normalized_id, entry))

    _append_normalization_summary_warning(
        warnings,
        claim_location=claim_location,
        claim_text=claim_text,
        normalized_pairs=normalized_pairs,
    )

    if compatible:
        return "warning" if normalized_pairs else "pass"

    if routing_warnings and not compatible:
        warnings.append(
            _warning(
                claim_location=claim_location,
                claim_text=claim_text,
                evidence_id=routing_warnings[0][0],
                evidence_entry=routing_warnings[0][2],
                issue="Routing warning: market-risk evidence should not support governance/incentive claim unless risk oversight is explicit.",
                suggested_action="Cite governance, incentive, board, compensation, or uncertainty evidence for this claim.",
                normalized_id=routing_warnings[0][1],
            )
        )
        return "fail" if _is_material_group(group_name) else "warning"

    if weak_metadata:
        custom_issue = (
            weak_metadata[0][3]
            if len(weak_metadata[0]) > 3
            else "Evidence exists but lacks category metadata for strict validation."
        )
        custom_action = (
            "Missing stronger support: claim would need customer/scale/pricing-power evidence."
            if "business-model evidence supports business description" in custom_issue
            else "Use stronger category metadata or a more claim-specific evidence_id."
        )
        warnings.append(
            _warning(
                claim_location=claim_location,
                claim_text=claim_text,
                evidence_id=weak_metadata[0][0],
                evidence_entry=weak_metadata[0][2],
                issue=custom_issue,
                suggested_action=custom_action,
                normalized_id=weak_metadata[0][1],
            )
        )
        return "warning"

    if incompatible:
        warnings.append(
            _warning(
                claim_location=claim_location,
                claim_text=claim_text,
                evidence_id=incompatible[0][0],
                evidence_entry=incompatible[0][2],
                issue="Claim has only incompatible evidence after claim-specific filtering.",
                suggested_action="Cite evidence IDs that match the specific claim topic instead of adjacent evidence.",
                normalized_id=incompatible[0][1],
            )
        )
        return "fail" if _is_material_group(group_name) else "warning"

    _append_normalization_summary_warning(
        warnings,
        claim_location=claim_location,
        claim_text=claim_text,
        normalized_pairs=normalized_pairs,
    )
    return "warning" if normalized_pairs else "pass"


def validate_analyst_evidence_grounding(
    *,
    assessment: Dict[str, str],
    key_findings: List[str],
    red_flags: List[str],
    open_uncertainties: List[str],
    claim_evidence_map: Dict[str, List[str]],
    supporting_pcim_sections: List[str],
    consumed_sections: List[str],
    supplied_evidence_ids: List[str],
    evidence_lookup: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    warnings: List[Dict[str, Any]] = []
    status = "pass"
    top_level_normalized_pairs: List[Tuple[str, str]] = []

    invalid_sections = [section for section in supporting_pcim_sections if section not in consumed_sections]
    if invalid_sections:
        status = "fail"
        for section in invalid_sections:
            warnings.append(
                {
                    "claim_location": "supporting_pcim_sections",
                    "claim_text": section,
                    "evidence_id": None,
                    "evidence_category": None,
                    "issue": "Unknown supporting PCIM section.",
                    "suggested_action": "Remove undeclared section from supporting_pcim_sections.",
                }
            )

    for evidence_id in supplied_evidence_ids:
        entry, canonical_id, normalized_id, was_normalized = resolve_evidence_id(evidence_id, evidence_lookup)
        if entry is None:
            status = "fail"
            warnings.append(
                _warning(
                    claim_location="evidence_ids",
                    claim_text="top_level_evidence_ids",
                    evidence_id=evidence_id,
                    evidence_entry=None,
                    issue="Evidence ID is not present in PCIM evidence lookup.",
                    suggested_action="Remove the unknown evidence_id or cite one that exists in PCIM.",
                    normalized_id=normalized_id,
                )
            )
            continue
        if was_normalized:
            top_level_normalized_pairs.append((evidence_id, canonical_id or normalized_id))

    _append_normalization_summary_warning(
        warnings,
        claim_location="evidence_ids",
        claim_text="top_level_evidence_ids",
        normalized_pairs=top_level_normalized_pairs,
    )

    claim_groups = {
        "assessment": assessment,
        "key_findings": {str(idx): text for idx, text in enumerate(key_findings)},
        "red_flags": {str(idx): text for idx, text in enumerate(red_flags)},
        "open_uncertainties": {str(idx): text for idx, text in enumerate(open_uncertainties)},
    }

    for group_name, items in claim_groups.items():
        for item_key, claim_text in items.items():
            if not isinstance(claim_text, str) or not claim_text.strip():
                continue
            base_location = f"{group_name}.{item_key}"
            cleaned_claim_text, inline_evidence_ids = strip_inline_evidence_prose(claim_text)
            evidence_ids = claim_evidence_map.get(base_location, [])
            if not evidence_ids and inline_evidence_ids:
                evidence_ids = inline_evidence_ids
            if not evidence_ids and not (_is_missing_data_claim(cleaned_claim_text) and "uncertainty_missing_data" in supporting_pcim_sections):
                continue

            claim_units = split_claim_text(cleaned_claim_text)
            unit_statuses = []
            for idx, claim_unit in enumerate(claim_units):
                claim_location = base_location if len(claim_units) == 1 else f"{base_location}#{idx + 1}"
                unit_status = _validate_claim_unit(
                    claim_location=claim_location,
                    claim_text=claim_unit,
                    evidence_ids=evidence_ids,
                    evidence_lookup=evidence_lookup,
                    warnings=warnings,
                    supporting_pcim_sections=supporting_pcim_sections,
                )
                unit_statuses.append(unit_status)

            if "fail" in unit_statuses:
                status = "fail" if _is_material_group(group_name) or status == "fail" else "warning"
            elif "warning" in unit_statuses and status == "pass":
                status = "warning"

    warnings = _dedupe_and_limit_warnings(warnings)
    if status == "pass" and warnings:
        status = "warning"

    return {
        "evidence_grounding_status": status,
        "evidence_grounding_warnings": warnings,
    }
