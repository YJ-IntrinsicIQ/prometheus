"""The Financial Fact Registry is the only authority on which extracted figures may be used.

Every consumer of a year's financial data (ratios, growth, trends, the quality summary, CIM / PCIM, the truth pack and, through them, the investor panels and Ask) reads
`normalized_fundamentals.json`. A registry that rejects a figure but leaves it in that file only quarantines it for the registry's own readers: the rejected value then
flows on through every other path (a bank's liquidity-bucket "debt" reached the panel metric registry that way).

`settle_financial_authority` closes that path at the source. It builds the registry from the normalized figures alone, and moves every figure the registry rejects
(invalid or unreliable) out of its section and into `registry_exclusions`, with the reasons. Its section entry is left empty - unavailable, not substituted - so a consumer
cannot read the value by any route, and the registry rebuilt afterwards still lists the figure as quarantined. Ratios and growth are then computed from what remains.
The eligibility of a figure is the registry's decision; whether the figure was independently verified against the filing is a separate status that never changes it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from core.context_paths import guarded_write_text, resolve_output_root

from .entity_basis import declared_entity_basis
from .fact_registry import BALANCE_SHEET_STOCK_METRICS, build_financial_fact_registry
from .normalizer import _empty_entry

SECTIONS = ("profit_and_loss", "balance_sheet", "cash_flow", "share_data", "corporate_actions", "shareholding_pattern")
_DERIVED_FROM_NORMALIZED = frozenset({"financial_ratios.json", "financial_growth.json"})
_REJECTED = {"invalid", "unreliable"}
STOCK_METRICS = BALANCE_SHEET_STOCK_METRICS | {"other_assets"}


def settle_financial_authority(
    *,
    company: str,
    year: str,
    financial_root: Path,
    output_root: Path | str,
    authorize_served_write: bool = False,
    chunk_paths: Iterable[Path] = (),
) -> Dict[str, Any]:
    """Moves registry-rejected figures out of normalized_fundamentals.json. Idempotent. Returns {metric_id: reasons} for what is excluded after the call."""
    root = resolve_output_root(output_root, authorize_served=authorize_served_write)
    path = Path(financial_root) / "normalized_fundamentals.json"
    normalized = json.loads(path.read_text(encoding="utf-8"))
    registry, _report, _quarantine = build_financial_fact_registry(company=company, year=year, financial_root=Path(financial_root), ignore_artifacts=_DERIVED_FROM_NORMALIZED)

    # what the registry considers a rejected figure (the context it decided in is kept, so the rebuilt registry decides identically on the emptied file)
    rejected = {fact.metric_id: fact for fact in [*registry.invalid_facts, *registry.unreliable_facts] if fact.availability_status in _REJECTED and not fact.usable_downstream}
    exclusions: Dict[str, Any] = dict(normalized.get("registry_exclusions") or {})
    # Alternate-basis candidates that are rows of a NOTE table while the statement itself was extracted are the same unvetted rows the registry refuses as primary figures (a related-party
    # note's "Property, plant and equipment" under a basis view of a company whose balance sheet states 10,035 crore): they do not travel in the file either.
    if any(isinstance(e, dict) and e.get("is_primary_statement") for e in (normalized.get("balance_sheet") or {}).values()):
        for sections in (normalized.get("basis_views") or {}).values():
            for metric_id, entry in list((sections.get("balance_sheet") or {}).items()):
                if (metric_id in STOCK_METRICS and isinstance(entry, dict) and entry.get("value_crore") is not None and not entry.get("is_primary_statement") and not entry.get("derived")
                        and str(entry.get("source_section_type") or "") == "financial_note"):
                    sections["balance_sheet"][metric_id] = {**_empty_entry(metric_id), "excluded_by_registry": "note_table_row"}
    context = dict(normalized.get("registry_context") or {})
    year_dir = Path(financial_root).parent
    entity_basis = declared_entity_basis([*chunk_paths, year_dir / "extracted" / "clean_chunks.json", year_dir / "extracted" / "clean_chunks_rechunked.json"])
    context["entity_basis"] = entity_basis
    if entity_basis in {"standalone", "consolidated"}:
        _apply_entity_basis(normalized, entity_basis)
    context.setdefault("bank_format", _bank_format(registry, normalized))        # decided on the full file: the emptied entries no longer say which schedule they came from
    for section in SECTIONS:
        block = normalized.get(section)
        if not isinstance(block, dict):
            continue
        for metric_id, entry in list(block.items()):
            fact = rejected.get(metric_id)
            if fact is None or not isinstance(entry, dict) or entry.get("value_crore") is None and entry.get("value_per_share") is None and entry.get("value_shares") is None and entry.get("raw_number") is None:
                continue
            exclusions[metric_id] = {"section": section, "status": fact.availability_status, "reasons": list(fact.warnings), "entry": entry}
            block[metric_id] = {**_empty_entry(metric_id), "excluded_by_registry": fact.availability_status}
    # A metric the registry rejects for the year is rejected in every reporting-basis view of the file too: the alternate views are alternates of the same extraction (the same figure
    # under another label or page, or a sibling basis of the same unreliable statement), and a consumer that reads a basis view (CIM carries them) must not find it there.
    for sections in (normalized.get("basis_views") or {}).values():
        for section in SECTIONS:
            for metric_id, entry in list((sections.get(section) or {}).items()):
                record = exclusions.get(metric_id)
                if record and isinstance(entry, dict) and (entry.get("value_crore") is not None or entry.get("value_per_share") is not None or entry.get("value_shares") is not None):
                    sections[section][metric_id] = {**_empty_entry(metric_id), "excluded_by_registry": record["status"]}
    _sync_registry_capex(normalized, registry)
    normalized["registry_exclusions"] = exclusions
    normalized["registry_context"] = context
    guarded_write_text(root, path, json.dumps(normalized, indent=2, ensure_ascii=False))
    return {metric_id: record["reasons"] for metric_id, record in exclusions.items()}


def _sync_registry_capex(normalized: Dict[str, Any], registry) -> None:
    """Total capex is the registry's decision (PPE/CWIP purchases PLUS separately reported intangible purchases). The normalized file carries the first capex line extracted; ratios
    and growth are computed from the normalized file, so a registry correction not written back leaves free cash flow, FCF margin and capex growth computed on part of capex.
    The synced figure is a total of two cash-flow lines and is recorded as DERIVED from them (a total carrying one line's label would misstate its source); free cash flow, derived at
    normalization from that first line, is re-derived from the same cash flow and the registry's total."""
    facts = [*getattr(registry, "available_facts", []), *registry.derived_facts, *getattr(registry, "partial_facts", [])]
    fact = next((f for f in facts if f.metric_id == "capex" and f.usable_downstream and isinstance(f.value, (int, float))), None)
    cash_flow = normalized.get("cash_flow") or {}
    entry = cash_flow.get("capex")
    if not isinstance(entry, dict) or not isinstance(entry.get("value_crore"), (int, float)):
        return
    components = {f.metric_id: f.value for f in facts if f.metric_id in {"capex_ppe_cwip_cash_outflow", "capex_intangible_cash_outflow"} and isinstance(f.value, (int, float)) and abs(f.value) > 1e-6}
    if fact is not None and abs(entry["value_crore"] - fact.value) > 0.005:
        entry["value_crore_before_registry"] = entry["value_crore"]
        entry["value_crore"] = round(float(fact.value), 6)
        entry["capex_abs_crore"] = abs(entry["value_crore"])
        entry["registry_synced"] = "capex is the registry's total of PPE/CWIP and separately reported intangible purchases"
    label = "derived: capex = purchase of property, plant and equipment + purchase of intangible assets (separate cash-flow lines)"
    if len(components) == 2 and abs(sum(components.values()) - entry["value_crore"]) <= 0.005 and entry.get("source_line_item") != label:
        entry.update({"derived": True, "formula": "capex = PPE/CWIP purchases + intangible purchases (separate cash-flow lines)", "inputs_used": components,
                      "source_line_item_before_registry": entry.get("source_line_item_before_registry") or entry.get("source_line_item"), "source_line_item": label})
    fcf = cash_flow.get("fcf")
    inputs = fcf.get("inputs_used") if isinstance(fcf, dict) else None
    if (isinstance(fcf, dict) and fcf.get("derived") and isinstance(inputs, dict) and isinstance(inputs.get("cfo"), (int, float)) and isinstance(inputs.get("capex"), (int, float))
            and fcf.get("value_crore") is not None and abs(inputs["capex"] - entry["value_crore"]) > 0.005):
        fcf.setdefault("value_crore_before_registry", fcf["value_crore"])
        fcf["value_crore"] = round(float(inputs["cfo"]) + entry["value_crore"], 6)
        fcf["inputs_used"] = {**inputs, "capex": entry["value_crore"]}
        fcf["registry_synced"] = "re-derived from cfo and the registry's total capex"


def _apply_entity_basis(normalized: Dict[str, Any], entity_basis: str) -> None:
    """The report presents only `entity_basis` statements: every figure taken from it is on that basis, whatever a table-level signal said. The label that was replaced is kept."""
    normalized["preferred_basis"] = entity_basis
    for section in SECTIONS:
        for entry in (normalized.get(section) or {}).values():
            if isinstance(entry, dict) and entry.get("basis") in {"consolidated", "standalone", "unknown"} and entry.get("basis") != entity_basis and any(
                    entry.get(k) is not None for k in ("value_crore", "value_per_share", "value_shares", "raw_number")):
                entry["basis_relabelled_from"] = entry["basis"]
                entry["basis"] = entity_basis


def _bank_format(registry, normalized: Dict[str, Any]) -> bool:
    return any(
        str((entry or {}).get("source_section_type") or "").startswith("schedule_")
        for section in ("balance_sheet", "profit_and_loss")
        for entry in (normalized.get(section) or {}).values()
        if isinstance(entry, dict)
    ) or "interest earned" in str(((normalized.get("profit_and_loss") or {}).get("revenue") or {}).get("source_line_item") or "").lower()


def rejected_metric_ids(*, company: str, year: str, financial_root: Path) -> List[str]:
    """Metrics the registry rejects for this year NOW: those in the persisted registry (if one exists) and those a registry built from the year's files would reject. A calculation reads
    this at the moment it runs, so a figure that looks valid in the normalized file cannot be used merely because the settlement stage did not run first."""
    rejected = set()
    persisted = Path(financial_root) / "financial_fact_registry.json"
    if persisted.exists():
        try:
            payload = json.loads(persisted.read_text(encoding="utf-8"))
            rejected |= {f["metric_id"] for key in ("invalid_facts", "unreliable_facts") for f in payload.get(key) or [] if isinstance(f, dict) and not f.get("usable_downstream")}
        except (OSError, ValueError):
            pass
    try:
        registry, _report, _quarantine = build_financial_fact_registry(company=company, year=year, financial_root=Path(financial_root), ignore_artifacts=_DERIVED_FROM_NORMALIZED)
        rejected |= {f.metric_id for f in [*registry.invalid_facts, *registry.unreliable_facts] if not f.usable_downstream}
    except (RuntimeError, ValueError, KeyError, FileNotFoundError):
        pass
    return sorted(rejected)


def withhold_metrics(normalized: Dict[str, Any], metric_ids) -> Dict[str, Any]:
    """A copy of the normalized payload in which each listed metric is an empty (unavailable) entry in every section and every basis view."""
    import copy
    cleaned = copy.deepcopy(normalized)
    wanted = set(metric_ids)
    blocks = [cleaned] + list((cleaned.get("basis_views") or {}).values())
    for block in blocks:
        for section in SECTIONS:
            for metric_id in wanted & set((block.get(section) or {})):
                if isinstance(block[section][metric_id], dict):
                    block[section][metric_id] = {**_empty_entry(metric_id), "excluded_by_registry": "rejected"}
    return cleaned


def excluded_metrics(financial_root: Path) -> List[str]:
    """The metrics whose figures the registry has rejected for this year (empty when none or when the year has no normalized file)."""
    path = Path(financial_root) / "normalized_fundamentals.json"
    if not path.exists():
        return []
    return sorted((json.loads(path.read_text(encoding="utf-8")).get("registry_exclusions") or {}))
