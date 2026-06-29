import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.base_cleaner import BaseCleaner  # noqa: E402


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
    )


def main():
    create_cleaner().run()


if __name__ == "__main__":
    main()
