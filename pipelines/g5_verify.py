#!/usr/bin/env python3
"""M63 / G5 — claim-to-evidence verification gate (zero AI calls).

This is a thin gate over components that already exist; it adds only what was missing:

  reused  claim_validator   : the verdict / acceptance vocabulary (SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, CONTRADICTED; ACCEPT, NEEDS_REVIEW, REJECT) and its rule that a
                              rejection is absolute and only agreement of both legs accepts
          entity_matcher    : subject identity (normalised similarity) for named deals, projects, risks
          g4 Ledger         : company, latest FY, section basis (standalone / consolidated), the parsed concentration note (typed facts with page, entity, basis)
          g5_provenance     : claim classes, profiles, anchor search, resolve()
  new     SourceFact / RecordFact typed evidence, strict per-metric source extractors, period-specific destination-record probes, compound-claim components,
          the VERIFIED rule, and the investor-facing fallback

VERIFIED requires, for EVERY component of the claim (every piece of its subject phrase maps to an evidence profile or the claim fails closed), all of:
  0. the claim's own identity matches: no other company named, no qualifier (a facility, deal, industry, event status), no forecast meaning, no other fiscal year, the asserted basis,
     figure and column (current, prior, variance), unit scale and subtype (customer vs depositor concentration; aggregate vs subcategory) agree with the source fact
  1. a SourceFact whose company, FY, basis, metric and (where the claim names one) subject match the claim exactly - a topic mention or a number near a keyword is a LEAD, not a fact
  2. a RecordFact from the specific destination record the claim is about, inspected for that FY and subject (a value in another year does not count)
  3. for NOT_APPLICABLE, a rule that makes the metric inapplicable in total for the business class (never inferred from the class alone)
Anything else fails closed (UNVERIFIED, with machine-readable reason codes); a record that holds the figure CONTRADICTS a 'not extracted' claim; NOT_DISCLOSED is never VERIFIED here.
"""
from __future__ import annotations

import json
import re
from typing import Any

from intelligence.ask_intrinsiciq.claim_validator import ACCEPT, NEEDS_REVIEW, REJECT, VERDICT_CONTRADICTED, VERDICT_PARTIALLY, VERDICT_SUPPORTED, VERDICT_UNSUPPORTED
from knowledge.entity_matcher import normalize, similarity
from pipelines import g4_investor_answers as g4
from pipelines import g5_provenance as G

# ───────────────────────────── typed evidence ─────────────────────────────
def source_fact(company: str, fy: str, basis: str, metric: str, page: int, text: str, value: float | None, unit: str = "", subject: str = "", values: list | None = None,
                subcategory: str = "", subtype: str = "") -> dict:
    return {"company": company, "fy": fy, "basis": basis, "metric": metric, "subject": subject, "page": page, "text": text[:240], "value": value, "values": values if values is not None else ([value] if value is not None else []),
            "unit": unit, "subcategory": subcategory, "subtype": subtype, "exact": True}


def record_fact(company: str, fy: str, metric: str, present: bool | None, record: str, detail: str, subject: str = "", basis: str = "unknown", summary: str = "") -> dict:
    return {"basis": basis, "summary": summary, "company": company, "fy": fy, "metric": metric, "subject": subject, "present": present, "record": record, "detail": detail}


def _chunks(L) -> list[dict]:
    return G._chunks(L)


def _flat(c: dict) -> str:
    return " ".join(str(c.get("text", "")).split())


def _local_basis(L, body: str, start: int, page: int) -> str:
    """Basis of a table row: the nearest preceding 'Standalone' / 'Consolidated' wording in the same chunk (a mixed-basis ratio table labels each block); a chunk that names both
    without one governing the row is 'ambiguous'; otherwise the section heading (G4 Ledger.section_basis)."""
    near = list(re.finditer(r"\b(standalone|consolidated)\b", body[max(0, start - 700): start], re.I))
    if near:
        return near[-1].group(1).lower()
    if re.search(r"\bstandalone\b", body, re.I) and re.search(r"\bconsolidated\b", body, re.I):
        return "ambiguous"
    return L.section_basis(page)


COL = r"(?:\s*\(?-?\d[\d,]*\.?\d*\)?\s*%?)"


def _numbers(tail: str) -> list[float]:
    out = []
    for m in re.finditer(r"\(?(-?)(\d[\d,]*\.?\d*)\)?\s*%?", tail):
        try:
            v = float(m.group(2).replace(",", "").rstrip("."))
        except ValueError:
            break
        out.append(-v if m.group(1) or m.group(0).startswith("(") else v)
    return out


def _unit_scale(body: str, pos: int) -> str:
    near = body[max(0, pos - 320): pos + 40]
    for rx, u in ((r"in\s+(?:₹|rs\.?|inr)?\s*millions?|₹\s*in\s*millions?|\bmn\b", "INR million"), (r"in\s+(?:₹|rs\.?|inr)?\s*crores?|\bcr\b", "INR crore"), (r"in\s+(?:₹|rs\.?|inr)?\s*lakhs?", "INR lakh"), (r"in\s+(?:₹|rs\.?|inr)?\s*(?:thousand|'000)", "INR thousand")):
        if re.search(rx, near, re.I):
            return u
    return "INR (scale not stated)"


def _scan(L, metric: str, label: str, lo: float, hi: float, unit: str, pct: bool | None = None, gap: int = 14) -> list[dict]:
    """Strict extractor: the metric's own label, then (same sentence, within `gap` non-digit characters) the table row's numbers. Keeps every column (current, prior, variance), the
    local basis of the table, and for contingent liabilities the unit scale and subcategory. A number-before-label layout, a number that qualifies the next word (revenue, EBITDA, CAGR,
    YoY, growth) and a label with no adjacent number are skipped: leads, not facts."""
    out = []
    rx = rf"{label}(?:\s*\(?(?:%|times|x|₹|`|rs\.?|inr|per\s+share)\)?)?[^\d.;]{{0,{gap}}}(?:₹|`|rs\.?\s*|inr\s*)?\s*(\d[\d,]*\.?\d*)(\s*%)?(?!\s*(?:yoy|revenue|ebitda|cagr|growth|pat\b|ebit\b))"
    for c in _chunks(L):
        body = _flat(c)
        n = 0
        for m in re.finditer(rx, body, re.I):
            raw = m.group(1).rstrip(",")
            try:
                v = float(raw.replace(",", ""))
            except ValueError:
                continue
            if not lo <= v <= hi or not isinstance(c.get("page"), int):
                continue
            if pct is True and not m.group(2) or pct is False and m.group(2):
                continue
            sub, u = "", unit
            if metric == "contingent_liabilities":
                win = body[m.start(): m.end() + 140]
                sm = re.search(r"claims? against[^0-9]{0,80}|not acknowledged[^0-9]{0,60}|disputed[^0-9]{0,60}|guarantees?[^0-9]{0,40}", win, re.I)
                if not sm or ("," not in raw and "." not in raw and (v < 100 or 1900 <= v <= 2100)):
                    continue
                sub, u = " ".join(sm.group(0).split())[:80], _unit_scale(body, m.start())
                if re.search(r"\btotal\s+contingent", body[max(0, m.start() - 12): m.start() + 20], re.I):
                    sub = "total"
            tail = body[m.start(1): m.end(1) + 60]
            cols = _numbers(tail)[:4] or [v]
            out.append(source_fact(L.key, L.fy, _local_basis(L, body, m.start(), c["page"]), metric, c["page"], body[max(0, m.start() - 40): m.end() + 60], cols[0], u, values=cols, subcategory=sub))
            n += 1
            if n >= 3:
                break
    return out


