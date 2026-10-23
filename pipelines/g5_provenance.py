#!/usr/bin/env python3
"""M63 / G5 — shared absence-provenance mechanism (zero AI calls, read-only).

Three parts, all company-independent:
  1. classify(clause)      -> one of six semantic classes, with the rule that decided it (nothing is dropped silently: every exclusion keeps its rule id)
  2. PROFILES + resolve()  -> for a disclosure topic, what the structured records hold, what the filing carries (strong = the term next to a figure; weak = a mention only),
                              and therefore the only states the evidence can support
  3. group_key()           -> claims with the same company, period, topic, assertion kind and record/source scope share one resolution

Rules the mechanism enforces:
  * NOT_EXTRACTED needs the filing to CARRY the disclosure (strong hit with a page locator) and the records to lack it
  * NOT_DISCLOSED is never concluded from a failed lexical search; the best the machine can say is NOT_DISCLOSED_CANDIDATE, which goes to the review queue
  * NOT_APPLICABLE comes from the business-model class (bank vs industrial) and names the reason
  * a record that actually holds the figure contradicts a "missing from the records" claim
  * a weak hit (the topic is mentioned, no figure beside it) cannot support either state; it goes to review with the page
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pipelines import g4_investor_answers as g4

DISCLOSURE_ABSENCE, EXTRACTION_ABSENCE, INAPPLICABLE_MEASURE = "DISCLOSURE_ABSENCE", "EXTRACTION_ABSENCE", "INAPPLICABLE_MEASURE"
ANALYTIC_UNCERTAINTY, EXPLANATORY, UI_OR_SYSTEM = "ANALYTIC_UNCERTAINTY", "EXPLANATORY", "UI_PLACEHOLDER_OR_SYSTEM_LIMITATION"
GENUINE = (DISCLOSURE_ABSENCE, EXTRACTION_ABSENCE, INAPPLICABLE_MEASURE)

# ───────────────────────────── 1. semantic classification ─────────────────────────────
UI_LABELS = {"missing data", "missing measurement", "missing disclosure", "untested assumption", "unknown", "not in the extracted records", "not extracted into the records", "not extracted", "not in the records"}
SYSTEM_RX = re.compile(r"\bprometheus\s+holds\s+no\b|\bno\s+(?:external\s+)?market\s+(?:price|data)\b|no market price, price history or valuation", re.I)
EXPLAIN_RX = re.compile(r"\bis\s+not\s+(?:evidence|a\s+finding|failure|a\s+clean\s+bill|counted\s+as|the\s+same\s+as)\b|\bnot\s+(?:evidence|a\s+finding)\s+(?:of|that)\b|\bnot\s+counted\s+as\s+failure\b|\bis\s+a\s+(?:gap|question)\s+(?:to\s+ask|for\s+management)\b"
                        r"|\bnot\s+failure\b|\bnot\s+a\s+finding\b|^\s*if\s+|\bhas\s+to\s+be\s+financed\b|\bnot\s+available\s+for\s+reinvestment\b|\bmay\s+(?:support|confirm)\b|\bdoes\s+not\s+(?:by\s+itself\s+)?(?:show|prove|mean)\b|\bshould\s+not\s+be\s+read\b|\bis\s+an\s+unexamined\b|\b(?:for|of|among)\s+(?:\w+\s+){1,3}with\s+no\s+(?:later|subsequent|further)\s+(?:disclosure|evidence)\b|\bmissing\s+disclosure\s+without\b|\bnot\s+that\s+none\s+exists\b|\bmeans\s+no\s+evidence\s+is\s+linked\b|\bdoes\s+not\s+mean\b", re.I)
ANALYTIC_RX = re.compile(r"\bwhat\s+it\s+returned\b|\bnot\s+shown\s+to\s+have\b|\bno\s+explanation\b|\blink\s+to\s+reported\b|\bmargin\s+stability\b|\bcannot\s+be\s+(?:assessed|judged|computed|tested|sized|built|called)\b|\bnot\s+comparable\b"
                         r"|\bpayoff\b|\bcreated\s+value\b|\bfinancial\s+(?:impact|outcomes?|returns?)\b|\boperating\s+returns?\b|\binitiative-level\b|\bis\s+proven\b|\bthe\s+cause\b|\bwhat\s+drove\b|\bdrove\b|\brealised\s+impact\b|\bnot\s+quantified\b|\bis\s+not\s+shown\b|\bnot\s+stated\s+(?:whether|how)\b|\bwhether\b|\bnot\s+scored\b|\bno\s+measurable\s+test\b|\boutcome\b|\bnot\s+reconciled\b|\bnot\s+(?:been\s+)?(?:established|proven)\b", re.I)
INAPPLICABLE_RX = re.compile(r"\b(?:do|does)\s+not\s+apply\b|\bnot\s+applicable\b|\bare\s+not\s+computed\s+for\s+a\s+bank\b|\bnot\s+economically\s+meaningful\b|\bnot\s+computed\s+for\s+a\s+bank\b", re.I)
RECORD_RX = re.compile(r"\brecords?\b|\brecorded\b|\blinked\b|\btracked\b|\bcaptured\b|\btimeline\b|\btracker\b|\bledger\b|\bstructured\b|\bregister\b|\b(?:in|from)\s+the\s+(?:extracted\s+|structured\s+|project\s+|capacity\s+|canonical\s+)?(?:records?|data)\b|\bextracted\b|\bnot\s+been\s+extracted\b|\bstructured\s+records\b|\bcanonical\s+data\b|\bavailable\s+data\b|\bproject\s+records\b|\bcapacity\s+records\b|\bthe\s+records\s+(?:hold|show|contain)\b|\brecords\s+(?:hold|show)\s+no\b", re.I)
SOURCE_NEG = re.compile(r"\b(?:annual report|report|filing|company|management|statements?|notes?|accounts|disclosures?)\s+(?:\w+\s+){0,2}(?:do|does|did|has|have|provide|provides|give|gives)\s+(?:not|no)\b|\bnot\s+(?:been\s+)?disclosed\b|\bno\s+(?:\w+\s+){0,3}disclosure\b|\bundisclosed\b|\bis\s+silent\b|\bnot\s+found\s+after\s+searching\b|\bnot\s+(?:stated|reported|given)\s+in\s+the\s+(?:annual report|filing|report)\b", re.I)
SELF_RX = re.compile(r"^\s*no\s+(?:margin\s+of\s+safety|rating|valuation|price\s+target|intrinsic\s+value)\s+(?:is|are)\s+(?:stated|given|estimated)\b|\bcalculated,?\s+not\s+(?:management-)?stated\b|\bcalculated\s+from\s+disclosed\b.*\bnot\s+stated\s+by\s+management|\bno\s+deadline\s+stated\b|\btimeframe\s*=\s*not\s+stated\b|\bno\s+explicit\s+revision\b", re.I)  # statements about how our own figure/label was formed, not about a disclosure
COVERAGE_RX = re.compile(r"\b(?:no\s+)?FY\s?\d{2,4}(?:-\d{2,4})?\s+(?:or\s+FY\s?\d{2,4}\s+)?(?:report|data)\b[^.]{0,30}\b(?:not\s+in|no)\b|\bnot\s+in\s+the\s+records\b.*\bFY|\bthe\s+FY\s?\d{2,4}\s+(?:annual\s+)?report\s+is\s+not\s+in\s+the\s+records\b|\(no\s+FY\s?\d{2,4}(?:\s+or\s+FY\s?\d{2,4})?\s+data\)|\bsource\s+years\s+covered\b", re.I)  # which reports the system holds
ATTRIB_RX = re.compile(r"\b(?:link|connection|relationship)\s+(?:to|between|with)\s+(?:the\s+)?(?:reported|financial|economic|business)\b|\bcause\s+of\b|\bwhat\s+drove\b|\bdrove\b", re.I)  # causal / attribution links are analytic even when worded "not disclosed"
NEG_RX = re.compile(r"\b(?:not|no|nor|never|lacks?|missing|unavailable|without|cannot)\b|n't\b", re.I)


def split_clauses(sentence: str) -> list[str]:
    """Clauses of one sentence. A comma splits only where both sides carry a negation, so a genuine claim cannot hide behind an explanatory one."""
    s = " ".join(str(sentence).split())
    if "Checked so far:" in s or "Not yet concluded:" in s:      # the gate's own fallback wording is one unit
        return [s.strip(" .")]
    out: list[str] = []
    for part in re.split(r";\s+|,\s+so\s+|,\s+but\s+", s):
        bits = re.split(r",\s+(?:and\s+)?(?!not\b|nor\b)(?=[^,]*\b(?:not|no)\b)", part)
        if len(bits) > 1 and all(NEG_RX.search(b) for b in bits):
            out += bits
        else:
            out.append(part)
    return [c.strip(" .") for c in out if c.strip(" .")]


def classify(clause: str) -> tuple[str | None, str]:
    """(class, rule id). None = the clause asserts no absence at all. A clause is judged genuine unless a rule names why it is not."""
    c = " ".join(re.sub(r"“[^”]*”", " ", str(clause)).split())
    if not c or not NEG_RX.search(c) and c.lower() not in UI_LABELS:
        return None, "no-negation"
    if "Checked so far:" in c or "Not yet concluded:" in c:
        return EXPLANATORY, "g5-fallback-wording"
    if c.endswith("?"):
        return UI_OR_SYSTEM, "ui-question"
    if COVERAGE_RX.search(c):
        return UI_OR_SYSTEM, "system-coverage"
    if SELF_RX.search(c):
        return EXPLANATORY, "own-label-or-method"
    if c.lower().rstrip(".") in UI_LABELS:
        return UI_OR_SYSTEM, "ui-label"
    if SYSTEM_RX.search(c):
        return UI_OR_SYSTEM, "system-limitation"
    if INAPPLICABLE_RX.search(c):
        return INAPPLICABLE_MEASURE, "inapplicable"
    if EXPLAIN_RX.search(c):
        return EXPLANATORY, "explanatory"
    if ATTRIB_RX.search(c):
        return ANALYTIC_UNCERTAINTY, "analytic-attribution"
    kind = g4.claim_kind(c)
    if kind == "disclosure_absence" or re.search(r"\bnot\s+(?:yet\s+|separately\s+|all\s+|been\s+|fully\s+)?(?:disclosed|given|stated|reported|provided|extracted|recorded|linked)\b|\bno\s+(?:\w+\s+){1,3}(?:is|are|was|were)\s+(?:reported|stated|given|recorded|disclosed|linked)\b|\b(?:records?|register)\s+(?:hold|holds|show|shows)\s+no\b|\bnot\s+in\s+the\b", c, re.I):
        if ANALYTIC_RX.search(c) and not re.search(r"\bnot\s+(?:given|disclosed|extracted|in the)\b|\bhold\s+no\b|\bnot\s+been\s+extracted\b", c, re.I):
            return ANALYTIC_UNCERTAINTY, "analytic-outcome"
        source_neg = bool(SOURCE_NEG.search(c))
        if RECORD_RX.search(c) and not source_neg:
            return EXTRACTION_ABSENCE, "record-level"
        return DISCLOSURE_ABSENCE, "source-level"
    if ANALYTIC_RX.search(c):
        return ANALYTIC_UNCERTAINTY, "analytic"
    if kind == "method":
        return EXPLANATORY, "method"
    return None, "no-absence-structure"


# ───────────────────────────── 2. topic profiles and evidence ─────────────────────────────
def P(label, claim, anchors, strong, rec=None, applies="both", record_files=(), note=""):
    return dict(label=label, claim=re.compile(claim, re.I), anchors=tuple(anchors), strong=tuple(re.compile(s, re.I) for s in strong), rec=rec, applies=applies, record_files=record_files, note=note)


NUM = r"[^.]{0,90}?\d[\d,.]*"          # a figure within the same sentence
PROFILES: dict[str, dict] = {
    "interest_coverage": P("Interest coverage", r"interest\s+coverage", [r"interest\s+coverage", r"times\s+interest\s+earned", r"\bicr\b"], [rf"interest\s+coverage(?:\s+ratio)?{NUM}", rf"times\s+interest\s+earned{NUM}"], rec=("debt_and_liquidity", "interest_coverage"), applies="industrial"),
    "roce": P("Return on capital employed", r"\broce\b|return\s+on\s+capital\s+employed", [r"\broce\b", r"return\s+on\s+capital\s+employed"], [rf"\broce\b{NUM}", rf"return\s+on\s+capital\s+employed{NUM}"], rec=("return_on_capital", "roce"), applies="industrial"),
    "book_value": P("Book value per share", r"book\s+value", [r"book\s+value\s+per\s+share", r"net\s+asset\s+value\s+per\s+share", r"\bbvps\b"], [rf"book\s+value\s+per\s+(?:equity\s+)?share{NUM}", rf"net\s+asset\s+value\s+per\s+share{NUM}"], rec=("per_share", "book_value_per_share")),
    "capex_split": P("Maintenance versus growth capex split", r"maintenance[- ](?:versus|vs|and|or)?[- ]*growth|maintenance\s+capex|capex\s+split|capital\s+spending\s+split|split\s+(?:between|of)\s+maintenance", list(g4.CAPEX_SPLIT_PATTERNS),
                     [rf"maintenance\s+(?:capex|capital\s+expenditure){NUM}", rf"growth\s+(?:capex|capital\s+expenditure){NUM}", rf"expansion\s+capex{NUM}"], applies="industrial"),
    "revenue_split": P("Revenue by product, segment or region", r"revenue\s+(?:breakdown|mix|by\s+(?:source|product|segment|region)|split)|mix\s+by\s+segment|segment\s+or\s+geography|split\s+of\s+revenue|margins\s+by\s+revenue\s+source|product,\s+segment\s+or\s+region|revenue\s+is\s+not\s+broken|between\s+sources",
                       [r"segment", r"geograph", r"revenue\s+by\s+(?:region|geography|market|segment|product)"], [rf"segment\s+(?:revenue|results?){NUM}", rf"revenue\s+by\s+(?:geography|region|segment|product|market){NUM}", rf"segment\s+(?:information|reporting|assets|liabilities){NUM}"], rec=("__model__", "engines")),
    "project_outcomes": P("Project utilisation, output and returns", r"utili[sz]ation|throughput|incremental\s+revenue|site-level\s+revenue|project\s+records|capacity\s+records|output\s+and\s+returns|cost,\s+output", [r"capacity\s+utili[sz]ation", r"utili[sz]ation", r"throughput", r"incremental\s+revenue"], [rf"capacity\s+utili[sz]ation{NUM}", rf"utili[sz]ation{NUM}%", rf"throughput{NUM}"], record_files=("capacity/capacity_assessments.json", "projects/project_assessments.json")),
    "competitive_position": P("Competitive position (share, pricing power vs peers)", r"moat|competitive\s+position|market\s+share|pricing\s+power|peer|competition|competitive\s+threats", [r"market\s+share", r"pricing\s+power", r"competitive\s+position", r"switching\s+cost"], [rf"market\s+share{NUM}%", rf"(?:our|the company.s)\s+market\s+share{NUM}"]),
    "market_size": P("Market size and industry dynamics", r"market\s+size|industry\s+dynamics|growth\s+runway|total\s+addressable", [r"market\s+size", r"industry\s+size", r"addressable\s+market", r"industry\s+(?:growth|outlook)"], [rf"(?:market|industry)\s+size{NUM}", rf"addressable\s+market{NUM}", rf"industry\s+(?:is\s+)?(?:expected|projected|estimated)\s+to\s+grow{NUM}"]),
    "management_incentives": P("Management incentives (pay, ESOP, promoter alignment)", r"incentives?\b|esop|remuneration|promoter\s+alignment|pay\b", [r"remuneration", r"\besops?\b", r"stock\s+option", r"managerial\s+personnel"], [rf"remuneration{NUM}", rf"\besops?\b{NUM}", rf"stock\s+options?{NUM}"]),
    "rd_spend": P("R&D spending and pipeline", r"research\s+and\s+development|r&d|pipeline\s+(?:stages|outcomes)", [r"research\s+and\s+development", r"r\s*&\s*d\b"], [rf"research\s+and\s+development(?:\s+(?:expense|expenditure|spend))?{NUM}", rf"r\s*&\s*d\s+(?:expense|expenditure|spend)\w*{NUM}"], applies="industrial"),
    "contingent": P("Contingent liabilities", r"contingent\s+liabilit", [r"contingent\s+liabilit"], [rf"contingent\s+liabilit\w+{NUM}"], rec=("balance_sheet_strength", "contingent_liabilities")),
    "peer_comparison": P("Peer comparison", r"peer|competitor", [r"peer", r"competitor"], [rf"peer\s+(?:group|comparison){NUM}"]),
    "commitment_followthrough": P("Follow-through reporting against prior commitments", r"follow-through|register\s+has\s+not\s+linked|progression\s+tracker|evidence\s+is\s+(?:not\s+)?linked|against\s+prior-year\s+commitments|later\s+evidence|confirm\s+or\s+contradict|no\s+later\s+disclosure|score-target|confirmation|fulfilment|approval\s+is\s+not|no\s+evidence\s+either\s+way|nor\s+evidence\s+of\s+non-delivery", [r"progress\s+(?:against|towards|on)", r"against\s+(?:our\s+)?(?:targets?|commitments?)", r"status\s+of\s+(?:our\s+)?(?:targets?|commitments?)"], [rf"progress\s+(?:against|towards)\s+(?:our\s+)?(?:targets?|commitments?|goals?){NUM}", rf"against\s+(?:our\s+)?(?:targets?|commitments?)[^.]{{0,60}}(?:achieved|met|completed|%)"], note="per-commitment: needs a per-commitment later-filing check"),
    "transaction_amounts": P("Consideration for completed transactions", r"^amount:|amounts?\s+(?:are\s+)?not\s+in\s+the\s+extracted|completed\s+transactions?\s+are\s+recorded|consideration", [r"\bconsideration\b", r"purchase\s+price"], [rf"(?:aggregate\s+|total\s+)?consideration{NUM}", rf"purchase\s+price{NUM}"]),
    "working_capital": P("Working-capital and cash-conversion measures", r"working[- ]capital|cash[- ]conversion|free[- ]cash[- ]flow measures|receivable days", [r"working\s+capital"], []),
    "bank_measure": P("Industrial borrowing and owner-earnings measures", r"borrowing ratios|owner[- ]earnings|debt-to-equity", [r"owner\s+earnings"], []),
    "risk_response": P("Management response to a recorded risk", r"management\s+response|response\s+is\s+(?:recorded|linked)|no\s+response\s+is\s+recorded|response\s+is\s+linked", [r"mitigation", r"risk\s+mitigat"], [rf"mitigation\s+(?:plan|measures?|strateg\w+|:){NUM}?", r"risk\s+mitigation\s+(?:plan|measures?|strateg)"], note="per-risk: the filing's mitigation column must be matched to each recorded risk"),
    "management_depth": P("Management depth, succession and organisation quality", r"management\s+depth|succession|quality\s+of\s+its\s+sales", [r"succession", r"key\s+managerial\s+personnel", r"senior\s+management"], [rf"succession\s+plan\w*{NUM}?", r"key\s+managerial\s+personnel\s+(?:are|include|comprise)"]),
    "segment_margins": P("Product-level or segment margins", r"product-level|segment\s+margins|margins\s+by", [r"segment\s+(?:profit|margin|result)", r"segment\s+results?"], [rf"segment\s+(?:profit|results?|margin)s?{NUM}"]),
    "capital_outcomes": P("Returns on specific capital allocations", r"capital\s+deployed|capital\s+allocation\s+lacks|operating\s+outcomes|capital\s+is\s+recorded\s+under|no\s+capital\s+is\s+recorded|capital\s+deployments?\s+lack|returns\s+on\s+(?:acquisitions|capex)|financial\s+returns|operating\s+returns?|acquisition\s+outcomes?|initiative-level", [r"return\s+on\s+(?:capital|investment)", r"\broic\b", r"payback"], [rf"\broic\b{NUM}", rf"return\s+on\s+(?:invested\s+)?capital{NUM}"]),
}
# topics that already have an anchor family in g4 (concentration, transactions, guidance, order book, credit cost) reuse it
for t, label, claim in (("concentration", "Customer / depositor concentration", r"concentration|customer"), ("transactions", "Transaction status", r"transaction\s+status|transactions?\s+mentioned|completed\s+and\s+pending|pending[- ]transaction|completed\s+(?:deal|transaction)|completion\s+status|transactions?\s+and\s+their"),
                        ("guidance", "Management guidance", r"guidance"),
                        ("order_book", "Order book", r"order\s+book|backlog"), ("credit_cost", "Credit cost", r"credit\s+cost")):
    PROFILES[t] = P(label, claim, g4.ANCHORS[t], [])
    PROFILES[t]["g4_family"] = True
PROFILES["segment_mix"] = PROFILES["revenue_split"]


def topic_of(text: str) -> str | None:
    for tid, p in PROFILES.items():
        if p["claim"].search(text):
            return tid
    return None


def _chunks(L: "g4.Ledger", fy: str | None = None) -> list[dict]:
    d = L.j(L.cdir / (fy or L.fy) / "extracted" / "clean_chunks.json") or []
    return d if isinstance(d, list) else d.get("chunks", [])


def _record_has(L: "g4.Ledger", p: dict) -> tuple[bool | None, str]:
    """Do the structured records hold the figure? True / False / None (no probe defined)."""
    if p.get("record_files"):
        found = []

        def numeric_under(o, depth=0):
            if isinstance(o, dict):
                return any((re.search(r"utili[sz]ation|throughput|incremental_revenue", str(k), re.I) and isinstance(v, (int, float)) and not isinstance(v, bool)) or numeric_under(v, depth + 1) for k, v in o.items())
            return any(numeric_under(v, depth + 1) for v in o) if isinstance(o, list) else False
        for rel in p["record_files"]:
            if numeric_under(L.m(rel)):
                found.append(rel)
        return (bool(found), f"capacity/project records: {', '.join(found) or 'no utilisation, throughput or incremental-revenue figure'}")
    if not p.get("rec"):
        return None, "no record probe defined"
    group, metric = p["rec"]
    if group == "__model__":
        return None, "company-model engines are checked by the surface builder at render time"
    tr = (L.m("financials/financial_trends.json") or {}).get("trend_groups", {})
    ser = [x for x in (((tr.get(group) or {}).get(metric) or {}).get("series") or []) if x.get("value") is not None]
    return bool(ser), f"financial_trends.{group}.{metric}: {len(ser)} year(s) with a value ({', '.join(str(x.get('year')) for x in ser[:6]) or 'none'})"


def generic_locators(L: "g4.Ledger", phrase: str, limit: int = 4) -> list[int]:
    """Pages whose text carries most of a claim's content words (a reviewer aid, never evidence)."""
    words = [w for w in re.findall(r"[a-z]{5,}", phrase.lower()) if w not in {"records", "extracted", "structured", "disclosed", "cannot", "which", "there", "their", "these", "those", "other", "given", "stated", "shown", "reported"}]
    if len(words) < 2:
        return []
    scored = []
    for c in _chunks(L):
        t = str(c.get("text", "")).lower()
        n = sum(w in t for w in words)
        if n >= max(2, int(len(words) * 0.6)) and isinstance(c.get("page"), int):
            scored.append((-n, c["page"]))
    return [p for _, p in sorted(scored)[:limit]]


