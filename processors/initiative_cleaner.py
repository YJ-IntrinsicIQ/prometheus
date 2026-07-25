import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.base_cleaner import BaseCleaner  # noqa: E402


INPUT_FILE = "extracted_initiatives.json"
OUTPUT_FILE = "clean_initiatives.json"

GOVERNANCE_TERMS = [
    "board",
    "director",
    "whistle",
    "policy",
    "secretarial",
    "evaluation",
    "csr",
]

INVALID_TERMS = [
    "plan",
    "target",
    "roadmap",
    "aim",
    "intend",
    "expects",
]


class InitiativeCleaner(BaseCleaner):
    def is_valid(self, item):
        initiative = item.get(
            "initiative",
            "",
        ).lower()

        if any(
            term in initiative
            for term in GOVERNANCE_TERMS
        ):
            return False

        return not any(
            term in initiative
            for term in INVALID_TERMS
        )


def create_cleaner():
    return InitiativeCleaner(
        INPUT_FILE,
        OUTPUT_FILE,
        module_name="initiatives",
    )


def main():
    create_cleaner().run()


if __name__ == "__main__":
    main()
