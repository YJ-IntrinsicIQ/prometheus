import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.base_cleaner import BaseCleaner  # noqa: E402


INPUT_FILE = "extracted_capital_allocations.json"
OUTPUT_FILE = "clean_capital_allocation.json"


def normalize(text):
    return (
        text.lower()
        .strip()
    )


class CapitalAllocationCleaner(BaseCleaner):
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
            key = normalize(
                item["action"]
            )

            if key not in seen:
                seen[key] = item

        return list(
            seen.values()
        )


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
    )


def main():
    create_cleaner().run()


if __name__ == "__main__":
    main()
