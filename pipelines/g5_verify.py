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

VERIFIED requires, for EVERY component of the claim, all of:
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
def source_fact(company: str, fy: str, basis: str, metric: str, page: int, text: str, value: float | None, unit: str = "", subject: str = "") -> dict:
    return {"company": company, "fy": fy, "basis": basis, "metric": metric, "subject": subject, "page": page, "text": text[:240], "value": value, "unit": unit, "exact": True}


def record_fact(company: str, fy: str, metric: str, present: bool | None, record: str, detail: str, subject: str = "") -> dict:
    return {"company": company, "fy": fy, "metric": metric, "subject": subject, "present": present, "record": record, "detail": detail}


def _chunks(L) -> list[dict]:
    return G._chunks(L)


def _flat(c: dict) -> str:
    return " ".join(str(c.get("text", "")).split())


NUMBER = r"(?:₹|`|rs\.?\s*|inr\s*)?\s*(\d[\d,]*\.?\d*)"


def _scan(L, metric: str, label: str, lo: float, hi: float, unit: str, pct: bool | None = None, gap: int = 14) -> list[dict]:
    """Strict extractor: the metric's own label, then (within 14 non-digit characters, no sentence break) a number in a plausible range. pct=True requires a following '%',
    pct=False forbids one (a growth rate is not a per-share value). A number-before-label layout ('23% ROCE 32% Revenue'), a number that qualifies the next word (revenue, EBITDA,
    CAGR, YoY, growth) and a label with no adjacent number are skipped: those are leads, not facts."""
    out = []
    rx = rf"{label}(?:\s*\(?(?:%|times|x|₹|`|rs\.?|inr|per\s+share)\)?)?[^\d.;]{{0,{gap}}}(?:₹|`|rs\.?\s*|inr\s*)?\s*(\d[\d,]*\.?\d*)(\s*%)?(?!\s*(?:yoy|revenue|ebitda|cagr|growth|pat\b|ebit\b))"
    for c in _chunks(L):
        body = _flat(c)
        for m in re.finditer(rx, body, re.I):
            try:
                v = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if not lo <= v <= hi or not isinstance(c.get("page"), int):
                continue
            if pct is True and not m.group(2) or pct is False and m.group(2):
                continue
            raw = m.group(1).rstrip(",")
            v = float(raw.replace(",", ""))
            if metric == "contingent_liabilities" and not re.search(r"claims? against|not acknowledged|disputed|guarantee", body[m.start(): m.end() + 120], re.I):
                continue
            if metric == "contingent_liabilities" and ("," not in raw and "." not in raw and (v < 100 or 1900 <= v <= 2100)):      # a note number or a year is not an amount
                continue
            out.append(source_fact(L.key, L.fy, L.section_basis(c["page"]), metric, c["page"], body[max(0, m.start() - 40): m.end() + 60], v, unit))
            break
    return out


EXTRACTORS = {
    "book_value": lambda L: _scan(L, "book_value_per_share", r"book\s+value\s+per\s+(?:equity\s+)?share", 0.5, 100000, "INR per share", pct=False),
    "roce": lambda L: _scan(L, "roce", r"(?:return\s+on\s+capital\s+employed(?:\s*\(roce\))?|\broce\b)", 0.1, 400, "%", pct=True),
    "interest_coverage": lambda L: _scan(L, "interest_coverage", r"interest\s+(?:service\s+)?coverage(?:\s+ratio)?", 0.01, 100000, "times", pct=False),
    "contingent": lambda L: _scan(L, "contingent_liabilities", r"contingent\s+liabilit\w+", 1, 10 ** 9, "INR", gap=60),
}


def concentration_facts(L) -> list[dict]:
    """The parsed concentration note (G4 Ledger): typed, with page, basis and entity already attached."""
    f = L.facts.get("customer_conc")
    if not f:
        return []
    return [source_fact(L.key, f.fy or L.fy, f.basis, "customer_concentration" if not L.bank else "deposit_concentration", f.page, f.text, f.num, f.unit)]


EXTRACTORS["concentration"] = concentration_facts


# ───────────────────────────── destination-record probes (period-specific) ─────────────────────────────
TREND = {"book_value": ("per_share", "book_value_per_share"), "roce": ("return_on_capital", "roce"), "interest_coverage": ("debt_and_liquidity", "interest_coverage"),
         "contingent": ("balance_sheet_strength", "contingent_liabilities")}