def _pp(pages: list[int]) -> str:
    return ("p." if len(pages) == 1 else "pp.") + ", ".join(map(str, pages))


def resolve(L: "g4.Ledger", topic: str) -> dict:
    """The evidence-supported state for one (company, topic). Cached on the ledger."""
    key = f"g5res:{topic}"
    if key in L._c:
        return L._c[key]
    p = PROFILES[topic]
    out: dict[str, Any] = {"company": L.key, "fy": L.fy, "topic": topic, "label": p["label"], "scope": "records and the latest annual report (standalone/consolidated as the report states)"}
    if p["applies"] == "industrial" and L.bank:
        out.update(state="NOT_APPLICABLE", verified=True, basis="business-model class: bank — the measure is defined for industrial companies and does not describe a bank", locator="", contradicts=False, uncertainty="")
    else:
        rec, rec_basis = _record_has(L, p)
        chunks = _chunks(L)
        weak = [c["page"] for c in chunks if isinstance(c.get("page"), int) and any(re.search(a, " ".join(str(c.get("text", "")).split()).lower()) for a in p["anchors"])]
        strong = []
        if p.get("g4_family"):
            hits = g4.anchor_hits(L, topic)
            strong = hits["example_pages"] if hits["chunks_matching"] else []
            if topic == "concentration" and g4.find_disclosure(L, g4.BANK_CONC if L.bank else g4.CUSTOMER_CONC):
                strong = strong or [g4.find_disclosure(L, g4.BANK_CONC if L.bank else g4.CUSTOMER_CONC)["page"]]
            if topic == "transactions" and g4.transaction_status(L)["completed"]:
                strong = sorted({c["page"] for c in g4.transaction_status(L)["completed"]})
        else:
            for c in chunks:
                t = " ".join(str(c.get("text", "")).split()).lower()
                if isinstance(c.get("page"), int) and any(s.search(t) for s in p["strong"]):
                    strong.append(c["page"])
        strong, weak = sorted(set(strong))[:6], sorted(set(weak))[:6]
        out.update(record_basis=rec_basis, filing_strong_pages=strong, filing_weak_pages=weak, chunks_searched=len(chunks))
        if rec:
            out.update(state="CONTRADICTED_BY_RECORDS", verified=True, basis=rec_basis, locator="", contradicts=True, uncertainty="the records hold the figure; a 'missing from the records' claim is false")
        elif strong:
            out.update(state="NOT_EXTRACTED", verified=True, basis=f"the filing carries it beside a figure; the structured records do not ({rec_basis})", locator=_pp(strong), contradicts=False,
                       uncertainty="strong hit is lexical (term beside a figure); it shows the filing carries wording on the topic, not that every sub-element (period, entity) is disclosed")
        elif weak:
            out.update(state="REVIEW", verified=False, basis="the topic is mentioned in the filing but no figure sits beside it; a lexical match cannot decide carried-versus-not", locator=_pp(weak), contradicts=False, uncertainty="mention only")
        else:
            out.update(state="NOT_DISCLOSED_CANDIDATE", verified=False, basis=f"{len(chunks)} sections searched with the topic's anchor family; no match", locator="", contradicts=False,
                       uncertainty="a failed lexical search does not prove the filing is silent (tables, images, different wording); human confirmation required before NOT_DISCLOSED")
    L._c[key] = out
    return out


