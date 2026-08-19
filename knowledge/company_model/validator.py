from __future__ import annotations

import re
from typing import Any, Dict, List

from .contract import BUSINESS_MODEL_TYPES, COVERAGE_STATUSES, SCHEMA_VERSION


GENERIC_PHRASES = (
    "focused on growth and operational efficiency",
    "focused on growth",
    "operational efficiency",
    "strategic initiatives",
    "enhanced capabilities",
    "improving performance",
)

SPECIFICITY_TOKENS = (
    "platform",
    "messaging",
    "communications",
    "telecom",
    "security",
    "radar",
    "defence",
    "aerospace",
    "electronic warfare",
    "manufacturing",
    "semiconductor",
    "component",
    "catalogue",
    "music",
    "licensing",
    "royalty",
    "streaming",
    "youtube",
    "capacity",
    "plant",
    "content",
    "ip",
)


def validate_company_model(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    company_slug = str(payload.get("company_slug") or "").strip()
    if not company_slug:
        errors.append("company_slug is required")
    if payload.get("coverage_status") not in COVERAGE_STATUSES:
        errors.append("coverage_status is invalid")
    for key in ("company_identity", "current_business_model", "source_manifest"):
        if not isinstance(payload.get(key), dict):
            errors.append(f"{key} is required")

    source_manifest = payload.get("source_manifest") or {}
    manifest_company = str(source_manifest.get("company_slug") or company_slug).strip()
    if manifest_company and company_slug and manifest_company != company_slug:
        errors.append("source_manifest.company_slug must match company_slug")
    for mismatch in source_manifest.get("company_mismatch_errors", []) or []:
        errors.append(str(mismatch))

    business = payload.get("current_business_model") or {}
    model_type = business.get("business_model_type")
    if model_type not in BUSINESS_MODEL_TYPES:
        errors.append("current_business_model.business_model_type is invalid")
    for key in ("summary", "what_company_does", "how_revenue_happens", "economic_mechanism"):
        if not str(business.get(key) or "").strip() and payload.get("coverage_status") != "insufficient_evidence":
            errors.append(f"current_business_model.{key} is required for supported/partial coverage")
    if not business.get("evidence") and payload.get("coverage_status") != "insufficient_evidence":
        errors.append("current_business_model.evidence is required")

    offerings = payload.get("offerings") or []
    customers = payload.get("customers") or []
    revenue_engines = payload.get("revenue_engines") or []
    for section_name, section in (("offerings", offerings), ("customers", customers), ("revenue_engines", revenue_engines)):
        if not isinstance(section, list):
            errors.append(f"{section_name} must be a list")
            continue
        for index, item in enumerate(section):
            if not isinstance(item, dict):
                errors.append(f"{section_name}[{index}] must be an object")
                continue
            if not item.get("evidence") and payload.get("coverage_status") == "supported":
                warnings.append(f"{section_name}[{index}] lacks direct evidence")

    _validate_coherence(payload, errors, warnings)
    _validate_specificity(payload, errors, warnings)
    status = "fail" if errors else "warning" if warnings else "pass"
    return {
        "schema_version": "company_model_validation.v1",
        "company_slug": company_slug,
        "status": status,
        "errors": errors,
        "warnings": warnings,
    }


def _validate_coherence(payload: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    business = payload.get("current_business_model") or {}
    combined_business = " ".join(
        str(business.get(key) or "") for key in ("summary", "what_company_does", "what_it_sells", "who_pays", "how_revenue_happens", "economic_mechanism")
    ).lower()
    offering_text = " ".join(str(item.get("name") or "") + " " + str(item.get("description") or "") for item in payload.get("offerings", []) if isinstance(item, dict)).lower()
    customer_text = " ".join(str(item.get("payer_type") or "") + " " + str(item.get("end_user_type") or "") for item in payload.get("customers", []) if isinstance(item, dict)).lower()
    revenue_text = " ".join(str(item.get("description") or "") + " " + str(item.get("billing_basis") or "") for item in payload.get("revenue_engines", []) if isinstance(item, dict)).lower()

    if payload.get("coverage_status") == "supported":
        if not offering_text:
            errors.append("supported model requires offerings")
        if not customer_text:
            errors.append("supported model requires customers")
        if not revenue_text:
            errors.append("supported model requires revenue_engines")

    if offering_text and not any(token in combined_business for token in _important_terms(offering_text)):
        warnings.append("current_business_model.what_it_sells has weak alignment with offerings")
    if customer_text and not any(token in combined_business for token in _important_terms(customer_text)):
        warnings.append("current_business_model.who_pays has weak alignment with customers")

    model_type = business.get("business_model_type")
    if model_type == "platform" and any(token in revenue_text for token in ("milestone", "project delivery", "manufacturing sale")):
        errors.append("platform business cannot rely only on manufacturing/project milestone revenue engine")
    if model_type == "content_ip" and any(token in revenue_text for token in ("milestone", "manufacturing", "plant")):
        errors.append("content_ip business cannot rely on manufacturing/milestone revenue engine")
    if model_type == "manufacturing" and any(token in revenue_text for token in ("royalty", "streaming", "advertising")):
        errors.append("manufacturing business cannot rely on content royalty/ad revenue engine")


def _validate_specificity(payload: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    if payload.get("coverage_status") == "insufficient_evidence":
        return
    business = payload.get("current_business_model") or {}
    text = " ".join(
        str(business.get(key) or "")
        for key in ("summary", "what_company_does", "what_it_sells", "who_pays", "how_revenue_happens", "economic_mechanism")
    ).lower()
    if any(phrase in text for phrase in GENERIC_PHRASES) and not any(token in text for token in SPECIFICITY_TOKENS):
        errors.append("business description is generic and lacks company-specific economic mechanism")
    specific_hits = [token for token in SPECIFICITY_TOKENS if token in text]
    if len(set(specific_hits)) < 2:
        errors.append("business description lacks enough specificity to identify the business without company name")
    if len(str(business.get("economic_mechanism") or "").split()) < 8:
        errors.append("economic_mechanism is too thin")


def _important_terms(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [word for word in words if len(word) >= 5 and word not in {"customer", "customers", "revenue", "business", "company", "through", "service", "services"}][:20]

