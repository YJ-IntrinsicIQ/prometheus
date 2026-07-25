from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


VALID_PCIM_SECTIONS = {
    "business_understanding",
    "financial_strength_inputs",
    "management_quality_inputs",
    "growth_quality_inputs",
    "moat_inputs",
    "capital_allocation_inputs",
    "risk_inputs",
    "incentive_inputs",
    "simplicity_and_story_inputs",
    "governance_and_incentive_inputs",
    "business_economics_inputs",
    "growth_execution_inputs",
    "story_vs_numbers_inputs",
    "financial_fundamentals_inputs",
    "financial_trend_inputs",
    "financial_growth_inputs",
    "profitability_inputs",
    "cash_conversion_inputs",
    "return_on_capital_inputs",
    "balance_sheet_strength_inputs",
    "working_capital_inputs",
    "per_share_inputs",
    "corporate_action_inputs",
    "ownership_inputs",
    "financial_quality_inputs",
    "financial_driver_inputs",
    "multi_year_financial_inputs",
    "multi_year_inputs",
    "evidence_map",
    "uncertainty_missing_data",
}

REQUIRED_FIELDS = {
    "doctrine_id",
    "investor_lens",
    "primary_focus",
    "canonical_principles",
    "canonical_questions",
    "evidence_required_from_pcim",
    "evidence_to_ignore_or_downweight",
    "red_flags",
    "uncertainty_rules",
    "output_contract",
    "input_source_policy",
}

REQUIRED_OUTPUT_CONTRACT_FIELDS = {
    "summary",
    "rating_scale",
    "required_sections",
    "required_evidence",
    "uncertainty_reporting",
}


class DoctrineValidationError(ValueError):
    pass


class InvestorDoctrineRegistry:
    def __init__(self, doctrines_dir: Path | str):
        self.doctrines_dir = Path(doctrines_dir)

    def doctrine_paths(self) -> List[Path]:
        if not self.doctrines_dir.exists():
            return []
        return sorted(self.doctrines_dir.glob("*.json"), key=lambda path: path.name)

    def load_all(self) -> List[Dict[str, Any]]:
        doctrines: List[Dict[str, Any]] = []
        seen_ids = set()
        for path in self.doctrine_paths():
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.validate(payload, source=str(path))
            doctrine_id = payload["doctrine_id"]
            if doctrine_id in seen_ids:
                raise DoctrineValidationError(f"Duplicate doctrine_id: {doctrine_id}")
            seen_ids.add(doctrine_id)
            doctrines.append(payload)
        return doctrines

    def get(self, doctrine_id: str) -> Optional[Dict[str, Any]]:
        for doctrine in self.load_all():
            if doctrine["doctrine_id"] == doctrine_id:
                return doctrine
        return None

    @classmethod
    def validate(cls, payload: Dict[str, Any], source: str = "<memory>") -> None:
        missing = REQUIRED_FIELDS - set(payload.keys())
        if missing:
            raise DoctrineValidationError(f"{source}: missing required fields: {sorted(missing)}")

        if payload["input_source_policy"] != "pcim_only":
            raise DoctrineValidationError(f"{source}: input_source_policy must be 'pcim_only'")

        for field in (
            "primary_focus",
            "canonical_principles",
            "canonical_questions",
            "evidence_required_from_pcim",
            "evidence_to_ignore_or_downweight",
            "red_flags",
            "uncertainty_rules",
        ):
            value = payload.get(field)
            if not isinstance(value, list) or not value:
                raise DoctrineValidationError(f"{source}: {field} must be a non-empty list")

        output_contract = payload.get("output_contract")
        if not isinstance(output_contract, dict):
            raise DoctrineValidationError(f"{source}: output_contract must be an object")
        missing_output = REQUIRED_OUTPUT_CONTRACT_FIELDS - set(output_contract.keys())
        if missing_output:
            raise DoctrineValidationError(
                f"{source}: output_contract missing required fields: {sorted(missing_output)}"
            )

        required_sections = payload.get("evidence_required_from_pcim", [])
        invalid_sections = [section for section in required_sections if section not in VALID_PCIM_SECTIONS]
        if invalid_sections:
            raise DoctrineValidationError(
                f"{source}: invalid PCIM sections referenced: {sorted(set(invalid_sections))}"
            )

        raw_document_phrases = ("raw document", "raw documents", "annual report", "filing pdf", "document chunk")
        for field in (
            "evidence_required_from_pcim",
            "evidence_to_ignore_or_downweight",
            "canonical_questions",
            "uncertainty_rules",
        ):
            for item in payload.get(field, []):
                normalized = str(item).lower()
                if any(phrase in normalized for phrase in raw_document_phrases):
                    raise DoctrineValidationError(
                        f"{source}: doctrine field {field} must not instruct raw-document access"
                    )


def load_doctrine_registry(
    doctrines_dir: Path | str = Path(__file__).resolve().parent / "doctrines",
) -> List[Dict[str, Any]]:
    return InvestorDoctrineRegistry(doctrines_dir).load_all()