def system_limitation_ok(root: Path) -> tuple[bool, str]:
    """'Prometheus holds no market data' is a statement about system inputs: verified by looking for any price / valuation input in the company data."""
    hits = [str(p.relative_to(root)) for p in (root / "companies").glob("*/company_memory/**/*") if p.is_file() and re.search(r"market_?data|price_?history|stock_?price|valuation_?estimate|share_?price", p.name, re.I)]
    return (not hits), ("no file named for market data, price history, share price or a valuation estimate exists under companies/*/company_memory" if not hits else f"found: {hits[:3]}")


def group_key(company: str, fy: str, topic: str, cls: str, scope: str) -> str:
    return "|".join((company, fy, topic or "unprofiled", cls, scope))


# ───────────────────────────── 4. claim ledger: entries, rewrites, review queue ─────────────────────────────
STOP = {"records", "record", "extracted", "reported", "stated", "given", "disclosed", "related", "measure", "itself", "separate", "report", "filing", "figure", "still", "which", "their", "there", "these", "those", "would", "could", "other", "linked", "shown", "found", "available"}


def content_key(clause: str) -> str:
    words = sorted({w for w in re.findall(r"[a-z]{5,}", re.sub(r"[™]", "", clause.lower())) if w not in STOP})
    return "+".join(words[:3]) or "x"


