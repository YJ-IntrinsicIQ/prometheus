from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .sanitizer import sanitize_public_payload, sanitize_public_text


MAX_GROUPS = 5
MAX_PUBLIC_OFFERINGS = 8
MAX_PUBLIC_CAPABILITIES = 4
PROMOTIONAL_TERMS = {
    "world-class",
    "revolutionary",
    "cutting-edge",
    "market-leading",
}

OFFERING_PATTERNS = [
    {
        "canonical_name": "Automated Test Equipment",
        "aliases": ["automated test equipment", "ate"],
        "classification": "physical_product",
        "group_hint": "Products",
        "simple_explanation": "Equipment used to test whether complex electronic systems are working properly.",
        "role_in_business": "project-based offering",
        "revenue_contribution_status": "unknown",
        "revenue_model": "project or programme delivery",
    },
    {
        "canonical_name": "Electronic systems",
        "aliases": ["electronic systems", "electronic system"],
        "classification": "integrated_solution",
        "group_hint": "Systems and solutions",
        "simple_explanation": "Integrated electronic systems built for demanding technical use cases.",
        "role_in_business": "project-based offering",
        "revenue_contribution_status": "unknown",
        "revenue_model": "project or programme delivery",
    },
    {
        "canonical_name": "Defence and space subsystems",
        "aliases": ["subsystems", "space/defence subsystems", "defence subsystems", "space subsystems"],
        "classification": "subsystem",
        "group_hint": "Subsystems",
        "simple_explanation": "Smaller subsystems that are supplied into larger defence or space programmes.",
        "role_in_business": "project-based offering",
        "revenue_contribution_status": "unknown",
        "revenue_model": "programme-linked subsystem delivery",
    },
    {
        "canonical_name": "Radar systems",
        "aliases": ["radars", "radar systems", "radar"],
        "classification": "integrated_solution",
        "group_hint": "Systems and solutions",
        "simple_explanation": "Radar-related systems used in larger defence or monitoring programmes.",
        "role_in_business": "project-based offering",
        "revenue_contribution_status": "unknown",
        "revenue_model": "project or programme delivery",
    },
    {
        "canonical_name": "Electronic warfare systems",
        "aliases": ["electronic warfare", "ew", "mobile electronic warfare systems"],
        "classification": "integrated_solution",
        "group_hint": "Systems and solutions",
        "simple_explanation": "Electronic warfare systems used in specialised defence applications.",
        "role_in_business": "project-based offering",
        "revenue_contribution_status": "unknown",
        "revenue_model": "project or programme delivery",
    },
    {
        "canonical_name": "Communication systems",
        "aliases": ["communication systems"],
        "classification": "integrated_solution",
        "group_hint": "Systems and solutions",
        "simple_explanation": "Communication systems that support mission or programme operations.",
        "role_in_business": "project-based offering",
        "revenue_contribution_status": "unknown",
        "revenue_model": "project or programme delivery",
    },
    {
        "canonical_name": "Enterprise communications platform",
        "aliases": [
            "cpaas",
            "communications platform",
            "communications platforms",
            "enterprise communications",
            "messaging platform",
            "messaging platforms",
            "omnichannel messaging",
            "cloud communications",
        ],
        "classification": "software_platform",
        "group_hint": "Software and platforms",
        "simple_explanation": "A software platform that helps enterprises and telecom partners send, manage, or secure customer communications.",
        "role_in_business": "core platform offering",
        "revenue_contribution_status": "unknown",
        "revenue_model": "platform or service revenue",
    },
    {
        "canonical_name": "Marketing automation tools",
        "aliases": ["marketing automation", "predictive analytics", "customer engagement", "push notifications", "in-app messaging"],
        "classification": "software_product",
        "group_hint": "Software and platforms",
        "simple_explanation": "Software tools used to automate customer engagement and communication workflows.",
        "role_in_business": "software-led offering",
        "revenue_contribution_status": "unknown",
        "revenue_model": "platform or service revenue",
    },
    {
        "canonical_name": "Satellite systems",
        "aliases": ["satellite systems", "satellite payloads", "nanosatellite components"],
        "classification": "integrated_solution",
        "group_hint": "Systems and solutions",
        "simple_explanation": "Satellite-related systems or components supplied into space programmes.",
        "role_in_business": "project-based offering",
        "revenue_contribution_status": "unknown",
        "revenue_model": "programme-linked system delivery",
    },
    {
        "canonical_name": "Control systems",
        "aliases": ["control systems", "control system"],
        "classification": "subsystem",
        "group_hint": "Subsystems",
        "simple_explanation": "Control systems that help manage how larger equipment operates.",
        "role_in_business": "project-based offering",
        "revenue_contribution_status": "unknown",
        "revenue_model": "programme-linked subsystem delivery",
    },
    {
        "canonical_name": "Navigation systems",
        "aliases": ["navigation", "navigation systems"],
        "classification": "subsystem",
        "group_hint": "Subsystems",
        "simple_explanation": "Navigation-related systems used inside larger platforms or programmes.",
        "role_in_business": "project-based offering",
        "revenue_contribution_status": "unknown",
        "revenue_model": "programme-linked subsystem delivery",
    },
    {
        "canonical_name": "Software tools",
        "aliases": ["software tools", "workflow automation", "embedded software", "firmware"],
        "classification": "software_product",
        "group_hint": "Software and tools",
        "simple_explanation": "Software or firmware tools that support design, testing, or delivery workflows.",
        "role_in_business": "strategic but economically unproven",
        "revenue_contribution_status": "unknown",
        "revenue_model": "not clearly disclosed",
    },
    {
        "canonical_name": "Systems integration",
        "aliases": ["systems integration", "system integration", "satellite integration", "radar integration"],
        "classification": "engineering_service",
        "group_hint": "Services",
        "simple_explanation": "Integration work that combines many components into a working customer system.",
        "role_in_business": "project-based offering",
        "revenue_contribution_status": "partial",
        "revenue_model": "project integration work",
    },
    {
        "canonical_name": "Lifecycle support",
        "aliases": ["life cycle support", "lifecycle support"],
        "classification": "service",
        "group_hint": "Services",
        "simple_explanation": "Support provided after delivery so systems can continue operating as intended.",
        "role_in_business": "supporting service",
        "revenue_contribution_status": "unknown",
        "revenue_model": "service or support engagement",
    },
    {
        "canonical_name": "Testing and qualification",
        "aliases": ["environmental testing", "qualification", "testing facility", "test facility"],
        "classification": "manufacturing_service",
        "group_hint": "Capabilities",
        "simple_explanation": "Testing and qualification capability that helps products meet demanding standards.",
        "role_in_business": "capability that enables larger contracts",
        "revenue_contribution_status": "not_applicable",
        "revenue_model": "enabling capability rather than separately disclosed revenue",
    },
    {
        "canonical_name": "Electronics manufacturing capability",
        "aliases": ["ems", "manufacturing facility", "design to manufacture", "in-house design and manufacturing capability", "captive manufacturing facility"],
        "classification": "manufacturing_service",
        "group_hint": "Capabilities",
        "simple_explanation": "In-house manufacturing capability used to build and qualify complex electronics.",
        "role_in_business": "capability that enables larger contracts",
        "revenue_contribution_status": "not_applicable",
        "revenue_model": "enabling capability rather than separately disclosed revenue",
    },
]


