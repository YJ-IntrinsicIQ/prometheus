import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.capacity import NEGATIVE_PATTERNS, POSITIVE_PATTERNS, PROMPT  # noqa: E402
from core.base_extractor import BaseExtractor  # noqa: E402


def create_extractor():
    return BaseExtractor(
        input_file="capacity_discovery_results.json",
        output_file="extracted_capacity.json",
        prompt=PROMPT,
        output_key="capacity_expansions",
        module_name="capacity_expansions",
        positive_patterns=POSITIVE_PATTERNS,
        negative_patterns=NEGATIVE_PATTERNS,
    )


def extract_projects(chunk_text):
    return create_extractor().extract(
        chunk_text
    )


def main():
    capacity_items = create_extractor().run()

    print(
        f"Capacity extracted: "
        f"{len(capacity_items)}"
    )


if __name__ == "__main__":
    main()
