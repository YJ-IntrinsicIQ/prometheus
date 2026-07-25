import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.base_cleaner import BaseCleaner  # noqa: E402


INPUT_FILE = "extracted_promises.json"
OUTPUT_FILE = "clean_promises.json"

AUDITOR_TERMS = [
    "reasonable assurance",
    "audit",
    "auditor",
    "financial statements",
    "going concern",
]

GENERIC_PROMISES = [
    "future growth",
    "business objective",
    "strategic objective",
]


def normalize_text(text):
    return (
        text.lower()
        .strip()
    )


def clean_timeline(promise):
    timeline = promise.get(
        "timeline",
        "",
    )

    promise_text = normalize_text(
        promise.get(
            "promise",
            "",
        )
    )

    if (
        "manufacturing facility"
        in promise_text
        and "30 years"
        in timeline.lower()
    ):
        return ""

    return timeline


def promise_strength(promise):
    score = 0

    timeline = promise.get(
        "timeline",
        "",
    )

    text = (
        promise.get(
            "promise",
            "",
        )
        .lower()
    )

    if timeline:
        score += 2

    if "%" in text:
        score += 2

    if any(
        x in text
        for x in [
            "capacity",
            "facility",
            "plant",
            "commercial production",
            "energy reduction",
        ]
    ):
        score += 1

    return score


class PromiseCleaner(BaseCleaner):
    def is_valid(self, promise):
        promise_text = normalize_text(
            promise.get(
                "promise",
                "",
            )
        )

        source_chunk = normalize_text(
            promise.get(
                "source_chunk",
                "",
            )
        )

        if not promise_text:
            return False

        auditor_matches = 0

        for term in AUDITOR_TERMS:
            if term in source_chunk:
                auditor_matches += 1

        if auditor_matches >= 2:
            return False

        return True

    def clean_item(self, promise):
        promise["timeline"] = (
            clean_timeline(promise)
        )

        return promise

    def confidence_score(self, promise):
        score = 0

        if promise.get("promise"):
            score += 1

        if promise.get("timeline"):
            score += 1

        if promise.get("category"):
            score += 1

        if score == 3:
            return "high"

        if score == 2:
            return "medium"

        return "low"

    def deduplicate(self, promises):
        seen = {}

        for promise in promises:
            key = normalize_text(
                promise["promise"]
            )

            if key not in seen:
                seen[key] = promise

        return list(
            seen.values()
        )

    def report(self, promises, cleaned, removed):
        print("\n" + "=" * 50)
        print("PROMISE CLEANER REPORT")
        print("=" * 50)

        print(
            f"Original: {len(promises)}"
        )

        print(
            f"Cleaned: {len(cleaned)}"
        )

        print(
            f"Removed: {len(removed)}"
        )

        print("\nRemoved Promises:")

        for item in removed:
            print(
                "-",
                item.get(
                    "promise",
                    "UNKNOWN",
                ),
            )

        print(
            f"\nSaved: {self.output_file}"
        )


def is_valid_promise(promise):
    return create_cleaner().is_valid(promise)


def confidence_score(promise):
    return create_cleaner().confidence_score(promise)


def deduplicate(promises):
    return create_cleaner().deduplicate(promises)


def create_cleaner():
    return PromiseCleaner(
        INPUT_FILE,
        OUTPUT_FILE,
        module_name="promises",
    )


def main():
    create_cleaner().run()


if __name__ == "__main__":
    main()
