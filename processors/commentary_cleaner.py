import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.base_cleaner import BaseCleaner  # noqa: E402


INPUT_FILE = "extracted_commentary.json"
OUTPUT_FILE = "clean_commentary.json"


class CommentaryCleaner(BaseCleaner):
    def is_valid(self, item):
        return bool(
            item.get(
                "theme",
                "",
            )
        )


def create_cleaner():
    return CommentaryCleaner(
        INPUT_FILE,
        OUTPUT_FILE,
    )


def main():
    create_cleaner().run()


if __name__ == "__main__":
    main()
