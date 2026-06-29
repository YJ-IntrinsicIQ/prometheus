from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .constants import DEFAULT_DISCOVERY_PROFILE, DEFAULT_EXTRACTION_PROFILE


class Registry:
    def __init__(self, mappings: List[Dict[str, Any]] | None = None):
        self._mappings = mappings or self._default_mappings()

    @staticmethod
    def _default_mappings() -> List[Dict[str, Any]]:
        return [
            {
                "characteristics": ["Capital Intensive", "Asset Heavy"],
                "dnas": ["Manufacturing"],
                "question_modules": ["Capex", "Supply Chain"],
                "discovery_profile": {
                    "priority_entities": ["Plant", "Technology"],
                    "priority_events": ["Expansion", "Capacity Increase"],
                },
                "extraction_profile": {
                    "high_priority_sections": ["Operations", "Capex", "Technology"],
                },
                "report_template": "manufacturing_v1",
            },
            {
                "characteristics": ["Technology Driven", "IP Driven"],
                "dnas": ["Semiconductor"],
                "question_modules": ["Technology", "Innovation"],
                "discovery_profile": {
                    "priority_entities": ["Technology", "Research"],
                    "priority_events": ["Product Launch", "R&D Expansion"],
                },
                "extraction_profile": {
                    "high_priority_sections": ["Technology", "R&D", "Intellectual Property"],
                },
                "report_template": "semiconductor_v1",
            },
            {
                "characteristics": ["Recurring Revenue"],
                "dnas": ["Subscription"],
                "question_modules": ["Recurring Revenue", "Pricing Power"],
                "discovery_profile": {
                    "priority_entities": ["Customer", "Contract"],
                    "priority_events": ["Renewal", "Pricing Change"],
                },
                "extraction_profile": {
                    "high_priority_sections": ["Revenue", "Customer", "Pricing"],
                },
                "report_template": "software_v1",
            },
            {
                "characteristics": ["Consumer Brand"],
                "dnas": ["Consumer"],
                "question_modules": ["Brand", "Distribution"],
                "discovery_profile": {
                    "priority_entities": ["Brand", "Customer"],
                    "priority_events": ["Campaign", "Product Launch"],
                },
                "extraction_profile": {
                    "high_priority_sections": ["Marketing", "Brand", "Distribution"],
                },
                "report_template": "media_v1",
            },
            {
                "characteristics": ["Export Oriented"],
                "dnas": ["Export"],
                "question_modules": ["Export", "Regulation"],
                "discovery_profile": {
                    "priority_entities": ["Geography", "Customer"],
                    "priority_events": ["Market Entry", "Export Expansion"],
                },
                "extraction_profile": {
                    "high_priority_sections": ["Geography", "Export", "Regulation"],
                },
                "report_template": "generic_v1",
            },
        ]

    def find_matches(self, characteristics: List[str]) -> List[Dict[str, Any]]:
        normalized = {characteristic.strip().lower() for characteristic in characteristics if characteristic and characteristic.strip()}
        matches: List[Dict[str, Any]] = []
        for mapping in self._mappings:
            mapping_characteristics = {
                characteristic.strip().lower() for characteristic in mapping.get("characteristics", []) if characteristic and characteristic.strip()
            }
            if normalized.intersection(mapping_characteristics):
                matches.append(mapping)
        return matches

    def build_profile(self, characteristics: List[str]) -> Dict[str, Any]:
        matches = self.find_matches(characteristics)
        dnas: List[str] = []
        question_modules: List[str] = []
        discovery_profile = DEFAULT_DISCOVERY_PROFILE.copy()
        extraction_profile = DEFAULT_EXTRACTION_PROFILE.copy()
        report_template = "generic_v1"

        for mapping in matches:
            dnas.extend(mapping.get("dnas", []))
            question_modules.extend(mapping.get("question_modules", []))
            profile = mapping.get("discovery_profile") or {}
            discovery_profile["priority_entities"].extend(profile.get("priority_entities", []))
            discovery_profile["priority_events"].extend(profile.get("priority_events", []))
            extraction = mapping.get("extraction_profile") or {}
            extraction_profile["high_priority_sections"].extend(extraction.get("high_priority_sections", []))
            report_template = mapping.get("report_template", report_template)

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
