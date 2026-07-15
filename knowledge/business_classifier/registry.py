from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from .constants import (
    DEFAULT_DISCOVERY_PROFILE,
    DEFAULT_EXTRACTION_PROFILE,
    DEFAULT_REPORT_TEMPLATE,
)


@dataclass(frozen=True)
class ArchetypeSignals:
    characteristic_patterns: List[str] = field(default_factory=list)
    keyword_groups: List[List[str]] = field(default_factory=list)
    text_keyword_groups: List[List[str]] = field(default_factory=list)
    positive_signals: List[str] = field(default_factory=list)
    negative_signals: List[str] = field(default_factory=list)
    evidence_patterns: List[str] = field(default_factory=list)
    confidence_hints: List[str] = field(default_factory=list)

    @classmethod
    def from_legacy_mapping(cls, mapping: Dict[str, Any]) -> "ArchetypeSignals":
        characteristic_patterns = list(mapping.get("characteristics", []))
        keyword_groups = [
            list(group)
            for group in mapping.get("keyword_groups", [])
        ]
        text_keyword_groups = [
            list(group)
            for group in mapping.get("text_keyword_groups", [])
        ]
        positive_signals = list(mapping.get("positive_signals", [])) or list(characteristic_patterns)
        evidence_patterns = list(mapping.get("evidence_patterns", [])) or [
            " ".join(group)
            for group in text_keyword_groups
        ]
        return cls(
            characteristic_patterns=characteristic_patterns,
            keyword_groups=keyword_groups,
            text_keyword_groups=text_keyword_groups,
            positive_signals=positive_signals,
            negative_signals=list(mapping.get("negative_signals", [])),
            evidence_patterns=evidence_patterns,
            confidence_hints=list(mapping.get("confidence_hints", [])),
        )

    def to_legacy_mapping(self) -> Dict[str, Any]:
        return {
            "characteristics": list(self.characteristic_patterns),
            "keyword_groups": [list(group) for group in self.keyword_groups],
            "text_keyword_groups": [list(group) for group in self.text_keyword_groups],
        }


@dataclass(frozen=True)
class ArchetypeDefaults:
    question_modules: List[str] = field(default_factory=list)
    discovery_profile: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "priority_entities": [],
            "priority_events": [],
        }
    )
    extraction_profile: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "high_priority_sections": [],
        }
    )
    report_template: str = DEFAULT_REPORT_TEMPLATE

    @classmethod
    def from_legacy_mapping(cls, mapping: Dict[str, Any]) -> "ArchetypeDefaults":
        discovery_profile = mapping.get("discovery_profile") or {}
        extraction_profile = mapping.get("extraction_profile") or {}
        return cls(
            question_modules=list(mapping.get("question_modules", [])),
            discovery_profile={
                "priority_entities": list(discovery_profile.get("priority_entities", [])),
                "priority_events": list(discovery_profile.get("priority_events", [])),
            },
            extraction_profile={
                "high_priority_sections": list(
                    extraction_profile.get("high_priority_sections", [])
                ),
            },
            report_template=mapping.get("report_template", DEFAULT_REPORT_TEMPLATE),
        )


@dataclass(frozen=True)
class ArchetypeDefinition:
    archetype_id: str
    dnas: List[str]
    definition: str
    signals: ArchetypeSignals = field(default_factory=ArchetypeSignals)
    defaults: ArchetypeDefaults = field(default_factory=ArchetypeDefaults)

    @classmethod
    def from_legacy_mapping(cls, mapping: Dict[str, Any]) -> "ArchetypeDefinition":
        dnas = list(mapping.get("dnas", []))
        archetype_id = mapping.get("archetype_id") or "+".join(dnas) or "custom"
        definition = mapping.get("definition") or (
            f"Transitional archetype definition for {', '.join(dnas)}."
            if dnas
            else "Transitional archetype definition."
        )
        return cls(
            archetype_id=archetype_id,
            dnas=dnas,
            definition=definition,
            signals=ArchetypeSignals.from_legacy_mapping(mapping),
            defaults=ArchetypeDefaults.from_legacy_mapping(mapping),
        )

    def to_legacy_mapping(self) -> Dict[str, Any]:
        return {
            "archetype_id": self.archetype_id,
            "definition": self.definition,
            **self.signals.to_legacy_mapping(),
            "dnas": list(self.dnas),
            "question_modules": list(self.defaults.question_modules),
            "discovery_profile": {
                "priority_entities": list(
                    self.defaults.discovery_profile.get("priority_entities", [])
                ),
                "priority_events": list(
                    self.defaults.discovery_profile.get("priority_events", [])
                ),
            },
            "extraction_profile": {
                "high_priority_sections": list(
                    self.defaults.extraction_profile.get("high_priority_sections", [])
                ),
            },
            "report_template": self.defaults.report_template,
            "positive_signals": list(self.signals.positive_signals),
            "negative_signals": list(self.signals.negative_signals),
            "evidence_patterns": list(self.signals.evidence_patterns),
            "confidence_hints": list(self.signals.confidence_hints),
        }


