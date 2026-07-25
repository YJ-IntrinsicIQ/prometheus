import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.projects import NEGATIVE_PATTERNS, POSITIVE_PATTERNS, PROMPT  # noqa: E402
from core.base_extractor import BaseExtractor  # noqa: E402


def create_extractor():
    return BaseExtractor(
        input_file="project_discovery_results.json",
        output_file="extracted_projects.json",
        prompt=PROMPT,
        output_key="projects",
        module_name="projects",
        positive_patterns=POSITIVE_PATTERNS,
        negative_patterns=NEGATIVE_PATTERNS,
    )


def extract_projects(chunk_text):
    return create_extractor().extract(
        chunk_text
    )


def main():
    projects = create_extractor().run()

    print(
        f"Projects extracted: "
        f"{len(projects)}"
    )


if __name__ == "__main__":
    main()