def _trend_probe(L, topic: str) -> dict:
    g, m = TREND[topic]
    tr = (L.m("financials/financial_trends.json") or {}).get("trend_groups", {})
    ser = [x for x in (((tr.get(g) or {}).get(m) or {}).get("series") or []) if x.get("value") is not None]
    at_fy = [x for x in ser if str(x.get("year")).lower() == L.fy]
    other = [str(x.get("year")) for x in ser if str(x.get("year")).lower() != L.fy]
    return record_fact(L.key, L.fy, m, bool(at_fy), f"company_memory/financials/financial_trends.json:{g}.{m}", f"{L.fy.upper()}: {'value ' + str(at_fy[0]['value']) if at_fy else 'no value'}; other years with a value: {', '.join(other) or 'none'}")


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
    return record_fact(L.key, L.fy, "customer_concentration", bool(hits), "company_memory/company_model/company_model.json", f"fields named *concentration* with a value: {hits[:3] or 'none'}")


def _engines_probe(L) -> dict:
    cm = L.m("company_model/company_model.json") or {}
    ee = cm.get("economic_engines") or {}
    engines = ee.get("engines") or [] if ee.get("coverage_status") == "SUPPORTED" else []
    with_rev = [e.get("engine_name") for e in engines if any(h.get("revenue_share") is not None or h.get("revenue") is not None for h in (e.get("history") or []))]
    return record_fact(L.key, L.fy, "revenue_by_engine", bool(with_rev), "company_memory/company_model/company_model.json:economic_engines", f"coverage {ee.get('coverage_status')}; engines with revenue: {with_rev[:6] or 'none'}")


PART_KEYS = {"cost": r"cost|capex|invest|amount|spend", "output": r"output|capacity_added|throughput|units", "utilisation": r"utili[sz]ation", "returns": r"return|roi|incremental_revenue|payback"}


def _project_part_probe(L, part: str) -> dict:
    hits = []
    for rel in ("capacity/capacity_assessments.json", "projects/project_assessments.json", "projects/projects_registry.json", "capacity/capacity_registry.json"):
        d = L.m(rel)
        hits += [f"{rel}{p}" for p in _walk(d, lambda k, v, rx=PART_KEYS[part]: re.search(rx, k, re.I) and isinstance(v, (int, float)) and not isinstance(v, bool))]
    return record_fact(L.key, L.fy, f"project_{part}", bool(hits), "company_memory/{capacity,projects}/*.json", f"numeric fields for {part}: {hits[:3] or 'none'}")


PROBES = {"book_value": _trend_probe, "roce": _trend_probe, "interest_coverage": _trend_probe, "contingent": _trend_probe, "concentration": _concentration_probe, "revenue_split": _engines_probe}


def _wc_flag(L) -> str:
    return str((L.m("financials/investor_financial_modules/working_capital_quality_drilldown.json") or {}).get("working_capital_applicability") or "unknown")

# ───────────────────────────── compound claims: independent components ─────────────────────────────
PARTS = {
    "revenue_split": {"mix": r"split of revenue|revenue (?:mix|breakdown|split)|by product, segment or region|mix by segment", "margins": r"margins?"},
    "rd_spend": {"spend": r"spending|expense|expenditure|spend", "stages": r"pipeline stages?|stages", "outcomes": r"pipeline outcomes?|outcomes?"},
    "project_outcomes": {"cost": r"\bcosts?\b", "output": r"\boutputs?\b", "utilisation": r"utili[sz]ation|throughput", "returns": r"returns?|incremental revenue"},
    "management_incentives": {"pay": r"\bpay\b|remuneration", "esop": r"esop", "alignment": r"promoter alignment|alignment"},
    "capital_outcomes": {"output": r"\boutput\b", "margin": r"\bmargin\b", "cash": r"cash result|cash"},
    "competitive_position": {"share": r"market share", "pricing": r"pricing power", "peers": r"peers?"},
    "market_size": {"size": r"market size", "share": r"\bshare\b", "dynamics": r"industry dynamics|runway"},
}
SUBJECT_REQUIRED = {"risk_response", "transaction_amounts", "commitment_followthrough", "capital_outcomes", "project_outcomes", "management_depth"}
NA_TOTAL = {"working_capital": "the company's own working-capital module marks these measures not economically meaningful (banking schedule)",
            "bank_measure": "industrial borrowing, owner-earnings and working-capital measures are defined on operating cash flow before financing; a bank's operating cash flow includes loans and deposits",
            "interest_coverage": "interest coverage is defined on borrowing cost; a bank's cost of funds is its operating input, so the ratio is not a bank measure", "roce": "return on capital employed treats debt as capital; a bank's deposits are its stock in trade, so returns are judged on assets and equity"}