EXTRACTORS = {
    "book_value": lambda L: _scan(L, "book_value_per_share", r"book\s+value\s+per\s+(?:equity\s+)?share", 0.5, 100000, "INR per share", pct=False),
    "roce": lambda L: _scan(L, "roce", r"(?:return\s+on\s+capital\s+employed(?:\s*\(roce\))?|\broce\b)", 0.1, 400, "%", pct=True),
    "interest_coverage": lambda L: _scan(L, "interest_coverage", r"interest\s+(?:service\s+)?coverage(?:\s+ratio)?", 0.01, 100000, "times", pct=False),
    "contingent": lambda L: _scan(L, "contingent_liabilities", r"contingent\s+liabilit\w+", 1, 10 ** 9, "INR", gap=60),
}


def concentration_facts(L) -> list[dict]:
    """The parsed concentration note (G4 Ledger): typed with page, basis, subtype (customer revenue vs depositor funding) and every figure of the note."""
    f = L.facts.get("customer_conc")
    if not f:
        return []
    deposit = L.bank or bool(re.search(r"depositor|deposit", f.text, re.I))
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", f.text) if x.replace(",", "").replace(".", "", 1).isdigit()]
    return [source_fact(L.key, f.fy or L.fy, f.basis, "deposit_concentration" if deposit else "customer_concentration", f.page, f.text, f.num, f.unit, values=nums, subtype="deposit" if deposit else "customer")]


EXTRACTORS["concentration"] = concentration_facts


# ───────────────────────────── destination-record probes (period-specific) ─────────────────────────────
TREND = {"book_value": ("per_share", "book_value_per_share"), "roce": ("return_on_capital", "roce"), "interest_coverage": ("debt_and_liquidity", "interest_coverage"),
         "contingent": ("balance_sheet_strength", "contingent_liabilities")}


def _trend_probe(L, topic: str) -> dict:
    g, m = TREND[topic]
    tr = (L.m("financials/financial_trends.json") or {}).get("trend_groups", {})
    allrows = ((tr.get(g) or {}).get(m) or {}).get("series") or []
    ser = [x for x in allrows if x.get("value") is not None]
    at_fy = [x for x in ser if str(x.get("year")).lower() == L.fy]
    other = [str(x.get("year")) for x in ser if str(x.get("year")).lower() != L.fy]
    fy_rows = [x for x in allrows if str(x.get("year")).lower() == L.fy]          # the declared basis survives a null value
    basis = str((at_fy or fy_rows or [{}])[0].get("basis") or "unknown")
    return record_fact(L.key, L.fy, m, bool(at_fy), f"company_memory/financials/financial_trends.json:{g}.{m}", f"{L.fy.upper()}: {'value ' + str(at_fy[0]['value']) if at_fy else 'no value'}; other years with a value: {', '.join(other) or 'none'}",
                       basis=basis, summary=f"a {L.fy.upper()} value of {at_fy[0]['value']:g}" if at_fy else "")