class Registry:
    def __init__(
        self,
        mappings: Iterable[Dict[str, Any] | ArchetypeDefinition] | None = None,
    ):
        self._archetypes = [
            self._coerce_archetype(entry)
            for entry in (
                list(mappings)
                if mappings is not None
                else self._default_archetypes()
            )
        ]

    @staticmethod
    def _coerce_archetype(
        entry: Dict[str, Any] | ArchetypeDefinition,
    ) -> ArchetypeDefinition:
        if isinstance(entry, ArchetypeDefinition):
            return entry
        return ArchetypeDefinition.from_legacy_mapping(entry)

    @classmethod
    def _default_archetypes(cls) -> List[ArchetypeDefinition]:
        return [
            ArchetypeDefinition(
                archetype_id="manufacturing",
                dnas=["Manufacturing"],
                definition=(
                    "Businesses whose economics are driven by physical production capacity, "
                    "capital deployment, plant utilization, and operational scale-up."
                ),
                signals=ArchetypeSignals(
                    characteristic_patterns=[
                        "Capital Intensive",
                        "Asset Heavy",
                        "Advanced Manufacturing",
                        "Advanced Manufacturing Automation",
                        "Advanced Manufacturing & Automation",
                        "Energy Efficiency",
                        "Energy Efficiency Focus",
                        "Energy Efficiency & Sustainability",
                        "Financial Flexibility",
                        "Strategic Capital Allocation",
                        "Diversified capital structure (debt, equity conversion, acquisitions)",
                    ],
                    keyword_groups=[
                        ["manufacturing"],
                        ["capacity"],
                        ["capital", "allocation"],
                        ["energy", "efficiency"],
                        ["sustainability"],
                    ],
                    text_keyword_groups=[
                        ["capacity", "expansion"],
                        ["vertical", "integration"],
                        ["production", "capacity"],
                        ["capital", "intensive"],
                        ["plant"],
                        ["facility"],
                    ],
                    positive_signals=[
                        "Capacity expansion and plant buildout",
                        "Capital-intensive operations",
                        "Operational efficiency and throughput improvement",
                    ],
                    negative_signals=[
                        "Pure software or asset-light recurring revenue without physical operations",
                    ],
                    evidence_patterns=[
                        "Plant/facility expansion",
                        "Capex-led growth",
                        "Production capacity scaling",
                    ],
                    confidence_hints=[
                        "Stronger when physical assets and production economics are explicit",
                    ],
                ),
                defaults=ArchetypeDefaults(
                    question_modules=["capital_allocation"],
                    discovery_profile={
                        "priority_entities": ["Plant", "Technology"],
                        "priority_events": ["Expansion", "Capacity Increase"],
                    },
                    extraction_profile={
                        "high_priority_sections": ["Operations", "Capex", "Technology"],
                    },
                    report_template="manufacturing_v1",
                ),
            ),
            ArchetypeDefinition(
                archetype_id="semiconductor",
                dnas=["Semiconductor"],
                definition=(
                    "Manufacturing businesses centered on semiconductor, wafer, substrate, "
                    "chip-packaging, or electronics-material fabrication economics."
                ),
                signals=ArchetypeSignals(
                    characteristic_patterns=[
                        "Semiconductor manufacturing",
                        "Wafer and substrate manufacturing",
                        "Electronics materials and components manufacturing",
                        "Advanced Manufacturing",
                        "Advanced Manufacturing Automation",
                        "Advanced Manufacturing & Automation",
                    ],
                    keyword_groups=[
                        ["advanced", "manufacturing"],
                        ["digital", "twin"],
                        ["precision", "automation"],
                    ],
                    text_keyword_groups=[
                        ["semiconductor"],
                        ["wafer"],
                        ["wafers"],
                        ["silicon", "wafer"],
                        ["sapphire", "wafer"],
                        ["substrate"],
                        ["substrates"],
                        ["htcc"],
                        ["ltcc"],
                        ["packaged", "chip"],
                        ["packaged", "chips"],
                        ["chip", "packaging"],
                        ["advanced", "electronic", "products"],
                        ["advanced", "electronic", "modules"],
                        ["electronics", "components"],
                        ["electronics", "materials"],
                        ["fabrication"],
                        ["process", "led", "electronics", "manufacturing"],
                    ],
                    positive_signals=[
                        "Wafer, substrate, or packaged-chip production",
                        "Electronics-materials fabrication",
                        "Process-led advanced electronics manufacturing",
                    ],
                    negative_signals=[
                        "General software or compliance platform language without hardware/process evidence",
                    ],
                    evidence_patterns=[
                        "Wafers, substrates, chip packaging",
                        "Fabrication/process manufacturing",
                    ],
                    confidence_hints=[
                        "Requires hardware/process evidence, not just general technology claims",
                    ],
                ),
                defaults=ArchetypeDefaults(
                    question_modules=["technology"],
                    discovery_profile={
                        "priority_entities": ["Technology", "Research"],
                        "priority_events": ["Product Launch", "R&D Expansion"],
                    },
                    extraction_profile={
                        "high_priority_sections": ["Technology", "R&D", "Intellectual Property"],
                    },
                    report_template="semiconductor_v1",
                ),
            ),
            ArchetypeDefinition(
                archetype_id="enterprise_platform",
                dnas=["Enterprise Platform"],
                definition=(
                    "Businesses whose economics come from enterprise-facing software or "
                    "platform infrastructure, often API-led, workflow-embedded, and "
                    "partner-integrated."
                ),
                signals=ArchetypeSignals(
                    characteristic_patterns=[
                        "Enterprise Platform",
                        "Enterprise Communications Platform",
                        "API-first platform architecture",
                        "Usage-linked enterprise platform monetization",
                        "Operational resilience through active-active infrastructure",
                    ],
                    keyword_groups=[
                        ["enterprise", "platform"],
                        ["messaging", "platform"],
                        ["communications", "platform"],
                        ["workflow", "platform"],
                        ["api", "first"],
                    ],
                    text_keyword_groups=[
                        ["messaging", "platform"],
                        ["communications", "platform"],
                        ["enterprise", "communications"],
                        ["workflow", "platform"],
                        ["api", "first"],
                        ["omnichannel"],
                        ["rcs"],
                        ["maap"],
                        ["whatsapp", "business"],
                        ["telco", "partnership"],
                        ["operator", "partnership"],
                        ["platform", "integration"],
                        ["active active"],
                        ["deployment", "automation"],
                        ["observability"],
                        ["throughput"],
                    ],
                    positive_signals=[
                        "API-led product architecture",
                        "Usage-linked enterprise platform monetization",
                        "Operator/telco/ecosystem integration",
                        "Scalable platform reliability and observability",
                    ],
                    negative_signals=[
                        "Hardware fabrication without platform economics",
                    ],
                    evidence_patterns=[
                        "Messaging/communications infrastructure",
                        "High-throughput platform operations",
                        "Partner-integrated enterprise deployments",
                    ],
                    confidence_hints=[
                        "Stronger when platform architecture, usage scale, and partner integrations co-occur",
                    ],
                ),
                defaults=ArchetypeDefaults(
                    question_modules=[
                        "technology",
                        "platform_dependency",
                        "platform_economics",
                    ],
                    discovery_profile={
                        "priority_entities": ["Platform", "Partner", "Customer", "API"],
                        "priority_events": ["Platform Launch", "Partnership", "Customer Expansion"],
                    },
                    extraction_profile={
                        "high_priority_sections": ["Technology", "Platform", "Customer", "Regulation"],
                    },
                    report_template="software_v1",
                ),
            ),
            ArchetypeDefinition(
                archetype_id="compliance_infrastructure",
                dnas=["Compliance Infrastructure"],
                definition=(
                    "Businesses differentiated by trust, security, regulatory, anti-fraud, "
                    "or compliance layers embedded into a broader platform or workflow."
                ),
                signals=ArchetypeSignals(
                    characteristic_patterns=[
                        "Compliance Infrastructure",
                        "Security and compliance-led product differentiation",
                        "Trust and security layer",
                    ],
                    keyword_groups=[
                        ["security", "compliance"],
                        ["anti", "phishing"],
                        ["anti", "spam"],
                        ["trust", "layer"],
                    ],
                    text_keyword_groups=[
                        ["compliance", "platform"],
                        ["compliance", "product"],
                        ["security", "product"],
                        ["anti", "phishing"],
                        ["anti", "spam"],
                        ["spam", "protection"],
                        ["scam", "protection"],
                        ["trust", "layer"],
                        ["secure", "communication"],
                        ["regulatory", "compliance"],
                        ["devsecops"],
                        ["ssdlc"],
                    ],
                    positive_signals=[
                        "Embedded anti-fraud / anti-spam / anti-phishing protections",
                        "Regulatory compliance as product differentiation",
                        "Trust and security layers within customer workflows",
                    ],
                    negative_signals=[
                        "General cybersecurity buzzwords without embedded platform role",
                    ],
                    evidence_patterns=[
                        "Spam/phishing prevention",
                        "Compliance product embedded in communications or workflow platform",
                    ],
                    confidence_hints=[
                        "Stronger when compliance capability is part of the commercial product, not just internal hygiene",
                    ],
                ),
                defaults=ArchetypeDefaults(
                    question_modules=[
                        "technology",
                        "platform_dependency",
                        "compliance_infrastructure",
                    ],
                    discovery_profile={
                        "priority_entities": ["Regulator", "Platform", "Partner", "Customer"],
                        "priority_events": ["Compliance Change", "Platform Deployment", "Partnership"],
                    },
                    extraction_profile={
                        "high_priority_sections": ["Technology", "Platform", "Regulation", "Risk"],
                    },
                    report_template="software_v1",
                ),
            ),
            ArchetypeDefinition(
                archetype_id="subscription",
                dnas=["Subscription"],
                definition=(
                    "Businesses with recurring revenue economics driven by renewals, "
                    "repeat contract value, or recurring customer payment streams."
                ),
                signals=ArchetypeSignals(
                    characteristic_patterns=["Recurring Revenue"],
                    keyword_groups=[["recurring", "revenue"]],
                    positive_signals=[
                        "Renewal and recurring contract base",
                        "Predictable repeat monetization",
                    ],
                    evidence_patterns=[
                        "Recurring revenue / renewal language",
                    ],
                ),
                defaults=ArchetypeDefaults(
                    question_modules=[],
                    discovery_profile={
                        "priority_entities": ["Customer", "Contract"],
                        "priority_events": ["Renewal", "Pricing Change"],
                    },
                    extraction_profile={
                        "high_priority_sections": ["Revenue", "Customer", "Pricing"],
                    },
                    report_template="software_v1",
                ),
            ),
            ArchetypeDefinition(
                archetype_id="ip_library_platform_monetization",
                dnas=["IP Library", "Platform Monetization"],
                definition=(
                    "Businesses monetizing owned or licensed content/IP libraries through "
                    "digital distribution, rights licensing, recurring catalogue economics, "
                    "and platform-based audience reach."
                ),
                signals=ArchetypeSignals(
                    characteristic_patterns=[
                        "IP Driven",
                        "Large diversified content library",
                        "Catalogue-driven monetization",
                        "Large music catalogue/library",
                        "Multi-channel rights monetization",
                        "High-reach owned-channel monetization",
                        "Digital-first distribution with majority streaming revenue",
                    ],
                    keyword_groups=[
                        ["rights", "monetization"],
                        ["content", "library"],
                        ["digital", "licensing"],
                        ["platform", "distribution"],
                    ],
                    text_keyword_groups=[
                        ["content", "catalogue"],
                        ["content", "catalog"],
                        ["music", "catalogue"],
                        ["music", "catalog"],
                        ["song", "library"],
                        ["content", "library"],
                        ["rights", "monetization"],
                        ["sync", "licensing"],
                        ["performance", "rights"],
                        ["digital", "licensing"],
                        ["royalty"],
                        ["royalties"],
                        ["streaming", "revenue"],
                        ["streaming", "platforms"],
                        ["digital", "distribution"],
                        ["third", "party", "platforms"],
                        ["youtube", "channel"],
                        ["subscriber"],
                        ["audience", "monetization"],
                        ["evergreen", "catalogue"],
                        ["evergreen", "catalog"],
                    ],
                    positive_signals=[
                        "Owned/licensed content library economics",
                        "Rights monetization and recurring catalogue yield",
                        "Digital/platform distribution dependence",
                        "Owned-audience or channel monetization",
                    ],
                    negative_signals=[
                        "Pure software platform language without reusable content or IP library economics",
                    ],
                    evidence_patterns=[
                        "Catalogue / library scale",
                        "Licensing, royalties, streaming, owned channels",
                    ],
                    confidence_hints=[
                        "Stronger when both library monetization and platform distribution are explicit",
                    ],
                ),
                defaults=ArchetypeDefaults(
                    question_modules=[
                        "library_economics",
                        "platform_dependency",
                        "technology",
                    ],
                    discovery_profile={
                        "priority_entities": ["Platform", "Content Library", "Audience", "License"],
                        "priority_events": ["Licensing", "Distribution Expansion", "Rights Deal"],
                    },
                    extraction_profile={
                        "high_priority_sections": ["Revenue", "Digital", "Licensing", "Platform", "Content Library"],
                    },
                    report_template="media_v1",
                ),
            ),
            ArchetypeDefinition(
                archetype_id="consumer_brand",
                dnas=["Consumer"],
                definition=(
                    "Businesses whose economics are driven by brand strength, consumer "
                    "distribution, marketing reach, and product sell-through."
                ),
                signals=ArchetypeSignals(
                    characteristic_patterns=["Consumer Brand"],
                    keyword_groups=[["consumer", "brand"]],
                    positive_signals=[
                        "Brand-led distribution and consumer demand creation",
                    ],
                    evidence_patterns=[
                        "Brand building and consumer reach",
                    ],
                ),
                defaults=ArchetypeDefaults(
                    question_modules=[],
                    discovery_profile={
                        "priority_entities": ["Brand", "Customer"],
                        "priority_events": ["Campaign", "Product Launch"],
                    },
                    extraction_profile={
                        "high_priority_sections": ["Marketing", "Brand", "Distribution"],
                    },
                    report_template="media_v1",
                ),
            ),
            ArchetypeDefinition(
                archetype_id="export",
                dnas=["Export"],
                definition=(
                    "Businesses with meaningful growth, revenue, or strategic dependence on "
                    "international markets, foreign-currency sales, or cross-border expansion."
                ),
                signals=ArchetypeSignals(
                    characteristic_patterns=[
                        "Export Oriented",
                        "Geographic Expansion",
                        "Geographic expansion",
                        "Global Expansion",
                        "Regional Expansion",
                    ],
                    keyword_groups=[
                        ["global", "expansion"],
                        ["global", "market"],
                        ["overseas", "subsidiaries"],
                        ["overseas"],
                        ["export"],
                        ["geographic", "expansion"],
                        ["regional", "expansion"],
                    ],
                    text_keyword_groups=[
                        ["foreign", "currency"],
                        ["international", "customers"],
                        ["global", "supplier"],
                        ["global", "distribution"],
                        ["revenue", "from", "exports"],
                        ["revenue", "earned", "in", "foreign", "currency"],
                    ],
                    positive_signals=[
                        "Cross-border revenue and expansion",
                        "International distribution or customer base",
                    ],
                    evidence_patterns=[
                        "Export revenue",
                        "Foreign-currency earnings",
                        "Overseas / regional market expansion",
                    ],
                ),
                defaults=ArchetypeDefaults(
                    question_modules=[],
                    discovery_profile={
                        "priority_entities": ["Geography", "Customer"],
                        "priority_events": ["Market Entry", "Export Expansion"],
                    },
                    extraction_profile={
                        "high_priority_sections": ["Geography", "Export", "Regulation"],
                    },
                    report_template="generic_v1",
                ),
            ),
        ]

    @property
    def archetypes(self) -> List[ArchetypeDefinition]:
        return list(self._archetypes)

    def allowed_dnas(self) -> List[str]:
        allowed: List[str] = []
        for archetype in self._archetypes:
            allowed.extend(archetype.dnas)
        return list(dict.fromkeys(allowed))

    def find_archetypes_for_dnas(
        self,
        dnas: Iterable[str],
    ) -> List[ArchetypeDefinition]:
        normalized_targets = {
            self._normalize(dna)
            for dna in dnas
            if dna and str(dna).strip()
        }
        matches: List[ArchetypeDefinition] = []
        for archetype in self._archetypes:
            normalized_dnas = {
                self._normalize(dna)
                for dna in archetype.dnas
            }
            if normalized_targets.intersection(normalized_dnas):
                matches.append(archetype)
        return matches

    @property
    def mappings(self) -> List[Dict[str, Any]]:
        return [
            archetype.to_legacy_mapping()
            for archetype in self._archetypes
        ]

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
        return " ".join(normalized.split())

    def _matches_characteristic(
        self,
        characteristic: str,
        archetype: ArchetypeDefinition,
    ) -> bool:
        normalized_input = self._normalize(characteristic)
        if not normalized_input:
            return False

        normalized_patterns = [
            self._normalize(item)
            for item in archetype.signals.characteristic_patterns
            if item and str(item).strip()
        ]

        if normalized_input in normalized_patterns:
            return True

        for normalized_pattern in normalized_patterns:
            if not normalized_pattern:
                continue
            if normalized_pattern in normalized_input:
                return True
            if normalized_input in normalized_pattern:
                return True

        tokens = set(normalized_input.split())
        for keyword_group in archetype.signals.keyword_groups:
            normalized_group = [
                self._normalize(keyword)
                for keyword in keyword_group
                if self._normalize(keyword)
            ]
            if normalized_group and all(
                keyword in normalized_input if " " in keyword else keyword in tokens
                for keyword in normalized_group
            ):
                return True

        return False

    def _matches_text_signal(
        self,
        text: str,
        archetype: ArchetypeDefinition,
    ) -> bool:
        normalized_text = self._normalize(text)
        if not normalized_text:
            return False

        tokens = set(normalized_text.split())
        for keyword_group in archetype.signals.text_keyword_groups:
            normalized_group = [
                self._normalize(keyword)
                for keyword in keyword_group
                if self._normalize(keyword)
            ]
            if normalized_group and all(
                keyword in normalized_text if " " in keyword else keyword in tokens
                for keyword in normalized_group
            ):
                return True

        return False

    def _matches_mapping(self, characteristic: str, mapping: Dict[str, Any]) -> bool:
        return self._matches_characteristic(
            characteristic,
            self._coerce_archetype(mapping),
        )

    def _matches_text_group(self, text: str, mapping: Dict[str, Any]) -> bool:
        return self._matches_text_signal(
            text,
            self._coerce_archetype(mapping),
        )

    def find_matches(
        self,
        characteristics: List[str],
        texts: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        return [
            archetype.to_legacy_mapping()
            for archetype in self.find_matching_archetypes(
                characteristics,
                texts=texts,
            )
        ]

    def find_matching_archetypes(
        self,
        characteristics: List[str],
        texts: List[str] | None = None,
    ) -> List[ArchetypeDefinition]:
        matches: List[ArchetypeDefinition] = []
        supporting_texts = texts or []
        for archetype in self._archetypes:
            if any(
                self._matches_characteristic(characteristic, archetype)
                for characteristic in characteristics
            ):
                matches.append(archetype)
                continue
            if any(
                self._matches_text_signal(text, archetype)
                for text in supporting_texts
            ):
                matches.append(archetype)
        return matches

    def build_profile_from_dnas(
        self,
        business_dnas: List[str],
        extras: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        matches = self.find_archetypes_for_dnas(business_dnas)
        profile = self._build_profile_from_archetypes(matches)
        profile["business_dnas"] = list(
            dict.fromkeys(
                dna
                for dna in business_dnas
                if dna in self.allowed_dnas()
            )
        )
        if extras:
            profile.update(extras)
        return profile

    def build_profile(
        self,
        characteristics: List[str],
        texts: List[str] | None = None,
    ) -> Dict[str, Any]:
        matches = self.find_matching_archetypes(characteristics, texts=texts)
        return self._build_profile_from_archetypes(matches)

    def build_candidate_pack(
        self,
        evidence_snippets: List[str],
        max_candidates: int = 5,
    ) -> Dict[str, Any]:
        candidate_archetypes = self.find_matching_archetypes([], texts=evidence_snippets)
        if not candidate_archetypes:
            candidate_archetypes = self._archetypes[:max_candidates]
        else:
            candidate_archetypes = candidate_archetypes[:max_candidates]

        return {
            "allowed_dnas": self.allowed_dnas(),
            "candidate_archetypes": [
                {
                    "archetype_id": archetype.archetype_id,
                    "dnas": list(archetype.dnas),
                    "definition": archetype.definition,
                    "positive_signals": list(archetype.signals.positive_signals),
                    "negative_signals": list(archetype.signals.negative_signals),
                    "evidence_patterns": list(archetype.signals.evidence_patterns),
                    "default_question_modules": list(archetype.defaults.question_modules),
                    "default_report_template": archetype.defaults.report_template,
                }
                for archetype in candidate_archetypes
            ],
            "evidence_snippets": list(evidence_snippets),
        }

    def _build_profile_from_archetypes(
        self,
        matches: List[ArchetypeDefinition],
    ) -> Dict[str, Any]:
        dnas: List[str] = []
        question_modules: List[str] = []
        discovery_profile = {
            "priority_entities": list(DEFAULT_DISCOVERY_PROFILE["priority_entities"]),
            "priority_events": list(DEFAULT_DISCOVERY_PROFILE["priority_events"]),
        }
        extraction_profile = {
            "high_priority_sections": list(DEFAULT_EXTRACTION_PROFILE["high_priority_sections"]),
        }
        report_template = DEFAULT_REPORT_TEMPLATE
        report_template_priority = self._report_template_priority(report_template)

        for archetype in matches:
            dnas.extend(archetype.dnas)
            question_modules.extend(archetype.defaults.question_modules)
            discovery_profile["priority_entities"].extend(
                archetype.defaults.discovery_profile.get("priority_entities", [])
            )
            discovery_profile["priority_events"].extend(
                archetype.defaults.discovery_profile.get("priority_events", [])
            )
            extraction_profile["high_priority_sections"].extend(
                archetype.defaults.extraction_profile.get("high_priority_sections", [])
            )
            candidate_template = archetype.defaults.report_template or report_template
            candidate_priority = self._report_template_priority(candidate_template)
            if candidate_priority >= report_template_priority:
                report_template = candidate_template
                report_template_priority = candidate_priority

        return {
            "business_dnas": list(dict.fromkeys(dnas)),
            "question_modules": list(dict.fromkeys(question_modules)),
            "discovery_profile": {
                "priority_entities": list(dict.fromkeys(discovery_profile["priority_entities"])),
                "priority_events": list(dict.fromkeys(discovery_profile["priority_events"])),
            },
            "extraction_profile": {
                "high_priority_sections": list(dict.fromkeys(extraction_profile["high_priority_sections"])),
            },
            "report_template": report_template,
        }

    @staticmethod
    def _report_template_priority(template: str) -> int:
        priorities = {
            "generic_v1": 0,
            "manufacturing_v1": 1,
            "software_v1": 1,
            "media_v1": 2,
            "semiconductor_v1": 2,
        }
        return priorities.get(template, 0)
