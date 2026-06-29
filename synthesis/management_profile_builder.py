import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.context_paths import intelligence_path  # noqa: E402
from knowledge.cim import load_cim  # noqa: E402


SECTION_MAP = {
    "projects": "operations.projects",
    "promises": "management.promises",
    "capital_allocation": "financial.capital_allocation",
    "initiatives": "operations.initiatives",
}

OUTPUT_FILE = "management_profile.json"


def _get_section_items(cim, section_path):

    node = cim

    for part in section_path.split("."):

        if not isinstance(node, dict):
            return []

        node = node.get(part, {})

    if isinstance(node, dict):
        return node.get("items", [])

    return []


def build_profile():

    cim = load_cim()

    profile = {}

    for key, section_path in SECTION_MAP.items():

        profile[key] = _get_section_items(
            cim,
            section_path,
        )

    return profile


def print_summary(profile):

    print("\n" + "=" * 60)
    print("MANAGEMENT PROFILE")
    print("=" * 60)

    for section, items in profile.items():

        print(
            f"{section}: {len(items)}"
        )


def main():

    profile = build_profile()

    with open(
        intelligence_path(OUTPUT_FILE),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            profile,
            f,
            indent=2,
            ensure_ascii=False
        )

    print_summary(profile)

    print(
        f"\nSaved: {intelligence_path(OUTPUT_FILE)}"
    )


if __name__ == "__main__":
    main()
