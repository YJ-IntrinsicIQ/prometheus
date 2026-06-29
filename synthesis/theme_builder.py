import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.schemas import (
    PROJECT_NAME_FIELDS,
    PROMISE_FIELDS,
    INITIATIVE_FIELDS,
    CAPITAL_ACTION_FIELDS
)
from core.context_paths import intelligence_path
from knowledge.cim import load_cim

INPUT_FILE = "company_intelligence.json"
OUTPUT_FILE = "management_themes.json"

SECTION_MAP = {
    "projects": "operations.projects",
    "promises": "management.promises",
    "capital_allocation": "financial.capital_allocation",
    "initiatives": "operations.initiatives",
    "risks": "risk.identified",
    "capacity": "operations.capacity",
}


# ==================================================
# THEME DEFINITIONS
# ==================================================

THEMES = {

    "technology": [
        "ai",
        "iot",
        "digital",
        "automation",
        "robotics",
        "predictive",
        "digital twin"
    ],

    "r_and_d": [
        "research",
        "innovation",
        "r&d",
        "material",
        "iit"
    ],

    "energy": [
        "energy",
        "cooling",
        "hvac",
        "heat",
        "solar"
    ],

    "manufacturing": [
        "manufacturing",
        "facility",
        "plant",
        "production"
    ],

    "expansion": [
        "expansion",
        "new facility",
        "new plant",
        "capacity"
    ]
}


# ==================================================
# HELPERS
# ==================================================

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
            return str(value)

    return ""


def match_themes(text):

    text = text.lower()

    matched = []

    for theme, keywords in THEMES.items():

        for keyword in keywords:

            if keyword in text:

                matched.append(theme)
                break

    return matched


# ==================================================
# PROCESSORS
# ==================================================

def process_projects(profile, themes):

    for item in profile.get(
        "projects",
        []
    ):

        text = first_non_empty(
            item,
            PROJECT_NAME_FIELDS
        )

        for theme in match_themes(text):

            themes[theme]["projects"].append(text)


def process_promises(profile, themes):

    for item in profile.get(
        "promises",
        []
    ):

        text = first_non_empty(
            item,
            PROMISE_FIELDS
        )

        for theme in match_themes(text):

            themes[theme]["promises"].append(text)


def process_initiatives(profile, themes):

    for item in profile.get(
        "initiatives",
        []
    ):

        text = first_non_empty(
            item,
            INITIATIVE_FIELDS
        )

        for theme in match_themes(text):

            themes[theme]["initiatives"].append(text)


def process_capital(profile, themes):

    for item in profile.get(
        "capital_allocation",
        []
    ):

        text = first_non_empty(
            item,
            CAPITAL_ACTION_FIELDS
        )

        for theme in match_themes(text):

            themes[theme]["capital_actions"].append(text)


# ==================================================
# MAIN
# ==================================================

def build_themes(profile):

    themes = {}

    for theme in THEMES:

        themes[theme] = {
            "projects": [],
            "promises": [],
            "initiatives": [],
            "capital_actions": []
        }

    process_projects(
        profile,
        themes
    )

    process_promises(
        profile,
        themes
    )

    process_initiatives(
        profile,
        themes
    )

    process_capital(
        profile,
        themes
    )

    return themes


def main():

    profile = load_profile()

    themes = build_themes(
        profile
    )

    with open(
        intelligence_path(OUTPUT_FILE),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            themes,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\nTHEME SUMMARY")

    for theme, data in themes.items():

        total = (
            len(data["projects"])
            + len(data["promises"])
            + len(data["initiatives"])
            + len(data["capital_actions"])
        )

        print(
            f"{theme}: {total}"
        )


if __name__ == "__main__":
    main()
