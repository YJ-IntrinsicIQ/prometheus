import sys
from pathlib import Path

from pipelines.pipeline_context import get_context

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.base_cleaner import BaseCleaner  # noqa: E402
from knowledge.temporal_event_splitter import RISK_SPLITTER  # noqa: E402


INPUT_FILE = "extracted_risks.json"
OUTPUT_FILE = "clean_risks.json"

AUDIT_TERMS = [
    "audit",
    "auditor",
    "reasonable assurance",
    "financial statement",
    "going concern",
]


def normalize(text):
    return text.lower().strip()


class RiskCleaner(BaseCleaner):
    def clean_item(self, risk):
        """Apply temporal event splitting for compound risk items."""
        # First, split compound risk items
        split_items = RISK_SPLITTER.split(risk)

        # If split, return the list of split items
        if len(split_items) > 1:
            for item in split_items:
                context = get_context()
                if context is not None and not item.get("source_year"):
                    item["source_year"] = context.year
            return split_items

        # Single item - apply existing logic
        cleaned = dict(risk)
        context = get_context()
        if context is not None and not cleaned.get("source_year"):
            cleaned["source_year"] = context.year
        return cleaned

    def is_valid(self, risk):
        risk_text = normalize(
            risk.get(
                "risk",
                "",
            )
        )

        source_chunk = normalize(
            risk.get(
                "source_chunk",
                "",
            )
        )

        if not risk_text:
            return False

        matches = 0

        for term in AUDIT_TERMS:
            if term in source_chunk:
                matches += 1

        if matches >= 2:
            return False

        return True

    def confidence_score(self, risk):
        score = 0

        if risk.get("risk"):
            score += 1

        if risk.get("category"):
            score += 1

        if risk.get("severity"):
            score += 1

        if score == 3:
            return "high"

        if score == 2:
            return "medium"

        return "low"

    def deduplicate(self, risks):
        seen = {}

        for risk in risks:
            key = normalize(
                risk["risk"]
            )

            if key not in seen:
                seen[key] = risk

        return list(
            seen.values()
        )


def is_valid_risk(risk):
    return create_cleaner().is_valid(risk)


def confidence_score(risk):
    return create_cleaner().confidence_score(risk)


def deduplicate(risks):
    return create_cleaner().deduplicate(risks)


def create_cleaner():
    return RiskCleaner(
        INPUT_FILE,
        OUTPUT_FILE,
        module_name="risks",
    )


def main():
    create_cleaner().run()


if __name__ == "__main__":
    main()
