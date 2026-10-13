"""M63/G3.1: the minimum material-anchor coverage contract.

A filing can pass primary-statement extraction and still have its capital allocation, segments, contingencies, guidance or transactions silently dropped. For each
anchor family this module answers one question from artifacts that already exist - was the evidence FOUND, is its absence supported by SEARCH EVIDENCE, was it
NOT_EXTRACTED despite the filing mentioning it, or is the family NOT_APPLICABLE to the sector? A family is never reported absent without the search that supports it,
and an extraction run whose families include NOT_EXTRACTED is labelled incomplete instead of 'ready'.

It adds no extractor: it reads the raw tables, the sourced disclosures and (optionally) the management-commitment register the pipeline already produced."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

FOUND = "FOUND"
NOT_DISCLOSED = "NOT_DISCLOSED_WITH_SEARCH_EVIDENCE"
NOT_EXTRACTED = "NOT_EXTRACTED"
NOT_APPLICABLE = "NOT_APPLICABLE"
STATUSES = (FOUND, NOT_DISCLOSED, NOT_EXTRACTED, NOT_APPLICABLE)

# What the filing would say if the family were disclosed. The search is over the filing's own chunks, so a family with no hit is 'not disclosed' only in the sense of
# 'these patterns were searched in N chunks and never matched' - the evidence is recorded with the verdict.
_SEARCH: Dict[str, Sequence[str]] = {
    "primary_statements": (r"balance\s+sheet", r"statement\s+of\s+profit\s+and\s+loss|income\s+statement", r"cash\s+flows?"),
    "cash_flow_and_borrowings": (r"cash\s+flows?\s+from\s+operating|operating\s+activities", r"borrowings?|debentures?|term\s+loans?|working\s+capital\s+(?:loan|facilit)"),
    "capital_allocation": (r"dividend", r"buy-?back|repurchase\s+of\s+shares", r"capital\s+expenditure|capex|purchase\s+of\s+property"),
    "segments_and_geography": (r"segment", r"geograph|revenue\s+by\s+(?:region|geography|market)"),
    "risks_and_contingencies": (r"contingent\s+liabilit", r"claims\s+against\s+the\s+(?:company|bank)", r"\brisk\s+(?:factors?|management)\b|material\s+risks?"),
    "guidance_and_commitments": (r"\bguidance\b|\boutlook\b", r"(?:we|the\s+company)\s+(?:plan|aim|intend|expect|will)\s+to|target(?:s|ed)?\s+(?:of|to|by)\b"),
    "material_transactions": (r"definitive\s+agreement|proposed\s+acquisition|announced\s+the\s+(?:proposed\s+)?acquisition|scheme\s+of\s+arrangement|share\s+purchase\s+agreement|completed\s+the\s+acquisition|merger\s+agreement",),
}
_SINGLE_SEGMENT = re.compile(r"(?:operates?|operating)\s+(?:only\s+)?(?:in\s+)?(?:a\s+|one\s+)?(?:single|one)\s+(?:reportable\s+|business\s+|operating\s+)?segment|only\s+one\s+(?:reportable\s+)?segment|single\s+(?:reportable\s+)?segment", re.IGNORECASE)


def _text(chunk: Dict[str, Any]) -> str:
    return " ".join(str(chunk.get("text", "")).split())


def _search(chunks: Sequence[Dict[str, Any]], family: str) -> Dict[str, Any]:
    patterns = _SEARCH[family]
    pages: List[int] = []
    hit_chunks = 0
    for chunk in chunks:
        text = _text(chunk).lower()
        if any(re.search(p, text) for p in patterns):
            hit_chunks += 1
            if isinstance(chunk.get("page"), int) and len(pages) < 8 and chunk["page"] not in pages:
                pages.append(chunk["page"])
    return {"chunks_searched": len(chunks), "patterns": list(patterns), "chunks_matching": hit_chunks, "example_pages": pages}


def _rows(tables: Dict[str, Any], names: Iterable[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for name in names:
        for row in tables.get(name) or []:
            if isinstance(row, dict):
                out.append(row)
    return out


def _has_label(rows: Iterable[Dict[str, Any]], pattern: str) -> Optional[Dict[str, Any]]:
    for row in rows:
        if re.search(pattern, str(row.get("line_item_raw", "")), re.IGNORECASE) and row.get("values"):
            return row
    return None


def _is_bank(tables: Dict[str, Any]) -> bool:
    return any(str(row.get("source_section_type", "")).startswith("schedule_") for rows in tables.values() for row in (rows or []) if isinstance(row, dict))


def build_anchor_coverage(
    *,
    chunks: Sequence[Dict[str, Any]],
    raw_tables: Dict[str, Any],
    headline: Optional[Dict[str, Any]] = None,
    transactions: Optional[Dict[str, Any]] = None,
    buyback_or_dividend_disclosures: int = 0,
    commitment_register: Optional[Dict[str, Any]] = None,
    year: str = "",
) -> Dict[str, Any]:
    """Per-family verdicts with the evidence behind each. `commitment_register` is optional: without it the guidance family is reported from the search alone and says so."""
    tables = (raw_tables or {}).get("tables", raw_tables or {})
    bank = _is_bank(tables)
    families: Dict[str, Dict[str, Any]] = {}

    def verdict(family: str, found: Optional[Dict[str, Any]], note: str = "", applicable: bool = True) -> None:
        search = _search(chunks, family)
        if not applicable:
            status = NOT_APPLICABLE
        elif found:
            status = FOUND
        elif search["chunks_matching"] > 0:
            status = NOT_EXTRACTED
        else:
            status = NOT_DISCLOSED
        families[family] = {"status": status, "evidence": found or {}, "search": search, "note": note}

    pl, bs, cf = tables.get("profit_and_loss") or [], tables.get("balance_sheet") or [], tables.get("cash_flow") or []
    primary_ok = bool(_has_label(pl, r"profit|income|revenue") and _has_label(bs, r"total\s+(?:assets|equity|liabilit)|equity") and _has_label(cf, r"operating\s+activities|profit\s+before\s+tax"))
    verdict("primary_statements", {"profit_and_loss_rows": len(pl), "balance_sheet_rows": len(bs), "cash_flow_rows": len(cf)} if primary_ok else None)

    cfo = _has_label(cf, r"operating\s+activities")
    borrowing = _has_label(_rows(tables, ("balance_sheet", "borrowings")), r"borrowing|debenture|term\s+loan|debt")
    verdict("cash_flow_and_borrowings", {"cash_flow_from_operations": bool(cfo), "borrowings_row": (borrowing or {}).get("line_item_raw")} if cfo and (borrowing or bank) else None,
            note="a bank's funding is deposits; the industrial borrowings test does not apply" if bank else "")
    if bank and not families["cash_flow_and_borrowings"]["evidence"]:
        pass

    cap_rows = _has_label(cf, r"dividend|buy-?back|bought\s+back|purchase\s+of\s+property|acquisition\s+of\s+property|capital\s+expenditure|intangible")
    verdict("capital_allocation", {"cash_flow_line": cap_rows.get("line_item_raw")} if cap_rows else ({"narrative_disclosures": buyback_or_dividend_disclosures} if buyback_or_dividend_disclosures else None))

    segment_rows = _rows(tables, ("segment_reporting",))
    single = next((m.group(0) for c in chunks for m in [_SINGLE_SEGMENT.search(_text(c))] if m), None)
    verdict("segments_and_geography", {"segment_rows": len(segment_rows)} if segment_rows else ({"single_segment_statement": single} if single else None))

    contingent = _has_label(_rows(tables, tuple(tables)), r"contingent|claims\s+against")
    verdict("risks_and_contingencies", {"row": contingent.get("line_item_raw"), "page": contingent.get("page")} if contingent else None)

    if commitment_register is not None:
        mine = [c for c in commitment_register.get("commitments", []) if str(c.get("announcement_period", "")).lower() == year.lower()]
        verdict("guidance_and_commitments", {"register_items_for_year": len(mine)} if mine else None)
    else:
        verdict("guidance_and_commitments", None, note="the commitment register was not supplied: this verdict is from the text search alone and cannot be FOUND here")

    txns = [t for t in (transactions or {}).get("transactions", []) if t.get("target")]
    verdict("material_transactions", {"transactions": [{"target": t["target"], "status": t.get("status")} for t in txns]} if txns else None)

    incomplete = [name for name, fam in families.items() if fam["status"] == NOT_EXTRACTED]
    unassessed = [name for name, fam in families.items() if fam["note"].startswith("the commitment register was not supplied")]
    return {
        "year": year,
        "families": families,
        "counts": {s: sum(1 for fam in families.values() if fam["status"] == s) for s in STATUSES},
        "not_extracted": incomplete,
        "completeness": "INCOMPLETE" if incomplete else "COMPLETE_FOR_SEARCHED_FAMILIES",
        "caveat": ("families " + ", ".join(unassessed) + " were not assessed against a register; ") if unassessed else "",
    }


def extraction_status(readiness_status: str, coverage: Dict[str, Any]) -> str:
    """A statement-level READY is not an extraction success when a material family the filing mentions was not extracted."""
    if readiness_status == "READY" and coverage.get("not_extracted"):
        return "READY_STATEMENTS_ONLY"
    return readiness_status