def build_products_services(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], company_slug: str, generated_at: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    candidates = extract_offering_candidates(source_bundle)
    merged_items = merge_duplicate_offerings(candidates)
    groups = group_offerings(merged_items)
    customer_summary = build_customer_summary(source_bundle, merged_items)
    business_model_summary = build_business_model_summary(source_bundle, merged_items)
    revenue_logic_summary = build_revenue_logic_summary(source_bundle, merged_items)
    open_questions = build_open_questions(merged_items, source_bundle)

    coverage_status = "supported" if groups and len(merged_items) >= 3 else "partial" if groups else "unavailable"
    if not groups:
        payload = sanitize_public_payload(
            {
                "schema_version": "ask_intrinsiciq_products_services.v1",
                "company_slug": company_slug,
                "summary": "The available company memory describes the business at a high level, but does not yet provide a reliable products and services breakdown.",
                "groups": [],
                "business_model_summary": None,
                "customer_summary": None,
                "revenue_logic_summary": None,
                "open_questions": open_questions,
                "coverage_status": "unavailable",
                "generated_at": generated_at,
            }
        )
        return payload, {"candidates": candidates, "items": merged_items}

    summary = build_products_summary(groups)
    payload = sanitize_public_payload(
        {
            "schema_version": "ask_intrinsiciq_products_services.v1",
            "company_slug": company_slug,
            "summary": summary,
            "groups": groups,
            "business_model_summary": business_model_summary,
            "customer_summary": customer_summary,
            "revenue_logic_summary": revenue_logic_summary,
            "open_questions": open_questions,
            "coverage_status": coverage_status,
            "generated_at": generated_at,
        }
    )
    return payload, {"candidates": candidates, "items": merged_items, "journey_summary": business_journey_payload.get("summary")}


