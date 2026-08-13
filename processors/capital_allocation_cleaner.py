import sys
import re
from pathlib import Path

from pipelines.pipeline_context import get_context


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.base_cleaner import BaseCleaner  # noqa: E402
from knowledge.capital_allocation_taxonomy import (  # noqa: E402
    normalize_capital_allocation_item,
    validate_capital_allocation_items,
)


INPUT_FILE = "extracted_capital_allocations.json"
OUTPUT_FILE = "clean_capital_allocation.json"

_MULTI_EVENT_YEAR_FRAGMENT_RE = re.compile(
    r"(?:^|,|\band\b)\s*([^,]+?\b(?:19|20)\d{2}\b)",
    re.IGNORECASE,
)
_LEADING_ACTION_PREFIX_RE = re.compile(
    r"^(?:instituted/approved|institution/approval of|approved|instituted)\s+",
    re.IGNORECASE,
)
_CAPITAL_ALLOCATION_SPLIT_HINTS = (
    "plan",
    "scheme",
    "buyback",
    "dividend",
    "equity issuance",
    "employee stock",
    "stock purchase",
    "rsu",
    "esop",
    "esps",
    "employee stock purchase scheme",
    "preferential",
    "acquisition",
    "loan",
    "investment",
)


def normalize(text):
    return (
        text.lower()
        .strip()
    )


class CapitalAllocationCleaner(BaseCleaner):
    def _split_compound_action(self, item):
        action = normalize(item.get("action", ""))
        if not action or item.get("item_id") is None:
            return [item]

        if not any(hint in action for hint in _CAPITAL_ALLOCATION_SPLIT_HINTS):
            return [item]

        fragments = _MULTI_EVENT_YEAR_FRAGMENT_RE.findall(item.get("action", ""))
        if len(fragments) < 2 and "(" in item.get("action", "") and ")" in item.get("action", ""):
            inner = item.get("action", "").split("(", 1)[1].rsplit(")", 1)[0]
            fragments = [
                fragment.strip()
                for fragment in re.split(r",|\band\b", inner, flags=re.IGNORECASE)
                if re.search(r"\b(?:19|20)\d{2}\b", fragment or "")
            ]
        fragments = [
            _LEADING_ACTION_PREFIX_RE.sub("", fragment).strip(" ;.,")
            for fragment in fragments
        ]
        parsed = []
        for fragment in fragments:
            years = re.findall(r"\b(?:19|20)\d{2}\b", fragment)
            if not years:
                continue
            parsed.append((fragment, years[-1]))

        if len(parsed) < 2:
            return [item]

        if not all(
            any(hint in normalize(fragment) for hint in _CAPITAL_ALLOCATION_SPLIT_HINTS)
            for fragment, _ in parsed
        ):
            return [item]

        split_items = []
        for index, (fragment, year) in enumerate(parsed, start=1):
            split_item = dict(item)
            split_item["action"] = fragment
            split_item["value"] = fragment
            split_item["year"] = year
            split_item["split_from_item_id"] = item.get("item_id")
            split_item["split_event_index"] = index
            split_item["split_event_count"] = len(parsed)
            split_item["temporal_role"] = "historical_event"
            split_items.append(split_item)

        return split_items

    def clean_item(self, item):
        cleaned = normalize_capital_allocation_item(item)
        if cleaned.get("action"):
            return self._split_compound_action(cleaned)
        context = get_context()
        if context is not None and not cleaned.get("source_year"):
            cleaned["source_year"] = context.year
        return cleaned

    def is_valid(self, item):
        action = normalize(
            item.get(
                "action",
                "",
            )
        )

        if not action:
            return False

        return True

    def confidence_score(self, item):
        score = 0

        if item.get("action"):
            score += 1

        if item.get("category"):
            score += 1

        if item.get("purpose"):
            score += 1

        if item.get("amount"):
            score += 1

        if score >= 4:
            return "high"

        if score >= 2:
            return "medium"

        return "low"

    def deduplicate(self, items):
        seen = {}

        for item in items:
            key = (
                normalize(item["action"]),
                normalize(item.get("canonical_category", "")),
                normalize(item.get("amount", "")),
                str(item.get("page", "")),
            )

            if key not in seen:
                seen[key] = item

        return list(
            seen.values()
        )

    def run(self):
        cleaned = super().run()
        validation = validate_capital_allocation_items(cleaned)
        for warning in validation["warnings"]:
            print(f"WARNING: {warning}")
        if validation["errors"]:
            raise ValueError(
                "Capital allocation validation failed: "
                + "; ".join(validation["errors"])
            )
        return cleaned


def is_valid(item):
    return create_cleaner().is_valid(item)


def confidence_score(item):
    return create_cleaner().confidence_score(item)


def deduplicate(items):
    return create_cleaner().deduplicate(items)


def create_cleaner():
    return CapitalAllocationCleaner(
        INPUT_FILE,
        OUTPUT_FILE,
        module_name="capital_allocations",
    )


def main():
    create_cleaner().run()


if __name__ == "__main__":
    main()
