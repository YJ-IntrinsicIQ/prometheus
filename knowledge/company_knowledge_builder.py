import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.context_paths import (
    extracted_path,
    intelligence_path
)

OUTPUT_FILE = "company_knowledge.json"


# ============================================================
# Utility
# ============================================================

def load_json(filename, default):

    path = extracted_path(filename)

    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return default


# ============================================================
# Metadata
# ============================================================

def build_metadata():

    try:
        from pipelines.pipeline_context import get_context

        context = get_context()

        if context:

            return {
                "company": context.company,
                "year": context.year
            }

    except Exception:
        pass

    return {
        "company": None,
        "year": None
    }


# ============================================================
# Build Knowledge
# ============================================================

def build_company_knowledge():

    knowledge = {

        "metadata": build_metadata(),

        "projects":
            load_json(
                "clean_projects.json",
                []
            ),

        "promises":
            load_json(
                "clean_promises.json",
                []
            ),

        "risks":
            load_json(
                "clean_risks.json",
                []
            ),

        "capacity":
            load_json(
                "clean_capacity.json",
                []
            ),

        "capital_allocation":
            load_json(
                "clean_capital_allocation.json",
                []
            ),

        "initiatives":
            load_json(
                "clean_initiatives.json",
                []
            )
    }

    return knowledge


# ============================================================
# Statistics
# ============================================================

def print_summary(knowledge):

    print("\n" + "=" * 60)
    print("COMPANY KNOWLEDGE")
    print("=" * 60)

    print(
        f"Company : {knowledge['metadata']['company']}"
    )

    print(
        f"Year    : {knowledge['metadata']['year']}"
    )

    print()

    print(
        f"Projects             : {len(knowledge['projects'])}"
    )

    print(
        f"Promises            : {len(knowledge['promises'])}"
    )

    print(
        f"Risks               : {len(knowledge['risks'])}"
    )

    print(
        f"Capacity            : {len(knowledge['capacity'])}"
    )

    print(
        f"Capital Allocation  : {len(knowledge['capital_allocation'])}"
    )

    print(
        f"Initiatives         : {len(knowledge['initiatives'])}"
    )


# ============================================================
# Main
# ============================================================

def main():

    knowledge = build_company_knowledge()

    output = intelligence_path(
        OUTPUT_FILE
    )

    with open(
        output,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            knowledge,
            f,
            indent=2,
            ensure_ascii=False
        )

    print_summary(
        knowledge
    )

    print(
        f"\nSaved: {output}"
    )


if __name__ == "__main__":
    main()