def extract_offering_candidates(source_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    texts = _collect_source_texts(source_bundle)
    candidates: List[Dict[str, Any]] = []
    for source_kind, year, text in texts:
        lowered = text.lower()
        for pattern in OFFERING_PATTERNS:
            matched_alias = None
            for alias in pattern["aliases"]:
                if re.search(rf"\b{re.escape(alias.lower())}\b", lowered):
                    matched_alias = alias
                    break
            if not matched_alias:
                continue
            candidates.append(
                {
                    "name": pattern["canonical_name"],
                    "normalized_name": normalize_offering_name(pattern["canonical_name"]),
                    "classification": pattern["classification"],
                    "group_hint": pattern["group_hint"],
                    "simple_explanation": pattern["simple_explanation"],
                    "customer_type": infer_customer_type(source_bundle, pattern["classification"]),
                    "customer_types": _customer_types_for_item(source_bundle, pattern["classification"]),
                    "role_in_business": pattern["role_in_business"],
                    "revenue_model": pattern.get("revenue_model") or infer_revenue_model(text, pattern["classification"]),
                    "revenue_contribution_status": classify_revenue_contribution(pattern, text),
                    "revenue_contribution": None,
                    "evidence_status": classify_evidence_status(source_kind),
                    "source_kind": source_kind,
                    "year": year,
                    "matched_alias": matched_alias,
                    "provenance": {"source_kind": source_kind, "year": year, "matched_alias": matched_alias},
                }
            )
    return sorted(candidates, key=lambda item: (item["normalized_name"], _year_sort_key(item.get("year")), item["source_kind"]))


def normalize_offering_name(candidate: str) -> str:
    text = str(candidate or "").lower()
    text = re.sub(r"\bate\b", "automated test equipment", text)
    text = re.sub(r"\bew\b", "electronic warfare", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split()).strip()


def merge_duplicate_offerings(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        key = candidate["normalized_name"]
        existing = merged.get(key)
        if existing is None:
            merged[key] = {
                "id": _slugify(candidate["name"]),
                "name": candidate["name"],
                "normalized_name": key,
                "classification": candidate["classification"],
                "group_hint": candidate["group_hint"],
                "simple_explanation": candidate["simple_explanation"],
                "customer_type": candidate["customer_type"],
                "customer_types": list(candidate.get("customer_types") or []),
                "role_in_business": candidate["role_in_business"],
                "revenue_model": candidate.get("revenue_model") or "not clearly disclosed",
                "revenue_contribution_status": candidate["revenue_contribution_status"],
                "revenue_contribution": None,
                "evidence_status": candidate["evidence_status"],
                "display_order": 0,
                "source_periods": [str(candidate.get("year") or "").upper()] if str(candidate.get("year") or "").strip() else [],
                "provenance_items": [candidate["provenance"]],
            }
            continue
        existing["evidence_status"] = _merge_evidence_status(existing["evidence_status"], candidate["evidence_status"])
        existing["revenue_contribution_status"] = _merge_revenue_status(existing["revenue_contribution_status"], candidate["revenue_contribution_status"])
        if existing["customer_type"].startswith("Customer type is not clearly") and not candidate["customer_type"].startswith("Customer type is not clearly"):
            existing["customer_type"] = candidate["customer_type"]
        for customer_type in candidate.get("customer_types") or []:
            if customer_type not in existing["customer_types"]:
                existing["customer_types"].append(customer_type)
        period = str(candidate.get("year") or "").upper()
        if period and period not in existing["source_periods"]:
            existing["source_periods"].append(period)
        existing["provenance_items"].append(candidate["provenance"])
    items = sorted(merged.values(), key=lambda item: (item["group_hint"], item["name"].lower()))
    for index, item in enumerate(items, start=1):
        item["display_order"] = index
    return items


def group_offerings(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item["group_hint"], []).append(item)
    priority = {
        "Products": 1,
        "Systems and solutions": 2,
        "Subsystems": 3,
        "Services": 4,
        "Capabilities": 5,
        "Software and platforms": 6,
        "Software and tools": 7,
        "Other offerings": 8,
    }
    ordered_titles = sorted(grouped.keys(), key=lambda title: (priority.get(title, 99), title))
    if len(ordered_titles) > MAX_GROUPS:
        keep = ordered_titles[: MAX_GROUPS - 1]
        overflow = ordered_titles[MAX_GROUPS - 1 :]
        grouped["Other offerings"] = [entry for title in overflow for entry in grouped[title]]
        ordered_titles = keep + ["Other offerings"]
    groups = []
    offering_count = 0
    capability_count = 0
    for group_index, title in enumerate(ordered_titles, start=1):
        description = group_description(title)
        entries = sorted(grouped[title], key=lambda item: item["name"].lower())
        public_items = []
        for local_index, item in enumerate(entries, start=1):
            is_capability = item["group_hint"] == "Capabilities"
            if is_capability and capability_count >= MAX_PUBLIC_CAPABILITIES:
                continue
            if not is_capability and offering_count >= MAX_PUBLIC_OFFERINGS:
                continue
            capability_count += 1 if is_capability else 0
            offering_count += 0 if is_capability else 1
            public_items.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "group": _public_group_name(item["group_hint"], item["classification"]),
                    "simple_explanation": item["simple_explanation"],
                    "customer_type": item["customer_type"],
                    "customer_types": item.get("customer_types") or [],
                    "role_in_business": item["role_in_business"],
                    "revenue_model": item.get("revenue_model") or "not clearly disclosed",
                    "revenue_contribution_status": item["revenue_contribution_status"],
                    "revenue_contribution": None,
                    "evidence_status": item["evidence_status"],
                    "source_periods": item.get("source_periods") or [],
                    "display_order": local_index,
                }
            )
        if not public_items:
            continue
        groups.append(
            {
                "id": _slugify(title),
                "title": title,
                "description": description,
                "items": public_items,
            }
        )
    return groups


