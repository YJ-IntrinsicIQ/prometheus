import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.initiatives import PROMPT  # noqa: E402
from core.base_extractor import BaseExtractor  # noqa: E402


def create_extractor():
    return BaseExtractor(
        input_file="initiative_discovery_results.json",
        output_file="extracted_initiatives.json",
        prompt=PROMPT,
        output_key="initiatives",
    )


def main():
    initiatives = create_extractor().run()

    print(
        f"Initiatives extracted: "
        f"{len(initiatives)}"
    )


if __name__ == "__main__":
    main()
