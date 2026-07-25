import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.base_cleaner import BaseCleaner  # noqa: E402
from knowledge.capital_allocation_taxonomy import (  # noqa: E402
    normalize_capital_allocation_item,
    validate_capital_allocation_items,
)


INPUT_FILE = "extracted_capital_allocations.json"
OUTPUT_FILE = "clean_capital_allocation.json"


def normalize(text):
    return (
        text.lower()
        .strip()
    )


class CapitalAllocationCleaner(BaseCleaner):
    def clean_item(self, item):
        return normalize_capital_allocation_item(item)

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