def classify_revenue_contribution(pattern: Dict[str, Any], text: str) -> str:
    if pattern["revenue_contribution_status"] == "not_applicable":
        return "not_applicable"
    lowered = text.lower()
    if "service" in lowered and "product" in lowered:
        return "partial"
    return pattern["revenue_contribution_status"]


def classify_evidence_status(source_kind: str) -> str:
    if source_kind in {"pcim_business_model", "cim_business_model"}:
        return "direct"
    if source_kind in {"cim_initiative", "cim_project", "journey"}:
        return "partial"
    return "derived"


def build_products_summary(groups: List[Dict[str, Any]]) -> str:
    offerings = []
    capabilities = []
    for group in groups:
        for item in group.get("items", []):
            if str(item.get("group") or "") == "capability" or "capability" in str(item.get("role_in_business") or "").lower():
                capabilities.append(str(item.get("name") or "").strip())
            else:
                offerings.append(str(item.get("name") or "").strip())
    offerings = [item for item in offerings if item]
    capabilities = [item for item in capabilities if item]
    if not offerings and not capabilities:
        return "The available evidence does not yet support a reliable offering map."
    offering_text = _join_human_list(offerings[:3]).lower()
    capability_text = _join_human_list(capabilities[:2]).lower()
    if offering_text and capability_text:
        return sanitize_public_text(
            f"The company appears to build and deliver {offering_text}, supported by capabilities such as {capability_text}."
        )
    if offering_text:
        return sanitize_public_text(
            f"The company appears to build and deliver {offering_text}."
        )
    return sanitize_public_text(
        f"The available evidence shows enabling capabilities such as {capability_text}, but it does not yet separate sellable offerings cleanly."
    )


