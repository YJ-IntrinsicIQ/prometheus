import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.promises import NEGATIVE_PATTERNS, POSITIVE_PATTERNS, PROMPT  # noqa: E402
from core.base_extractor import BaseExtractor  # noqa: E402


def create_extractor():
    return BaseExtractor(
        input_file="promise_discovery_results.json",
        output_file="extracted_promises.json",
        prompt=PROMPT,
        output_key="promises",
        module_name="promises",
        positive_patterns=POSITIVE_PATTERNS,
        negative_patterns=NEGATIVE_PATTERNS,
    )


def extract_projects(chunk_text):
    return create_extractor().extract(
        chunk_text
    )


def main():
    promises = create_extractor().run()

    print(
        f"Promises extracted: "
        f"{len(promises)}"
    )


if __name__ == "__main__":
    main()
