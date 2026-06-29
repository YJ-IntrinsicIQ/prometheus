import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.commentary import PROMPT  # noqa: E402
from core.base_extractor import BaseExtractor  # noqa: E402


def create_extractor():
    return BaseExtractor(
        input_file="commentary_discovery_results.json",
        output_file="extracted_commentary.json",
        prompt=PROMPT,
        output_key="commentary",
    )


def main():
    commentary = create_extractor().run()

    print(
        f"Commentary extracted: "
        f"{len(commentary)}"
    )


if __name__ == "__main__":
    main()