def build_business_model_summary(source_bundle: Dict[str, Any], items: List[Dict[str, Any]]) -> Optional[str]:
    latest_model = _latest_business_model_text(source_bundle)
    lowered = latest_model.lower()
    system_names = [
        item["name"]
        for item in items
        if item["classification"] in {"integrated_solution", "subsystem", "physical_product"}
    ]
    if "defence" in lowered or "space" in lowered or "aerospace" in lowered:
        if system_names:
            return sanitize_public_text(
                f"The company appears to be a specialised defence and aerospace electronics maker that designs, builds, tests, and delivers {_join_human_list(system_names[:3]).lower()}."
            )
        return sanitize_public_text(
            "The company appears to be a specialised defence and aerospace electronics maker that designs, builds, and qualifies complex equipment for institutional programmes."
        )
    if "contract" in lowered or "project" in lowered:
        return sanitize_public_text(
            "The company appears to earn mainly through project-based delivery of specialised products and systems."
        )
    if any(item["classification"] in {"software_platform", "software_product"} for item in items):
        return sanitize_public_text(
            "The company appears to earn through software-led platforms, communication workflows, and managed technology services."
        )
    return sanitize_public_text(
        "The available evidence suggests the company earns by supplying specialised products, subsystems, and support work to institutional customers."
    )


def build_customer_summary(source_bundle: Dict[str, Any], items: List[Dict[str, Any]]) -> Optional[str]:
    customer_labels = _customer_labels(source_bundle)
    if not customer_labels:
        return sanitize_public_text("The available evidence does not clearly establish the full customer mix.")
    pays = []
    integrates = []
    uses = []
    for label in customer_labels:
        if label in {"enterprise customer", "telecom operator", "international customer", "government agency"}:
            pays.append(label)
            uses.append(label)
        elif label in {"defence integrator", "original equipment manufacturer"}:
            pays.append(label)
            integrates.append(label)
    sentences = []
    if pays:
        sentences.append(f"The available evidence points to {_join_human_list(pays)} as the main paying customers.")
    if integrates:
        sentences.append(f"Integration and programme delivery also appear to involve {_join_human_list(integrates)}.")
    if uses and not integrates:
        sentences.append(f"The visible end users appear to include {_join_human_list(uses)}.")
    return sanitize_public_text(" ".join(sentences))


def build_revenue_logic_summary(source_bundle: Dict[str, Any], items: List[Dict[str, Any]]) -> Optional[str]:
    model_text = _latest_business_model_text(source_bundle).lower()
    if any(token in model_text for token in ("cpaas", "saas", "platform", "messaging", "marketing automation", "cloud communications")):
        return sanitize_public_text(
            "Revenue appears tied to enterprise communication platforms, messaging services, managed deployments, and communication volumes."
        )
    if "contract" in model_text or "project" in model_text or "order" in model_text:
        return sanitize_public_text(
            "Revenue appears to follow a project path: win an order or programme, design and build the system, complete testing or qualification, then bill and collect against delivery or acceptance milestones."
        )
    return sanitize_public_text(
        "The available evidence does not show product-level revenue contribution, but the visible offerings appear tied to customer programmes rather than recurring subscription revenue."
    )


def build_open_questions(items: List[Dict[str, Any]], source_bundle: Dict[str, Any]) -> List[str]:
    questions: List[str] = []
    if any(item["revenue_contribution_status"] == "unknown" for item in items):
        questions.append("Which offerings contribute the most revenue?")
    if any(item["classification"] == "software_product" for item in items):
        questions.append("How much revenue comes from software or tool-based offerings?")
    if any(item["role_in_business"] == "supporting service" for item in items):
        questions.append("Are service revenues growing faster than product revenues?")
    if any(item["role_in_business"] == "capability that enables larger contracts" for item in items):
        questions.append("Which capabilities directly help the company win larger contracts?")
    if not questions:
        questions.append("How concentrated is revenue by customer or programme?")
    return [sanitize_public_text(question) for question in questions[:4]]