def review_id(company: str, topic: str | None, clause: str) -> str:
    import hashlib
    return f"RQ-{company}-{topic or 'kpi-' + hashlib.sha1(content_key(clause).encode()).hexdigest()[:6]}"


REWRITE_NOT_EXTRACTED = "{label} is not extracted into the records; the annual report carries related disclosure ({locator})"
SUBJECT_RX = re.compile(r"^(?P<s>.{6,170}?)\s+(?P<aux>is|are)\s+not\s+(?:disclosed|stated|reported|given|provided|available|shown)\b", re.I)


def rewrite_for(clause: str, label: str, locator: str) -> str:
    """Keep the claim's own subject; change only what the evidence contradicts (that the filing does not carry it)."""
    m = SUBJECT_RX.match(clause)
    subj, aux = (m.group("s"), m.group("aux")) if m else (label, "is")
    return f"{subj} {aux} not extracted into the records; the annual report carries related disclosure ({locator})"


def judge(L: "g4.Ledger", clause: str, cls: str, context: str = "") -> dict:
    """The provenance verdict for one genuine absence clause, from the evidence gate (pipelines/g5_verify): state, whether it is VERIFIED, the investor replacement when the wording
    claims more than the evidence supports, the fallback parts, and the review item if a person must decide."""
    from pipelines import g5_verify as V
    v = V.verify_claim(L, clause, cls, context)
    topic = v["topic"]
    out: dict[str, Any] = {"claim": clause, "class": cls, "topic": topic, "company": L.key, "fy": L.fy, "verification": v, "fallback": v.get("fallback"), "reasons": v["reasons"], "rewrite": None, "review": None,
                           "basis": v.get("basis", "; ".join(v["reasons"])), "locator": v.get("locator", ""), "level": v["level"], "record_statement_ok": v.get("record_statement_ok", False)}
    if topic:
        out["evidence_group"] = group_key(L.key, L.fy, topic, cls, "record" if cls == EXTRACTION_ABSENCE else "source")
    st = v["status"]
    if st == "VERIFIED":
        out.update(state=v["state"], verified=True, status="VERIFIED_NOT_EXTRACTED" if v["state"] == "NOT_EXTRACTED" else "VERIFIED_NOT_APPLICABLE", supplement=V.source_supplement(v))
        return out
    # the one customer rule: a statement that is not VERIFIED, and is not a record fact the destination probe confirmed, is replaced by what is established
    needs_replacement = not out["record_statement_ok"]
    fb = v.get("fallback")
    text = V.fallback_sentence(fb) if (fb and needs_replacement) else None
    if st == "CONTRADICTED":
        out.update(state=None, verified=False, status="CONTRADICTED", rewrite=text)
        return out
    out.update(verified=False, review=review_id(L.key, topic, clause))
    if not topic:
        out.update(state=None, status="UNRESOLVED_UNPROFILED", locators_hint=v.get("leads"), rewrite=text)
    elif v["level"] == "SEARCH_FACT" or (v["level"] == "SOURCE_NEGATIVE" and resolve(L, topic)["state"] == "NOT_DISCLOSED_CANDIDATE"):
        out.update(state="NOT_DISCLOSED", status="UNRESOLVED_NOT_DISCLOSED_CANDIDATE", rewrite=text)
    else:
        out.update(state=None, status="UNRESOLVED_REVIEW", rewrite=text)
    out["record_verified"] = bool(v["record_facts"]) and all(r["present"] is False for r in v["record_facts"])
    return out


