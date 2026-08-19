import json

from core.context_paths import extraction_path
from pipelines.pipeline_context import get_context
from knowledge.evidence_layer import (
    finalize_cleaned_item,
    validate_cleaned_item,
)


class BaseCleaner:
    add_confidence = True

    def __init__(
        self,
        input_file,
        output_file,
        module_name=None,
    ):
        self.input_file = extraction_path(input_file)
        self.output_file = extraction_path(output_file)
        self.module_name = module_name or output_file

    def is_valid(self, item):
        return True

    def confidence_score(self, item):
        return "low"

    def deduplicate(self, items):
        return items

    def clean_item(self, item):
        return item

    def _validation_failure_message(self, *, raw_item, finalized_item, validation, context):
        period_quality = (finalized_item.get("evidence_quality") or {}).get("period_resolution") or {}
        raw_period = (
            raw_item.get("year")
            or raw_item.get("time_reference")
            or raw_item.get("period")
            or raw_item.get("announcement_period")
            or raw_item.get("latest_period")
            or raw_item.get("source_year")
            or ""
        )
        source_period = finalized_item.get("source_year") or getattr(context, "year", "") or ""
        normalized_period = period_quality.get("resolved_period") or finalized_item.get("year") or ""
        period_status = str(period_quality.get("status") or "").upper()
        error_text = "; ".join(validation.get("errors") or [])
        failure_class = period_quality.get("failure_class") or ("PERIOD_RESOLUTION_UNSUPPORTED" if "period resolution" in error_text else "VALIDATION_ERROR")
        reason = "; ".join(
            filter(
                None,
                [
                    *(period_quality.get("basis") or []),
                    *(period_quality.get("limitations") or []),
                    error_text,
                ],
            )
        )
        diagnostics = {
            "failure_class": failure_class,
            "company": getattr(context, "company", ""),
            "year": getattr(context, "year", ""),
            "module": self.module_name,
            "item_id": finalized_item.get("item_id", ""),
            "raw_period": raw_period,
            "source_period": source_period,
            "normalized_period": normalized_period,
            "period_status": period_status,
            "reason": reason,
        }
        return (
            f"Invalid cleaned {self.module_name} item: "
            + error_text
            + " | diagnostics="
            + json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)
        )

    def report(self, items, cleaned, removed):
        print(
            f"Original: {len(items)}"
        )

        print(
            f"Cleaned: {len(cleaned)}"
        )

    def run(self):
        context = get_context()
        with open(
            self.input_file,
            "r",
            encoding="utf-8",
        ) as f:
            items = json.load(f)

        cleaned = []
        removed = []
        validation_warnings = []

        for item in items:
            raw_item = dict(item)
            if not self.is_valid(raw_item):
                removed.append(raw_item)
                continue

            cleaned_item = self.clean_item(dict(raw_item))
            candidate_items = cleaned_item if isinstance(cleaned_item, list) else [cleaned_item]

            for candidate in candidate_items:
                if context is not None and not candidate.get("source_year"):
                    candidate["source_year"] = context.year

                if self.add_confidence:
                    candidate["confidence"] = (
                        self.confidence_score(candidate)
                    )

                candidate["_raw_item"] = raw_item
                cleaned.append(candidate)

        cleaned = self.deduplicate(
            cleaned
        )

        finalized = []
        for index, item in enumerate(cleaned, start=1):
            raw_item = item.pop("_raw_item", {})
            item = finalize_cleaned_item(
                item,
                module_name=self.module_name,
                item_index=index,
            )
            validation = validate_cleaned_item(
                item,
                module_name=self.module_name,
            )
            if validation["errors"]:
                error_text = "; ".join(validation["errors"])
                # Quarantine/HARD_FAIL outcomes: remove silently without crashing the cleaner
                # These are valid-filter decisions per the four-outcome business relevance contract.
                is_quarantine_decision = (
                    "business relevance outcome: QUARANTINE" in error_text
                    or "business relevance outcome: HARD_FAIL" in error_text
                    or "business relevance quarantined" in error_text
                    or "source period ownership mismatch" in error_text
                )
                if is_quarantine_decision:
                    removed.append(item)
                    continue
                raise ValueError(
                    self._validation_failure_message(
                        raw_item=raw_item,
                        finalized_item=item,
                        validation=validation,
                        context=context,
                    )
                )
            validation_warnings.extend(validation["warnings"])
            finalized.append(item)
        cleaned = finalized

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

        for warning in dict.fromkeys(validation_warnings):
            print(
                f"WARNING: {warning}"
            )

        return cleaned
