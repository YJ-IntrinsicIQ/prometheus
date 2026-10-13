"""
Fact-pack enrichment for Contract V5 — ENG-MISSION52.2a

Adds source-backed facts the V2 fact pack does not carry, WITHOUT modifying
fact_pack_v2.py (whose digest is part of the frozen V3/V4 contract identities):

  * hard-commitment detail with original (unit-preserving) statements and source refs
  * regulatory-filing follow-up chain (delivery / deadline adherence / outcome kept separate)
  * capital-allocation facts from the canonical ledger + announced-transaction state
  * named-entity statements (products / transactions) from canonical progression events
  * behavioral consistency evidence per dimension from canonical dimension records

Deterministic. Zero AI calls. Every fact carries period and source.
Sparse-safe: missing canonical files yield empty structures, never invented facts.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ENRICHMENT_VERSION = "m522d_enrichment_v2"
REPO_ROOT = Path(__file__).resolve().parents[2]

_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]
_MONTH_YEAR = re.compile(r"\b(" + "|".join(m.capitalize() for m in _MONTHS) + r")\s+(?:\d{1,2},\s+)?(20\d{2})\b", re.I)

_FUTURE_INTENT = re.compile(
    r"expected to be (?:filed|submitted)|plan(?:s|ned)? to (?:file|submit)|will be (?:filed|submitted)|to be (?:filed|submitted)",
    re.I)
_FILED = re.compile(r"\bfiled\b|\bfiling\b|\bsubmitted\b", re.I)
_VALIDATED = re.compile(r"\bvalidated\b", re.I)
_APPROVED = re.compile(r"\bapproved\b|marketing authori[sz]ation (?:was |has been )?granted|positive (?:chmp )?opinion", re.I)
_PHASE = re.compile(r"\bPhase\s*(3|III|2|II|1|I)\b", re.I)
_REG_FILING_COMMITMENT = re.compile(
    r"\b(?:file|submit)\b.{0,120}\b(?:ema|fda|usfda|european medicines|regulator|authority|agency)\b", re.I)

_GENERIC_NAMES = {"others", "other", "acquisition", "expansion"}

POSITIVE_TYPES = {"project_operational", "capacity_operational", "project_partially_operational",
                  "capacity_partially_operational", "risk_reducing"}
NEGATIVE_TYPES = {"project_paused", "capacity_delayed", "risk_recurring", "risk_persistent", "risk_increasing"}
ADAPTATION_TYPES = {"project_superseded", "capacity_superseded"}

_ASSESSMENT_TO_CANON = {
    "strong": "CONSISTENT", "positive": "CONSISTENT", "improving": "CONSISTENT",
    "mixed": "INCONSISTENT", "weak": "INCONSISTENT", "negative": "INCONSISTENT",
    "deteriorating": "INCONSISTENT",
}


def _load(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fy_num(label: str) -> Optional[int]:
    m = re.search(r"(\d{2,4})", str(label or ""))
    if not m:
        return None
    n = int(m.group(1))
    return n % 100 if n > 100 else n


def _fy_label(label: str) -> str:
    n = _fy_num(label)
    return f"FY{n:02d}" if n is not None else str(label).upper()


def _is_generic(name: str) -> bool:
    n = str(name or "").strip().lower()
    return len(n) < 4 or n in _GENERIC_NAMES


def _chunks(path: Path) -> List[Dict[str, Any]]:
    d = _load(path)
    if isinstance(d, dict):
        d = d.get("chunks", [])
    return [c for c in d if isinstance(c, dict)] if isinstance(d, list) else []


# ── Target-period arithmetic ─────────────────────────────────────────────────

def parse_target_end(timeframe: str) -> Optional[Tuple[int, int]]:
    """Return (year, month) at which the stated target period ends, or None."""
    tf = str(timeframe or "")
    m = re.search(r"H([12])\s*CY(\d{2,4})", tf, re.I)
    if m:
        y = int(m.group(2)); y = y + 2000 if y < 100 else y
        return (y, 6 if m.group(1) == "1" else 12)
    m = re.search(r"\bby\s+(20\d{2})\b", tf, re.I) or re.search(r"\b(20\d{2})\b", tf)
    if m:
        return (int(m.group(1)), 12)
    return None


def _month_year_tuple(text: str) -> Optional[Tuple[int, int, str]]:
    m = _MONTH_YEAR.search(text or "")
    if not m:
        return None
    return (int(m.group(2)), _MONTHS.index(m.group(1).lower()) + 1, m.group(0))


# ── Regulatory follow-up ─────────────────────────────────────────────────────

def _entity_names(mem: Path) -> List[str]:
    reg = _load(mem / "verification_entities.json") or {}
    return [e.get("entity", "").lower() for e in reg.get("entities", []) if e.get("entity")]


def _entity_types(mem: Path) -> Dict[str, str]:
    reg = _load(mem / "verification_entities.json") or {}
    return {e.get("entity", "").lower(): e.get("event_type", "") for e in reg.get("entities", []) if e.get("entity")}


_PRODUCT_TYPES = {"PRODUCT_LAUNCH", "REGULATORY_APPROVAL"}


def _segment(text: str, idx: int, subject: str, other_entities: List[str], allow_table: bool = True) -> str:
    start = max(text.rfind(". ", 0, idx), text.rfind("•", 0, idx), text.rfind("\n", 0, idx)) + 1
    ends = [e for e in (text.find(". ", idx), text.find("•", idx), text.find("\n", idx)) if e != -1]
    end = min(ends) + 1 if ends else len(text)
    sentence = text[start:end].strip()
    if len(sentence) <= 260:
        return sentence
    if not allow_table:
        return ""
    window = text[idx: idx + 200]
    low = window.lower()
    cut = len(window)
    for ent in other_entities:
        j = low.find(ent, len(subject))
        if j != -1:
            cut = min(cut, j)
    return window[:cut].strip()


def scan_regulatory_followup(
    company_dir: Path,
    subject: str,
    announce_period: str,
    years_used: List[str],
    entities: List[str],
    allow_table: bool = True,
) -> List[Dict[str, Any]]:
    """Find dated/sourced filing, validation and approval statements about `subject`.

    allow_table=True additionally reads table-style pipeline rows (used only for commitments
    whose stated action is the exact filing step); products use sentence-level evidence only.
    """
    ann = _fy_num(announce_period) or 0
    subj = subject.lower()
    others = [e for e in entities if e != subj]
    events: List[Dict[str, Any]] = []
    seen = set()
    for fy in years_used:
        n = _fy_num(fy)
        if n is None or n < ann:
            continue
        files: List[Tuple[Path, str]] = []
        if n > ann:
            files.append((company_dir / fy / "extracted" / "clean_chunks.json", "annual_report"))
        for q in sorted((company_dir / fy / "quarters").glob("Q*/quarterly_chunks.json")) if (company_dir / fy / "quarters").exists() else []:
            files.append((q, f"quarter_{q.parent.name}"))
        for path, doc in files:
            for ch in _chunks(path):
                text = str(ch.get("text", ""))
                low = text.lower()
                pos = 0
                while True:
                    idx = low.find(subj, pos)
                    if idx == -1:
                        break
                    pos = idx + len(subj)
                    seg = _segment(text, idx, subj, others, allow_table)
                    if not seg or _FUTURE_INTENT.search(seg):
                        continue
                    kinds = []
                    if _VALIDATED.search(seg) and re.search(r"submission|application|maa", seg, re.I):
                        kinds.append("VALIDATED")
                    if _FILED.search(seg):
                        kinds.append("FILED")
                    seg_ap = re.sub(r"\b(?:cumulative\s+)?A?NDAs?\s+(?:\w+\s+)?approved\b", "", seg, flags=re.I)
                    if _APPROVED.search(seg_ap) and "not approved" not in seg.lower():
                        kinds.append("APPROVED")
                    if "FILED" in kinds and re.search(r"\bApproval\b", seg) and "APPROVED" not in kinds:
                        kinds.append("NEXT_MILESTONE_APPROVAL")
                    if _PHASE.search(seg):
                        kinds.append("PHASE")
                    dt = _month_year_tuple(seg)
                    for kind in kinds:
                        key = (fy, doc, kind, dt[2] if dt else "")
                        if key in seen:
                            continue
                        seen.add(key)
                        page = ch.get("page") or (ch.get("metadata") or {}).get("page")
                        events.append({
                            "period": fy, "document": doc, "page": page,
                            "chunk_id": ch.get("chunk_id"), "kind": kind,
                            "date_text": dt[2] if dt else None,
                            "date_ym": [dt[0], dt[1]] if dt else None,
                            "excerpt": seg[:240],
                        })
    events.sort(key=lambda e: (_fy_num(e["period"]) or 0, e["document"], e["kind"]))
    return events


def _document_upper_bound(period: str, document: str) -> Optional[Tuple[int, int]]:
    """Latest calendar month a statement in this document can describe (document end date)."""
    n = _fy_num(period)
    if n is None:
        return None
    m = re.match(r"quarter_Q([1-4])", document or "")
    if m:
        q = int(m.group(1))
        return (2000 + n - 1, {1: 6, 2: 9, 3: 12}[q]) if q < 4 else (2000 + n, 3)
    return (2000 + n, 3)


def derive_commitment_states(
    target_timeframe: str, events: List[Dict[str, Any]], latest_fy: int, regulatory: bool
) -> Dict[str, Any]:
    """Filing delivery, deadline adherence and regulatory approval are independent facts.

    Deadline adherence needs a dated FILING statement. A dated VALIDATION statement is a
    different milestone: it is recorded, but never converted into a filing date (no inference
    from one milestone to another)."""
    target_end = parse_target_end(target_timeframe)
    horizon = (2000 + latest_fy, 3)
    explicit_period = bool(re.search(r"\b(?:FY|CY|H[12]CY|Q[1-4])\s*\d", str(target_timeframe), re.I))
    out: Dict[str, Any] = {
        "DELIVERY_STATE": "NOT_EVIDENCED",
        "TIMELINE_ADHERENCE_STATE": "UNABLE_TO_VERIFY",
        "REGULATORY_OUTCOME_STATE": "NOT_APPLICABLE",
        "TARGET_PERIOD_STATE": "UNKNOWN",
        "target_period_convention": "EXPLICIT" if explicit_period else "UNSPECIFIED_CALENDAR_OR_FINANCIAL_YEAR",
        "filed_no_later_than": None,
        "filed_no_later_than_source": None,
        "dated_statements": [],
        "validation_statements": [],
        "deadline_note": None,
        "basis": [],
    }
    if target_end:
        # a bare "By 2025" is read both ways (FY ends March, calendar year ends December)
        ends = [target_end] if explicit_period else [(target_end[0], 3), target_end]
        out["TARGET_PERIOD_STATE"] = "TARGET_PERIOD_PASSED" if all(e < horizon for e in ends) else "TARGET_PERIOD_OPEN"
    if not regulatory:
        return out
    filing = [e for e in events if e["kind"] in ("FILED", "VALIDATED")]
    if filing:
        out["DELIVERY_STATE"] = "FILING_CONFIRMED_BY_SOURCE_TEXT"
        bounded = [(b, e) for e in filing for b in [_document_upper_bound(e["period"], e["document"])] if b]
        if bounded:
            lo, src = min(bounded, key=lambda t: t[0])
            out["filed_no_later_than"] = f"{_MONTHS[lo[1] - 1].capitalize()} {lo[0]}"
            out["filed_no_later_than_source"] = f"{_fy_label(src['period'])} {src['document'].replace('_', ' ').replace('quarter Q', 'Q')}"
    key = lambda e: tuple(e["date_ym"])
    out["dated_statements"] = [
        {"kind": e["kind"], "date": e["date_text"], "period": e["period"], "document": e["document"], "page": e.get("page")}
        for e in sorted((e for e in events if e["kind"] == "FILED" and e.get("date_ym")), key=key)]
    out["validation_statements"] = [
        {"date": e["date_text"], "period": e["period"], "document": e["document"], "page": e.get("page")}
        for e in sorted((e for e in events if e["kind"] == "VALIDATED" and e.get("date_ym")), key=key)]
    if out["dated_statements"] and target_end:
        within = [d for d in out["dated_statements"]]
        first = sorted((e for e in events if e["kind"] == "FILED" and e.get("date_ym")), key=key)[0]
        out["TIMELINE_ADHERENCE_STATE"] = (
            "WITHIN_TARGET_PERIOD_PER_DATED_FILING_STATEMENT" if tuple(first["date_ym"]) <= target_end
            else "AFTER_TARGET_PERIOD_PER_DATED_FILING_STATEMENT")
    elif filing:
        out["TIMELINE_ADHERENCE_STATE"] = "UNABLE_TO_VERIFY"
        out["deadline_note"] = ("the filing date is not stated; only dated EMA validation statements exist "
                                "(a different milestone), and their subject/date cannot be reconciled from the extracted text")
    if any(e["kind"] == "APPROVED" for e in events):
        out["REGULATORY_OUTCOME_STATE"] = "APPROVAL_EVIDENCED"
    elif filing:
        out["REGULATORY_OUTCOME_STATE"] = "NOT_EVIDENCED_PENDING"
    else:
        out["REGULATORY_OUTCOME_STATE"] = "UNKNOWN"
    # mission vocabulary (aliases; same values)
    out["FILING_DELIVERY"] = out["DELIVERY_STATE"]
    out["DEADLINE_ADHERENCE"] = out["TIMELINE_ADHERENCE_STATE"]
    out["REGULATORY_APPROVAL"] = out["REGULATORY_OUTCOME_STATE"]
    return out


_EMISSION_PROGRESS = [
    re.compile(r"achieved\s+an?\s+(\d+(?:\.\d+)?)\s?%\s+reduction\s+in\s+(?:our\s+)?absolute\s+Scope\s*1\s+and\s+Scope\s*2", re.I),
    re.compile(r"reduced\s+our\s+combined\s+Scope\s*1\s+and\s+Scope\s*2\s+carbon\s+emissions\s+by\s+(\d+(?:\.\d+)?)\s?%", re.I),
]
_HAZ_TABLE = re.compile(
    r"Hazardous Waste\s*\(i\)\s*Incineration\s+[\d,\.]+\s+[\d,\.]+\s*\(ii\)\s*Landfilling\s+[\d,\.]+\s+[\d,\.]+\s*"
    r"\(iii\)\s*Co-processing\s+([\d,\.]+)\s+([\d,\.]+)\s*\(iv\)\s*Other disposal operations\s+[\d,\.]+\s+[\d,\.]+\s*"
    r"Total\s+([\d,\.]+)\s+([\d,\.]+)", re.I)


def _num(x: str) -> float:
    return float(x.replace(",", ""))


def scan_quantified_progress(company_dir: Path, text: str, years_used: List[str]) -> Dict[str, Any]:
    """Reported progress for quantified commitments, from annual-report text.

    Topic extractors (not company-specific): emissions-reduction sentences, and the BRSR
    hazardous-waste disposal table (co-processed tonnes / total tonnes disposed). Values are
    reported as found; the hazardous-waste share is DERIVED (not a management-stated percentage).
    """
    low = text.lower()
    target = re.search(r"(\d+(?:\.\d+)?)\s?%", text)
    target_pct = float(target.group(1)) if target else None
    series: List[Dict[str, Any]] = []
    metric = basis = None
    if "scope 1" in low:
        metric, basis = "cumulative absolute Scope 1+2 emissions reduction vs baseline", "MANAGEMENT_STATED_PERCENT"
        for fy in years_used:
            for ch in _chunks(company_dir / fy / "extracted" / "clean_chunks.json"):
                hit = next((m for rx in _EMISSION_PROGRESS for m in [rx.search(str(ch.get("text", "")))] if m), None)
                if hit:
                    series.append({"period": fy, "value": float(hit.group(1)), "unit": "%", "page": ch.get("page") or (ch.get("metadata") or {}).get("page"),
                                   "chunk_id": ch.get("chunk_id"), "document": "annual_report"})
                    break
    elif "co-process" in low and "hazardous" in low:
        metric, basis = "hazardous waste co-processed as share of hazardous waste disposed (tonnes)", "DERIVED_FROM_DISPOSAL_TABLE"
        seen: Dict[str, Dict[str, Any]] = {}
        for fy in years_used:
            n = _fy_num(fy)
            for ch in _chunks(company_dir / fy / "extracted" / "clean_chunks.json"):
                m = _HAZ_TABLE.search(str(ch.get("text", "")))
                if not m:
                    continue
                page = ch.get("page") or (ch.get("metadata") or {}).get("page")
                for label, co, tot in ((fy, m.group(1), m.group(3)), (f"fy{n - 1:02d}", m.group(2), m.group(4))):
                    if label in seen and label != fy:
                        continue          # the report's own current-year column wins over a later report's prior-year column
                    seen[label] = {"period": label, "value": round(_num(co) / _num(tot) * 100, 1), "unit": "% of tonnes disposed",
                                   "co_processed_tonnes": _num(co), "total_tonnes": _num(tot), "page": page,
                                   "chunk_id": ch.get("chunk_id"), "document": "annual_report"}
                break
        series = sorted(seen.values(), key=lambda r: _fy_num(r["period"]) or 0)
    series.sort(key=lambda r: _fy_num(r["period"]) or 0)
    if not series:
        return {"metric": metric, "series": [], "progress_state": "NO_PROGRESS_STATEMENT_FOUND_IN_SEARCHED_SOURCES", "target_pct": target_pct}
    latest = series[-1]
    state = "REPORTED_PROGRESS"
    if target_pct is not None:
        state = "REPORTED_AT_OR_ABOVE_TARGET_LEVEL" if latest["value"] >= target_pct else "REPORTED_BELOW_TARGET_LEVEL"
    return {
        "metric": metric, "basis": basis, "target_pct": target_pct, "series": series, "progress_state": state,
        "latest_below_prior_report": len(series) > 1 and series[-1]["value"] < series[-2]["value"],
        "management_achievement_statement": "NOT_FOUND_IN_SEARCHED_SOURCES",
    }


def build_commitment_facts(
    company_dir: Path, mem: Path, hard_commitments: List[Dict[str, Any]],
    years_used: List[str], latest_fy: int,
) -> List[Dict[str, Any]]:
    data = _load(mem / "management_commitments" / "management_commitments.json") or {}
    by_id = {c.get("id"): c for c in data.get("commitments", []) if isinstance(c, dict)}
    entities = _entity_names(mem)
    facts = []
    for hc in hard_commitments:
        src = by_id.get(hc.get("id"), {})
        original = str(src.get("original_statement") or hc.get("normalized_commitment") or "").strip()
        ref = (src.get("source_references") or [{}])[0]
        subjects = [s.get("canonical") for s in (src.get("commitment_identity") or {}).get("named_subjects", []) if s.get("canonical")]
        regulatory = bool(_REG_FILING_COMMITMENT.search(original)) and bool(subjects)
        events = (
            scan_regulatory_followup(company_dir, subjects[0], src.get("announcement_period", ""), years_used, entities)
            if regulatory else []
        )
        states = derive_commitment_states(hc.get("expected_timeframe", ""), events, latest_fy, regulatory)
        facts.append({
            "id": hc.get("id"),
            "display_text": original.rstrip(".").strip(),
            "target": hc.get("expected_timeframe", ""),
            "announcement_period": src.get("announcement_period", ""),
            "source_page": ref.get("page"),
            "source_artifact": ref.get("source_artifact"),
            "tracker_status": src.get("status", "Unable To Verify"),
            "named_subject": subjects[0] if subjects else None,
            "regulatory_filing_commitment": regulatory,
            "followup_events": events,
            "progress": scan_quantified_progress(company_dir, original, years_used),
            **states,
        })
    return facts


# ── Capital allocation ───────────────────────────────────────────────────────

_ACQ_NAME = re.compile(r"^(?:acquisition|incorporation)(?:/\w+)?\s*(?:of\b|\()", re.I)
_NON_TRANSACTION = re.compile(r"^(?:sale|disposal|purchase|increase|decrease|investment|loan)\b", re.I)


def is_named_acquisition(name: str) -> bool:
    """Ledger rows labelled 'acquisition' are only treated as named transactions when the label
    actually names an acquired entity (cash-flow line items and divestments are excluded)."""
    n = str(name or "").strip()
    return bool(_ACQ_NAME.match(n)) and not _NON_TRANSACTION.match(n)


def _clean_transaction_name(name: str) -> Tuple[str, Optional[str]]:
    m0 = re.match(r"^Acquisition\s*\((.+)\)\s*$", str(name).strip(), re.I)
    if m0:
        return m0.group(1).strip(), None
    n = re.sub(r"^(?:Acquisition/incorporation|Incorporation/acquisition|Acquisition)\s+of\s+", "", str(name), flags=re.I)
    date = None
    m = re.search(r"(\d{2})\.(\d{2})\.(20\d{2})", n)
    if m:
        date = f"{int(m.group(1))} {_MONTHS[int(m.group(2)) - 1].capitalize()} {m.group(3)}"
    n = re.split(r"\s*\((?:Formerly|Date)", n)[0].strip()
    return n, date


def _announced_transactions(company_dir: Path, mem: Path, latest_year: Optional[str]) -> List[Dict[str, Any]]:
    reg = _load(mem / "projects" / "projects_registry.json") or {}
    projects = reg.get("projects", reg if isinstance(reg, list) else [])
    out = []
    for p in projects:
        if not isinstance(p, dict) or p.get("project_type") != "acquisition_integration":
            continue
        m = re.search(r"\(([^)]+)\)", p.get("project_name", ""))
        counterparty = m.group(1).strip() if m else None
        if not counterparty:
            continue
        rec = {
            "counterparty": counterparty,
            "project_id": p.get("project_id"),
            "canonical_status": p.get("current_status", "unable_to_verify"),
            "latest_period": p.get("latest_period"),
            "agreement_date": None, "price_per_share": None, "enterprise_valuation": None,
            "closing_conditions": None, "reference": None, "completed": False,
        }
        # source text is read only from years listed in financial_year_index.years_used (the tracked set)
        for ch in (_chunks(company_dir / latest_year / "extracted" / "clean_chunks.json") if latest_year else []):
            text = str(ch.get("text", ""))
            if counterparty.lower() not in text.lower():
                continue
            m_agr = re.search(
                r"On\s+([A-Z][a-z]+\s+\d{1,2},\s+20\d{2}),\s+the\s+(?:Group|Company)\s+entered\s+into\s+a\s+definitive\s+agreement\s+to\s+acquire",
                text)
            if m_agr:
                seg = text[m_agr.start(): m_agr.start() + 520]
                rec["agreement_date"] = m_agr.group(1)
                mp = re.search(r"(USD|US\$)\s*(\d[\d,]*\.?\d*)\s+per share", seg)
                mv = re.search(r"enterprise valuation of\s+(USD|US\$)\s*(\d[\d,]*\.?\d*)\s*(billion|million)", seg, re.I)
                mc = re.search(r"subject to ([^.]*)", seg, re.I)
                rec["price_per_share"] = f"{mp.group(1)} {mp.group(2)} per share" if mp else None
                rec["enterprise_valuation"] = f"{mv.group(1)} {mv.group(2)} {mv.group(3).lower()}" if mv else None
                rec["closing_conditions"] = mc.group(1).strip() if mc else None
                page = ch.get("page") or (ch.get("metadata") or {}).get("page")
                rec["reference"] = f"{_fy_label(latest_year)} annual report, p.{page}" if page else f"{_fy_label(latest_year)} annual report"
                break
        for ch in (_chunks(company_dir / latest_year / "extracted" / "clean_chunks.json") if latest_year else []):
            text = str(ch.get("text", ""))
            m_ip = re.search(r"[^.]*integration planning[^.]*\.", text, re.I)
            if m_ip and counterparty.lower() in text.lower():
                rec["integration_planning_statement"] = {"text": m_ip.group(0).strip(), "page": ch.get("page") or (ch.get("metadata") or {}).get("page")}
                break
        out.append(rec)
    return out


def build_capital_facts(company_dir: Path, mem: Path, latest_year: Optional[str]) -> Dict[str, Any]:
    ledger = _load(mem / "capital_allocation_outcomes" / "capital_allocation_outcomes.json") or {}
    profile = _load(mem / "capital_allocation_outcomes" / "capital_allocation_longitudinal_profile.json") or {}
    allocs = [a for a in ledger.get("allocations", []) if isinstance(a, dict)]

    def periods(cat: str) -> List[str]:
        ps = set()
        for a in allocs:
            if a.get("allocation_category") == cat:
                ps.update(a.get("deployment_periods", []))
        return sorted(ps, key=lambda p: _fy_num(p) or 0)

    acquisitions = []
    unnamed_periods: List[str] = []
    for a in allocs:
        if a.get("allocation_category") != "acquisition":
            continue
        if not is_named_acquisition(a.get("allocation_name")):
            if _is_generic(a.get("allocation_name")):
                unnamed_periods.extend(a.get("deployment_periods", []))
            continue
        name, date = _clean_transaction_name(a.get("allocation_name", ""))
        acquisitions.append({
            "allocation_id": a.get("allocation_id"), "name": name, "date": date,
            "periods": a.get("deployment_periods", []),
            "deployment_state": a.get("deployment_state"),
            "financial_outcome_state": a.get("financial_outcome_state"),
            "operating_outcome_state": a.get("operating_outcome_state"),
            "outcome_attribution": a.get("outcome_attribution"),
        })
    no_fin = (None, "UNABLE_TO_ATTRIBUTE", "UNABLE_TO_VERIFY")
    no_op = (None, "UNABLE_TO_VERIFY", "NO_VERIFIED_OUTCOME")
    return {
        "acquisitions": acquisitions,
        "unnamed_acquisition_periods": sorted(set(unnamed_periods), key=lambda p: _fy_num(p) or 0),
        "acquisition_event_count": len(acquisitions),
        "acquisitions_with_attributable_outcome": sum(1 for a in acquisitions if a["financial_outcome_state"] not in no_fin),
        "acquisitions_with_integration_visible": sum(1 for a in acquisitions if a["operating_outcome_state"] not in no_op),
        "dividend_periods": periods("dividend"),
        "buyback_periods": periods("share_buyback"),
        "ledger_periods": sorted({p for a in allocs for p in a.get("deployment_periods", [])}, key=lambda p: _fy_num(p) or 0),
        "capital_weighted_conclusions_permitted": bool((profile.get("amount_coverage") or {}).get("capital_weighted_conclusions_permitted", False)),
        "announced_transactions": _announced_transactions(company_dir, mem, latest_year),
    }


# ── Named-entity statements (products / transactions) ────────────────────────

_ACTION_STEMS = re.compile(r"launch|approv|acquir|acquisition|licens|filed|validated", re.I)


def build_named_entity_statements(mem: Path) -> List[Dict[str, Any]]:
    entities = _entity_names(mem)
    types = _entity_types(mem)
    prog = _load(mem / "management_progression" / "management_progression.json") or {}
    cands = []
    seen = set()
    for item in prog.get("progression_items", []):
        for ev in item.get("events", []):
            st = str(ev.get("statement_text", ""))
            if not st or st in seen or ev.get("event_type") != "commentary_change":
                continue
            names = sorted({e for e in entities if re.search(r"\b" + re.escape(e) + r"\b", st, re.I)})
            if names and _ACTION_STEMS.search(st) and len(st) <= 400:
                seen.add(st)
                cands.append({
                    "statement": st.rstrip("."), "entities": [n.upper() for n in names],
                    "product_entities": [n.upper() for n in names if types.get(n) in _PRODUCT_TYPES],
                    "transaction_entities": [n.upper() for n in names if types.get(n) not in _PRODUCT_TYPES],
                    "period": ev.get("source_period"), "event_id": ev.get("event_id"),
                    "item_id": item.get("item_id"), "status": item.get("current_status"),
                })
    cands.sort(key=lambda c: (-len(c["entities"]), -(_fy_num(c["period"]) or 0)))
    return cands


def build_product_milestones(company_dir: Path, mem: Path, years_used: List[str],
                             statements: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]],
                             exclude: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Source-reported approval / pipeline-phase statements for named products (no duplicates)."""
    entities = _entity_names(mem)
    types = _entity_types(mem)
    wanted = {e.lower() for s in statements for e in s.get("product_entities", [])}
    for it in evidence_items:
        if str(it.get("evidence_type", "")).startswith("commitment"):
            for e in entities:
                if types.get(e) in _PRODUCT_TYPES and re.search(r"\b" + re.escape(e) + r"\b", str(it.get("summary", "")), re.I):
                    wanted.add(e)
    wanted -= {x.lower() for x in exclude}
    out: Dict[str, List[Dict[str, Any]]] = {}
    used_excerpts = set()
    for ent in sorted(wanted):
        evs = scan_regulatory_followup(company_dir, ent, "fy20", years_used, entities, allow_table=False)
        approved = [e for e in evs if e["kind"] == "APPROVED"]
        phase = sorted((e for e in evs if e["kind"] == "PHASE"), key=lambda e: -(_fy_num(e["period"]) or 0))
        pick = approved[0] if approved else (phase[0] if phase else None)
        if not pick or pick["excerpt"][:80] in used_excerpts:
            continue
        if any(o != ent and o in pick["excerpt"].lower() for o in wanted):
            continue  # alias of another wanted product (e.g. molecule name vs brand)
        used_excerpts.add(pick["excerpt"][:80])
        region = None
        m = re.search(r"Approved in the\s+([A-Z]{2,3})\b", pick["excerpt"])
        if m:
            region = m.group(1)
        ph = _PHASE.search(pick["excerpt"])
        tl = re.search(r"Topline data during\s+(H[12]CY\d{2})", pick["excerpt"])
        out[ent.upper()] = [{**pick, "region": region,
                             "phase": f"Phase {ph.group(1)}" if ph and pick["kind"] == "PHASE" else None,
                             "topline": tl.group(1) if tl else None}]
    return out


