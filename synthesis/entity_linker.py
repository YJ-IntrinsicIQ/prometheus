import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.context_paths import intelligence_path  # noqa: E402
from synthesis.theme_builder import build_themes, load_profile  # noqa: E402

INPUT_FILE = "company_intelligence.json"
OUTPUT_FILE = "entity_links.json"


def load_data():

    profile = load_profile()

    return build_themes(profile)


def build_links(themes):

    links = []

    for theme, data in themes.items():

        strength = (
            len(data["projects"])
            + len(data["promises"])
            + len(data["initiatives"])
            + len(data["capital_actions"])
        )

        links.append({

            "theme": theme,

            "strength": strength,

            "promises":
                data["promises"],

            "initiatives":
                data["initiatives"],

            "projects":
                data["projects"],

            "capital_actions":
                data["capital_actions"]
        })

    links.sort(
        key=lambda x: x["strength"],
        reverse=True
    )

    return links


def main():

    themes = load_data()

    links = build_links(
        themes
    )

    with open(
        intelligence_path(OUTPUT_FILE),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            links,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\nENTITY LINKS\n")

    for item in links:

        print(
            f"{item['theme']}: "
            f"{item['strength']}"
        )


if __name__ == "__main__":
    main()
