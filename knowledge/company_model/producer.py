from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .contract import SCHEMA_VERSION, confidence, evidence_ref
from .evidence_adapter import CompanyModelSources, load_company_model_sources, loaded_payload, yearly_payloads
from .validator import validate_company_model


def build_company_model(company_slug: str, *, companies_root: Path | str = Path("companies"), generated_at: str | None = None) -> Dict[str, Any]:
    sources = load_company_model_sources(company_slug, companies_root=companies_root)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    builder = CompanyModelProducer(sources=sources, generated_at=generated_at)
    return builder.build()


def write_company_model(company_slug: str, *, companies_root: Path | str = Path("companies"), generated_at: str | None = None) -> Dict[str, Path]:
    payload = build_company_model(company_slug, companies_root=companies_root, generated_at=generated_at)
    validation = validate_company_model(payload)
    output_dir = Path(companies_root) / company_slug / "company_memory" / "company_model"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = payload["source_manifest"]
    paths = {
        "company_model.json": output_dir / "company_model.json",
        "company_model_validation.json": output_dir / "company_model_validation.json",
        "company_model_manifest.json": output_dir / "company_model_manifest.json",
    }
    paths["company_model.json"].write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["company_model_validation.json"].write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["company_model_manifest.json"].write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    if validation["status"] == "fail":
        raise ValueError(f"Company Model validation failed for {company_slug}: {validation['errors']}")
    return paths


