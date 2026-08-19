from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .basis_resolution_schema import (
    BasisEvidence,
    FieldBasisResolution,
    FinancialBasisResolutionReport,
    validate_financial_basis_resolution_payload,
)
from .fact_registry import write_financial_fact_registry


DIRECT_STANDALONE_PATTERNS: Tuple[str, ...] = (
    "standalone financial statements",
    "standalone balance sheet",
    "standalone statement of profit and loss",
    "standalone cash flow statement",
    "standalone statement of cash flows",
    "standalone financial results",
    "separate financial statements",
)

DIRECT_CONSOLIDATED_PATTERNS: Tuple[str, ...] = (
    "consolidated financial statements",
    "consolidated balance sheet",
    "consolidated statement of profit and loss",
    "consolidated cash flow statement",
    "consolidated statement of cash flows",
    "consolidated financial results",
    "group financial statements",
)

NO_SUBSIDIARY_PATTERNS: Tuple[str, ...] = (
    "no subsidiaries",
    "has no subsidiaries",
    "does not have any subsidiaries",
    "does not have subsidiaries",
    "no subsidiary",
    "has no subsidiary",
    "no associates",
    "no associate",
    "no joint venture",
    "no joint ventures",
    "consolidated financial statements are not required",
    "preparation of consolidated financial statements is not required",
    "consolidated financial statements are not applicable",
)

SUBSIDIARY_PATTERNS: Tuple[str, ...] = (
    "subsidiary",
    "subsidiaries",
    "associate",
    "associates",
    "joint venture",
    "joint ventures",
)

BASIS_WARNING_PATTERNS: Tuple[str, ...] = (
    "basis unclear",
    "preferred basis unknown",
    "standalone/consolidated basis is unclear",
    "standalone consolidated basis is unclear",
    "basis unknown",
)

PREFERRED_BASIS_FIELD_PATHS = {
    "profit_and_loss.revenue",
    "profit_and_loss.pat",
    "balance_sheet.total_assets",
    "balance_sheet.net_worth",
    "balance_sheet.total_liabilities",
    "cash_flow.cfo",
    "cash_flow.capex",
}

FIELD_TO_TABLE_TYPE = {
    "profit_and_loss": "profit_and_loss",
    "balance_sheet": "balance_sheet",
    "cash_flow": "cash_flow",
    "share_data": "share_capital",
    "corporate_actions": "corporate_actions",
    "shareholding_pattern": "shareholding_pattern",
}

RELATED_DISCOVERY_SECTIONS = {
    "profit_and_loss": {"primary_profit_and_loss_statement", "financial_note"},
    "balance_sheet": {"primary_balance_sheet_statement", "financial_note", "share_capital_note"},
    "cash_flow": {"primary_cash_flow_statement", "financial_note"},
    "share_capital": {"share_capital_note", "financial_note", "eps_note"},
    "corporate_actions": {"corporate_action_note", "financial_note"},
    "shareholding_pattern": {"shareholding_note", "financial_note"},
}

NOT_APPLICABLE_METRICS = {
    "shareholding_promoter_percent",
    "shareholding_public_percent",
    "shareholding_sum_check",
}


