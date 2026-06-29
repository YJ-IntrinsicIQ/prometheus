import json
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.context_paths import intelligence_path  # noqa: E402
from knowledge.cim import load_cim  # noqa: E402

INPUT_FILE = "company_intelligence.json"
OUTPUT_FILE = "management_summary.json"

SECTION_MAP = {
    "projects": "operations.projects",
    "promises": "management.promises",
    "capital_allocation": "financial.capital_allocation",
    "initiatives": "operations.initiatives",
    "risks": "risk.identified",
}


# ==========================================================
# Helpers
# ==========================================================

def _get_section_items(cim, section_path):

    node = cim

    for part in section_path.split("."):

        if not isinstance(node, dict):
            return []

        node = node.get(part, {})

    if isinstance(node, dict):
        return node.get("items", [])

    return []


def load_profile():

    cim = load_cim()

    profile = {}

    for key, section_path in SECTION_MAP.items():

        profile[key] = _get_section_items(
            cim,
            section_path,
        )

    return profile


def first_non_empty(item, fields):

    for field in fields:

        value = item.get(field)

        if value:
            return value

    return ""


# ==========================================================
# Schema Mapping
# ==========================================================

from core.schemas import (
    PROJECT_NAME_FIELDS,
    PROMISE_FIELDS,
    INITIATIVE_FIELDS,
    CAPITAL_ACTION_FIELDS
)


# ==========================================================
# Summary Builders
# ==========================================================

def summarize_projects(profile):

    projects = []

    for item in profile.get(
        "projects",
        []
    ):

        project = first_non_empty(
            item,
            PROJECT_NAME_FIELDS
        )

        if project:
            projects.append(project)

    return projects


def summarize_promises(profile):

    promises = []

    for item in profile.get(
        "promises",
        []
    ):

        promise = first_non_empty(
            item,
            PROMISE_FIELDS
        )

        if promise:
            promises.append(promise)

    return promises


def summarize_initiatives(profile):

    initiatives = []

    for item in profile.get(
        "initiatives",
        []
    ):

        initiative = first_non_empty(
            item,
            INITIATIVE_FIELDS
        )

        if initiative:
            initiatives.append(initiative)

    return initiatives


def summarize_capital(profile):

    actions = []

    for item in profile.get(
        "capital_allocation",
        []
    ):

        action = first_non_empty(
            item,
            CAPITAL_ACTION_FIELDS
        )

        if action:
            actions.append(action)

    return actions


def extract_focus_areas(profile):

    categories = []

    for item in profile.get(
        "initiatives",
        []
    ):

        category = item.get(
            "category",
            ""
        )

        if category:
            categories.append(
                category
            )

    counts = Counter(categories)

    return [
        category
        for category, _
        in counts.most_common()
    ]


# ==========================================================
# Main Summary
# ==========================================================

def build_summary(profile):

    projects = summarize_projects(
        profile
    )

    promises = summarize_promises(
        profile
    )

    initiatives = summarize_initiatives(
        profile
    )

    capital_actions = summarize_capital(
        profile
    )

    focus_areas = extract_focus_areas(
        profile
    )

    return {

        "management_focus_areas":
            focus_areas,

        "major_projects":
            projects,

        "major_promises":
            promises,

        "key_initiatives":
            initiatives,

        "capital_allocation_actions":
            capital_actions,

        "statistics": {

            "project_count":
                len(projects),

            "promise_count":
                len(promises),

            "initiative_count":
                len(initiatives),

            "capital_action_count":
                len(capital_actions)
        }
    }


def print_summary(summary):

    print("\n" + "=" * 60)
    print("MANAGEMENT SUMMARY")
    print("=" * 60)

    print("\nFocus Areas:")

    for area in summary[
        "management_focus_areas"
    ]:

        print(f"- {area}")

    stats = summary["statistics"]

    print("\nStatistics:")
    print(
        f"Projects: {stats['project_count']}"
    )
    print(
        f"Promises: {stats['promise_count']}"
    )
    print(
        f"Initiatives: {stats['initiative_count']}"
    )
    print(
        f"Capital Actions: {stats['capital_action_count']}"
    )


def main():

    profile = load_profile()

    summary = build_summary(
        profile
    )

    with open(
        intelligence_path(OUTPUT_FILE),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            summary,
            f,
            indent=2,
            ensure_ascii=False
        )

    print_summary(
        summary
    )

    print(
        f"\nSaved: {intelligence_path(OUTPUT_FILE)}"
    )


if __name__ == "__main__":
    main()