def infer_customer_type(source_bundle: Dict[str, Any], classification: str) -> str:
    labels = _customer_labels(source_bundle)
    if not labels:
        return "Customer type is not clearly established in the available evidence."
    return ", ".join(labels[:3])


def _customer_types_for_item(source_bundle: Dict[str, Any], classification: str) -> List[str]:
    labels = _customer_labels(source_bundle)
    if classification in {"service", "engineering_service", "manufacturing_service"} and "defence integrator" in labels:
        return [label for label in labels if label != "international customer"][:3]
    return labels[:3]


def infer_revenue_model(text: str, classification: str) -> str:
    lowered = str(text or "").lower()
    if classification in {"manufacturing_service"}:
        return "enabling capability rather than separately disclosed revenue"
    if "milestone" in lowered or "acceptance" in lowered:
        return "delivery or milestone-based billing"
    if "service" in lowered:
        return "service or support engagement"
    return "project or programme delivery"


def _customer_labels(source_bundle: Dict[str, Any]) -> List[str]:
    collected_text = " ".join(
        text.lower()
        for _, _, text in _collect_source_texts(source_bundle)
        if str(text).strip()
    )
    analysis_sources = []
    for key in ("buffett_analysis", "graham_analysis", "fisher_analysis", "munger_analysis", "lynch_analysis"):
        payload = ((source_bundle.get("sources") or {}).get(key) or {}).get("payload") or {}
        analysis_sources.extend(str(item).lower() for item in payload.get("key_findings", []) if str(item).strip())
        analysis_sources.extend(str(item).lower() for item in payload.get("red_flags", []) if str(item).strip())
        analysis_sources.extend(str(item).lower() for item in payload.get("open_uncertainties", []) if str(item).strip())
    text = f"{_latest_business_model_text(source_bundle).lower()} {collected_text} {' '.join(analysis_sources)}"
    labels: List[str] = []
    platform_context = any(token in text for token in ("cpaas", "messaging platform", "communications platform", "enterprise communications", "cloud communications", "marketing automation"))
    defence_context = any(token in text for token in ("defence", "aerospace", "radar", "electronic warfare", "drdo", "isro", "mod "))
    if platform_context:
        labels.append("enterprise customer")
        if any(token in text for token in ("telecom", "telco", "operator", "carrier")):
            labels.append("telecom operator")
    if defence_context and any(token in text for token in ("mod", "drdo", "isro", "government")):
        labels.append("government agency")
    if defence_context and "oem" in text:
        labels.append("original equipment manufacturer")
    if defence_context and ("defence" in text or "integrator" in text):
        labels.append("defence integrator")
    if "export" in text or "international" in text:
        labels.append("international customer")
    if not labels:
        return []
    unique = []
    for label in labels:
        if label not in unique:
            unique.append(label)
    return unique


def group_description(title: str) -> str:
    mapping = {
        "Products": "Direct offerings that can be sold as products or delivered systems.",
        "Systems and solutions": "Larger systems or subsystems that appear to anchor customer delivery.",
        "Subsystems": "Smaller modules or subsystems supplied into larger defence or space programmes.",
        "Software and tools": "Software-led tools or embedded logic that support the wider offering set.",
        "Software and platforms": "Software platforms and tools used to deliver customer communication or workflow services.",
        "Services": "Service layers that help deliver, integrate, or support customer systems.",
        "Capabilities": "Capabilities that seem to enable larger customer programmes rather than stand alone as disclosed revenue lines.",
        "Other offerings": "Additional offerings that are visible but less clearly disclosed.",
    }
    return mapping.get(title, "Offerings grouped from the available company-memory evidence.")


def _public_group_name(group_hint: str, classification: str) -> str:
    if classification == "subsystem":
        return "subsystem"
    mapping = {
        "Products": "product",
        "Systems and solutions": "system",
        "Software and platforms": "platform",
        "Software and tools": "product",
        "Services": "service",
        "Capabilities": "capability",
        "Other offerings": "product",
    }
    return mapping.get(group_hint, "product")