def audit_text(L: "g4.Ledger", fields: list[tuple[str, str]], entries: list[dict] | None) -> dict:
    """Full-scope check of one answer or surface: every genuine clause must have a claim-linked entry whose state equals the evidence-supported state."""
    problems = {"untagged": [], "state_mismatch": [], "contradicted": [], "unresolved": []}
    linked = 0
    for loc, text in fields:
        for sent in re.split(r"(?<=[.;])\s+(?=[A-Z“\d])", " ".join(str(text).split())):
            for clause in split_clauses(sent):
                cls, _ = classify(clause)
                if cls not in GENUINE:
                    continue
                j = judge(L, clause, cls, sent)
                e = next((x for x in (entries or []) if x.get("claim") and (x["claim"] in clause or clause in x["claim"])), None)
                if e is None:
                    problems["untagged"].append(clause[:120])
                    continue
                linked += 1
                if j["status"] in ("CONTRADICTED", "WRONG_NOT_APPLICABLE_CLAIM"):
                    problems["contradicted"].append(clause[:120])
                elif j["status"].startswith("UNRESOLVED"):
                    problems["unresolved"].append(clause[:120])
                elif e.get("state") != j["state"]:
                    problems["state_mismatch"].append(clause[:120])
    return {**problems, "linked": linked}