def _walk(o, pred, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if pred(str(k), v):
                yield f"{path}.{k}"
            yield from _walk(v, pred, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk(v, pred, f"{path}[{i}]")


def _concentration_probe(L) -> dict:
    cm = L.m("company_model/company_model.json")
    hits = list(_walk(cm, lambda k, v: re.search(r"concentrat", k, re.I) and not k.endswith("_known") and not isinstance(v, bool) and v not in (None, "", [], {}, "unknown")))
    return record_fact(L.key, L.fy, "customer_concentration", bool(hits), "company_memory/company_model/company_model.json", f"fields named *concentration* with a value: {hits[:3] or 'none'}", summary="a concentration figure" if hits else "")


def _engines_probe(L) -> dict:
    cm = L.m("company_model/company_model.json") or {}
    ee = cm.get("economic_engines") or {}
    engines = ee.get("engines") or [] if ee.get("coverage_status") == "SUPPORTED" else []
    with_rev = [e.get("engine_name") for e in engines if any(h.get("revenue_share") is not None or h.get("revenue") is not None for h in (e.get("history") or []))]
    return record_fact(L.key, L.fy, "revenue_by_engine", bool(with_rev), "company_memory/company_model/company_model.json:economic_engines", f"coverage {ee.get('coverage_status')}; engines with revenue: {with_rev[:6] or 'none'}", summary=f"revenue for {len(with_rev)} segments or regions ({', '.join(with_rev[:4])})" if with_rev else "")


PART_KEYS = {"cost": r"capital_deployed|actual_cost|^cost$|total_cost", "output": r"actual_output|achieved|produced|throughput|capacity_added", "utilisation": r"utili[sz]ation", "returns": r"return|roi|payback", "revenue": r"incremental_revenue|site_revenue|revenue_contribution"}      # achieved / deployed figures; an *expected* cost or output is a plan, not an outcome
EMPTY = (None, "", [], {}, False)


def _is_figure(v) -> bool:
    """A figure is a number or text containing a digit; a status word such as 'unknown' or 'partially_observed' is not a figure."""
    if isinstance(v, bool) or v in EMPTY:
        return False
    return isinstance(v, (int, float)) or (isinstance(v, str) and bool(re.search(r"\d", v)))


def _project_names(L) -> list[str]:
    n = [p.get("project_name", "") for p in (L.m("projects/projects_registry.json") or {}).get("projects", [])]
    n += [c.get("capacity_name", "") for c in (L.m("capacity/capacity_registry.json") or {}).get("capacity_items", [])]
    return [x for x in n if x]


def _project_part_probe(L, part: str, subject: str = "") -> dict:
    """Universal over the project and capacity registries (or over the one named project): does any record hold a non-empty value for this component?"""
    hits = []
    for rel, key in (("projects/projects_registry.json", "projects"), ("capacity/capacity_registry.json", "capacity_items")):
        for rec in (L.m(rel) or {}).get(key, []):
            nm = rec.get("project_name") or rec.get("capacity_name") or ""
            if subject and similarity(normalize(nm), normalize(subject)) < 0.6:
                continue
            hits += [f"{rel}:{nm[:40]}{p}" for p in _walk(rec, lambda k, v, rx=PART_KEYS[part]: re.search(rx, k, re.I) and _is_figure(v))]
    return record_fact(L.key, L.fy, f"project_{part}", bool(hits), "company_memory/{projects,capacity}/*registry.json", f"non-empty {part} fields: {hits[:3] or 'none'}", subject=subject, summary=f"{len(hits)} project or capacity entries carry a recorded {part} figure" if hits else "")


PROBES = {"book_value": _trend_probe, "roce": _trend_probe, "interest_coverage": _trend_probe, "contingent": _trend_probe, "concentration": _concentration_probe, "revenue_split": _engines_probe}


def _wc_flag(L) -> str:
    return str((L.m("financials/investor_financial_modules/working_capital_quality_drilldown.json") or {}).get("working_capital_applicability") or "unknown")


# ───────────────────────────── compound claims: independent components ─────────────────────────────
PARTS = {
    "revenue_split": {"mix": r"split of revenue|revenue (?:mix|breakdown|split)|by product, segment or region|mix by segment", "margins": r"margins?"},
    "rd_spend": {"spend": r"spending|expense|expenditure|spend", "stages": r"pipeline stages?|stages", "outcomes": r"pipeline outcomes?|outcomes?"},
    "project_outcomes": {"cost": r"\bcosts?\b", "output": r"\boutputs?\b", "utilisation": r"utili[sz]ation|throughput", "returns": r"returns?|incremental revenue", "revenue": r"site-level revenue|incremental revenue|revenue by site"},
    "management_incentives": {"pay": r"\bpay\b|remuneration", "esop": r"esop", "alignment": r"promoter alignment|alignment"},
    "capital_outcomes": {"output": r"\boutput\b", "margin": r"\bmargin\b", "cash": r"cash result|cash"},
    "competitive_position": {"share": r"market share", "pricing": r"pricing power", "peers": r"peers?"},
    "market_size": {"size": r"market size", "share": r"\bshare\b", "dynamics": r"industry dynamics|runway"},
}
SUBJECT_REQUIRED = {"risk_response", "transaction_amounts", "commitment_followthrough", "capital_outcomes", "management_depth"}      # (project claims are universal over the project registry unless they name a project)
NA_TOTAL = {"working_capital": "the company's own working-capital module marks these measures not economically meaningful (banking schedule)",
            "bank_measure": "industrial borrowing, owner-earnings and working-capital measures are defined on operating cash flow before financing; a bank's operating cash flow includes loans and deposits",
            "interest_coverage": "interest coverage is defined on borrowing cost; a bank's cost of funds is its operating input, so the ratio is not a bank measure", "roce": "return on capital employed treats debt as capital; a bank's deposits are its stock in trade, so returns are judged on assets and equity"}

# investor-facing fallback pieces, per profile (what it matters for, what would settle it) - short on purpose
META = {
    "capex_split": ("whether the maintenance share of capex is disclosed", "how much spending only sustains the business changes what cash is truly free", "a read of the cash-flow, asset and investment notes for any purpose split"),
    "revenue_split": ("whether revenue and margins by product, segment or region are disclosed", "growth quality depends on which activities earn the margin", "the segment note and the segment discussion in management's review"),
    "segment_margins": ("whether product-level or segment margins are disclosed", "a blended margin can hide a weak or strong business line", "the statutory segment note and any product discussion"),
    "rd_spend": ("whether total R&D spend, pipeline stages and outcomes are disclosed together", "future revenue depends on pipeline productivity, not only spend", "the R&D, capitalised-development and pipeline sections"),
    "project_outcomes": ("whether cost, output, utilisation and returns are disclosed for each project", "execution does not show payoff until returns are visible", "the project-level disclosures for each named project"),
    "capital_outcomes": ("whether returns on specific capital allocations are disclosed", "company-wide returns cannot show what an individual allocation earned", "allocation-level notes for each named deal or programme"),
    "commitment_followthrough": ("whether the promised measure was met under its original definition and deadline", "a related result is not proof of delivery, and silence is not proof of failure", "the original commitment text and the later report passage for the same metric"),
    "risk_response": ("whether management disclosed a response to this specific risk", "a general governance statement does not show the risk is being managed", "the filing's mitigation text for the same risk"),
    "management_depth": ("whether the depth and quality of management and its organisations are evidenced", "named executives and hires describe people, not capability or succession quality", "evidence of continuity and capability beyond the roster"),
    "management_incentives": ("whether pay, ESOP terms and promoter alignment are all evidenced", "incentives show whose interests management serves", "the remuneration and ESOP notes plus shareholding data"),
    "competitive_position": ("whether market share and pricing power against peers are disclosed", "a durable advantage needs evidence against named competitors", "the industry and peer disclosures"),
    "market_size": ("whether market size, company share and growth runway are disclosed", "runway depends on the size of the market the company can win", "the industry and strategy sections"),
    "peer_comparison": ("whether a peer comparison is disclosed", "relative performance needs a like-for-like peer set", "any peer or benchmark table"),
    "transactions": ("whether any other transaction is pending", "a completed deal is not pending exposure and a pending one changes risk", "the transaction notes and board disclosures"),
    "transaction_amounts": ("whether the consideration for the named deals is disclosed", "price paid is the starting point for judging a deal", "the business-combination and subsequent-event notes for the named deals"),
    "contingent": ("whether the contingent-liability amounts are extracted", "claims not yet recognised can be large relative to equity", "the contingent-liability note"),
    "concentration": ("whether the concentration note is extracted into the records", "dependence on a few customers or depositors changes risk", "the concentration note"),
    "book_value": ("whether book value per share is extracted into the records", "an asset-based floor value needs a book value", "the key-ratio table"),
    "roce": ("whether return on capital employed is extracted into the records", "it shows what the whole capital base earns", "the key-ratio table"),
    "interest_coverage": ("whether interest coverage is extracted into the records", "it shows how comfortably earnings carry debt cost", "the ratio table and finance-cost note"),
    "guidance": ("whether management guidance is extracted", "guidance is the benchmark later results are judged against", "the outlook sections"),
    "order_book": ("whether the order book is extracted", "an order book shows forward revenue visibility", "the business review"),
    "credit_cost": ("whether credit cost is extracted", "it is the main earnings drag for a lender", "the provisioning note"),
}



# ───────────────────────────── the gate ─────────────────────────────
NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
PRED = re.compile(r"\b(?:is|are|was|were|do|does|did|has|have)\s+(?:not|no)\b|\bnot\s+(?:yet\s+)?(?:extracted|disclosed|stated|reported|given|provided|available|found|recorded|linked)\b|\b(?:hold|holds|show|shows|provides?)\s+no\b", re.I)
FY_TOKEN = re.compile(r"\bFY\s?(?:20)?\d{2}(?:\s?[-–]\s?(?:20)?\d{2})?\b|\b20\d{2}\s?[-–]\s?\d{2}\b", re.I)
QUAL = re.compile(r"\b(?:for|of|after|before|from|at|in|during|under|within)\s+(?:the\s+|its\s+|our\s+)?(?:[A-Z][\w&.\-]+|completion|acquisition|deal|transaction|facility|plant|project|industry|sector|segment|product|products|division|unit|subsidiary|business|group|peers?|competitors?)\b")
FORECAST = re.compile(r"\b(?:expected|forecast|projected|estimated|guided|targeted?|pro\s?forma|budgeted|anticipated)\b", re.I)


def _aliases() -> dict[str, list[str]]:
    from pipelines import m59_question_batch as m59
    out = {}
    for k, name in m59.NAMES.items():
        tok = name.lower().split()
        a = {name.lower(), " ".join(tok[:2]), k.replace("_", " "), k}
        if tok[0] not in {"data", "sun", "the"}:
            a.add(tok[0])
        out[k] = sorted(a, key=len, reverse=True)
    return out


def parse_claim(L, clause: str) -> dict:
    """The claim's own identity: the subject phrase before the negation, split into the facts the claim asserts (company, basis, FY, numbers, qualifier, forecast meaning, subtype).
    Anything the gate cannot match against a typed source fact and a destination record blocks VERIFIED."""
    s = " ".join(clause.split())
    m = PRED.search(s)
    subject = s[:m.start()] if m else s
    if ":" in subject:
        subject = subject.split(":")[0]
    low = subject.lower()
    al = _aliases()
    others = [k for k, a in al.items() if k != L.key and any(re.search(rf"\b{re.escape(x)}\b", low) for x in a)]
    own = any(re.search(rf"\b{re.escape(x)}\b", low) for x in al.get(L.key, []))
    fys = [f"fy{x[-2:]}" for x in re.findall(r"FY\s?(\d{2,4})(?!\d)", subject)]
    basis = sorted(set(re.findall(r"\b(consolidated|standalone)\b", low)))
    clean = FY_TOKEN.sub(" ", subject)
    nums = []
    for mm in re.finditer(r"(\d[\d,]*\.?\d*)\s*(%|million|crores?|\bcr\b|times|x)?", clean):
        try:
            nums.append((float(mm.group(1).replace(",", "").rstrip(".")), mm.group(2) or ""))
        except ValueError:
            pass
    for w, n in NUMWORDS.items():
        if re.search(rf"\b{w}\b\s+(?:major\s+|top\s+|large\s+)?(?:customers?|clients?|buyers?|depositors?|borrowers?)", low):
            nums.append((float(n), "count"))
    strip = clean
    for t, p in G.PROFILES.items():
        strip = p["claim"].sub(" ", strip)
    for a in sum(al.values(), []):
        strip = re.sub(rf"\b{re.escape(a)}\b", " ", strip, flags=re.I)
    strip = re.sub(r"\b(consolidated|standalone)\b", " ", strip, flags=re.I)
    strip = re.sub(r"\b(?:in|into|from|within)\s+(?:the\s+)?(?:\w+\s+){0,2}(?:records?|data|register|ledger|models?)\b", " ", strip, flags=re.I)
    qual = [q for q in QUAL.finditer(strip) if q.start() > 0]
    subtype = "deposit" if re.search(r"deposit", low) else "borrower" if re.search(r"borrower|advances|loan book", low) else "customer" if re.search(r"customer|client|buyer", low) else ""
    return {"subject": subject, "other_companies": others, "own_named": own, "fys": fys, "basis": basis, "numbers": nums, "qualifiers": [q.group(0).strip() for q in qual], "forecast": bool(FORECAST.search(low)),
            "subtype": subtype, "total": bool(re.search(r"\btotal\b|\baggregate\b", low))}


def _pieces(subject: str) -> list[str]:
    out = []
    for p in re.split(r"\s*(?:,|\band\b|&|;|\bor\b)\s*", re.sub(r"\([^)]*\)", lambda m: m.group(0).replace(",", "§"), subject)):
        p = p.replace("§", ",").strip(" —-:()")
        if p and p.lower() not in {"the", "a", "an"}:
            out.append(p)
    return out


def _map_pieces(subject: str, whole_topic: str | None) -> tuple[list[str], list[str]]:
    """Topics asserted by the subject and the pieces that map to no evidence profile (never dropped silently)."""
    topics: list[str] = []
    unmapped: list[str] = []
    pieces = _pieces(subject)
    found = [t for t, p in G.PROFILES.items() if p["claim"].search(subject) and t != "segment_mix"]
    for p in pieces:
        t = G.topic_of(p)
        if t == "segment_mix":
            t = "revenue_split"
        if t is None:
            for tt in found:
                if any(re.search(rx, p, re.I) for rx in PARTS.get(tt, {}).values()):
                    t = tt
                    break
        if t is None and re.search(r"\b(?:figures?|data|amounts?|records?|numbers?)\b", p, re.I) and not re.search(r"[A-Za-z]{4,}\s+[A-Za-z]{4,}", re.sub(r"\b(?:figures?|data|amounts?|records?|numbers?|the|of)\b", "", p, flags=re.I)):
            continue
        if t is None:
            unmapped.append(p)
        elif t not in topics:
            topics.append(t)
    if not topics and whole_topic:
        topics = [whole_topic]
        unmapped = []
    return topics, unmapped


def _assertion_level(clause: str) -> str:
    if re.search(r"not found after searching|sections searched", clause, re.I):
        return "SEARCH_FACT"
    cls, _ = G.classify(clause)
    if cls == G.INAPPLICABLE_MEASURE or re.search(r"\bdoes not apply\b|\bdo not apply\b", clause, re.I):
        return "NOT_APPLICABLE"
    return "RECORD_FACT" if cls == G.EXTRACTION_ABSENCE else "SOURCE_NEGATIVE"


def _cached(L, key: str, fn):
    k = "g5v:" + key
    if k not in L._c:
        L._c[k] = fn()
    return L._c[k]


def _components(topic: str, clause: str) -> list[str]:
    parts = PARTS.get(topic) or {}
    hit = [k for k, rx in parts.items() if re.search(rx, clause, re.I)]
    return hit if len(hit) > 1 else ["whole"]


def _subject(clause: str) -> str:
    m = re.search(r"\b(?:for|at|of)\s+(?:the\s+)?((?:[A-Z][\w&.-]*\s?){1,4})(?:\s+(?:plant|project|facility|site|programme|program))?", clause)
    return (m.group(1).strip() if m else "")


def _has_subject(L, clause: str, context: str) -> bool:
    """A subject is identified only if the sentence names a capitalised entity or an id that is not just the company or a generic noun."""
    text = f"{clause} {context}"
    names = re.findall(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b|\b(MC-\d+|RQ-[\w-]+)\b|\b([A-Z][a-z]+™)", text)
    generic = {normalize(L.name), "management", "the company"}
    return any(normalize(next(g for g in n if g)) not in generic for n in names)


def verify_claim(L, clause: str, cls: str, context: str = "") -> dict:
    """The verdict for one genuine absence clause. Never raises a claim to VERIFIED on a topic mention; always returns machine reasons and an investor fallback."""
    level = _assertion_level(clause)
    whole = G.topic_of(clause) or (G.topic_of(context) if context else None)
    contract = parse_claim(L, clause)
    topics, unmapped = _map_pieces(contract["subject"], whole)
    res: dict[str, Any] = {"claim": clause, "topic": topics[0] if topics else whole, "topics": topics, "level": level, "company": L.key, "fy": L.fy, "contract": contract, "components": [], "reasons": [],
                           "record_facts": [], "source_facts": [], "leads": []}
    if not topics:
        res.update(verdict=VERDICT_UNSUPPORTED, acceptance=NEEDS_REVIEW, status="UNVERIFIED", reasons=["NO_EVIDENCE_PROFILE"], state=None, fallback=generic_fallback(clause), leads=G.generic_locators(L, clause), record_statement_ok=False)
        return res
    topic = topics[0]
    # claim-level identity blockers: they change WHAT is claimed, so evidence about the default subject neither proves nor refutes it
    blockers: list[str] = []
    if contract["other_companies"]:
        blockers.append("WRONG_COMPANY:" + ",".join(contract["other_companies"]))
    other = [y for y in contract["fys"] if y != L.fy]
    if other and level != "SEARCH_FACT":
        blockers.append("WRONG_OR_UNMATCHED_PERIOD:" + ",".join(other))
    if contract["qualifiers"] and level != "SEARCH_FACT":
        blockers.append("QUALIFIER_NOT_MATCHED:" + "; ".join(contract["qualifiers"])[:80])
    if contract["forecast"]:
        blockers.append("FORECAST_NOT_ACTUAL")
    for u in unmapped:
        blockers.append("UNSUPPORTED_COMPONENT:" + u[:60])
    subj = _subject(clause) if "project_outcomes" in topics else ""
    if subj and not any(similarity(normalize(n), normalize(subj)) >= 0.6 for n in _project_names(L)):
        blockers.append("SUBJECT_NOT_IN_RECORD:" + subj)
    for t in topics:
        if t in SUBJECT_REQUIRED and not _has_subject(L, clause, context):
            blockers.append("SUBJECT_NOT_IDENTIFIED")
            break
    res["reasons"] += blockers
    # applicability, decided per component (no sector blanket)
    if level == "NOT_APPLICABLE":
        ok = bool(topics) and not unmapped and L.bank and all(t in NA_TOTAL and (t != "working_capital" or _wc_flag(L) == "not_economically_meaningful") for t in topics) and not blockers
        if ok:
            res["components"] = [{"part": t, "topic": t, "verdict": VERDICT_SUPPORTED, "source_facts": [], "record_facts": [], "reasons": [], "basis": NA_TOTAL[t]} for t in topics]
            res.update(verdict=VERDICT_SUPPORTED, acceptance=ACCEPT, status="VERIFIED", state="NOT_APPLICABLE", basis="; ".join(NA_TOTAL[t] for t in topics), locator="", fallback=None, record_statement_ok=False)
        else:
            res["components"] = [{"part": t, "topic": t, "verdict": VERDICT_PARTIALLY if t in NA_TOTAL else VERDICT_UNSUPPORTED, "source_facts": [], "record_facts": [], "reasons": [] if t in NA_TOTAL else ["INAPPLICABILITY_NOT_ESTABLISHED_IN_TOTAL"], "basis": ""} for t in topics] + \
                                [{"part": u, "topic": None, "verdict": VERDICT_UNSUPPORTED, "source_facts": [], "record_facts": [], "reasons": ["UNSUPPORTED_COMPONENT"], "basis": ""} for u in unmapped]
            res["reasons"].append("INAPPLICABILITY_NOT_ESTABLISHED_IN_TOTAL")
            res.update(verdict=VERDICT_PARTIALLY, acceptance=NEEDS_REVIEW, status="UNVERIFIED", state=None, record_statement_ok=False)
            _finish(L, res, topic, G.PROFILES[topic])
        return res
    verdicts = []
    for t in topics:
        for c in _components(t, clause):
            verdicts.append(_verify_component(L, t, c, level, clause, contract, subj))
    res["components"] = verdicts + [{"part": u, "topic": None, "verdict": VERDICT_UNSUPPORTED, "source_facts": [], "record_facts": [], "reasons": ["UNSUPPORTED_COMPONENT"], "basis": "no evidence profile for this component"} for u in unmapped]
    res["record_facts"] = [f for v in verdicts for f in v["record_facts"]]
    res["source_facts"] = [f for v in verdicts for f in v["source_facts"] if v["verdict"] in (VERDICT_SUPPORTED, VERDICT_CONTRADICTED)]
    res["reasons"] += [r for v in verdicts for r in v["reasons"] if r not in res["reasons"]]
    identity_blocked = any(b.startswith(("WRONG_COMPANY", "WRONG_OR_UNMATCHED_PERIOD", "QUALIFIER_NOT_MATCHED", "FORECAST_NOT_ACTUAL", "SUBJECT_")) for b in blockers)
    if identity_blocked:                                               # the evidence is about a different subject than the claim: it neither proves nor refutes it
        res.update(verdict=VERDICT_UNSUPPORTED, acceptance=NEEDS_REVIEW, status="UNVERIFIED", state=None)
        res["record_facts"] = [] if any(b.startswith(("WRONG_COMPANY", "FORECAST", "QUALIFIER")) for b in blockers) else res["record_facts"]
        res["source_facts"] = []
    elif any(v["verdict"] == VERDICT_CONTRADICTED for v in verdicts):
        res.update(verdict=VERDICT_CONTRADICTED, acceptance=REJECT, status="CONTRADICTED", state=None)
    elif all(v["verdict"] == VERDICT_SUPPORTED for v in verdicts) and not blockers:
        res.update(verdict=VERDICT_SUPPORTED, acceptance=ACCEPT, status="VERIFIED", state="NOT_EXTRACTED", basis="; ".join(v["basis"] for v in verdicts), locator="; ".join(f"p.{f['page']}" for f in res["source_facts"]))
    else:
        res.update(verdict=VERDICT_PARTIALLY if any(v["verdict"] == VERDICT_SUPPORTED for v in verdicts) else VERDICT_UNSUPPORTED, acceptance=NEEDS_REVIEW, status="UNVERIFIED", state=None)
    res["record_statement_ok"] = bool(level == "RECORD_FACT" and res["status"] == "UNVERIFIED" and not blockers and verdicts and all(v["record_facts"] and all(r["present"] is False for r in v["record_facts"]) for v in verdicts))
    return _finish(L, res, topic, G.PROFILES[topic])


def _numbers_match(contract: dict, f: dict, topic: str) -> list[str]:
    reasons = []
    cur = f["values"][0] if f["values"] else f["value"]
    for v, unit in contract["numbers"]:
        if unit == "count":
            if v not in [round(x) for x in f["values"] if float(x).is_integer()][:1] and not (topic == "concentration" and v in [x for x in f["values"][:1]]):
                reasons.append(f"ASSERTED_VALUE_MISMATCH:count {v:g}")
            continue
        scale_ok = True
        if unit in ("million", "crore", "crores", "cr"):
            want = {"million": "million", "crore": "crore", "crores": "crore", "cr": "crore"}[unit]
            scale_ok = want in f["unit"].lower()
        if f["metric"] == "customer_concentration":
            if v not in f["values"]:
                reasons.append(f"ASSERTED_VALUE_MISMATCH:{v:g}")
            continue
        if cur is not None and abs(v - cur) <= max(0.06, abs(cur) * 0.005) and scale_ok:
            continue
        if any(abs(v - x) <= max(0.06, abs(x) * 0.005) for x in f["values"][1:]):
            reasons.append(f"ASSERTED_VALUE_IS_PRIOR_OR_VARIANCE_COLUMN:{v:g}")
        else:
            reasons.append(f"ASSERTED_VALUE_MISMATCH:{v:g}")
    return reasons


def _verify_component(L, topic: str, part: str, level: str, clause: str, contract: dict, subj: str = "") -> dict:
    v: dict[str, Any] = {"part": part, "topic": topic, "source_facts": [], "record_facts": [], "reasons": [], "basis": ""}
    ex = EXTRACTORS.get(topic)
    src = [f for f in (_cached(L, f"src:{topic}", lambda: ex(L)) if ex else []) if f["company"] == L.key and f["fy"] == L.fy]
    if topic == "project_outcomes" and part != "whole":                      # each component against the project registry, for the named project if one is named
        rec = _cached(L, f"rec:{topic}:{part}:{subj}", lambda: _project_part_probe(L, part, subj))
    elif topic in PROBES:
        rec = _cached(L, f"rec:{topic}", lambda: PROBES[topic](L, topic) if topic in TREND else PROBES[topic](L))
    else:
        rec = None
    v["source_facts"], v["record_facts"] = src, ([rec] if rec else [])
    if rec is not None and rec["present"]:
        v.update(verdict=VERDICT_CONTRADICTED, basis=rec["detail"])
        v["reasons"].append("RECORD_HOLDS_THE_FIGURE")
        return v
    if level == "SOURCE_NEGATIVE":
        if src:
            v.update(verdict=VERDICT_CONTRADICTED, basis="the report carries it")
            v["reasons"].append("SOURCE_CARRIES_WHAT_THE_CLAIM_DENIES")
        else:
            v.update(verdict=VERDICT_UNSUPPORTED, basis="no exact source fact")
            v["reasons"].append("NOT_DISCLOSED_NEEDS_HUMAN_SIGNOFF")
        return v
    if level == "SEARCH_FACT":
        v.update(verdict=VERDICT_PARTIALLY, basis="a search found nothing")
        v["reasons"].append("SEARCH_NEGATIVE_IS_NOT_PROOF_OF_NONDISCLOSURE")
        return v
    # RECORD_FACT: both legs, and the claim's own identity must match the fact
    if rec is None:
        v["reasons"].append("NO_DESTINATION_RECORD_PROBE")
    if not src:
        v["reasons"].append("NO_EXACT_SOURCE_FACT")
    if not src or rec is None:
        v.update(verdict=VERDICT_PARTIALLY if (rec is not None and not rec["present"]) else VERDICT_UNSUPPORTED, basis=(rec["detail"] if rec else "no probe"))
        return v
    facts = src
    if contract["basis"]:
        facts = [f for f in src if f["basis"] in contract["basis"]]
        if not facts:
            v["reasons"].append("BASIS_NOT_ESTABLISHED:asserted " + "/".join(contract["basis"]) + ", source " + "/".join(sorted({f["basis"] for f in src})))
            v.update(verdict=VERDICT_PARTIALLY, basis="no source fact on the asserted basis")
            return v
    if any(f["basis"] == "ambiguous" for f in facts):
        v["reasons"].append("BASIS_NOT_ESTABLISHED:ambiguous table")
        v.update(verdict=VERDICT_PARTIALLY, basis="the source table's basis could not be resolved")
        return v
    st = contract["subtype"]
    if st and any(f["subtype"] and f["subtype"] != st for f in facts):
        v["reasons"].append(f"SUBTYPE_MISMATCH:claim {st}, source {facts[0]['subtype']}")
        v.update(verdict=VERDICT_PARTIALLY, basis="the source note concerns a different kind of concentration")
        return v
    if topic == "contingent" and (contract["total"] or not re.search(r"claims?|guarantee|disput", contract["subject"], re.I)) and all(f["subcategory"] != "total" for f in facts):
        v["reasons"].append("AGGREGATE_NOT_ESTABLISHED:source gives a subcategory")
        v.update(verdict=VERDICT_PARTIALLY, basis="the source figure is one subcategory, not the total")
        return v
    bad = [r for f in facts[:1] for r in _numbers_match(contract, f, topic)]
    if bad:
        v["reasons"] += bad
        v.update(verdict=VERDICT_PARTIALLY, basis="the asserted figure is not the source's current-year figure")
        return v
    if len({(f["basis"], f["values"][0]) for f in facts if f["values"]}) > len({f["basis"] for f in facts}):
        v["reasons"].append("SOURCE_CONFLICT_SAME_BASIS")
        v.update(verdict=VERDICT_PARTIALLY, basis="the report states different values for one metric on one basis")
        return v
    f = facts[0]
    if rec.get("basis", "unknown") not in ("unknown", f["basis"]) and f["basis"] != "unknown":
        v["reasons"].append(f"BASIS_MISMATCH:source={f['basis']},record={rec['basis']}")
        v.update(verdict=VERDICT_PARTIALLY, basis="source and destination record are on different bases")
        return v
    if f["basis"] == "unknown" and topic not in ("concentration", "book_value", "roce", "interest_coverage"):
        v["reasons"].append("SOURCE_IDENTITY_MISMATCH:basis")
        v.update(verdict=VERDICT_PARTIALLY, basis="source fact identity incomplete")
        return v
    v["source_facts"] = [f]
    v.update(verdict=VERDICT_SUPPORTED, basis=f"source: {f['metric']} {f['values'][0]:g} {f['unit']} ({f['fy'].upper()}, {f['basis']}, p.{f['page']}; columns {', '.join(f'{x:g}' for x in f['values'][:3])}); record: {rec['detail']}")
    return v


def _finish(L, res: dict, topic: str, prof: dict) -> dict:
    res["leads"] = sorted({f for f in (G.resolve(L, topic).get("filing_weak_pages") or [])})[:6]
    res["fallback"] = None if res["status"] == "VERIFIED" else fallback(L, res, topic, prof)
    return res


def _pp(pages: list[int]) -> str:
    return ("p." if len(pages) == 1 else "pp.") + ", ".join(map(str, pages))


REPORT_STATES = {"contingent", "concentration", "book_value", "roce", "interest_coverage", "guidance", "order_book", "credit_cost"}


def _lc(label: str) -> str:
    return label if label[:2].isupper() else label[0].lower() + label[1:]


PART_FALLBACK = {   # when some components of a compound claim are already established, only the unproven ones are carried forward
    ("revenue_split", "margins"): ("whether margins by product, segment or region are disclosed", "a blended margin hides which activity earns the return", "the segment note and management's segment discussion"),
}


def fallback(L, res: dict, topic: str, prof: dict) -> dict:
    """What is established, what is not concluded, why it matters, what would help. `established` holds only facts that passed verification: probe results, and source facts from
    components whose identity (company, FY, basis, subject, figure) matched. Text matches are named as unread leads."""
    q, why, resolve = META.get(topic, (f"whether {_lc(prof['label'])} is disclosed", "the answer depends on it", "a read of the relevant section"))
    if topic in REPORT_STATES:
        q = f"whether the {L.fy.upper()} report states {_lc(prof['label'])}"
    comps = res.get("components") or []
    for c in comps:
        if (c["topic"], c["part"]) in PART_FALLBACK and c["verdict"] not in (VERDICT_SUPPORTED, VERDICT_CONTRADICTED):
            q, why, resolve = PART_FALLBACK[(c["topic"], c["part"])]
    if topic == "revenue_split" and any(c["part"] == "mix" and c["verdict"] == VERDICT_CONTRADICTED for c in comps) and "margins" in res["contract"]["subject"].lower():
        q, why, resolve = PART_FALLBACK[("revenue_split", "margins")]
    est: list[str] = []
    for rf in res["record_facts"]:
        t = f"the records hold no {rf['metric'].replace('_', ' ')} for {L.fy.upper()}" if rf["present"] is False else f"the records already hold {rf['metric'].replace('_', ' ')} ({rf.get('summary') or 'a value'})"
        if t not in est:
            est.append(t)
    for sf in res["source_facts"]:
        t = f"the {L.fy.upper()} report states {sf['metric'].replace('_', ' ')} {sf['values'][0]:g}{'%' if sf['unit'] == '%' else ''} ({sf['basis']}, p.{sf['page']})"
        if t not in est:
            est.append(t)
    if res["level"] == "SEARCH_FACT" or (not est and G.resolve(L, topic)["state"] == "NOT_DISCLOSED_CANDIDATE"):
        est.append(f"a text search of the {L.fy.upper()} report found no {_lc(prof['label'])}")
    if not est and res["leads"] and res["level"] != "NOT_APPLICABLE":
        est.append(f"the {L.fy.upper()} report mentions {_lc(prof['label'])} on {_pp(res['leads'])}, not yet read for figures")
    return {"established": est, "not_concluded": q, "why_it_matters": why, "would_resolve": resolve, "leads": res["leads"]}


CAUSE_TAIL = re.compile(r"\s*(?:,\s*)?\b(?:due to|because of|because|owing to|as a result of|caused by|following|attributable to|on account of|since)\b.*$", re.I)
PREDICATE_WORDS = re.compile(r"\b(?:is|are|was|were|has|have|had)?\s*(?:not|no|never|missing|unavailable|absent|undisclosed|unreported|unstated|not\s+(?:been\s+)?(?:given|stated|reported|disclosed|available|found|recorded|extracted|separately|yet))\b.*$", re.I)


def subject_core(clause: str) -> str:
    """What a statement is ABOUT, with its predicate and any causal explanation removed: an unsupported premise must not come back as fact, not even inside an uncertainty note."""
    s = " ".join(clause.split()).strip(" ,;:)(")
    s = CAUSE_TAIL.sub("", s)
    s = PREDICATE_WORDS.sub("", s).strip(" ,;:)(")
    if ", and " in s:
        s = s.split(", and ")[-1]
    s = re.sub(r"^(?:this is|these are|it is|that is)\s+(?:a|an|the)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*\([^)]*$", "", s).strip(" ,;:)(")
    return s[:90]


def generic_fallback(clause: str) -> dict:
    core = subject_core(clause)
    about = f"what the filing and the records establish about {core}" if len(core) >= 4 else "what the filing and the records establish on this point"
    return {"established": [], "not_concluded": about, "why_it_matters": "the recorded statement could not be matched to a source passage", "would_resolve": "the original filing passage", "leads": [], "generic": True}


# ───────────────────────────── positive claims: acquisition / completion of a named event ─────────────────────────────
EVENT_STOP = {"the", "this", "that", "these", "those", "its", "our", "their", "management", "capital", "total", "business", "strategic", "share", "equity", "organic", "inorganic", "any", "each", "every", "no", "one", "all",
              "recorded", "completed", "pending", "announced", "proposed"}
ENTITY = r"[A-Z][\w&.\-]*(?:\s+(?:of\s+)?[A-Z][\w&.\-]*){0,4}"
EVENT_PATTERNS = (
    re.compile(rf"(?P<done>\b(?:completed|closed|consummated)\s+)?(?:the\s+)?(?P<e>{ENTITY})\s+(?P<w>acquisition|merger|takeover|buyout|amalgamation)\b"),
    re.compile(rf"(?P<done>\b(?:completed|closed|consummated)\s+)?\b(?P<w>acquired|acquiring|acquisition of|acquire)\s+(?:the\s+)?(?:\d+\s+equity\s+shares\s+of\s+)?(?P<e>{ENTITY})"),
    re.compile(rf"(?P<w>acquisitions?(?:\s+outcomes?)?)\s*\((?P<e>{ENTITY})\)", re.I),
)
from knowledge.capital_allocation_taxonomy import ACQ_TYPE, DONE_STATUS as DONE, MINOR_TYPE, PENDING_STATUS as PENDING  # noqa: E402  (one event vocabulary for generation and verification)


def _event_records(L) -> list[dict]:
    recs = []
    tl = (L.m("capital_allocation_timeline.json") or {}).get("timeline") or []
    for y in tl:
        for a in y.get("capital_allocation_actions") or []:
            ref = a.get("evidence_references") or {}
            recs.append({"text": " ".join(str(a.get(k) or "") for k in ("value", "purpose", "category", "status")), "category": str(a.get("category") or ""), "value": str(a.get("value") or ""),
                         "status": " ".join(str(a.get(k) or "") for k in ("status", "purpose", "value")), "fy": str(a.get("source_year") or y.get("fiscal_year") or ""), "page": ref.get("page"), "amount": str(a.get("amount") or "")})
    for a in (L.m("capital_allocation_outcomes/capital_allocation_outcomes.json") or {}).get("allocations") or []:
        recs.append({"text": " ".join(str(a.get(k) or "") for k in ("allocation_name", "inferred_business_purpose")), "category": str(a.get("allocation_category") or ""), "value": str(a.get("allocation_name") or ""),
                     "status": str(a.get("current_status") or ""), "fy": str(a.get("first_observed_period") or ""), "page": None, "amount": ""})
    return recs


def _full_name(rec: dict, entity: str) -> str:
    m = re.search(rf"\b(?:of|in)\s+({re.escape(entity.split()[0])}[\w&.\- ]*?(?:Private Limited|Limited|Ltd\.?|Inc\.?|Corporation|Corp\.?|LLC|Pvt\.? Ltd\.?)?)(?=$|[,.;(])", rec["value"])
    return (m.group(1) if m else entity).strip()


SENT_SPLIT = re.compile(r"(?<=[.;])\s+(?=[A-Z0-9(‘“])")


def _filing_event_support(L, first: str) -> dict:
    """What the company's own filings say about an entity's event, from the sentences that name it: an acquisition / merger / amalgamation sentence (strict type words) or a
    minority-stake sentence. Searched across every fiscal-year folder; cached."""
    def go():
        out = {"acq": None, "minor": None, "done": False}
        for fy in sorted(p.name for p in L.cdir.glob("fy??")):
            for c in G._chunks(L, fy):
                body = _flat(c)
                if first.lower() not in body.lower():
                    continue
                for sent in SENT_SPLIT.split(body):
                    if first.lower() not in sent.lower():
                        continue
                    if ACQ_TYPE.search(sent) and not MINOR_TYPE.search(sent):
                        out["acq"] = out["acq"] or {"fy": fy, "page": c.get("page"), "text": sent[:200]}
                        out["done"] = out["done"] or bool(re.search(r"\bcompleted\b|\beffective\b|\bconsummated\b|\bbecame effective\b|\bapproved\b", sent, re.I))
                    elif MINOR_TYPE.search(sent):
                        out["minor"] = out["minor"] or {"fy": fy, "page": c.get("page"), "text": sent[:200]}
        return out
    return _cached(L, "filing_event:" + first.lower(), go)


def verify_events(L, sentence: str) -> list[dict]:
    """Positive claims about a named event ('the X acquisition', 'acquired X', 'completed ... deal'): the claim's event type and completion status must match the typed capital-allocation
    record for that entity (category, value, status); an entity the records do not name is an unsupported premise. Returns one finding per assertion; [] for sentences with none."""
    found, seen = [], set()
    for rx in EVENT_PATTERNS:
        for m in rx.finditer(sentence):
            ent = re.sub(r"^(?:The|A|An)\s+", "", m.group("e").strip())
            first = ent.split()[0] if ent.split() else ""
            if not first or first.lower() in EVENT_STOP or re.match(r"^(?:FY\s?\d|20\d{2}|Q[1-4]\b|H[12]\b)", first) or (m.start("e"), m.end("w") if "w" in m.groupdict() else 0) in seen:
                continue
            word = m.group("w").lower()
            asserted = "acquisition" if re.match(r"acqui|merger|takeover|buyout|amalgam", word) else word
            seen.add((m.start("e"), 0))
            done = bool(m.groupdict().get("done")) or bool(re.search(r"\b(?:completed|closed|consummated)\b", sentence[max(0, m.start() - 24): m.end() + 24], re.I))
            recs = [r for r in _cached(L, "events", lambda: _event_records(L)) if first.lower() in r["text"].lower()]
            fil = _filing_event_support(L, first)
            f = {"entity": ent, "asserted": asserted, "completion_asserted": done, "span": (m.start("done") if m.groupdict().get("done") else m.start(), m.end()), "phrase": sentence[m.start("done") if m.groupdict().get("done") else m.start(): m.end()], "records": len(recs)}
            rec_acq = [r for r in recs if ACQ_TYPE.search(r["category"]) or (not MINOR_TYPE.search(r["category"] + " " + r["value"]) and ACQ_TYPE.search(r["value"]))]
            if rec_acq or fil["acq"]:                                               # a record or a filing sentence names the entity in an acquisition / merger / amalgamation
                ok = rec_acq[0] if rec_acq else None
                pend = ok and PENDING.search(ok["status"]) and not re.search(r"\bcompleted\b|\bconsummated\b", ok["status"], re.I)
                if done and ((pend and not fil["done"]) or (not ok and not fil["done"])):
                    f.update(status="UNSUPPORTED_COMPLETION", replacement=f"{ent} acquisition (completion not established{': ' + re.sub(' +', ' ', ok['status']).strip()[:80] if ok else ''})")
                else:
                    f.update(status="SUPPORTED_EVENT", replacement=None)
            elif recs or fil["minor"]:
                r = recs[0] if recs else {"category": "equity investment", "value": ent, "fy": fil["minor"]["fy"], "page": fil["minor"]["page"], "amount": ""}
                cat = r["category"] or "equity investment"
                full = _full_name(r, ent)
                where = ", ".join(x for x in (r["fy"].upper() if r["fy"] else "", f"p.{r['page']}" if r["page"] else "") if x)
                detail = f" ({where}{': ' + r['amount'] if r['amount'] else ''})" if where else ""
                f.update(status="UNSUPPORTED_EVENT_TYPE", replacement=f"{cat.lower()} in {full}{detail}", record_category=cat)
            else:
                f.update(status="UNSUPPORTED_EVENT_PREMISE", replacement=f"{ent} matter (its type and status are not established in the records)")
            found.append(f)
    return found


def apply_event_rewrites(L, text: str) -> tuple[str, list[dict]]:
    """Replace each unsupported event phrase by what the record supports; returns (new text, findings)."""
    out, findings = text, []
    for f in sorted(verify_events(L, text), key=lambda x: -x["span"][0]):
        findings.append(f)
        if f["status"] != "SUPPORTED_EVENT" and f["replacement"] and f["phrase"] in out:
            i = out.find(f["phrase"])
            rep = f["replacement"]
            if i == 0 or out[max(0, i - 2):i] in (". ", "; ", ": "):
                rep = rep[0].upper() + rep[1:]                                       # sentence start
            out = out[:i] + rep + out[i + len(f["phrase"]):]
    return out, findings


METRIC_WORDS = {"roce": "return on capital employed (ROCE)", "book_value_per_share": "book value per share", "interest_coverage": "interest coverage"}


def source_supplement(res: dict) -> str:
    """A verified claim also gives the investor the verified source figure it was checked against (identity already matched), in one clause."""
    for f in res.get("source_facts", []):
        if f["metric"] in METRIC_WORDS and f["values"]:
            unit = "%" if f["unit"] == "%" else (" times" if f["unit"] == "times" else "")
            return f"the {f['fy'].upper()} report states {METRIC_WORDS[f['metric']]} of {f['values'][0]:g}{unit} ({f['basis']}, p.{f['page']})"
        if f["metric"] in ("customer_concentration", "deposit_concentration"):
            return re.sub(r"\s+", " ", f["text"]).strip().rstrip(".")
    return ""


FALLBACK_MARK = "Checked so far:"


def fallback_sentence(fb: dict, label: str = "", short: bool = False) -> str:
    """One compact investor sentence. Internal states stay in the entry; none is printed here. The fixed lead-ins let the classifier recognise its own wording."""
    if short:
        return f"Not yet concluded: {fb['not_concluded']}"
    est = ", and ".join(fb["established"][:2])
    lead = f"{FALLBACK_MARK} {est}. " if est else ""
    return f"{lead}Not yet concluded: {fb['not_concluded']}, which matters because {fb['why_it_matters']}; {fb['would_resolve']} would help"
