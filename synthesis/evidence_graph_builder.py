import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.context_paths import intelligence_path  # noqa: E402
from knowledge.cim import load_cim  # noqa: E402

INPUT_FILE = "company_intelligence.json"
OUTPUT_FILE = "evidence_graph.json"

SECTION_MAP = {
    "promises": "management.promises",
    "projects": "operations.projects",
    "initiatives": "operations.initiatives",
    "capital_allocation": "financial.capital_allocation",
    "capacity": "operations.capacity",
    "risks": "risk.identified",
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


def load_data():

    cim = load_cim()

    profile = {}

    for key, section_path in SECTION_MAP.items():

        profile[key] = _get_section_items(
            cim,
            section_path,
        )

    return profile


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


def build_graph(links):

    graph = {}

    theme_data = {}

    for theme in THEME_KEYWORDS:
        theme_data[theme] = {
            "promises": [],
            "initiatives": [],
            "projects": [],
            "capital_actions": []
        }

    for item in links.get("promises", []):
        text = _first_non_empty(item, ["promise", "name", "title"])
        for theme in _match_themes(text):
            theme_data[theme]["promises"].append(text)

    for item in links.get("initiatives", []):
        text = _first_non_empty(item, ["initiative", "name", "title"])
        for theme in _match_themes(text):
            theme_data[theme]["initiatives"].append(text)

    for item in links.get("projects", []):
        text = _first_non_empty(item, ["project_name", "name", "title"])
        for theme in _match_themes(text):
            theme_data[theme]["projects"].append(text)

    for item in links.get("capital_allocation", []):
        text = _first_non_empty(item, ["action", "name", "title"])
        for theme in _match_themes(text):
            theme_data[theme]["capital_actions"].append(text)

    for theme, data in theme_data.items():

        graph[theme] = {
            "promises": data.get("promises", []),
            "initiatives": data.get("initiatives", []),
            "projects": data.get("projects", []),
            "capital_actions": data.get("capital_actions", [])
        }

    return graph


def main():

    links = load_data()

    graph = build_graph(
        links
    )

    with open(
        intelligence_path(OUTPUT_FILE),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            graph,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        "\nEVIDENCE GRAPH CREATED\n"
    )

    for theme in graph:

        print(
            f"- {theme}"
        )


if __name__ == "__main__":
    main()