FIELDS = ("simple_answer", "what_may_mean_economically", "what_is_not_yet_proven", "why_it_matters", "investor_interpretation", "what_evidence_shows", "what_to_monitor", "key_points", "evidence_gaps")


def _text_fields(a: dict):
    """(field, index or None, text) for every investor-facing string of an answer."""
    for f in FIELDS:
        v = a.get(f)
        if isinstance(v, list):
            for i, s in enumerate(v):
                if isinstance(s, str) and s:
                    yield f, i, s
        elif isinstance(v, str) and v:
            yield f, None, v


def annotate_answer(L: "g4.Ledger", a: dict, compact: bool = False) -> tuple[dict, dict]:
    """Return (annotated copy, report). A clause whose wording claims more than the evidence supports (contradicted, or a source-level negative / inapplicability that is not
    VERIFIED) is replaced by the evidence gate's investor fallback; a record-level statement the gate cannot verify is kept as written. Claim-linked `g5_absence` entries carry the
    state and `verification`; everything that is not VERIFIED is listed in `g5_review_pending` with its machine reasons. Everything else is left byte-identical."""
    import copy
    from pipelines import g5_verify as V
    b = copy.deepcopy(a)
    changes: list[dict] = []
    seen_topic: set[str] = set()
    generated: list[tuple[str, dict]] = []
    event_checks: list[dict] = []
    def walk_events(o, path):                                   # positive claims first, in EVERY investor-visible string (claims, relationships, key points…): an acquisition / completion the records do not support is restated as the record describes it
        if isinstance(o, str):
            t2, evs = V.apply_event_rewrites(L, o)
            event_checks.extend({**e, "field": path} for e in evs)
            if t2 != o:
                changes.append({"field": path, "before": o, "after": t2, "reason": "UNSUPPORTED_EVENT", "topic": "event", "reasons": [e["status"] for e in evs if e["status"] != "SUPPORTED_EVENT"], "locator": ""})
            return t2
        if isinstance(o, list):
            return [walk_events(x, f"{path}[{i}]") for i, x in enumerate(o)]
        if isinstance(o, dict):
            return {k: (v if re.match(r"^g[45]\d*_", k) else walk_events(v, f"{path}.{k}")) for k, v in o.items()}
        return o
    b = walk_events(b, "")
    for f, i, t in list(_text_fields(b)):
        new = t
        for sent in re.split(r"(?<=[.;])\s+(?=[A-Z“\d])", " ".join(t.split())):
            for clause in split_clauses(sent):
                cls, _ = classify(clause)
                if cls in GENUINE:
                    j = judge(L, clause, cls, sent)
                    if j.get("supplement") and clause in new and j["supplement"] not in new:
                        new = new.replace(clause, clause + "; " + j["supplement"], 1)
                        changes.append({"field": f if i is None else f"{f}[{i}]", "before": clause, "after": clause + "; " + j["supplement"], "reason": "VERIFIED_SUPPLEMENT", "topic": j["topic"], "reasons": [], "locator": j.get("locator", "")})
                    if j.get("rewrite") and clause in new:
                        short = compact or (j["topic"] or clause) in seen_topic
                        text = V.fallback_sentence(j["fallback"], short=short)
                        seen_topic.add(j["topic"] or clause)
                        head = ""
                        hm = re.match(r"^(.{20,}?)\s+(?:because|since)\s+", clause)       # keep the method statement that preceded the unsupported reason
                        if hm:
                            head = hm.group(1).rstrip(" ,;") + ". "
                        core = clause.rstrip(")] ")
                        tail = clause[len(core):].strip()                       # keep the closing bracket of an aside so the sentence stays balanced
                        new = re.sub(re.escape(clause) + r"(?:,\s+so\b[^.;]*)?", lambda _m: head + text + tail, new, count=1)      # and drop a consequence ("…, so X cannot be assessed") that rested on the unsupported premise
                        generated.append((text, j))
                        changes.append({"field": f if i is None else f"{f}[{i}]", "before": clause, "after": head + text, "reason": j["status"], "topic": j["topic"], "reasons": j["reasons"], "locator": j.get("locator", "")})
        if new != t:
            if i is None:
                b[f] = new
            else:
                b[f][i] = new
    for di, dd in enumerate(b.get("deterministic_precision_facts") or []):          # the precision facts' meanings are investor text too
        mean = dd.get("semantic_meaning") if isinstance(dd, dict) else None
        if not mean:
            continue
        newm = mean
        for sent in re.split(r"(?<=[.;])\s+(?=[A-Z“\d])", " ".join(str(mean).split())):
            for clause in split_clauses(sent):
                cls, _ = classify(clause)
                if cls in GENUINE:
                    j = judge(L, clause, cls, sent)
                    if j.get("rewrite") and clause in newm:
                        text = V.fallback_sentence(j["fallback"], short=True if (compact or (j["topic"] or clause) in seen_topic) else False)
                        seen_topic.add(j["topic"] or clause)
                        newm = newm.replace(clause, text, 1)
                        generated.append((text, j))
                        changes.append({"field": f"deterministic_precision_facts[{di}].semantic_meaning", "before": clause, "after": text, "reason": j["status"], "topic": j["topic"], "reasons": j["reasons"], "locator": ""})
        if newm != mean:
            dd["semantic_meaning"] = newm
    entries, pending, system = [], [], []
    seen: set[str] = set()
    dpf_texts = [("deterministic_precision_facts", i, str(d.get("semantic_meaning"))) for i, d in enumerate(b.get("deterministic_precision_facts") or []) if isinstance(d, dict) and d.get("semantic_meaning")]
    for f, i, t in list(_text_fields(b)) + dpf_texts:
        for sent in re.split(r"(?<=[.;])\s+(?=[A-Z“\d])", " ".join(t.split())):
            for clause in split_clauses(sent):
                cls, rule = classify(clause)
                where = f if i is None else f"{f}[{i}]"
                if cls == UI_OR_SYSTEM and rule in ("system-limitation", "system-coverage"):
                    system.append({"claim": clause, "field": where, "rule": rule})
                    continue
                if cls not in GENUINE or clause in seen:
                    continue
                seen.add(clause)
                j = judge(L, clause, cls, sent)
                base = {"claim": clause, "field": where, "topic": j["topic"] or "other", "basis": j["basis"], "locator": j.get("locator", ""), "evidence_group": j.get("evidence_group", ""), "review": j.get("review"),
                        "reasons": j["reasons"], "record_verified": j.get("record_verified", False), "record_statement_ok": j.get("record_statement_ok", False)}
                if j["status"] in ("VERIFIED_NOT_EXTRACTED", "VERIFIED_NOT_APPLICABLE"):
                    entries.append({**base, "state": j["state"], "verification": "VERIFIED"})
                elif j["status"] == "UNRESOLVED_NOT_DISCLOSED_CANDIDATE":
                    entries.append({**base, "state": "NOT_DISCLOSED", "verification": "PENDING_HUMAN_CONFIRMATION"})
                    pending.append({"review": j["review"], "claim": clause, "field": where, "status": j["status"], "reasons": j["reasons"]})
                else:
                    pending.append({"review": j["review"], "claim": clause, "field": where, "status": j["status"], "reasons": j["reasons"], "record_verified": base["record_verified"]})
    scoped = [{"claim": text, "topic": j["topic"], "state": None, "verification": "UNVERIFIED_SCOPED_STATEMENT", "replaces_status": j["status"], "reasons": j["reasons"], "fallback": j["fallback"], "review": j.get("review"), "replacement": text} for text, j in generated]
    b["g5_absence"] = entries + scoped if (entries or scoped) else None
    if not b["g5_absence"]:
        b.pop("g5_absence")
    if pending:
        b["g5_review_pending"] = pending
    else:
        b.pop("g5_review_pending", None)
    if system:
        b["g5_system_statements"] = system
    if event_checks:
        b["g5_event_checks"] = [{k: v for k, v in e.items() if k != "span"} for e in event_checks]
    return b, {"changes": changes, "entries": len(entries), "pending": len(pending), "system": len(system), "scoped": len(scoped)}


def coverage_check(L: "g4.Ledger", clause: str) -> tuple[bool | None, str]:
    """'The FY27 report is not in the records' / 'no FY22 or FY23 data': verified against the company's year folders and fact registries. None = nothing to check."""
    yrs = [int(x[-2:]) for x in re.findall(r"FY\s?(\d{2,4})(?!\d)", clause)]
    yrs = [y for y in yrs if 10 <= y <= 40]
    if not yrs:
        return None, "no fiscal year named"
    held, absent = [], []
    for y in yrs:
        d = L.cdir / f"fy{y:02d}"
        has = d.exists() and (d / "financials" / "financial_fact_registry.json").exists()
        (held if has else absent).append(f"FY{y}")
    if held:
        return False, f"the records do hold fact registries for {', '.join(held)}"
    return True, f"no year folder with a fact registry for {', '.join(absent)} (folders present: {', '.join(sorted(p.name for p in L.cdir.glob('fy??')))})"
