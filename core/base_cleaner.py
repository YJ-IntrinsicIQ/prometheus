import json

from core.context_paths import extraction_path


class BaseCleaner:
    add_confidence = True

    def __init__(
        self,
        input_file,
        output_file,
    ):
        self.input_file = extraction_path(input_file)
        self.output_file = extraction_path(output_file)

    def is_valid(self, item):
        return True

    def confidence_score(self, item):
        return "low"

    def deduplicate(self, items):
        return items

    def clean_item(self, item):
        return item

    def report(self, items, cleaned, removed):
        print(
            f"Original: {len(items)}"
        )

        print(
            f"Cleaned: {len(cleaned)}"
        )

    def run(self):
        with open(
            self.input_file,
            "r",
            encoding="utf-8",
        ) as f:
            items = json.load(f)

        cleaned = []
        removed = []

        for item in items:
            if not self.is_valid(item):
                removed.append(item)
                continue

            item = self.clean_item(item)

            if self.add_confidence:
                item["confidence"] = (
                    self.confidence_score(item)
                )

            cleaned.append(item)

        cleaned = self.deduplicate(
            cleaned
        )

        with open(
            self.output_file,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                cleaned,
                f,
                indent=2,
                ensure_ascii=False,
            )

        self.report(
            items,
            cleaned,
            removed,
        )

        return cleaned