# investor-facing fallback pieces, per profile (what it matters for, what would settle it) - short on purpose
META = {
    "capex_split": ("whether the maintenance share of capex is disclosed", "owner earnings rest on how much spending only sustains the business", "a read of the cash-flow, asset and investment notes for any purpose split"),
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
def _assertion_level(clause: str) -> str:
    if re.search(r"not found after searching|sections searched", clause, re.I):
        return "SEARCH_FACT"
    cls, _ = G.classify(clause)
    if cls == G.INAPPLICABLE_MEASURE or re.search(r"\bdoes not apply\b|\bdo not apply\b", clause, re.I):
        return "NOT_APPLICABLE"
    return "RECORD_FACT" if cls == G.EXTRACTION_ABSENCE else "SOURCE_NEGATIVE"


def _named_fy(clause: str) -> list[str]:
    return [f"fy{x[-2:]}" for x in re.findall(r"FY\s?(\d{2,4})(?!\d)", clause)]


def _components(topic: str, clause: str) -> list[str]:
    parts = PARTS.get(topic) or {}
    hit = [k for k, rx in parts.items() if re.search(rx, clause, re.I)]
    return hit if len(hit) > 1 else ["whole"]


def verify_claim(L, clause: str, cls: str, context: str = "") -> dict:
    """The verdict for one genuine absence clause. Never raises a claim to VERIFIED on a topic mention; always returns machine reasons and an investor fallback."""
    topic = G.topic_of(clause) or (G.topic_of(context) if context else None)
    level = _assertion_level(clause)
    res: dict[str, Any] = {"claim": clause, "topic": topic, "level": level, "company": L.key, "fy": L.fy, "components": [], "reasons": [], "record_facts": [], "source_facts": [], "leads": []}
    if topic is None:
        res.update(verdict=VERDICT_UNSUPPORTED, acceptance=NEEDS_REVIEW, status="UNVERIFIED", reasons=["NO_EVIDENCE_PROFILE"], state=None, fallback=None, leads=G.generic_locators(L, clause))
        return res
    prof = G.PROFILES[topic]
    # 1. identity: a claim that names another fiscal year is not answered by this year's report
    other = [y for y in _named_fy(clause) if y != L.fy]
    if other and level != "SEARCH_FACT":
        res["reasons"].append("WRONG_OR_UNMATCHED_PERIOD:" + ",".join(other))
    # 2. subject-required claims must name their subject (deal, project, risk, commitment); the generic clause cannot be matched to one
    if topic in SUBJECT_REQUIRED and not _has_subject(L, clause, context):
        res["reasons"].append("SUBJECT_NOT_IDENTIFIED")
    # 3. applicability
    if level == "NOT_APPLICABLE":
        wc_ok = topic != "working_capital" or _wc_flag(L) == "not_economically_meaningful"
        if topic in NA_TOTAL and L.bank and wc_ok and not res["reasons"]:
            res.update(verdict=VERDICT_SUPPORTED, acceptance=ACCEPT, status="VERIFIED", state="NOT_APPLICABLE", basis=NA_TOTAL[topic], locator="", fallback=None)
        else:
            res["reasons"].append("INAPPLICABILITY_NOT_ESTABLISHED_IN_TOTAL")
            res.update(verdict=VERDICT_PARTIALLY, acceptance=NEEDS_REVIEW, status="UNVERIFIED", state=None)
        return _finish(L, res, topic, prof)
    # 4. components, each judged independently
    comps = _components(topic, clause)
    verdicts = []
    for c in comps:
        verdicts.append(_verify_component(L, topic, c, level, clause))
    res["components"] = verdicts
    res["source_facts"] = [f for v in verdicts for f in v["source_facts"]]
    res["record_facts"] = [f for v in verdicts for f in v["record_facts"]]
    res["reasons"] += [r for v in verdicts for r in v["reasons"] if r not in res["reasons"]]
    if any(v["verdict"] == VERDICT_CONTRADICTED for v in verdicts):
        res.update(verdict=VERDICT_CONTRADICTED, acceptance=REJECT, status="CONTRADICTED", state=None)
    elif all(v["verdict"] == VERDICT_SUPPORTED for v in verdicts) and not [r for r in res["reasons"] if r.startswith(("WRONG", "SUBJECT"))]:
        res.update(verdict=VERDICT_SUPPORTED, acceptance=ACCEPT, status="VERIFIED", state="NOT_EXTRACTED", basis="; ".join(v["basis"] for v in verdicts), locator="; ".join(f"p.{f['page']}" for f in res["source_facts"]))
    else:
        res.update(verdict=VERDICT_PARTIALLY if any(v["verdict"] == VERDICT_SUPPORTED for v in verdicts) else VERDICT_UNSUPPORTED, acceptance=NEEDS_REVIEW, status="UNVERIFIED", state=None)
    return _finish(L, res, topic, prof)


def _has_subject(L, clause: str, context: str) -> bool:
    """A subject is identified only if the sentence names a capitalised entity or an id that is not just the company or a generic noun."""
    text = f"{clause} {context}"
    names = re.findall(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b|\b(MC-\d+|RQ-[\w-]+)\b|\b([A-Z][a-z]+™)", text)
    generic = {normalize(L.name), "management", "the company"}
    return any(normalize(next(g for g in n if g)) not in generic for n in names)


def _verify_component(L, topic: str, part: str, level: str, clause: str) -> dict:
    v: dict[str, Any] = {"part": part, "topic": topic, "source_facts": [], "record_facts": [], "reasons": [], "basis": ""}
    ex = EXTRACTORS.get(topic)
    src = ex(L) if ex else []
    if topic == "project_outcomes" and part != "whole":
        rec = _project_part_probe(L, part)
    elif topic in PROBES:
        rec = PROBES[topic](L, topic) if topic in TREND else PROBES[topic](L)
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
    # RECORD_FACT: both legs
    if rec is None:
        v["reasons"].append("NO_DESTINATION_RECORD_PROBE")
    if not src:
        v["reasons"].append("NO_EXACT_SOURCE_FACT")
    if rec is not None and src:
        f = src[0]
        mismatch = [k for k, want in (("company", L.key), ("fy", L.fy)) if f[k] != want]
        if mismatch or (f["basis"] == "unknown" and topic not in ("concentration", "book_value", "roce", "interest_coverage")):      # company-level KPIs may be stated without a basis; the scope then records that
            v["reasons"].append("SOURCE_IDENTITY_MISMATCH:" + ",".join(mismatch or ["basis"]))
            v.update(verdict=VERDICT_PARTIALLY, basis="source fact identity incomplete")
            return v
        v.update(verdict=VERDICT_SUPPORTED, basis=f"source: {f['metric']} {f['value']} {f['unit']} ({f['fy'].upper()}, {f['basis']}, p.{f['page']}); record: {rec['detail']}")
        return v
    v.update(verdict=VERDICT_PARTIALLY if (rec is not None and not rec["present"]) else VERDICT_UNSUPPORTED, basis=(rec["detail"] if rec else "no probe"))
    return v


def _finish(L, res: dict, topic: str, prof: dict) -> dict:
    res["leads"] = sorted({f for f in (G.resolve(L, topic).get("filing_weak_pages") or [])})[:6]
    res["fallback"] = None if res["status"] == "VERIFIED" else fallback(L, res, topic, prof)
    return res


def _pp(pages: list[int]) -> str:
    return ("p." if len(pages) == 1 else "pp.") + ", ".join(map(str, pages))


def fallback(L, res: dict, topic: str, prof: dict) -> dict:
    """What is verified, what is not concluded, why it matters, what would settle it. Only verified facts go in `established`; leads are named as unread."""
    q, why, resolve = META.get(topic, (f"whether {prof['label'].lower()} is disclosed", "the answer depends on it", "a read of the relevant section"))
    est = []
    for rf in res["record_facts"]:
        if rf["present"] is False:
            est.append(f"the records hold no {rf['metric'].replace('_', ' ')} for {L.fy.upper()}")
        elif rf["present"]:
            est.append(f"the records already hold {rf['metric'].replace('_', ' ')} ({rf['detail']})")
    for sf in res["source_facts"]:
        est.append(f"the {L.fy.upper()} report states {sf['metric'].replace('_', ' ')} {sf['value']:g}{'%' if sf['unit'] == '%' else ''} ({sf['basis']}, p.{sf['page']})")
    if res["level"] == "SEARCH_FACT" or (not est and topic in G.PROFILES and G.resolve(L, topic)["state"] == "NOT_DISCLOSED_CANDIDATE"):
        r = G.resolve(L, topic)
        est.append(f"a search of {r.get('chunks_searched', 'the')} sections of the {L.fy.upper()} report found no {prof['label'].lower()}")
    if not est and res["leads"]:
        est.append(f"the {L.fy.upper()} report discusses {prof['label'].lower()} on {_pp(res['leads'])}, not yet read for figures")
    return {"established": est, "not_concluded": q, "why_it_matters": why, "would_resolve": resolve, "leads": res["leads"]}


def fallback_sentence(fb: dict, label: str) -> str:
    """One compact investor sentence. Internal states stay in the entry; none is printed here."""
    est = "; ".join(fb["established"][:2]) or "no verified fact is available yet"
    est = est[0].upper() + est[1:]
    return f"{est}. Not yet concluded: {fb['not_concluded']}, which matters because {fb['why_it_matters']}; {fb['would_resolve']} would settle it"