# ── Behavioral consistency evidence ──────────────────────────────────────────

def _project_status_map(mem: Path) -> Dict[str, str]:
    reg = _load(mem / "projects" / "projects_registry.json") or {}
    projects = reg.get("projects", reg if isinstance(reg, list) else [])
    return {p.get("project_id"): p.get("current_status") for p in projects if isinstance(p, dict)}


def effective_evidence_type(item: Dict[str, Any], project_status: Dict[str, str]) -> str:
    """Canonical lifecycle authority overrides a stale per-period evidence type."""
    etype = item.get("evidence_type", "")
    if item.get("source_stream") == "projects":
        status = project_status.get(item.get("source_item_id"))
        if status in ("unable_to_verify", "announced") and etype in ("project_operational", "project_partially_operational"):
            return "project_unable_to_verify"
    return etype


def clean_statement(text: str, limit: int = 170) -> str:
    """Whole-clause truncation (no ellipsis): investor text must not end mid-phrase or with a trailing mark."""
    t = re.sub(r"\s*\(text truncated\)", "", str(text)).strip().rstrip(".")
    if len(t) <= limit:
        return t
    head = t[:limit]
    cut = max(head.rfind(", "), head.rfind("; "), head.rfind(" while "), head.rfind(" and "))
    return (head[:cut] if cut > limit // 2 else head.rsplit(" ", 1)[0]).rstrip(",;: ")


_TYPE_RANK = {"project_operational": 0, "capacity_operational": 0}


def _named(items: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    """Most material first: fully operational before partial, then most recent."""
    out, seen = [], set()
    for it in sorted(items, key=lambda i: (_TYPE_RANK.get(i.get("evidence_type"), 1), -(_fy_num(i.get("period")) or 0))):
        s = str(it.get("summary", "")).strip()
        if _is_generic(s) or s.lower() in seen:
            continue
        seen.add(s.lower())
        out.append(f"{s} ({_fy_label(it.get('period'))})")
        if len(out) >= limit:
            break
    return out


def build_dimension_behavior(mem: Path, evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    dims = (_load(mem / "management_quality" / "management_quality_dimensions.json") or {}).get("dimensions", [])
    pstat = _project_status_map(mem)
    themes = (_load(mem / "management_commentary" / "commentary_themes.json") or {}).get("themes", [])
    out: Dict[str, Any] = {"dimensions": {}, "stated_strategy": None}
    for d in dims:
        name = d.get("dimension")
        if not name:
            continue
        items = [e for e in evidence_items if name in (e.get("dimensions") or [])]
        typed = [(effective_evidence_type(e, pstat), e) for e in items]
        pos = [e for t, e in typed if t in POSITIVE_TYPES]
        neg = [e for t, e in typed if t in NEGATIVE_TYPES]
        adapt = [e for t, e in typed if t in ADAPTATION_TYPES]
        unv = [e for t, e in typed if t not in POSITIVE_TYPES | NEGATIVE_TYPES | ADAPTATION_TYPES]
        conflicts = d.get("conflicting_evidence") or []
        out["dimensions"][name] = {
            "canonical_assessment": str(d.get("assessment", "")).lower(),
            "canonical_status": _ASSESSMENT_TO_CANON.get(str(d.get("assessment", "")).lower(), "UNABLE_TO_VERIFY"),
            "positive": _named([e for e in pos if "risk" not in e.get("evidence_type", "")]),
            "reducing_risks": _named([e for t, e in typed if t == "risk_reducing"]),
            "negative_operational": _named([e for t, e in typed if t in ("project_paused", "capacity_delayed")]),
            "recurring_risks": _named([e for t, e in typed if t in ("risk_recurring", "risk_persistent", "risk_increasing")], limit=4),
            "adaptation": _named(adapt, limit=2),
            "counts": {"positive": len(pos), "negative": len(neg), "adaptation": len(adapt),
                       "unverified": len(unv), "conflicting_in_canonical": len(conflicts)},
            "periods": sorted({e.get("period") for e in items if e.get("period")}, key=lambda p: _fy_num(p) or 0),
        }
    best = None
    for t in themes:
        cs = ((t.get("consistency_assessment") or {}).get("consistency_status") or "").lower()
        nt = str(t.get("normalized_theme", "")).lower()
        evs = t.get("commentary_events") or []
        pers = sorted({e.get("period") for e in evs if e.get("period")}, key=lambda p: _fy_num(p) or 0)
        if cs == "consistent" and len(pers) >= 3 and re.search(r"innovation|strateg|product", nt):
            if best is None or len(pers) > len(best["periods"]):
                label = re.sub(r"\br d\b", "R&D", nt.replace("_", " "))
                best = {"theme": label, "theme_id": t.get("theme_id"), "event_count": len(evs), "periods": pers,
                        "first_statement": clean_statement(evs[0].get("description") or evs[0].get("title") or ""),
                        "latest_statement": clean_statement(evs[-1].get("description") or evs[-1].get("title") or "")}
    out["stated_strategy"] = best
    return out


# ── Input manifest (registry-free freshness binding) ─────────────────────────

_MEMORY_INPUTS = [
    "management_commitments/management_commitments.json",
    "management_progression/management_progression.json",
    "management_commentary/commentary_themes.json",
    "management_quality/management_quality_dimensions.json",
    "management_quality/management_quality_evidence.json",
    "management_quality/management_quality_summary.json",
    "capital_allocation_outcomes/capital_allocation_outcomes.json",
    "capital_allocation_outcomes/capital_allocation_longitudinal_profile.json",
    "projects/projects_registry.json",
    "verification_entities.json",
    "financial_year_index.json",
    "financial_truth_pack.json",
]


def build_input_manifest(company_dir: Path, mem: Path, years_used: List[str]) -> Dict[str, str]:
    """SHA-256 of every file this enrichment can read, keyed by company-relative path."""
    paths = [mem / rel for rel in _MEMORY_INPUTS]
    for fy in years_used:
        paths.append(company_dir / fy / "extracted" / "clean_chunks.json")
        qdir = company_dir / fy / "quarters"
        if qdir.exists():
            paths.extend(sorted(qdir.glob("Q*/quarterly_chunks.json")))
    out: Dict[str, str] = {}
    for p in paths:
        if p.exists():
            out[str(p.relative_to(company_dir))] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def manifest_digest(manifest: Dict[str, str]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


# ── Progression-tracker scope and reconciliation ─────────────────────────────

_STREAM_LABEL = {"commitment": "strategic commitment statement", "commentary": "commentary theme", "project": "legacy project"}


def reconcile_progression_tracker(mem: Path, product_milestones: Dict[str, List[Dict[str, Any]]],
                                  capital: Dict[str, Any]) -> Dict[str, Any]:
    """Item-level reconciliation of the management-progression tracker with other records.

    The tracker is a population of tracked management statements/themes/projects, NOT a ledger of
    company deliveries. Verdicts are conservative and never change tracker status.
    """
    prog = _load(mem / "management_progression" / "management_progression.json") or {}
    entities = _entity_names(mem)
    items = []
    acq_names = [a["name"].lower() for a in capital.get("acquisitions", [])]
    for it in prog.get("progression_items", []):
        text = " ".join([str(it.get("theme", ""))] + [str(e.get("statement_text", "")) for e in it.get("events", [])])
        named = sorted({e for e in entities if re.search(r"\b" + re.escape(e) + r"\b", text, re.I)})
        approved = [e for e in named if e.upper() in product_milestones and product_milestones[e.upper()][0]["kind"] == "APPROVED"]
        verdict, matched, why = "NO_MATCH_FOUND", [], "no named product/transaction or delivery record corresponds to this item in the searched records"
        if approved and re.search(r"launch|approv", text, re.I) and len(approved) == len(named):
            verdict = "MATCHED_PARTIAL_PROGRESS"
            matched = [f"{e.upper()}: {product_milestones[e.upper()][0]['excerpt'][:90]}" for e in approved]
            why = "named products have sourced approval statements; launch is management-reported only"
        elif named:
            verdict, matched = "AMBIGUOUS_MATCH", [e.upper() for e in named]
            why = "item names entities that have records, but the item itself is not a delivery claim about them"
        elif acq_names and re.search(r"acqui", text, re.I):
            verdict, matched = "AMBIGUOUS_MATCH", [a for a in acq_names]
            why = "completed acquisitions exist, but nothing shows they are this item's delivery"
        periods = sorted({e.get("source_period") for e in it.get("events", []) if e.get("source_period")}, key=lambda p: _fy_num(p) or 0)
        items.append({
            "item_id": it.get("item_id"), "origin": _STREAM_LABEL.get((it.get("stream_types") or ["?"])[0], (it.get("stream_types") or ["?"])[0]),
            "initiative": str(it.get("theme", ""))[:110], "lifecycle_status": it.get("current_status"),
            "latest_source_period": periods[-1] if periods else None, "matching_evidence": matched,
            "same_item": verdict in ("MATCHED_DELIVERY_EVIDENCE", "MATCHED_PARTIAL_PROGRESS"), "verdict": verdict, "reason": why})
    from collections import Counter
    origins = Counter(i["origin"] for i in items)
    verdicts = Counter(i["verdict"] for i in items)
    delivered = sum(1 for i in items if i["lifecycle_status"] in ("delivered", "completed"))
    return {
        "tracked_items": len(items), "confirmed_delivered_in_tracker": delivered,
        "population": dict(origins), "verdict_counts": dict(verdicts), "items": items,
        "scope_note": "tracked management statements, themes and projects; not a ledger of company deliveries",
        "tracker_status_changed": False,
    }


# ── Financial reporting scope ────────────────────────────────────────────────

def build_financial_scope(mem: Path, latest_fy: int) -> Dict[str, Any]:
    pack = _load(mem / "financial_truth_pack.json") or {}
    want = f"fy{latest_fy:02d}"
    out: Dict[str, Any] = {}
    for key in ("revenue", "pat"):
        cands = [m for m in pack.get("usable_current_metrics", []) if isinstance(m, dict)
                 and m.get("metric_id") == key and m.get("fiscal_year") == want and m.get("source_line_item")]
        if cands:
            m = cands[0]
            out[key] = {"value": m.get("value"), "unit": m.get("unit"), "period": m.get("period"), "fiscal_year": want,
                        "basis": m.get("basis"), "line_item": m.get("source_line_item"), "source_page": m.get("source_page"),
                        "status": "ACTUAL" if m.get("availability_status") == "present_direct" else "DERIVED"}
    if out:
        out["npm"] = {"status": "DERIVED", "formula": "profit attributable to owners of the parent / revenue from operations"}
    return out


# ── Search coverage (bounds every absence statement) ─────────────────────────

def build_search_coverage(company_dir: Path, years_used: List[str]) -> Dict[str, Any]:
    annual = [fy for fy in years_used if (company_dir / fy / "extracted" / "clean_chunks.json").exists()]
    quarters = []
    for fy in years_used:
        qdir = company_dir / fy / "quarters"
        if qdir.exists():
            quarters.extend(f"{_fy_label(fy)} {q.parent.name}" for q in sorted(qdir.glob("Q*/quarterly_chunks.json")))
    rng = f"{_fy_label(years_used[0])}\u2013{_fy_label(years_used[-1])}" if years_used else "no years"
    qtxt = ""
    if quarters:
        qtxt = f", {len(quarters)} quarterly deck{'s' if len(quarters) != 1 else ''} ({', '.join(quarters)})"
    return {"annual_report_years": annual, "quarterly_decks": quarters, "period": rng,
            "text": (f"{len(annual)} annual reports ({rng}){qtxt} and the tracked evidence streams") if years_used else "no tracked source years"}


def build_contradiction_summary(mem: Path) -> Dict[str, Any]:
    sig = (_load(mem / "management_progression" / "management_progression.json") or {}).get("contradiction_signals", [])
    from collections import Counter
    types = Counter(s.get("signal_type") for s in sig)
    genuine = [s for s in sig if s.get("signal_type") != "repeated_unresolved"]
    return {"total": len(sig), "types": dict(types), "genuine_contradictions": len(genuine),
            "genuine": [{"signal_id": g.get("signal_id"), "type": g.get("signal_type"), "earlier_period": g.get("earlier_period"),
                         "later_period": g.get("later_period"), "source_item_id": g.get("source_item_id")} for g in genuine],
            "meaning_of_repeated_unresolved": "a statement was repeated in later periods without a recorded resolution; it is not a contradiction"}


# ── Entry point ──────────────────────────────────────────────────────────────

def enrich_fact_pack_v5(fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    company = fact_pack.get("company") or ""
    company_dir = REPO_ROOT / "companies" / company
    mem = company_dir / "company_memory"
    idx = _load(mem / "financial_year_index.json") or {}
    years_used = idx.get("years_used") or []
    latest_fy = fact_pack.get("latest_fy", 26)
    latest_year = years_used[-1] if years_used else None
    evidence_items = fact_pack.get("evidence_observations_raw", []) or []
    manifest = build_input_manifest(company_dir, mem, years_used)
    named = build_named_entity_statements(mem)
    commitments = build_commitment_facts(company_dir, mem, fact_pack.get("hard_commitments", []), years_used, latest_fy)
    capital = build_capital_facts(company_dir, mem, latest_year)
    milestones = build_product_milestones(company_dir, mem, years_used, named, evidence_items,
                                          [c["named_subject"] for c in commitments if c.get("named_subject")])
    tracker = reconcile_progression_tracker(mem, milestones, capital)
    return {
        "version": ENRICHMENT_VERSION,
        "company": company,
        "years_used": years_used,
        "evidence_horizon": _fy_label(latest_year) if latest_year else _fy_label(f"fy{latest_fy}"),
        "commitments": commitments,
        "capital": capital,
        "tracker": tracker,
        "financial_scope": build_financial_scope(mem, latest_fy),
        "search_coverage": build_search_coverage(company_dir, years_used),
        "contradictions": build_contradiction_summary(mem),
        "named_statements": named,
        "product_milestones": milestones,
        "behavior": build_dimension_behavior(mem, evidence_items),
        "project_status": _project_status_map(mem),
        "input_manifest": manifest,
        "input_manifest_digest": manifest_digest(manifest),
    }