def _normalize(text: Any) -> str:
    value = str(text or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _dedupe_preserve(items: Iterable[Any]) -> List[Any]:
    seen: List[Any] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _page_from_obj(obj: Dict[str, Any]) -> int | None:
    for key in ("page", "page_number", "source_page"):
        value = obj.get(key)
        if isinstance(value, int):
            return value
    return None


def _chunk_id_from_obj(obj: Dict[str, Any]) -> str:
    for key in ("chunk_id", "id"):
        value = obj.get(key)
        if value:
            return str(value)
    return ""


def _text_from_chunk(obj: Dict[str, Any]) -> str:
    for key in ("text", "chunk_text", "content", "excerpt", "text_excerpt"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _contains_any(text: str, patterns: Sequence[str]) -> List[str]:
    return [pattern for pattern in patterns if pattern in text]


def _subsidiary_positive_hits(text: str) -> List[str]:
    normalized = _normalize(text)
    negatives = _contains_any(normalized, NO_SUBSIDIARY_PATTERNS)
    if negatives:
        return []
    return _contains_any(normalized, SUBSIDIARY_PATTERNS)


def _basis_hits(text: str) -> Tuple[List[str], List[str]]:
    normalized = _normalize(text)
    return (
        _contains_any(normalized, DIRECT_STANDALONE_PATTERNS),
        _contains_any(normalized, DIRECT_CONSOLIDATED_PATTERNS),
    )


def _make_evidence(
    *,
    category: str,
    basis: str,
    confidence: str,
    score: int,
    text: str = "",
    source_artifact: str = "",
    page: int | None = None,
    chunk_id: str = "",
    proximity: str = "",
) -> BasisEvidence:
    return BasisEvidence(
        category=category,
        basis=basis,
        confidence=confidence,
        score=score,
        text=_clean(text),
        source_artifact=source_artifact,
        page=page,
        chunk_id=chunk_id,
        proximity=proximity,
    )


def _load_chunks(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    payload = _load_json(path)
    if isinstance(payload, dict) and isinstance(payload.get("chunks"), list):
        return [item for item in payload["chunks"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _load_discovery_items(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    payload = _load_json(path)
    sections = payload.get("sections") if isinstance(payload, dict) else None
    if not isinstance(sections, dict):
        return []
    items: List[Dict[str, Any]] = []
    for section_type, rows in sections.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                entry = dict(row)
                entry.setdefault("section_type", section_type)
                items.append(entry)
    return items


def _load_raw_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    payload = _load_json(path)
    tables = payload.get("tables") if isinstance(payload, dict) else None
    if not isinstance(tables, dict):
        return []
    rows: List[Dict[str, Any]] = []
    for table_type, items in tables.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault("table_type", table_type)
                rows.append(row)
    return rows


def _document_evidence(chunks: List[Dict[str, Any]], discovery_items: List[Dict[str, Any]]) -> Tuple[List[BasisEvidence], Dict[str, Any]]:
    evidence: List[BasisEvidence] = []
    direct_standalone_pages: List[int] = []
    direct_consolidated_pages: List[int] = []
    no_subs_pages: List[int] = []
    subsidiary_pages: List[int] = []

    for source_artifact, records in (
        ("clean_chunks.json", chunks),
        ("financial_discovery.json", discovery_items),
    ):
        for record in records:
            text = _text_from_chunk(record) if source_artifact == "clean_chunks.json" else str(record.get("text_excerpt") or "")
            if not text:
                continue
            page = _page_from_obj(record)
            chunk_id = _chunk_id_from_obj(record)
            standalone_hits, consolidated_hits = _basis_hits(text)
            for hit in standalone_hits:
                evidence.append(
                    _make_evidence(
                        category="direct_statement_title",
                        basis="standalone",
                        confidence="high",
                        score=100,
                        text=hit,
                        source_artifact=source_artifact,
                        page=page,
                        chunk_id=chunk_id,
                        proximity="document",
                    )
                )
                if isinstance(page, int):
                    direct_standalone_pages.append(page)
            for hit in consolidated_hits:
                evidence.append(
                    _make_evidence(
                        category="direct_statement_title",
                        basis="consolidated",
                        confidence="high",
                        score=100,
                        text=hit,
                        source_artifact=source_artifact,
                        page=page,
                        chunk_id=chunk_id,
                        proximity="document",
                    )
                )
                if isinstance(page, int):
                    direct_consolidated_pages.append(page)
            no_subs_hits = _contains_any(_normalize(text), NO_SUBSIDIARY_PATTERNS)
            for hit in no_subs_hits:
                evidence.append(
                    _make_evidence(
                        category="no_subsidiary_evidence",
                        basis="standalone",
                        confidence="medium",
                        score=65,
                        text=hit,
                        source_artifact=source_artifact,
                        page=page,
                        chunk_id=chunk_id,
                        proximity="document",
                    )
                )
                if isinstance(page, int):
                    no_subs_pages.append(page)
            for hit in _subsidiary_positive_hits(text):
                evidence.append(
                    _make_evidence(
                        category="subsidiary_exists_evidence",
                        basis="consolidated",
                        confidence="low",
                        score=35,
                        text=hit,
                        source_artifact=source_artifact,
                        page=page,
                        chunk_id=chunk_id,
                        proximity="document",
                    )
                )
                if isinstance(page, int):
                    subsidiary_pages.append(page)

    summary = {
        "direct_standalone_pages": _dedupe_preserve(direct_standalone_pages),
        "direct_consolidated_pages": _dedupe_preserve(direct_consolidated_pages),
        "no_subsidiary_pages": _dedupe_preserve(no_subs_pages),
        "subsidiary_pages": _dedupe_preserve(subsidiary_pages),
    }
    return evidence, summary


def _collect_structural_evidence(
    discovery_items: List[Dict[str, Any]],
    raw_rows: List[Dict[str, Any]],
) -> Tuple[List[BasisEvidence], Dict[str, Any], List[str]]:
    evidence: List[BasisEvidence] = []
    conflicts: List[str] = []
    discovered_bases: List[str] = []
    raw_bases: List[str] = []

    for record in discovery_items:
        basis = str(record.get("basis") or "").strip().lower()
        if basis in {"standalone", "consolidated"}:
            discovered_bases.append(basis)
    for row in raw_rows:
        basis = str(row.get("basis") or "").strip().lower()
        if basis in {"standalone", "consolidated"}:
            raw_bases.append(basis)

    found_bases = set(discovered_bases + raw_bases)
    if found_bases == {"standalone"}:
        evidence.append(
            _make_evidence(
                category="structural_single_basis_presence",
                basis="standalone",
                confidence="medium",
                score=55,
                text="Only standalone sections/tables were detected.",
                source_artifact="structural",
                proximity="document",
            )
        )
    elif found_bases == {"consolidated"}:
        evidence.append(
            _make_evidence(
                category="structural_single_basis_presence",
                basis="consolidated",
                confidence="medium",
                score=55,
                text="Only consolidated sections/tables were detected.",
                source_artifact="structural",
                proximity="document",
            )
        )
    elif found_bases == {"standalone", "consolidated"}:
        conflicts.append("Both standalone and consolidated sections/tables were detected in the same document set.")

    summary = {
        "discovery_basis_counts": {
            "standalone": discovered_bases.count("standalone"),
            "consolidated": discovered_bases.count("consolidated"),
        },
        "raw_table_basis_counts": {
            "standalone": raw_bases.count("standalone"),
            "consolidated": raw_bases.count("consolidated"),
        },
    }
    return evidence, summary, conflicts


def _table_related_evidence(
    *,
    row: Dict[str, Any],
    discovery_items: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    document_evidence: List[BasisEvidence],
) -> Tuple[List[BasisEvidence], List[BasisEvidence], List[str]]:
    row_evidence: List[BasisEvidence] = []
    rejected: List[BasisEvidence] = []
    conflicts: List[str] = []
    table_type = str(row.get("table_type") or row.get("statement_type") or "").strip()
    row_page = _page_from_obj(row)
    row_basis = str(row.get("basis") or "").strip().lower()
    if row_basis in {"standalone", "consolidated"}:
        row_evidence.append(
            _make_evidence(
                category="table_context_metadata",
                basis=row_basis,
                confidence="medium",
                score=70,
                text=str(row.get("line_item_raw") or ""),
                source_artifact="raw_financial_tables.json",
                page=row_page,
                chunk_id=_chunk_id_from_obj(row),
                proximity="same_table",
            )
        )

    related_sections = RELATED_DISCOVERY_SECTIONS.get(table_type, {"financial_note"})
    for item in discovery_items:
        page = _page_from_obj(item)
        if row_page is not None and page is not None and abs(page - row_page) > 1:
            continue
        if str(item.get("section_type") or "") not in related_sections:
            continue
        text = str(item.get("text_excerpt") or "")
        standalone_hits, consolidated_hits = _basis_hits(text)
        proximity = "same_page" if row_page is not None and page == row_page else "near_page"
        for hit in standalone_hits:
            row_evidence.append(
                _make_evidence(
                    category="direct_statement_title",
                    basis="standalone",
                    confidence="high",
                    score=100 if proximity == "same_page" else 85,
                    text=hit,
                    source_artifact="financial_discovery.json",
                    page=page,
                    chunk_id=_chunk_id_from_obj(item),
                    proximity=proximity,
                )
            )
        for hit in consolidated_hits:
            row_evidence.append(
                _make_evidence(
                    category="direct_statement_title",
                    basis="consolidated",
                    confidence="high",
                    score=100 if proximity == "same_page" else 85,
                    text=hit,
                    source_artifact="financial_discovery.json",
                    page=page,
                    chunk_id=_chunk_id_from_obj(item),
                    proximity=proximity,
                )
            )

    for chunk in chunks:
        page = _page_from_obj(chunk)
        if row_page is None or page is None or abs(page - row_page) > 1:
            continue
        text = _text_from_chunk(chunk)
        standalone_hits, consolidated_hits = _basis_hits(text)
        proximity = "same_page" if page == row_page else "near_page"
        for hit in standalone_hits:
            row_evidence.append(
                _make_evidence(
                    category="direct_statement_title",
                    basis="standalone",
                    confidence="high",
                    score=95 if proximity == "same_page" else 80,
                    text=hit,
                    source_artifact="clean_chunks.json",
                    page=page,
                    chunk_id=_chunk_id_from_obj(chunk),
                    proximity=proximity,
                )
            )
        for hit in consolidated_hits:
            row_evidence.append(
                _make_evidence(
                    category="direct_statement_title",
                    basis="consolidated",
                    confidence="high",
                    score=95 if proximity == "same_page" else 80,
                    text=hit,
                    source_artifact="clean_chunks.json",
                    page=page,
                    chunk_id=_chunk_id_from_obj(chunk),
                    proximity=proximity,
                )
            )

    strong_local = [item for item in row_evidence if item.score >= 80]
    if strong_local:
        for item in document_evidence:
            if item.basis != strong_local[0].basis and item.score < 80:
                rejected.append(item)
    else:
        row_evidence.extend(
            item
            for item in document_evidence
            if item.score >= 55
            and item.category in {"no_subsidiary_evidence", "structural_single_basis_presence"}
        )

    standalone_score = sum(item.score for item in row_evidence if item.basis == "standalone")
    consolidated_score = sum(item.score for item in row_evidence if item.basis == "consolidated")
    if standalone_score and consolidated_score and abs(standalone_score - consolidated_score) < 25:
        conflicts.append("Competing standalone and consolidated evidence remains unresolved near the table context.")

    return row_evidence, rejected, conflicts


def _resolve_basis_from_evidence(
    evidence: List[BasisEvidence],
    *,
    default_unknown_reason: str,
) -> Tuple[str, str, str, List[str], List[Dict[str, Any]], List[int], List[str]]:
    if not evidence:
        return "unknown", "low", default_unknown_reason, [], [], [], []
    standalone_score = sum(item.score for item in evidence if item.basis == "standalone")
    consolidated_score = sum(item.score for item in evidence if item.basis == "consolidated")
    not_applicable_score = sum(item.score for item in evidence if item.basis == "not_applicable")
    conflicts: List[str] = []
    if not_applicable_score and not (standalone_score or consolidated_score):
        chosen = "not_applicable"
        confidence = "high" if not_applicable_score >= 80 else "medium"
    elif standalone_score == 0 and consolidated_score == 0:
        return "unknown", "low", default_unknown_reason, [], [], [], []
    else:
        chosen = "standalone" if standalone_score > consolidated_score else "consolidated"
        top_score = max(standalone_score, consolidated_score)
        other_score = min(standalone_score, consolidated_score)
        if other_score and abs(top_score - other_score) < 25:
            conflicts.append("Standalone and consolidated evidence scores are too close to resolve confidently.")
            chosen = "unknown"
            confidence = "low"
        elif any(item.category == "direct_statement_title" and item.basis == chosen and item.score >= 90 for item in evidence):
            confidence = "high"
        elif top_score >= 60:
            confidence = "medium"
        else:
            confidence = "low"
    used = sorted(evidence, key=lambda item: item.score, reverse=True)[:5]
    pages = _dedupe_preserve(item.page for item in used if isinstance(item.page, int))
    chunks = _dedupe_preserve(item.chunk_id for item in used if item.chunk_id)
    if chosen == "unknown":
        reasoning = default_unknown_reason if not conflicts else conflicts[0]
    else:
        reasoning = f"Resolved as {chosen} from {len(used)} basis signals."
    return chosen, confidence, reasoning, conflicts, [item.to_dict() for item in used], pages, chunks


def _field_resolution_candidates(
    normalized_payload: Dict[str, Any],
    raw_rows: List[Dict[str, Any]],
    discovery_items: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    document_evidence: List[BasisEvidence],
) -> List[FieldBasisResolution]:
    resolutions: List[FieldBasisResolution] = []
    row_groups: Dict[Tuple[int | None, str], List[Dict[str, Any]]] = {}
    for row in raw_rows:
        row_groups.setdefault((_page_from_obj(row), str(row.get("table_type") or "")), []).append(row)

    for section_name, section_payload in normalized_payload.items():
        if not isinstance(section_payload, dict):
            continue
        if section_name in {"basis_manifest", "basis_views"}:
            continue
        for field_name, entry in section_payload.items():
            if not isinstance(entry, dict):
                continue
            if "canonical_field" not in entry:
                continue
            current_basis = str(entry.get("basis") or "unknown")
            metric_id = str(entry.get("canonical_field") or field_name)
            field_path = f"{section_name}.{field_name}"
            if metric_id in NOT_APPLICABLE_METRICS or current_basis == "not_applicable":
                resolutions.append(
                    FieldBasisResolution(
                        field_path=field_path,
                        metric_id=metric_id,
                        source_line_item=str(entry.get("source_line_item") or ""),
                        source_page=entry.get("source_page"),
                        current_basis=current_basis,
                        resolved_basis="not_applicable",
                        confidence="high",
                        reasoning="Metric is not applicable for standalone/consolidated basis resolution.",
                    )
                )
                continue
            table_type = FIELD_TO_TABLE_TYPE.get(section_name, section_name)
            source_page = entry.get("source_page")
            source_line = str(entry.get("source_line_item") or "")
            normalized_source = _normalize(source_line)
            candidate_rows = row_groups.get((source_page, table_type), [])
            matched_row = None
            for row in candidate_rows:
                if _normalize(str(row.get("line_item_raw") or "")) == normalized_source and normalized_source:
                    matched_row = row
                    break
            if matched_row is None and candidate_rows:
                matched_row = candidate_rows[0]

            evidence: List[BasisEvidence] = []
            rejected: List[BasisEvidence] = []
            conflicts: List[str] = []
            if matched_row is not None:
                evidence, rejected, conflicts = _table_related_evidence(
                    row=matched_row,
                    discovery_items=discovery_items,
                    chunks=chunks,
                    document_evidence=document_evidence,
                )
            else:
                evidence = [item for item in document_evidence if item.score >= 55]

            resolved_basis, confidence, reasoning, extra_conflicts, used, _pages, _chunks = _resolve_basis_from_evidence(
                evidence,
                default_unknown_reason="No reliable basis evidence was found for this fact.",
            )
            resolutions.append(
                FieldBasisResolution(
                    field_path=field_path,
                    metric_id=metric_id,
                    source_line_item=source_line,
                    source_page=source_page if isinstance(source_page, int) else None,
                    current_basis=current_basis,
                    resolved_basis=resolved_basis,
                    confidence=confidence,
                    evidence_used=used,
                    evidence_rejected=[item.to_dict() for item in rejected],
                    basis_conflicts=conflicts + extra_conflicts,
                    reasoning=reasoning,
                    warnings=[],
                )
            )
    return resolutions


def _global_basis_resolution(
    document_evidence: List[BasisEvidence],
    structural_evidence: List[BasisEvidence],
    structural_conflicts: List[str],
) -> Tuple[str, str, str, List[str], List[Dict[str, Any]], List[int], List[str]]:
    combined = document_evidence + structural_evidence
    resolved_basis, confidence, reasoning, conflicts, used, pages, chunks = _resolve_basis_from_evidence(
        combined,
        default_unknown_reason="No reliable document-level basis evidence was found.",
    )
    return resolved_basis, confidence, reasoning, structural_conflicts + conflicts, used, pages, chunks


def _apply_to_normalized(
    normalized_path: Path,
    resolution_report: FinancialBasisResolutionReport,
) -> int:
    if not normalized_path.exists():
        return 0
    payload = _load_json(normalized_path)
    updated = 0
    resolution_map = {item.field_path: item for item in resolution_report.field_resolutions}
    for section_name, section_payload in payload.items():
        if not isinstance(section_payload, dict):
            continue
        for field_name, entry in section_payload.items():
            if not isinstance(entry, dict) or "canonical_field" not in entry:
                continue
            field_path = f"{section_name}.{field_name}"
            resolution = resolution_map.get(field_path)
            if resolution is None:
                continue
            current_basis = str(entry.get("basis") or "unknown")
            current_preferred = str(payload.get("preferred_basis") or "unknown")
            if (
                current_preferred in {"standalone", "consolidated"}
                and current_basis in {"standalone", "consolidated"}
                and current_basis != current_preferred
            ):
                entry["basis"] = "unknown"
                for comparative in entry.get("comparatives", []):
                    if isinstance(comparative, dict) and str(comparative.get("basis") or "unknown") == current_basis:
                        comparative["basis"] = "unknown"
                updated += 1
                continue
            if current_basis != "unknown":
                continue
            if resolution.resolved_basis not in {"standalone", "consolidated"}:
                continue
            if resolution.confidence not in {"medium", "high"}:
                continue
            if current_preferred in {"standalone", "consolidated"} and resolution.resolved_basis != current_preferred:
                continue
            entry["basis"] = resolution.resolved_basis
            for comparative in entry.get("comparatives", []):
                if isinstance(comparative, dict) and str(comparative.get("basis") or "unknown") == "unknown":
                    comparative["basis"] = resolution.resolved_basis
            resolution.applied_to_normalized = True
            updated += 1

    current_preferred = str(payload.get("preferred_basis") or "unknown")
    critical_field_bases: List[str] = []
    for section_name, section_payload in payload.items():
        if not isinstance(section_payload, dict):
            continue
        for field_name, entry in section_payload.items():
            if not isinstance(entry, dict) or "canonical_field" not in entry:
                continue
            if f"{section_name}.{field_name}" not in PREFERRED_BASIS_FIELD_PATHS:
                continue
            if not any(
                isinstance(entry.get(value_key), (int, float))
                for value_key in ("value_crore", "value_per_share", "value_shares")
            ) and not entry.get("value_original"):
                continue
            basis = str(entry.get("basis") or "unknown")
            if basis in {"standalone", "consolidated", "unknown"}:
                critical_field_bases.append(basis)

    explicit_critical_bases = sorted({basis for basis in critical_field_bases if basis in {"standalone", "consolidated"}})
    has_unknown_critical = "unknown" in critical_field_bases
    field_preferred_basis = current_preferred
    field_basis_confidence = str(payload.get("basis_confidence") or "low")
    field_reason = ""
    if len(explicit_critical_bases) == 1 and not has_unknown_critical:
        field_preferred_basis = explicit_critical_bases[0]
        field_basis_confidence = "high"
        field_reason = "selected from resolved critical field-level basis ownership"
    elif len(explicit_critical_bases) > 1:
        field_preferred_basis = "mixed"
        field_basis_confidence = "low"
        field_reason = "critical fields resolve to more than one explicit reporting basis"
    elif has_unknown_critical:
        field_preferred_basis = "unknown"
        field_basis_confidence = "low"
        if explicit_critical_bases:
            field_reason = "some critical fields resolved, but other critical fields remain unknown"
        else:
            field_reason = "critical field-level basis ownership remains unresolved"
    else:
        field_preferred_basis = "unknown"
        field_basis_confidence = "low"
        field_reason = "no populated critical field has explicit basis ownership"

    if field_preferred_basis in {"mixed", "standalone", "consolidated", "unknown"}:
        payload["preferred_basis"] = field_preferred_basis
        payload["basis_confidence"] = field_basis_confidence
        manifest = payload.get("basis_manifest")
        if not isinstance(manifest, dict):
            manifest = {}
            payload["basis_manifest"] = manifest
        manifest["preferred_basis"] = field_preferred_basis
        manifest["basis_confidence"] = field_basis_confidence
        manifest["selected_basis_reason"] = field_reason or str(manifest.get("selected_basis_reason") or "")
        options = manifest.get("basis_options_available")
        if not isinstance(options, list):
            options = []
        for basis in explicit_critical_bases:
            if basis not in options:
                options.append(basis)
        manifest["basis_options_available"] = options
        warnings = manifest.get("basis_warnings")
        if not isinstance(warnings, list):
            warnings = []
        payload["warnings"] = list(payload.get("warnings") or [])
        if field_preferred_basis == "mixed":
            warnings.append("critical financial fields resolve to mixed standalone/consolidated basis")
        elif field_preferred_basis == "unknown" and has_unknown_critical:
            warnings.append("critical financial fields include unresolved basis after financial_basis_resolution")
        manifest["basis_warnings"] = _dedupe_preserve(warnings)

    _write_json(normalized_path, payload)
    return updated


def _apply_to_truth_report(
    reconciliation_path: Path,
    resolution_report: FinancialBasisResolutionReport,
) -> int:
    if not reconciliation_path.exists():
        return 0
    payload = _load_json(reconciliation_path)
    warnings = list(payload.get("warnings") or [])
    unresolved = list(payload.get("unresolved_contradictions") or [])
    resolved = list(payload.get("resolved_contradictions") or [])
    warning_resolutions = list(payload.get("warning_resolutions") or [])
    applied = 0

    for message in warnings + unresolved:
        lowered = str(message or "").lower()
        if not any(pattern in lowered for pattern in BASIS_WARNING_PATTERNS):
            continue
        if resolution_report.resolved_basis not in {"standalone", "consolidated"}:
            continue
        if resolution_report.confidence not in {"medium", "high"}:
            continue
        entry = {
            "original_warning": message,
            "resolution_status": "resolved",
            "resolved_by": "financial_basis_resolution",
            "evidence_used": list(resolution_report.evidence_used),
        }
        if entry not in warning_resolutions:
            warning_resolutions.append(entry)
            applied += 1
        if message in unresolved:
            unresolved.remove(message)
        resolution_text = (
            f"Basis warning resolved by financial_basis_resolution.json: "
            f"{resolution_report.resolved_basis} ({resolution_report.confidence})."
        )
        if resolution_text not in resolved:
            resolved.append(resolution_text)

    payload["unresolved_contradictions"] = unresolved
    payload["resolved_contradictions"] = resolved
    payload["warning_resolutions"] = warning_resolutions
    _write_json(reconciliation_path, payload)
    return applied


def _apply_to_fact_registry(fact_registry_path: Path) -> int:
    if not fact_registry_path.exists():
        return 0
    return 1


def build_financial_basis_resolution(
    *,
    company: str,
    year: str,
    financial_root: Path,
) -> FinancialBasisResolutionReport:
    chunks = _load_chunks(financial_root.parent / "extracted" / "clean_chunks.json")
    discovery_items = _load_discovery_items(financial_root / "financial_discovery.json")
    raw_rows = _load_raw_rows(financial_root / "raw_financial_tables.json")
    normalized_payload = _load_json(financial_root / "normalized_fundamentals.json") if (financial_root / "normalized_fundamentals.json").exists() else {}

    document_evidence, document_summary = _document_evidence(chunks, discovery_items)
    structural_evidence, structural_summary, structural_conflicts = _collect_structural_evidence(discovery_items, raw_rows)
    resolved_basis, confidence, reasoning, conflicts, evidence_used, source_pages, source_chunks = _global_basis_resolution(
        document_evidence,
        structural_evidence,
        structural_conflicts,
    )

    field_resolutions = _field_resolution_candidates(
        normalized_payload if isinstance(normalized_payload, dict) else {},
        raw_rows,
        discovery_items,
        chunks,
        document_evidence + structural_evidence,
    )

    warnings: List[str] = []
    found_bases = {
        item.resolved_basis
        for item in field_resolutions
        if item.resolved_basis in {"standalone", "consolidated"}
    }
    if found_bases == {"standalone", "consolidated"}:
        warnings.append("Both standalone and consolidated basis appear in the same document set; field-level basis was preserved independently.")
    if any(
        item.category == "subsidiary_exists_evidence"
        for item in document_evidence
    ) and all(item.resolved_basis != "consolidated" for item in field_resolutions):
        warnings.append("Subsidiary evidence exists, but extracted facts remain standalone or unknown; consolidated statements may also exist.")

    report = FinancialBasisResolutionReport(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        resolved_basis=resolved_basis,
        confidence=confidence,
        evidence_used=evidence_used,
        evidence_rejected=[],
        basis_conflicts=conflicts,
        reasoning=reasoning,
        source_pages=source_pages,
        source_chunks=source_chunks,
        warnings=warnings,
        document_basis_summary={
            **document_summary,
            **structural_summary,
        },
        field_resolutions=field_resolutions,
        warning_resolutions=[],
    )
    errors = validate_financial_basis_resolution_payload(report.to_dict())
    if errors:
        raise ValueError("; ".join(errors))
    return report


def write_financial_basis_resolution(
    *,
    company: str,
    year: str,
    financial_root: Path,
    output_path: Path,
) -> FinancialBasisResolutionReport:
    report = build_financial_basis_resolution(company=company, year=year, financial_root=financial_root)
    normalized_path = financial_root / "normalized_fundamentals.json"
    registry_path = financial_root / "financial_fact_registry.json"
    reconciliation_path = financial_root / "financial_truth_reconciliation_report.json"
    quarantine_path = financial_root / "financial_artifact_quarantine_report.json"

    _apply_to_normalized(normalized_path, report)

    if registry_path.exists():
        write_financial_fact_registry(
            company=company,
            year=year,
            financial_root=financial_root,
            registry_output_path=registry_path,
            reconciliation_output_path=reconciliation_path if reconciliation_path.exists() else financial_root / "financial_truth_reconciliation_report.json",
            quarantine_output_path=quarantine_path,
        )
        for item in report.field_resolutions:
            if item.applied_to_normalized and item.resolved_basis in {"standalone", "consolidated"}:
                item.applied_to_fact_registry = True

    _apply_to_truth_report(reconciliation_path, report)
    _write_json(output_path, report.to_dict())
    return report
