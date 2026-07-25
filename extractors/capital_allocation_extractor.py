import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.capital_allocation import NEGATIVE_PATTERNS, POSITIVE_PATTERNS, PROMPT  # noqa: E402
from core.base_extractor import BaseExtractor  # noqa: E402


def create_extractor():
    return BaseExtractor(
        input_file="capital_allocation_discovery_results.json",
        output_file="extracted_capital_allocations.json",
        prompt=PROMPT,
        output_key="capital_allocations",
        module_name="capital_allocations",
        positive_patterns=POSITIVE_PATTERNS,
        negative_patterns=NEGATIVE_PATTERNS,
    )


def extract_projects(chunk_text):
    return create_extractor().extract(
        chunk_text
    )


def main():
    allocations = create_extractor().run()

    print(
        f"Allocations extracted: "
        f"{len(allocations)}"
    )


if __name__ == "__main__":
    main()
