import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.base_cleaner import BaseCleaner  # noqa: E402
from knowledge.temporal_event_splitter import CAPACITY_SPLITTER  # noqa: E402


INPUT_FILE = "extracted_capacity.json"
OUTPUT_FILE = "clean_capacity.json"


def normalize(text):
    return text.lower().strip()


class CapacityCleaner(BaseCleaner):
    add_confidence = False

    def is_valid(self, item):
        capacity_type = normalize(
            item.get(
                "capacity_type",
                "",
            )
        )

        return bool(
            capacity_type
        )

    def clean_item(self, item):
        """Apply temporal event splitting for compound capacity items."""
        return CAPACITY_SPLITTER.split(item)

    def deduplicate(self, items):
        seen = {}

        for item in items:
            key = normalize(
                item["capacity_type"]
            )

            if key not in seen:
                seen[key] = item

        return list(
            seen.values()
        )


def create_cleaner():
    return CapacityCleaner(
        INPUT_FILE,
        OUTPUT_FILE,
        module_name="capacity_expansions",
    )


def is_valid(item):
    return create_cleaner().is_valid(item)


def deduplicate(items):
    return create_cleaner().deduplicate(items)


def main():
    create_cleaner().run()


if __name__ == "__main__":
    main()
