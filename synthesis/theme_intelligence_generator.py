import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.context_paths import intelligence_path  # noqa: E402

INPUT_FILE = "management_focus_analysis.json"
OUTPUT_FILE = "theme_intelligence.json"


def load_data():

    with open(
        intelligence_path(INPUT_FILE),
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def calculate_execution_score(item):

    score = (
        item["projects"]
        + item["initiatives"]
        + item["capital_actions"]
    )

    if score >= 6:
        return "high"

    if score >= 3:
        return "medium"

    return "low"


def generate_assessment(item):

    theme = item["theme"]

    projects = item["projects"]
    initiatives = item["initiatives"]
    promises = item["promises"]

    if projects > 0 and initiatives > 0:

        return (
            f"Management appears to be actively "
            f"executing on {theme} through both "
            f"initiatives and projects."
        )

    if initiatives > 0:

        return (
            f"Management attention toward "
            f"{theme} is visible primarily "
            f"through operational initiatives."
        )

    if promises > 0:

        return (
            f"{theme} currently appears more "
            f"aspirational than executed."
        )

    return (
        f"Limited evidence available for "
        f"{theme}."
    )


def build_report(data):

    report = []

    for item in data:

        report.append({

            "theme":
                item["theme"],

            "weight_percent":
                item["weight_percent"],

            "focus_level":
                item["focus_level"],

            "execution_score":
                calculate_execution_score(
                    item
                ),

            "assessment":
                generate_assessment(
                    item
                )
        })

    return report


def main():

    data = load_data()

    report = build_report(
        data
    )

    with open(
        intelligence_path(OUTPUT_FILE),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        "\nTHEME INTELLIGENCE\n"
    )

    for item in report:

        print(
            f"{item['theme']}: "
            f"{item['execution_score']}"
        )


if __name__ == "__main__":
    main()
