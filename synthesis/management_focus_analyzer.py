import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.context_paths import intelligence_path  # noqa: E402
from knowledge.cim import load_cim  # noqa: E402

INPUT_FILE = "company_intelligence.json"
OUTPUT_FILE = "management_focus_analysis.json"

SECTION_MAP = {
    "projects": "operations.projects",
    "promises": "management.promises",
    "capital_allocation": "financial.capital_allocation",
    "initiatives": "operations.initiatives",
    "risks": "risk.identified",
    "capacity": "operations.capacity",
}

THEME_KEYWORDS = {
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


def _get_section_items(cim, section_path):

    node = cim

    for part in section_path.split("."):

        if not isinstance(node, dict):
            return []

        node = node.get(part, {})

    if isinstance(node, dict):
        return node.get("items", [])

    return []


def load_links():

    cim = load_cim()

    profile = {}

    for key, section_path in SECTION_MAP.items():

        profile[key] = _get_section_items(
            cim,
            section_path,
        )

    return profile


def classify_focus(strength):

    if strength >= 8:
        return "High"

    if strength >= 4:
        return "Medium"

    return "Low"


def _first_non_empty(item, fields):

    for field in fields:

        value = item.get(field)

        if value:
            return str(value)

    return ""


def _match_themes(text):

    text = text.lower()
    matched = []

    for theme, keywords in THEME_KEYWORDS.items():

        for keyword in keywords:

            if keyword in text:
                matched.append(theme)
                break

    return matched


def build_analysis(links):

    analysis = []

    theme_data = {}

    for theme in THEME_KEYWORDS:
        theme_data[theme] = {
            "projects": [],
            "promises": [],
            "initiatives": [],
            "capital_actions": []
        }

    for item in links.get("projects", []):
        text = _first_non_empty(item, ["project_name", "name", "title"])
        for theme in _match_themes(text):
            theme_data[theme]["projects"].append(text)

    for item in links.get("promises", []):
        text = _first_non_empty(item, ["promise", "name", "title"])
        for theme in _match_themes(text):
            theme_data[theme]["promises"].append(text)

    for item in links.get("initiatives", []):
        text = _first_non_empty(item, ["initiative", "name", "title"])
        for theme in _match_themes(text):
            theme_data[theme]["initiatives"].append(text)

    for item in links.get("capital_allocation", []):
        text = _first_non_empty(item, ["action", "name", "title"])
        for theme in _match_themes(text):
            theme_data[theme]["capital_actions"].append(text)

    links_for_analysis = []

    for theme, data in theme_data.items():
        strength = (
            len(data["projects"])
            + len(data["promises"])
            + len(data["initiatives"])
            + len(data["capital_actions"])
        )

        links_for_analysis.append({
            "theme": theme,
            "strength": strength,
            "projects": data["projects"],
            "promises": data["promises"],
            "initiatives": data["initiatives"],
            "capital_actions": data["capital_actions"]
        })

    total_strength = sum(
        item["strength"]
        for item in links_for_analysis
    )

    if total_strength == 0:
        return []

    for item in links_for_analysis:

        strength = item["strength"]

        weight = round(
            (strength / total_strength) * 100,
            2
        )

        analysis.append({
            "theme": item["theme"],
            "strength": strength,
            "weight_percent": weight,
            "focus_level": classify_focus(strength),
            "projects": len(item["projects"]),
            "promises": len(item["promises"]),
            "initiatives": len(item["initiatives"]),
            "capital_actions": len(item["capital_actions"])
        })

    return analysis


def main():

    links = load_links()

    analysis = build_analysis(
        links
    )

    if not analysis:
        print("\nMANAGEMENT FOCUS ANALYSIS")
        print("No management themes identified.\n")

        with open(
            intelligence_path(OUTPUT_FILE),
            "w",
            encoding="utf-8"
        ) as f:
            json.dump([], f, indent=2)

        return

    with open(
        intelligence_path(OUTPUT_FILE),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            analysis,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        "\nMANAGEMENT FOCUS ANALYSIS\n"
    )

    for item in analysis:

        print(
            f"{item['theme']} "
            f"({item['weight_percent']}%) "
            f"- {item['focus_level']}"
        )


if __name__ == "__main__":
    main()