class CompanyModelProducer:
    def __init__(self, *, sources: CompanyModelSources, generated_at: str) -> None:
        self.sources = sources
        self.company_slug = sources.company_slug
        self.generated_at = generated_at
        self.pcim = loaded_payload(sources, "pcim")
        self.cim = loaded_payload(sources, "cim")
        self.blueprints = yearly_payloads(sources, "business_blueprint")
        self.classifications = yearly_payloads(sources, "business_classification")

    def build(self) -> Dict[str, Any]:
        latest = self._latest_business_model()
        if not latest:
            return self._insufficient_payload()

        model_type = self._classify_business_model_type(latest)
        evidence = self._business_evidence(latest)
        offerings = self._build_offerings(latest, model_type, evidence)
        customers = self._build_customers(latest, model_type, evidence)
        revenue_engines = self._build_revenue_engines(latest, model_type, evidence)
        economic_drivers = self._build_economic_drivers(latest, revenue_engines, evidence)
        dependencies = self._build_dependencies(latest, model_type, evidence)
        evolution = self._build_business_model_evolution()
        uncertainties = self._build_uncertainties(customers, revenue_engines, offerings)

        coverage_status = "supported" if offerings and customers and revenue_engines else "partial"
        what_sells = [item["name"] for item in offerings[:5]]
        who_pays = [item["payer_type"] for item in customers[:5]]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "company_slug": self.company_slug,
            "generated_at": self.generated_at,
            "coverage_status": coverage_status,
            "company_identity": self._company_identity(evidence),
            "current_business_model": {
                "summary": latest["summary"],
                "business_model_type": model_type,
                "what_company_does": latest["what_company_does"],
                "what_it_sells": what_sells,
                "who_pays": who_pays,
                "who_uses": [item["end_user_type"] for item in customers[:5] if item.get("end_user_type")],
                "use_cases": self._build_use_cases(latest, model_type),
                "how_revenue_happens": self._revenue_summary(revenue_engines, latest, model_type),
                "economic_mechanism": self._economic_mechanism(latest, model_type, revenue_engines),
                "source_period": latest["source_period"],
                "confidence": confidence("high", basis=["PCIM latest business view" if latest["source_artifact"] == "pcim_v1.json" else "Business blueprint"]),
                "evidence": evidence,
            },
            "offerings": offerings,
            "customers": customers,
            "revenue_engines": revenue_engines,
            "economic_drivers": economic_drivers,
            "dependencies": dependencies,
            "business_model_evolution": evolution,
            "uncertainties": uncertainties,
            "source_manifest": self._source_manifest(coverage_status),
        }
        return payload

    def _insufficient_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "company_slug": self.company_slug,
            "generated_at": self.generated_at,
            "coverage_status": "insufficient_evidence",
            "company_identity": self._company_identity([]),
            "current_business_model": {
                "summary": "",
                "business_model_type": "other",
                "what_company_does": "",
                "what_it_sells": [],
                "who_pays": [],
                "who_uses": [],
                "use_cases": [],
                "how_revenue_happens": "",
                "economic_mechanism": "",
                "source_period": "",
                "confidence": confidence("low", limitations=["No governed business model source was available."]),
                "evidence": [],
            },
            "offerings": [],
            "customers": [],
            "revenue_engines": [],
            "economic_drivers": [],
            "dependencies": [],
            "business_model_evolution": [],
            "uncertainties": [
                {
                    "uncertainty_id": "missing_business_model_evidence",
                    "question": "What does the company do and how does it earn revenue?",
                    "why_it_matters": "The Company Model cannot become canonical without governed business-model evidence.",
                    "blocking": True,
                    "evidence_needed": ["business_blueprint.json or pcim_v1.json business_understanding"],
                }
            ],
            "source_manifest": self._source_manifest("insufficient_evidence"),
        }

    def _latest_business_model(self) -> Optional[Dict[str, Any]]:
        pcim_business = ((self.pcim.get("business_understanding") or {}).get("latest_business_view") or {}).get("business_model") or {}
        if pcim_business:
            return self._normalize_business_model(pcim_business, source_artifact="pcim_v1.json", field_path="business_understanding.latest_business_view.business_model")
        yearly_models = []
        for entry in self.blueprints:
            understanding = (entry.get("payload") or {}).get("business_understanding") or {}
            if understanding:
                yearly_models.append((entry["year"], understanding, entry["relative_path"]))
        if not yearly_models:
            return None
        year, understanding, relative_path = sorted(yearly_models, key=lambda item: _year_sort_key(item[0]))[-1]
        normalized = self._normalize_business_model(understanding, source_artifact=relative_path, field_path="business_understanding")
        normalized["source_period"] = year
        return normalized

    def _normalize_business_model(self, item: Dict[str, Any], *, source_artifact: str, field_path: str) -> Dict[str, Any]:
        summary = _clean(item.get("business_summary") or item.get("summary"))
        model = _clean(item.get("business_model"))
        value = _clean(item.get("value_creation"))
        competitive = _clean(item.get("competitive_position_summary") or item.get("competitive_position"))
        source_period = _clean(item.get("source_year") or item.get("year"))
        return {
            "summary": summary or model,
            "business_model": model,
            "value_creation": value,
            "competitive_position": competitive,
            "characteristics": [_clean(value) for value in item.get("characteristics", []) if _clean(value)],
            "source_period": source_period,
            "source_artifact": source_artifact,
            "field_path": field_path,
            "evidence_ids": [str(value) for value in item.get("evidence_ids", []) if str(value).strip()],
            "what_company_does": summary or model,
        }

    def _business_evidence(self, latest: Dict[str, Any]) -> List[Dict[str, Any]]:
        evidence_ids = latest.get("evidence_ids") or []
        if evidence_ids:
            return [
                evidence_ref(
                    source_artifact=latest["source_artifact"],
                    source_period=latest.get("source_period") or "",
                    evidence_id=evidence_ids[0],
                    field_path=latest["field_path"],
                    excerpt=_truncate(latest.get("summary") or latest.get("business_model") or "", 260),
                )
            ]
        return [
            evidence_ref(
                source_artifact=latest["source_artifact"],
                source_period=latest.get("source_period") or "",
                field_path=latest["field_path"],
                excerpt=_truncate(latest.get("summary") or latest.get("business_model") or "", 260),
            )
        ]

    def _company_identity(self, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        company_value = self.pcim.get("company") if isinstance(self.pcim, dict) else None
        name = str(company_value or self.company_slug).strip()
        return {
            "name": name,
            "legal_name": name if name != self.company_slug else "",
            "ticker": "",
            "industry": "",
            "confidence": confidence("medium" if evidence else "low", basis=["Company-scoped artifact path"]),
            "evidence": list(evidence[:1]),
        }

    def _classify_business_model_type(self, latest: Dict[str, Any]) -> str:
        text = self._all_business_text(latest)
        dnas = " ".join(self._latest_dnas()).lower()
        if _has_any(f"{text} {dnas}", ["music", "catalogue", "catalog", "licensing", "royalty", "streaming", "content", "ip library", "youtube"]):
            return "content_ip"
        platform_score = _match_score(text, ["cpaas", "enterprise messaging", "communications platform", "messaging platform", "telecom operator", "saas", "software platform"])
        manufacturing_score = _match_score(text, ["semiconductor", "electronic component", "defence", "aerospace", "radar", "electronic warfare", "manufacturing", "plant", "factory", "cleanroom"])
        if manufacturing_score >= max(2, platform_score):
            return "manufacturing"
        if platform_score > 0 or _has_any(f"{text} {dnas}", ["platform", "messaging", "communications", "saas", "software"]):
            return "platform"
        if _has_any(f"{text} {dnas}", ["service", "support", "consulting"]):
            return "services"
        return "other"

    def _latest_dnas(self) -> List[str]:
        if not self.classifications:
            return []
        return list((self.classifications[-1].get("payload") or {}).get("business_dnas") or (self.classifications[-1].get("payload") or {}).get("dnas") or [])

    def _all_business_text(self, latest: Dict[str, Any]) -> str:
        return " ".join(
            [
                latest.get("summary") or "",
                latest.get("business_model") or "",
                latest.get("value_creation") or "",
                latest.get("competitive_position") or "",
                " ".join(latest.get("characteristics") or []),
            ]
        ).lower()

    def _build_offerings(self, latest: Dict[str, Any], model_type: str, evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        text = self._all_business_text(latest)
        patterns = [
            ("enterprise_communications_platform", "Enterprise communications platform", "platform", ["cpaas", "enterprise messaging", "communications platform", "messaging"]),
            ("security_products", "AI/security communication products", "platform", ["anti-scam", "fraud", "security", "trubloq"]),
            ("marketing_automation", "Marketing automation tools", "platform", ["marketing automation", "predictive analytics", "customer engagement", "push", "in-app"]),
            ("defence_electronics_systems", "Defence and aerospace electronics systems", "product", ["defence", "aerospace", "radar", "electronic warfare", "avionics", "satellite"]),
            ("manufacturing_testing_capability", "Manufacturing and testing capability", "manufacturing_capability", ["manufacturing", "manufacturing/testing", "emi-emc", "integration facility", "cleanroom", "plant", "factory"]),
            ("music_catalogue", "Music catalogue and content rights", "content_ip", ["music catalogue", "catalogue", "catalog", "songs", "content rights", "ip library"]),
            ("digital_content_distribution", "Digital music distribution and licensing", "service", ["streaming", "youtube", "spotify", "apple music", "licensing", "royalties"]),
            ("semiconductor_components", "Semiconductor and electronic components", "product", ["semiconductor", "electronic components", "led", "sensor modules", "ceramic substrates"]),
            ("advanced_manufacturing_capacity", "Advanced manufacturing capacity", "manufacturing_capability", ["greenfield", "plant", "facility", "automation", "digital twins", "capacity"]),
        ]
        offerings = []
        for offering_id, name, category, aliases in patterns:
            if not _has_any(text, aliases):
                continue
            if category == "manufacturing_capability" and model_type != "manufacturing":
                continue
            if offering_id == "semiconductor_components" and not _has_any(text, ["semiconductor", "electronic components", "ceramic substrates", "sensor modules"]):
                continue
            offerings.append(
                {
                    "offering_id": offering_id,
                    "name": name,
                    "category": category,
                    "description": self._offering_description(name, model_type, latest),
                    "customer_problem_solved": self._customer_problem(name, model_type),
                    "revenue_role": "primary" if len(offerings) == 0 else "secondary",
                    "current_or_historical": "current",
                    "source_period": latest.get("source_period") or "",
                    "confidence": confidence("medium", basis=["Matched governed business-model evidence"]),
                    "evidence": evidence,
                }
            )
        if not offerings and latest.get("summary"):
            offerings.append(
                {
                    "offering_id": "business_offering_from_governed_summary",
                    "name": _truncate(latest.get("summary") or "Business offering", 80),
                    "category": "other",
                    "description": latest.get("business_model") or latest.get("summary"),
                    "customer_problem_solved": latest.get("value_creation") or "Customer problem not specifically disclosed.",
                    "revenue_role": "unknown",
                    "current_or_historical": "current",
                    "source_period": latest.get("source_period") or "",
                    "confidence": confidence("low", limitations=["Offering extracted from broad business summary only."]),
                    "evidence": evidence,
                }
            )
        return offerings[:5]

    def _build_customers(self, latest: Dict[str, Any], model_type: str, evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        text = self._all_business_text(latest)
        customers = []
        specs = [
            ("enterprise_customers", "large enterprises", "enterprise users", "enterprise", ["enterprise", "b2b"]),
            ("telecom_operators", "telecom operators", "telecom subscribers protected through operator networks", "operator", ["telecom", "operator", "carrier"]),
            ("government_defence_customers", "government defence/aerospace customers", "defence and space end users", "government", ["government", "ministry of defence", "mod", "defence customers", "defence and aerospace customers", "national defence programmes", "isro", "armed forces"]),
            ("oem_integrators", "OEM or system integrator customers", "programme end users", "OEM", ["oem", "integrator"]),
            ("streaming_platforms", "digital platforms and licensing partners", "listeners/viewers on digital platforms", "platform_partner", ["youtube", "spotify", "apple music", "amazon", "streaming platform", "licensing"]),
            ("overseas_customers", "international customers or subsidiaries", "international users", "international", ["international", "overseas", "export"]),
            ("industrial_customers", "industrial customers", "industrial users", "industrial", ["industrial users", "industrial customers", "machine monitoring"]),
            ("manufacturing_customers", "electronics or semiconductor customers", "industrial/electronics end markets", "industrial", ["semiconductor", "electronic components", "led", "sensor modules"]),
        ]
        for customer_id, payer, user, relationship, aliases in specs:
            if not _has_any(text, aliases):
                continue
            if customer_id == "government_defence_customers" and not (
                _has_any(text, ["defence", "aerospace", "isro", "armed forces"])
                and _has_any(text, ["government", "ministry of defence", "mod", "defence customers", "defence and aerospace customers", "national defence programmes", "isro", "armed forces"])
            ):
                continue
            if customer_id == "manufacturing_customers" and model_type != "manufacturing":
                continue
            customers.append(
                {
                    "customer_segment_id": customer_id,
                    "payer_type": payer,
                    "end_user_type": user,
                    "relationship_type": relationship,
                    "concentration_known": False,
                    "concentration_evidence": "",
                    "confidence": confidence("medium", basis=["Customer segment inferred from governed business model text"]),
                    "evidence": evidence,
                }
            )
        return customers[:5]

    def _build_revenue_engines(self, latest: Dict[str, Any], model_type: str, evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        text = self._all_business_text(latest)
        engine_specs = []
        if model_type == "platform":
            engine_specs.append(("platform_usage_services", "Platform, messaging, managed deployment, or usage-linked service revenue", "usage"))
        if model_type == "content_ip":
            if _has_any(text, ["royalty", "streaming"]):
                engine_specs.append(("streaming_royalties", "Streaming royalties from digital music consumption", "royalty"))
            if _has_any(text, ["licensing", "rights"]):
                engine_specs.append(("content_licensing", "Licensing and rights monetization from content IP", "license"))
            if _has_any(text, ["advertising", "youtube"]):
                engine_specs.append(("audience_ad_revenue", "Advertising revenue linked to owned digital audience reach", "ad_revenue"))
        if model_type == "manufacturing":
            if _has_any(text, ["contract", "project", "customer order", "defence", "aerospace"]):
                engine_specs.append(("project_system_delivery", "Project/order delivery revenue from engineered systems or components", "milestone"))
            else:
                engine_specs.append(("manufactured_product_sales", "Sale of manufactured products or components supported by production capacity", "sale"))
        if model_type == "services":
            engine_specs.append(("service_fees", "Service fees for customer support or delivery work", "service_fee"))
        if not engine_specs:
            engine_specs.append(("revenue_model_unclear", latest.get("business_model") or "Revenue mechanism not clearly disclosed", "unknown"))
        return [
            {
                "engine_id": engine_id,
                "description": description,
                "billing_basis": billing,
                "cash_conversion_notes": "Cash conversion requires separate financial evidence and is not inferred from the business model alone.",
                "working_capital_implications": self._working_capital_implication(model_type, billing),
                "source_period": latest.get("source_period") or "",
                "confidence": confidence("medium", basis=["Revenue engine resolved from governed business model text"]),
                "evidence": evidence,
            }
            for engine_id, description, billing in engine_specs[:4]
        ]

    def _build_economic_drivers(self, latest: Dict[str, Any], revenue_engines: List[Dict[str, Any]], evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        drivers = []
        for phrase in [latest.get("value_creation"), latest.get("competitive_position"), *latest.get("characteristics", [])]:
            cleaned = _clean(phrase)
            if not cleaned:
                continue
            drivers.append(
                {
                    "driver": _truncate(cleaned, 90),
                    "mechanism": _truncate(cleaned, 220),
                    "direction": "strengthens",
                    "evidence": evidence,
                }
            )
            if len(drivers) >= 4:
                break
        return drivers

    def _build_dependencies(self, latest: Dict[str, Any], model_type: str, evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        text = self._all_business_text(latest)
        specs = [
            ("technology", "technology", ["technology", "software", "automation", "digital", "ai", "platform"]),
            ("manufacturing capacity", "capacity", ["capacity", "plant", "facility", "manufacturing", "cleanroom"]),
            ("customer/channel access", "customer_access", ["customer", "operator", "platform partnership", "youtube", "spotify", "government"]),
            ("capital availability", "capital", ["qip", "debt", "loan", "funding", "capex", "working capital"]),
            ("content catalogue", "content_catalog", ["catalogue", "catalog", "songs", "content", "rights"]),
            ("regulatory/program qualification", "regulation", ["defence", "compliance", "qualification", "regulatory", "government"]),
        ]
        dependencies = []
        for label, dep_type, aliases in specs:
            if not _has_any(text, aliases):
                continue
            dependencies.append(
                {
                    "dependency": label,
                    "type": dep_type,
                    "why_it_matters": self._dependency_mechanism(label, model_type),
                    "evidence": evidence,
                }
            )
        return dependencies[:5]

    def _build_use_cases(self, latest: Dict[str, Any], model_type: str) -> List[str]:
        text = self._all_business_text(latest)
        if model_type == "platform":
            return _dedupe(["enterprise communications", "customer engagement", "fraud/spam reduction" if "fraud" in text or "scam" in text else "workflow communication"])
        if model_type == "content_ip":
            return ["music consumption, licensing, and audience monetization"]
        if model_type == "manufacturing":
            if _has_any(text, ["defence", "aerospace", "radar"]):
                return ["defence/aerospace programme delivery", "specialised electronics manufacturing"]
            return ["electronic component production", "capacity-led manufacturing scale-up"]
        return []

    def _build_business_model_evolution(self) -> List[Dict[str, Any]]:
        entries = []
        models = ((self.pcim.get("business_understanding") or {}).get("business_model_by_year") or [])
        normalized = [self._normalize_business_model(item, source_artifact="pcim_v1.json", field_path="business_understanding.business_model_by_year") for item in models if isinstance(item, dict)]
        normalized = [item for item in normalized if item.get("source_period") and (item.get("summary") or item.get("business_model"))]
        for previous, current in zip(normalized, normalized[1:]):
            if _similar(previous.get("business_model") or previous.get("summary"), current.get("business_model") or current.get("summary")):
                continue
            entries.append(
                {
                    "change_id": f"{previous['source_period']}_to_{current['source_period']}_business_model_change",
                    "from_period": previous["source_period"],
                    "to_period": current["source_period"],
                    "what_changed": _truncate(current.get("summary") or current.get("business_model") or "", 220),
                    "why_it_changed": _truncate(current.get("value_creation") or "Later governed evidence shows a changed or more specific business emphasis.", 220),
                    "evidence_of_change": _truncate(current.get("business_model") or current.get("summary") or "", 220),
                    "thesis_impact": "unresolved",
                    "confidence": confidence("medium", basis=["PCIM business_model_by_year"]),
                    "evidence": self._business_evidence(current),
                }
            )
            if len(entries) >= 6:
                break
        return entries

    def _build_uncertainties(self, customers: List[Dict[str, Any]], revenue_engines: List[Dict[str, Any]], offerings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        uncertainties = []
        if customers and not any(item.get("concentration_known") for item in customers):
            uncertainties.append(
                {
                    "uncertainty_id": "customer_concentration_unknown",
                    "question": "How concentrated is revenue across the main customer segments?",
                    "why_it_matters": "Customer concentration can change revenue durability and bargaining power.",
                    "blocking": False,
                    "evidence_needed": ["customer-level revenue or segment concentration disclosure"],
                }
            )
        if offerings and not any(item.get("revenue_role") == "primary" and item.get("revenue_role") != "unknown" for item in offerings):
            uncertainties.append(
                {
                    "uncertainty_id": "offering_revenue_mix_unknown",
                    "question": "Which offering contributes most to revenue and profit?",
                    "why_it_matters": "Offering mix affects margin quality, growth runway, and customer dependence.",
                    "blocking": False,
                    "evidence_needed": ["product/service revenue split"],
                }
            )
        if revenue_engines:
            uncertainties.append(
                {
                    "uncertainty_id": "cash_conversion_requires_financial_truth",
                    "question": "How quickly does reported revenue convert into cash?",
                    "why_it_matters": "The business model describes revenue formation, but cash conversion requires audited financial evidence.",
                    "blocking": False,
                    "evidence_needed": ["cash-flow and working-capital evidence"],
                }
            )
        return uncertainties[:4]

    def _source_manifest(self, coverage_status: str) -> Dict[str, Any]:
        return {
            "schema_version": "company_model_manifest.v1",
            "company_slug": self.company_slug,
            "generated_at": self.generated_at,
            "coverage_status": coverage_status,
            "sources_used": self.sources.source_files_found,
            "sources_missing": self.sources.source_files_missing,
            "legacy_adapter_used": self.sources.legacy_adapter_used,
            "legacy_adapter_sources": self.sources.legacy_adapter_sources,
            "legacy_adapter_sunset_condition": "Delete once Company Model producer reads native governed observations and downstream consumers no longer require PCIM/multi-year compatibility inputs.",
            "company_mismatch_errors": self.sources.warnings,
        }

    def _revenue_summary(self, revenue_engines: List[Dict[str, Any]], latest: Dict[str, Any], model_type: str) -> str:
        if revenue_engines:
            return "; ".join(item["description"] for item in revenue_engines[:3])
        return latest.get("business_model") or ""

    def _economic_mechanism(self, latest: Dict[str, Any], model_type: str, revenue_engines: List[Dict[str, Any]]) -> str:
        value = latest.get("value_creation") or latest.get("competitive_position") or ""
        if value:
            return value
        if model_type == "platform":
            return "The business creates value when customer usage of the platform turns communication workflows into recurring or repeat service revenue."
        if model_type == "content_ip":
            return "The business creates value when owned content rights continue generating royalties, licensing income, or advertising economics across platforms."
        if model_type == "manufacturing":
            return "The business creates value when manufacturing capacity and technical qualification convert customer orders into delivered products and cash collection."
        return "The economic mechanism is not sufficiently established by governed evidence."

    def _offering_description(self, name: str, model_type: str, latest: Dict[str, Any]) -> str:
        return _truncate(latest.get("business_model") or latest.get("summary") or name, 220)

    def _customer_problem(self, name: str, model_type: str) -> str:
        if model_type == "platform":
            return "Helps customers operate communication, engagement, or security workflows."
        if model_type == "content_ip":
            return "Supplies monetizable content rights and audience-relevant music assets."
        if model_type == "manufacturing":
            return "Supplies specialised products, components, or manufacturing capability customers cannot easily build internally."
        return "Customer use case is only partly visible in governed evidence."

    def _working_capital_implication(self, model_type: str, billing: str) -> str:
        if billing in {"milestone", "sale"}:
            return "Working capital can depend on inventory, project execution, acceptance timing, and customer collections."
        if billing in {"royalty", "license", "ad_revenue"}:
            return "Working capital is likely less asset-heavy than manufacturing, but platform remittances and rights accounting still need evidence."
        if billing == "usage":
            return "Cash timing depends on usage billing, enterprise/operator terms, and collections evidence."
        return "Working-capital effect is not established."

    def _dependency_mechanism(self, label: str, model_type: str) -> str:
        mechanisms = {
            "technology": "Technology quality affects customer adoption, differentiation, and delivery reliability.",
            "manufacturing capacity": "Capacity matters only if it converts into utilization, delivery, and returns.",
            "customer/channel access": "Customer or channel access determines whether capability becomes revenue.",
            "capital availability": "Capital availability affects the ability to fund growth before returns are proven.",
            "content catalogue": "Catalogue depth determines how much content can be repeatedly monetized.",
            "regulatory/program qualification": "Qualification and compliance affect whether customers can buy and deploy the offering.",
        }
        return mechanisms.get(label, "The dependency affects whether the business model can convert capability into economics.")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _truncate(value: Any, limit: int) -> str:
    text = _clean(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _has_any(text: str, aliases: Iterable[str]) -> bool:
    lowered = str(text or "").lower()
    for alias in aliases:
        needle = str(alias or "").lower().strip()
        if not needle:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", lowered):
            return True
    return False


def _match_score(text: str, aliases: Iterable[str]) -> int:
    return sum(1 for alias in aliases if _has_any(text, [alias]))


def _dedupe(values: Iterable[str]) -> List[str]:
    result = []
    for value in values:
        cleaned = _clean(value)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _year_sort_key(value: Any) -> int:
    match = re.search(r"(\d{2,4})", str(value or "").lower())
    if not match:
        return -1
    number = int(match.group(1))
    return number % 100 if number >= 100 else number


def _similar(left: Any, right: Any) -> bool:
    left_words = set(re.findall(r"[a-z0-9]+", str(left or "").lower()))
    right_words = set(re.findall(r"[a-z0-9]+", str(right or "").lower()))
    if not left_words or not right_words:
        return False
    overlap = len(left_words & right_words) / max(len(left_words | right_words), 1)
    return overlap >= 0.72


def main(argv: Optional[List[str]] = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build canonical Company Model v1 artifacts.")
    parser.add_argument("company")
    parser.add_argument("--companies-root", default="companies")
    args = parser.parse_args(argv)
    paths = write_company_model(args.company, companies_root=Path(args.companies_root))
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
