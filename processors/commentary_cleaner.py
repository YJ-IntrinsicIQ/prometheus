import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.context_paths import extraction_path  # noqa: E402
from knowledge.evidence_layer import finalize_cleaned_item  # noqa: E402
from synthesis.management_summary_generator import (  # noqa: E402
    CONTEXT_TYPE_ACCOUNTING_DISCLOSURE,
    CONTEXT_TYPE_COMPANY_ACTION,
    CONTEXT_TYPE_COMPANY_CAPABILITY,
    CONTEXT_TYPE_COMPANY_PROMISE,
    CONTEXT_TYPE_COMPANY_RESULT,
    CONTEXT_TYPE_COMPANY_RISK_RESPONSE,
    CONTEXT_TYPE_EXTERNAL_CONTEXT,
    CONTEXT_TYPE_EXTERNAL_HEADWIND,
    CONTEXT_TYPE_EXTERNAL_TAILWIND,
    CONTEXT_TYPE_GOVERNANCE_DISCLOSURE,
    CONTEXT_TYPE_UNCERTAIN,
    _classify_management_item,
    _normalize_text,
)


INPUT_FILE = "extracted_commentary.json"
OUTPUT_FILE = "clean_commentary.json"

GROUPED_KEYS = (
    "company_management_actions",
    "company_promises",
    "company_capabilities",
    "company_results",
    "risk_responses",
    "external_context",
    "accounting_disclosures",
    "governance_disclosures",
    "uncertain_items",
)


def _empty_grouped_output():
    return {key: [] for key in GROUPED_KEYS}


def _group_name_for_context_type(context_type):
    mapping = {
        CONTEXT_TYPE_COMPANY_ACTION: "company_management_actions",
        CONTEXT_TYPE_COMPANY_PROMISE: "company_promises",
        CONTEXT_TYPE_COMPANY_CAPABILITY: "company_capabilities",
        CONTEXT_TYPE_COMPANY_RESULT: "company_results",
        CONTEXT_TYPE_COMPANY_RISK_RESPONSE: "risk_responses",
        CONTEXT_TYPE_EXTERNAL_CONTEXT: "external_context",
        CONTEXT_TYPE_EXTERNAL_TAILWIND: "external_context",
        CONTEXT_TYPE_EXTERNAL_HEADWIND: "external_context",
        CONTEXT_TYPE_ACCOUNTING_DISCLOSURE: "accounting_disclosures",
        CONTEXT_TYPE_GOVERNANCE_DISCLOSURE: "governance_disclosures",
        CONTEXT_TYPE_UNCERTAIN: "uncertain_items",
    }
    return mapping.get(context_type, "uncertain_items")


def _dedupe_group(items):
    seen = set()
    deduped = []
    for item in items:
        key = (
            item.get("context_type"),
            _normalize_text(item.get("value")),
            _normalize_text(item.get("category")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _validate_grouped_output(grouped):
    errors = []
    warnings = []

    for key in GROUPED_KEYS:
        items = grouped.get(key)
        if not isinstance(items, list):
            errors.append(f"{key} must be a list")
            continue
        for item in items:
            value = item.get("value") or "unknown commentary item"
            if item.get("source_chunk"):
                errors.append(f"{value}: source_chunk leakage in cleaned commentary")
            if not item.get("context_type"):
                errors.append(f"{value}: missing context_type")
            if not item.get("agency"):
                errors.append(f"{value}: missing agency")
            if not item.get("evidence_ids"):
                errors.append(f"{value}: missing evidence_ids")
            if key == "uncertain_items":
                warnings.append(f"{value}: uncertain context_type")
            if item.get("agency") == "uncertain":
                warnings.append(f"{value}: uncertain agency")
            quality = item.get("evidence_quality") or {}
            if quality.get("company_specificity") == "low":
                warnings.append(f"{value}: low company_specificity")
            if quality.get("investor_relevance") == "low":
                warnings.append(f"{value}: low investor_relevance")
            if not item.get("category"):
                warnings.append(f"{value}: vague category")

    validation = {
        "status": "pass" if not errors else "fail",
        "errors": list(dict.fromkeys(errors)),
        "warnings": list(dict.fromkeys(warnings)),
    }
    if errors:
        raise ValueError(
            "Commentary cleaner validation failed: "
            + "; ".join(validation["errors"])
        )
    return validation


class CommentaryCleaner:
    def __init__(self, input_file, output_file, module_name=None):
        self.input_file = extraction_path(input_file)
        self.output_file = extraction_path(output_file)
        self.module_name = module_name or "commentary"

    def _load_items(self):
        if not self.input_file.exists():
            return []
        with open(self.input_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _is_valid(self, item):
        return bool(item.get("theme") and item.get("commentary"))

    def _clean_commentary_item(self, item, index):
        working = dict(item)
        working["value"] = working.get("value") or working.get("commentary") or working.get("theme")
        working["category"] = working.get("category") or working.get("theme") or ""
        working["status"] = working.get("status") or working.get("sentiment") or ""
        classified = _classify_management_item(
            working,
            "commentary",
            working["value"],
        )
        cleaned = finalize_cleaned_item(
            working,
            module_name=self.module_name,
            item_index=index,
        )
        cleaned["context_type"] = classified["context_type"]
        cleaned["agency"] = classified["agency"]
        cleaned["reasoning"] = classified["reasoning"]
        cleaned["should_feed_management_consistency"] = classified["should_feed_management_consistency"]
        cleaned["should_feed_company_strategy"] = classified["should_feed_company_strategy"]
        cleaned["should_feed_external_context"] = classified["should_feed_external_context"]
        cleaned["actor"] = cleaned.get("actor") or cleaned["agency"]
        cleaned["context_type"] = cleaned["context_type"] or CONTEXT_TYPE_UNCERTAIN
        return cleaned

    def run(self):
        original = self._load_items()
        grouped = _empty_grouped_output()
        removed = []

        item_index = 0
        for item in original:
            if not self._is_valid(item):
                removed.append(item)
                continue
            item_index += 1
            cleaned = self._clean_commentary_item(item, item_index)
            group_name = _group_name_for_context_type(cleaned.get("context_type"))
            grouped[group_name].append(cleaned)

        for key in GROUPED_KEYS:
            grouped[key] = _dedupe_group(grouped[key])

        grouped["validation"] = _validate_grouped_output(grouped)

        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(grouped, f, indent=2, ensure_ascii=False)

        print(f"Original: {len(original)}")
        print(f"Cleaned commentary items: {sum(len(grouped[key]) for key in GROUPED_KEYS)}")
        print(f"Removed commentary items: {len(removed)}")
        print(f"Saved: {self.output_file}")
        return grouped


def create_cleaner():
    return CommentaryCleaner(
        INPUT_FILE,
        OUTPUT_FILE,
        module_name="commentary",
    )


def main():
    create_cleaner().run()


if __name__ == "__main__":
    main()