def _join_human_list(values: List[str]) -> str:
    cleaned = [value for value in values if value]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def _collect_source_texts(source_bundle: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    texts: List[Tuple[str, str, str]] = []
    sources = source_bundle.get("sources") or {}
    pcim = ((sources.get("pcim") or {}).get("payload")) or {}
    cim = ((sources.get("cim") or {}).get("payload")) or {}
    for item in ((pcim.get("business_understanding") or {}).get("business_model_by_year", []) or []):
        if not isinstance(item, dict):
            continue
        year = str(item.get("year") or "")
        for key in ("business_summary", "business_model", "value_creation"):
            value = str(item.get(key) or "").strip()
            if value:
                texts.append(("pcim_business_model", year, value))
        for characteristic in item.get("characteristics", []) or []:
            value = str(characteristic or "").strip()
            if value:
                texts.append(("pcim_business_model", year, value))

    for item in cim.get("business_model", []) or []:
        if not isinstance(item, dict):
            continue
        year = str(item.get("year") or "")
        for key in ("business_summary", "business_model", "value_creation"):
            value = str(item.get(key) or "").strip()
            if value:
                texts.append(("cim_business_model", year, value))
        for characteristic in item.get("characteristics", []) or []:
            value = str(characteristic or "").strip()
            if value:
                texts.append(("cim_business_model", year, value))

    for yearly in cim.get("initiatives", []) or []:
        if not isinstance(yearly, dict):
            continue
        year = str(yearly.get("year") or "")
        for item in yearly.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("value") or "").strip()
            if value:
                texts.append(("cim_initiative", year, value))

    for yearly in cim.get("projects", []) or []:
        if not isinstance(yearly, dict):
            continue
        year = str(yearly.get("year") or "")
        for item in yearly.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("value") or "").strip()
            if value:
                texts.append(("cim_project", year, value))

    return texts


def _latest_business_model_text(source_bundle: Dict[str, Any]) -> str:
    sources = source_bundle.get("sources") or {}
    pcim = ((sources.get("pcim") or {}).get("payload")) or {}
    latest = ((pcim.get("business_understanding") or {}).get("latest_business_view") or {}).get("business_model") or {}
    parts = []
    for key in ("business_summary", "business_model", "value_creation"):
        value = str(latest.get(key) or "").strip()
        if value:
            parts.append(value)
    if parts:
        return " ".join(parts).strip()

    business_models = ((pcim.get("business_understanding") or {}).get("business_model_by_year") or [])
    latest_year = sorted(
        [item for item in business_models if isinstance(item, dict)],
        key=lambda item: _year_sort_key(item.get("year")),
    )
    if latest_year:
        fallback = latest_year[-1]
        fallback_parts = []
        for key in ("business_summary", "business_model", "value_creation"):
            value = str(fallback.get(key) or "").strip()
            if value:
                fallback_parts.append(value)
        return " ".join(fallback_parts).strip()

    cim = ((sources.get("cim") or {}).get("payload")) or {}
    cim_models = cim.get("business_model") or []
    latest_cim = sorted(
        [item for item in cim_models if isinstance(item, dict)],
        key=lambda item: _year_sort_key(item.get("year")),
    )
    if latest_cim:
        fallback = latest_cim[-1]
        fallback_parts = []
        for key in ("business_summary", "business_model", "value_creation"):
            value = str(fallback.get(key) or "").strip()
            if value:
                fallback_parts.append(value)
        return " ".join(fallback_parts).strip()

    return ""


def _merge_evidence_status(first: str, second: str) -> str:
    order = {"direct": 5, "derived": 4, "partial": 3, "unreliable": 2, "missing": 1}
    return first if order.get(first, 0) >= order.get(second, 0) else second


def _merge_revenue_status(first: str, second: str) -> str:
    order = {"known": 4, "partial": 3, "unknown": 2, "not_applicable": 1}
    return first if order.get(first, 0) >= order.get(second, 0) else second


def _year_sort_key(value: Any) -> int:
    text = str(value or "").lower().replace("fy", "").strip()
    try:
        return int(text)
    except ValueError:
        return 0


def _slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")
