import json
from pathlib import Path

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
        diagnostics = self._validation_failure_diagnostics(
            raw_item=raw_item,
            finalized_item=finalized_item,
            validation=validation,
            context=context,
        )
        error_text = "; ".join(validation.get("errors") or [])
        return (
            f"Invalid cleaned {self.module_name} item: "
            + error_text
            + " | diagnostics="
            + json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)
        )

    def _validation_failure_diagnostics(self, *, raw_item, finalized_item, validation, context):
        period_quality = (finalized_item.get("evidence_quality") or {}).get("period_resolution") or {}
        materiality = (finalized_item.get("evidence_quality") or {}).get("progression_materiality") or {}
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
            "should_promote": materiality.get("should_promote"),
            "reason": reason,
        }
        return diagnostics

    def _is_local_rejection(self, *, raw_item=None, finalized_item, validation):
        """
        Decide whether to quarantine (local rejection) or hard fail at the cleaner boundary.

        Policy (per four-outcome contract):
        - HARD_FAIL: structural defects, promotable items with unresolved chronology → hard fail
        - QUARANTINE: valid content but unsuitable for canonical investor intelligence → local rejection
        - DEMOTE: valid but secondary → local rejection if also non-promotable and period ambiguous
        - KEEP with AMBIGUOUS period and should_promote=False: local rejection if incomplete/demoted/low-materiality

        The decision is based on promotability/materiality, not module-specific logic.
        """
        errors = list(validation.get("errors") or [])
        error_text = "; ".join(errors)

        def _has_text(value):
            return bool(str(value or "").strip())

        # Source period ownership mismatch is always a local rejection (cross-year contamination)
        if "source period ownership mismatch" in error_text:
            return True

        # QUARANTINE/HARD_FAIL from business relevance contract: always quarantine locally
        # These are valid filter decisions, not structural defects
        if (
            "business relevance outcome: QUARANTINE" in error_text
            or "business relevance outcome: HARD_FAIL" in error_text
            or "business relevance quarantined" in error_text
        ):
            return True

        # Handle "invalid or unsupported period resolution" errors
        if "invalid or unsupported period resolution" in errors:
            raw_item = raw_item or {}
            quality = finalized_item.get("evidence_quality") or {}
            period = quality.get("period_resolution") or {}
            materiality = quality.get("progression_materiality") or {}
            business_relevance = quality.get("business_relevance") or {}
            period_status = str(period.get("status") or "").upper()
            should_promote = materiality.get("should_promote")
            materiality_level = str(materiality.get("level") or "").lower()
            relevance_outcome = str(business_relevance.get("outcome") or "").upper()
            relevance_status = str(business_relevance.get("status") or "").lower()

            # Promotable items with ambiguous period always hard fail
            if should_promote:
                return False

            # DEMOTE outcome with ambiguous period: quarantine (valid but secondary)
            if relevance_outcome == "DEMOTE" and period_status == "AMBIGUOUS":
                return True

            # KEEP outcome + non-promotable + AMBIGUOUS period: quarantine locally.
            # Per PERIOD_RESOLUTION_UNSUPPORTED canonical fix: when period ambiguity
            # originates from incidental context years (e.g. market statistics tables,
            # historical references) rather than genuine chronology conflict, a non-promotable
            # KEEP item should be quarantined with diagnostics rather than hard-failed.
            # Applies to all modules including "initiatives".
            if relevance_outcome == "KEEP" and period_status == "AMBIGUOUS" and not should_promote:
                return True

            # Check for explicit incomplete/uncertain evidence in raw item text
            uncertainty_text = " ".join(
                str(value or "")
                for value in (
                    raw_item.get("status"),
                    raw_item.get("uncertainty_reason"),
                    raw_item.get("description"),
                    finalized_item.get("status"),
                    finalized_item.get("uncertainty_reason"),
                )
            ).lower()
            explicit_incomplete_evidence = any(
                marker in uncertainty_text
                for marker in (
                    "incomplete information",
                    "truncated",
                    "final status not",
                    "not fully specified",
                    "provided excerpt",
                    "provided text",
                )
            )

            # Capacity expansions need structured signals (current/target capacity)
            has_structured_capacity_signal = any(
                _has_text(raw_item.get(field)) or _has_text(finalized_item.get(field))
                for field in ("current_capacity", "target_capacity")
            )

            # Low/Unclear materiality non-required evidence for non-core modules
            low_materiality_non_required_evidence = (
                self.module_name in {"projects", "risks", "capacity_expansions", "commentary", "promises"}
                and materiality_level in {"low", "unclear"}
            )

            # Quarantine if: ambiguous period + non-promotable + (incomplete evidence OR demoted secondary OR low materiality non-required OR capacity without signal)
            return (
                period_status == "AMBIGUOUS"
                and should_promote is False
                and (
                    explicit_incomplete_evidence
                    or low_materiality_non_required_evidence
                    or (self.module_name == "capacity_expansions" and not has_structured_capacity_signal)
                )
            )

        return False

    def _rejection_record(self, *, raw_item, finalized_item, validation, context):
        diagnostics = self._validation_failure_diagnostics(
            raw_item=raw_item,
            finalized_item=finalized_item,
            validation=validation,
            context=context,
        )
        return {
            "item_id": finalized_item.get("item_id") or raw_item.get("item_id") or "",
            "source_item_id": raw_item.get("item_id") or "",
            "module": self.module_name,
            "decision": "quarantined",
            "validation_errors": list(validation.get("errors") or []),
            "validation_warnings": list(validation.get("warnings") or []),
            "failure_class": diagnostics.get("failure_class"),
            "diagnostics": diagnostics,
            "raw_period_fields": {
                "year": raw_item.get("year") or "",
                "time_reference": raw_item.get("time_reference") or "",
                "period": raw_item.get("period") or "",
                "source_year": raw_item.get("source_year") or "",
            },
            "cleaned_period_fields": {
                "year": finalized_item.get("year") or "",
                "source_year": finalized_item.get("source_year") or "",
                "period_resolution": (finalized_item.get("evidence_quality") or {}).get("period_resolution") or {},
                "progression_materiality": (finalized_item.get("evidence_quality") or {}).get("progression_materiality") or {},
            },
            "provenance": {
                "source_artifact": raw_item.get("source_artifact") or finalized_item.get("source_artifact") or "",
                "page": raw_item.get("page") or finalized_item.get("page") or "",
                "evidence_ids": finalized_item.get("evidence_ids") or raw_item.get("evidence_ids") or [],
            },
        }

    def _write_rejections(self, rejections):
        output_path = Path(self.output_file)
        rejection_path = output_path.with_name(f"{output_path.stem}_rejections.json")
        payload = {
            "schema_version": "cleaner_rejections.v1",
            "module": self.module_name,
            "rejection_count": len(rejections),
            "rejections": rejections,
        }
        rejection_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
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
        rejected = []
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
                if self._is_local_rejection(raw_item=raw_item, finalized_item=item, validation=validation):
                    rejected.append(
                        self._rejection_record(
                            raw_item=raw_item,
                            finalized_item=item,
                            validation=validation,
                            context=context,
                        )
                    )
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

        self._write_rejections(rejected)

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
