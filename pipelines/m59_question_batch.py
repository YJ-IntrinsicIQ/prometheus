#!/usr/bin/env python3
"""
M59 — repeatable batch workflow: onboard every pending company-question pair into the certified answer format.

Reads ONLY existing intelligence (legacy answer cards, existing hybrid answers, canonical company records, approved
answers). Makes ZERO AI calls. Writes candidate files and a review index; it NEVER touches the approval registry or the
served-answers file (shadow_level3_hybrid_answers.json). A candidate is served only after an owner registers its exact
digest through the existing approval workflow (answer_certification.py --mode approve).

Per pair: choose a path (reuse / adapt / correct / regenerate-deterministically / defer) -> build a certified-format
answer -> run the existing PACP validators (+ M59 checks where PACP has no family) -> classify:
READY / NEEDS_CORRECTION / DEFERRED / BLOCKED.

    python3 pipelines/m59_question_batch.py            # dry run, prints summary
    python3 pipelines/m59_question_batch.py --write    # writes candidate files + preview/ review package data
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipelines import pacp_adversarial as pa  # noqa: E402
from pipelines import answer_certification as ac  # noqa: E402
from pipelines.answer_certification import compute_content_fingerprint, compute_full_artifact_digest  # noqa: E402


def _load_catalog() -> list[dict]:
    """The canonical catalog, as the companies' generated research views carry it (they are produced from QUESTION_CATALOG and
    are identical across companies). Read from JSON so this module needs no import of the `intelligence` package."""
    # READ-ONLY exception: a static, import-time catalog read; this module never writes through this path (all writes use ac.companies_root()).
    view = json.loads((ROOT / "companies" / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / "company_research_view.json").read_text())
    return [{"id": c["id"], "title": c["title"], "questions": [{"id": q["id"], "title": q["title"]} for q in c["questions"]]} for c in view["categories"]]


QUESTION_CATALOG = _load_catalog()

COMPANIES = ["sun_pharma", "tanla", "ujjivan", "datapatterns"]
NAMES = {"sun_pharma": "Sun Pharma", "tanla": "Tanla", "ujjivan": "Ujjivan Small Finance Bank", "datapatterns": "Data Patterns"}
SLUGS = {"sun_pharma": "sun-pharma", "tanla": "tanla", "ujjivan": "ujjivan", "datapatterns": "datapatterns"}
BANKS = {"ujjivan"}
# Certified question ids whose approved answers live in the served file (each is a question in its own right).
CERTIFIED = ["what-has-management-promised", "what-did-management-actually-deliver", "what-could-go-wrong", "how-is-capital-allocated", "how-good-is-management"]
# A catalog question served by a certified answer ONLY where that answer genuinely covers it (see lib/catalog/catalog.ts).
VETTED_ALIASES = {"what-can-break-the-thesis": "what-could-go-wrong"}
SCHEMA = "m59_candidates_v1"


def completed_fy() -> int:
    """The most recent fiscal year (ending 31 March) that has fully elapsed today."""
    t = datetime.now(timezone.utc)
    return (t.year if t.month >= 4 else t.year - 1) % 100


AS_OF = completed_fy()

READY, FIX, DEFER, BLOCK = "READY", "NEEDS_CORRECTION", "DEFERRED", "BLOCKED"

# ───────────────────────────── text helpers ─────────────────────────────
ID_RE = re.compile(r"\s*\(?\b(?:MC|RG|PJ|CAO|CA|CP|CHK|MP|CM|CL|REL)-[A-Za-z0-9]{2,}(?:-[A-Za-z_]+)?\b\)?:?")
ENUM_RE = re.compile(r"\b[A-Z]{2,}(?:_[A-Z]{2,})+\b")
FY_RE = re.compile(r"\bfy(\d{2})\b", re.I)
GENERIC_UNCERTAINTY = [
    r"main limitation is precision or missing detail", r"current evidence still leaves open questions", r"clearest documented",
    r"identifies follow-up areas", r"strong enough to suggest the questions", r"come directly from the current evidence",
    r"^has management converted this statement", r"full claim-level verification requires progression evidence",
]
PLACEHOLDER = [r"not yet visible", r"\bis unavailable\b", r"unavailable\.$", r"\b0\.0 \(FY", r"research for this question is not complete"]
CAUSAL = re.compile(r"\b(because of|due to|led to|resulted in|drove|driven by|caused|thanks to|as a result of|contributed to)\b", re.I)
NEGATED_CAUSAL = re.compile(r"\b(not|no|cannot|can't|does not|do not|without|neither|never)\b[^.;]{0,60}\b(because of|due to|led to|resulted in|drove|driven by|caused|thanks to|as a result of|contributed to)\b", re.I)
RATING = re.compile(r"\b(assessed as (?:weak|strong|poor|good)|rating|rated|score of|overweight|underweight|buy|sell)\b", re.I)


def tidy(text: Any) -> str:
    t = str(text or "")
    t = ID_RE.sub("", t)
    t = ENUM_RE.sub(lambda m: m.group(0).lower().replace("_", " "), t)
    t = FY_RE.sub(lambda m: f"FY{m.group(1)}", t)
    t = re.sub(r"\bH([12])CY(\d{2})\b", r"H\1 20\2", t)
    t = re.sub(r"₹\s?(\d{1,3}(?:,\d{3})*|\d+)(\.\d+)?\s?(?:crore|cr|Cr)\b", lambda m: "₹" + f"{float(m.group(1).replace(',', '') + (m.group(2) or '')):,.0f}" + " crore", t)
    t = re.sub(r"\bINR\s?(\d[\d,]*(?:\.\d+)?)\s?(?:crore|cr|Cr)\b", r"₹\1 crore", t)
    t = re.sub(r"\bUTV\b", "unable to verify", t)
    t = re.sub(r"\bcanonical\b", "recorded", t)
    t = re.sub(r"₹\s?(\d{1,3}(?:,\d{3})*|\d+)(\.\d+)?\s?crore", lambda m: "₹" + f"{float(m.group(1).replace(',', '') + (m.group(2) or '')):,.0f}" + " crore", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    return t.strip()


def clip(t: str, n: int) -> str:
    t = t.strip()
    if len(t) <= n:
        return t
    return t[: n - 1].rsplit(" ", 1)[0].rstrip(",;:—- ") + "…"


def whole(t: str, n: int) -> str:
    """Return complete sentences/clauses of t within n characters, never a fragment cut mid-phrase."""
    t = t.strip()
    if len(t) <= n and re.search(r"[.!?)]$", t):
        return t
    cut = ""
    for sent in re.split(r"(?<=[.;])\s+", t):
        if len(cut) + len(sent) + 1 > n:
            break
        cut = (cut + " " + sent).strip()
    if not cut:
        head = t[:n]
        k = max(head.rfind(", "), head.rfind(" — "), head.rfind(" and "))
        cut = head[:k] if k > n // 2 else ""
    cut = cut.rstrip(",;:—- ")
    if re.search(r"\b(via|and|of|to|for|with|by|including|from|the|a|in|on|at|as|that|which)$", cut):
        cut = cut.rsplit(" ", 1)[0].rstrip(",;:—- ")
    return (cut + ".") if cut and not cut.endswith((".", ")")) else cut


def pname(t: str, n: int = 130) -> str:
    """A project name cut off inside a bracket is shortened to the text before the bracket."""
    t = tidy(t)
    t = clip(t, n)
    if t.count("(") > t.count(")"):
        t = t[: t.rfind("(")].strip(" —-,;…")
    return t


def drop_dangling(t: str) -> str:
    """A sentence that ends on a preposition or conjunction is a truncated source sentence; drop it rather than present it."""
    parts = re.split(r"(?<=[.])\s+", t.strip())
    if len(parts) > 1 and re.search(r"\b(via|and|of|to|for|with|by|including|from|the|a)\.$", parts[-1]):
        parts = parts[:-1]
    return " ".join(parts)


def poss(name: str) -> str:
    return name + ("'" if name.endswith("s") else "'s")


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def inr(n: float) -> str:
    return f"₹{n:,.0f} crore"


def is_generic(text: str) -> bool:
    return any(re.search(p, text, re.I) for p in GENERIC_UNCERTAINTY)


def words(answer: dict) -> int:
    parts = [answer.get("simple_answer", ""), *answer.get("what_evidence_shows", []), answer.get("what_may_mean_economically", ""), answer.get("what_is_not_yet_proven", ""), *answer.get("what_to_monitor", [])]
    return len(" ".join(str(p) for p in parts).split())


def fyn(p: Any) -> int | None:
    m = re.search(r"(\d{2})", str(p or ""))
    return int(m.group(1)) if m else None


# ───────────────────────────── company sources ─────────────────────────────
class Co:
    """Everything one batch needs about a company, loaded once."""

    def __init__(self, key: str, registry: dict) -> None:
        self.key = key
        self.name = NAMES[key]
        self.dir = ac.companies_root() / key / "company_memory"
        self.registry = registry
        self._cache: dict[str, Any] = {}
        self.bank = key in BANKS

    def j(self, rel: str) -> Any:
        if rel not in self._cache:
            p = self.dir / rel
            self._cache[rel] = json.loads(p.read_text()) if p.exists() else None
        return self._cache[rel]

    @property
    def cards(self) -> dict[str, dict]:
        d = self.j("ask_intrinsiciq/answer_cards.json") or {}
        return {c["question_id"]: c for c in d.get("answers", [])}

    @property
    def hybrid(self) -> dict[str, dict]:
        return (self.j("ask_intrinsiciq/shadow_level3_hybrid_answers.json") or {}).get("answers", {})

    def approved(self, qid: str) -> dict | None:
        """An approved answer, by the same fingerprint + full-digest test the app applies."""
        rec = self.registry.get(f"{self.key}:{qid}")
        e = self.hybrid.get(qid)
        if not rec or not e or e.get("status") != "PASS" or e.get("coverage") != "COMPLETE" or rec.get("status") in ("REVOKED", "PENDING_INDEPENDENT_REVIEW", "PENDING_MIGRATION_REVIEW"):
            return None
        a = e["answer"]
        if compute_content_fingerprint(a) != rec.get("fingerprint"):
            return None
        if rec.get("full_artifact_digest") and compute_full_artifact_digest(a) != rec["full_artifact_digest"]:
            return None
        return a

    @property
    def latest_year(self) -> int:
        d = self.j("gold/strategy_evolution_timeline.json") or {}
        return fyn((d.get("data_coverage") or {}).get("latest_period")) or max((fyn(p.name) or 0 for p in (ac.companies_root() / self.key).glob("fy??")), default=26)

    def series(self, group: str, metric: str) -> list[dict]:
        t = self.j("financials/financial_trends.json") or {}
        pts = (((t.get("trend_groups") or {}).get(group) or {}).get(metric) or {}).get("series") or []
        return sorted(({"fy": fyn(p["year"]), "v": float(p["value"]), "basis": p.get("basis", "unknown")} for p in pts if p.get("value") is not None), key=lambda x: x["fy"] or 0)

    def run(self, group: str, metric: str) -> list[dict]:
        """Latest stretch of consecutive years on one stated basis: the only years that may be compared."""
        out: list[dict] = []
        for p in reversed(self.series(group, metric)):
            if not out:
                if p["basis"] != "unknown":
                    out = [p]
            elif out[0]["fy"] - 1 == p["fy"] and out[0]["basis"] == p["basis"]:
                out.insert(0, p)
            else:
                break
        return out

    # numeric provenance: every number in the record families an answer may draw on
    @property
    def numbers(self) -> list[float]:
        if "numbers" not in self._cache:
            nums: set[float] = set()

            def walk(o: Any) -> None:
                if isinstance(o, bool):
                    return
                if isinstance(o, (int, float)):
                    nums.add(float(o))
                elif isinstance(o, str):
                    for m in re.finditer(r"-?\d[\d,]*\.?\d*", o):
                        try:
                            nums.add(float(m.group().replace(",", "")))
                        except ValueError:
                            pass
                elif isinstance(o, dict):
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)

            for sub in ["financials", "capital_allocation_outcomes", "economic_attribution", "management_progression", "projects", "capacity", "gold", "company_model", "management_commitments", "management_commentary", "risks"]:
                for f in (self.dir / sub).rglob("*.json"):
                    try:
                        walk(json.loads(f.read_text()))
                    except Exception:
                        pass
            for f in ["ownership_evolution.json", "risk_evolution.json", "promise_tracker.json", "capital_allocation_timeline.json"]:
                if (self.dir / f).exists():
                    walk(json.loads((self.dir / f).read_text()))
            for q in CERTIFIED:
                a = self.approved(q)
                if a:
                    walk(a)
            self._cache["numbers"] = sorted(nums)
        return self._cache["numbers"]


def number_supported(n: float, pool: list[float]) -> bool:
    import bisect
    for cand in (n, n / 100, n * 100, n / 10000000, n * 10000000):
        i = bisect.bisect_left(pool, cand - max(abs(cand) * 0.006, 0.06))
        if i < len(pool) and pool[i] <= cand + max(abs(cand) * 0.006, 0.06):
            return True
    return False


def unsupported_numbers(text: str, co: Co, allow: set[float]) -> list[str]:
    bad: list[str] = []
    stripped = re.sub(r"\bFY\d{2}(?:[–-]FY?\d{2})?\b|\bH[12] 20\d{2}\b|\b(?:19|20)\d{2}(?:[–-]\d{2,4})?\b|\b(?:p|pp)\.\s?\d+\b", " ", text)
    for m in re.finditer(r"-?\d[\d,]*\.?\d*", stripped):
        raw = m.group().replace(",", "")
        try:
            n = float(raw)
        except ValueError:
            continue
        if ("." not in raw and abs(n) < 100) or n in allow or any(abs(n - a) < 0.06 for a in allow):
            continue
        if not number_supported(n, co.numbers):
            bad.append(m.group())
    return bad


# ───────────────────────────── validation ─────────────────────────────
NARRATIVE = ["simple_answer", "what_evidence_shows", "what_may_mean_economically", "what_is_not_yet_proven", "what_to_monitor", "key_points"]


def ntext(a: dict) -> str:
    out = []
    for f in NARRATIVE:
        v = a.get(f)
        out.extend(v if isinstance(v, list) else [v] if v else [])
    return " ".join(str(x) for x in out)


RELEVANCE: dict[str, list[str]] = {
    "what-does-company-do": [r"."], "who-are-the-customers": [r"pay|customer|borrower|client|operator|government|distributor|depositor"],
    "how-does-it-make-money": [r"revenue|income|sales|sale|fee|interest|billing|spread"],
    "are-profits-converting-into-cash": [r"cash flow", r"profit"], "what-is-owner-earnings": [r"owner[- ]earnings"],
    "is-working-capital-a-concern": [r"working[- ]capital|receivable|inventory|cash conversion"], "are-per-share-economics-improving": [r"per share|EPS"],
    "what-promise-types-dominate": [r"intent|commitment|direction|statement"], "which-promises-are-overdue": [r"deadline|overdue|due"],
    "what-was-delivered-last-3-years": [r"FY\d{2}\s?[–-]\s?FY\d{2}"], "what-was-missed": [r"missed|miss"], "did-past-claims-come-true": [r"commitment"],
    "did-execution-lead-to-outcomes": [r"initiative|execution", r"outcome"], "what-projects-are-underway": [r"project"], "how-is-capacity-changing": [r"capacity"],
    "what-is-management-commentary-saying": [r"commentary|management (says|states|emphasi)"],
    "which-investments-created-value": [r"allocation|investment", r"value|outcome"], "what-is-the-return-on-capex": [r"capex|capital expenditure", r"return"],
    "what-incentives-matter": [r"promoter|incentive|ownership"], "what-regulatory-risks-remain-active": [r"regulat|governance|compliance|legal"],
    "which-disclosure-is-missing": [r"disclos"], "what-should-i-ask-ir": [r"\?"], "what-needs-management-clarification": [r"clarif|explain"],
    "what-remains-unresolved": [r"unresolved|open|not (yet )?(established|proven)"],
}


def validate(answer: dict, co: Co, qid: str, allow: set[float]) -> dict:
    checks: dict[str, tuple[str, str]] = {}
    text = ntext(answer)
    # structure (the answer contract)
    miss = [f for f in ("simple_answer", "what_evidence_shows", "what_may_mean_economically", "what_is_not_yet_proven", "what_to_monitor", "deterministic_precision_facts") if not answer.get(f) and f != "deterministic_precision_facts"]
    checks["contract_fields"] = ("FAIL", f"missing/empty: {miss}") if miss else ("PASS", "all required narrative fields present")
    checks["word_budget"] = ("FAIL", f"{words(answer)} words > 600") if words(answer) > 600 else ("PASS", f"{words(answer)} words")
    # relevance
    rel_fail = [p for p in RELEVANCE.get(qid, []) if not re.search(p, answer.get("simple_answer", "") + " " + " ".join(answer.get("what_evidence_shows", [])), re.I)]
    checks["answers_the_question"] = ("FAIL", f"answer does not engage the question (missing {rel_fail})") if rel_fail else ("PASS", "answer engages the question")
    # specificity
    gen = [x for x in [answer.get("what_is_not_yet_proven", ""), *answer.get("what_to_monitor", [])] if is_generic(str(x))]
    ph = [p for p in PLACEHOLDER if re.search(p, text, re.I)]
    checks["specific_not_generic"] = ("FAIL", f"generic/placeholder text: {gen[:1] or ph[:1]}") if (gen or ph) else ("PASS", "uncertainty and monitoring points are specific")
    # identifiers / ratings / causality
    ids = ID_RE.findall(text) + ENUM_RE.findall(text)
    checks["no_internal_identifiers"] = ("FAIL", f"internal identifiers: {ids[:3]}") if ids else ("PASS", "none")
    rl = RATING.findall(text)
    checks["no_ratings_or_recommendations"] = ("FAIL", f"rating language: {rl[:2]}") if rl else ("PASS", "none")
    sentences = re.split(r"(?<=[.;])\s+", text)
    causal = [s for s in sentences if CAUSAL.search(s) and not NEGATED_CAUSAL.search(s) and not re.search(r"\b(not|no|cannot|does not|do not|unproven|unestablished|not established)\b", s, re.I)]
    checks["no_unsupported_causal_claims"] = ("FAIL", f"causal wording: {causal[0][:140]}") if causal else ("PASS", "no causal claims outside explicit negation")
    # recurrence guards (M59.1): defects the independent audit found in validator-clean text
    frags = [t for t in [answer.get("simple_answer", ""), *answer.get("what_evidence_shows", []), *answer.get("what_to_monitor", [])] if re.search(r"(…|\.\.\.)\s*$", t) or t.count("(") > t.count(")") or re.search(r"\b(via|and|of|to|for|with|by|including|from|the|a|in|on|as|that|which)[.;:]?$", t.strip())]
    checks["no_truncated_text"] = ("FAIL", f"text cut off mid-phrase: {frags[0][-70:]!r}") if frags else ("PASS", "no cut-off sentences or unclosed brackets")
    span = re.search(r"(?:capex|capital expenditure|capital spending)[^.;]{0,60}(?:FY\d{2}\s?[–-]\s?FY\d{2}|across FY)", text, re.I)
    checks["period_consistency"] = ("FAIL", f"a capital-spending amount is given a multi-year span: {span.group(0)[:90]!r}") if span and not re.search(r"cumulative|total over|sum of", text, re.I) else ("PASS", "amounts carry the period they were reported for")
    roc = [x for x in sentences if re.search(r"dividend|buyback|repay", x, re.I) and re.search(r"value (?:was )?creat|created value|value creation|confirmed (?:deterministic )?outcome|demonstrated|realised value|realized value", x, re.I) and not re.search(r"\b(not|no|nor|cannot|does not|do not|without|neither)\b", x, re.I)]
    checks["return_of_capital_not_value"] = ("FAIL", f"dividends/buybacks/repayment counted as value creation: {roc[0][:120]}") if roc else ("PASS", "payouts and repayments are not presented as value created")
    lab_ = re.findall(r"\b[a-z]{3,}_[a-z_]{3,}\b", text) + re.findall(r"billed on a [a-z_]+ basis", text)
    tmpl = re.findall(r"branded pricing|regulatory approval cycles|volume throughput", text, re.I)
    checks["business_model_fit"] = ("FAIL", f"internal label or template text: {(lab_ or tmpl)[:2]}") if (lab_ or tmpl) else ("PASS", "no internal labels or cross-industry template language")
    if qid in ("what-needs-management-clarification", "what-should-i-ask-ir"):
        trk = re.findall(r"tracker|progression records|register records|unable to verify|stored records", text, re.I)
        checks["no_internal_tracker_questions"] = ("FAIL", f"asks management about Prometheus's own tracking: {trk[:2]}") if trk else ("PASS", "questions concern disclosures, not internal records")
    # numbers must trace to a stored record
    bad = unsupported_numbers(answer.get("simple_answer", "") + " " + " ".join(answer.get("what_evidence_shows", [])), co, allow)
    checks["numbers_trace_to_records"] = ("FAIL", f"numbers not found in records: {bad[:4]}") if bad else ("PASS", "every figure traces to a stored record or is a declared calculation")
    # sector: banks never judged with industrial measures
    if co.bank:
        r, d = pa.check_banking_no_industrial_working_capital(answer, company=co.key)
        if re.search(r"owner[- ]earnings|cash conversion cycle|inventory", text, re.I) and not re.search(r"not (meaningful|applicable)|does not apply|do not apply", text, re.I):
            r, d = "FAIL", "industrial cash-flow measure applied to a bank without stating it does not apply"
        checks["banking_appropriate"] = (r, d)
    # existing PACP machinery
    suite = pa.run_adversarial_suite(answer, co.key, qid)
    family_registered = suite["overall"] != "INCOMPLETE" or not suite["incomplete"]
    if pa._family(qid) == "unknown":
        glob = [(fn.__name__, *fn(answer, company=co.key, question_id=qid)) for fn in pa.GLOBAL_VALIDATORS]
        gf = [g for g in glob if g[1] == "FAIL"]
        checks["pacp_global"] = ("FAIL", "; ".join(f"{g[0]}: {g[2]}" for g in gf)) if gf else ("PASS", f"{len(glob)} global PACP checks pass (no PACP family registered for this question)")
        pacp = {"family_registered": False, "overall": "GLOBAL_ONLY", "fails": [g[0] for g in gf], "warns": [g[0] for g in glob if g[1] == "WARN"]}
    else:
        fam = pa._family(qid)
        registered = bool(pa.FAMILY_VALIDATORS.get(fam))
        if not registered:   # e.g. "execution": PACP maps the question but registers no validators — run globals + M59 execution guards
            glob = [(fn.__name__, *fn(answer, company=co.key, question_id=qid)) for fn in pa.GLOBAL_VALIDATORS]
            gf = [g for g in glob if g[1] == "FAIL"]
            checks["pacp_global"] = ("FAIL", "; ".join(f"{g[0]}: {g[2]}" for g in gf)) if gf else ("PASS", f"{len(glob)} global PACP checks pass (family '{fam}' has no registered validators)")
            pacp = {"family_registered": False, "overall": "GLOBAL_ONLY", "fails": [g[0] for g in gf], "warns": [g[0] for g in glob if g[1] == "WARN"]}
        else:
            checks["pacp_suite"] = ("FAIL" if suite["fails"] else "WARN" if suite["warns"] else "PASS", f"PACP {suite['overall']}: fails={suite['fails']} warns={suite['warns']}")
            pacp = {"family_registered": True, "overall": suite["overall"], "fails": suite["fails"], "warns": suite["warns"], "named_checks": suite["named_checks"]}
    if qid == "what-regulatory-risks-remain-active":
        rf = [(fn.__name__, *fn(answer, company=co.key, question_id=qid)) for fn in pa.FAMILY_VALIDATORS["risk"]]
        bad = [f"{n}: {d}" for n, r, d in rf if r == "FAIL"]
        checks["pacp_risk_validators"] = ("FAIL", "; ".join(bad)) if bad else ("PASS", f"{len(rf)} PACP risk validators pass")
    if qid == "did-execution-lead-to-outcomes":
        s = answer.get("simple_answer", "")
        checks["execution_not_outcome"] = ("PASS", "states what outcomes were or were not observed") if re.search(r"\boutcome", s, re.I) and re.search(r"\b(no|none|not|0|\d+ (has|have))\b", s, re.I) else ("FAIL", "does not say whether outcomes were observed")
    failed = [k for k, (r, _) in checks.items() if r == "FAIL"]
    return {"checks": {k: {"result": r, "detail": d} for k, (r, d) in checks.items()}, "failed": failed, "pacp": pacp}


# ───────────────────────────── answer builders ─────────────────────────────
def mk_answer(simple: str, evidence: list[str], econ: str, unproven: str, monitor: list[str], dpf: list[dict] | None = None, key_points: list[str] | None = None, interp: str | None = None) -> dict:
    ev = [tidy(e) for e in evidence if e]
    return {
        "simple_answer": tidy(simple), "what_evidence_shows": ev, "what_may_mean_economically": tidy(econ),
        "what_is_not_yet_proven": tidy(unproven), "what_to_monitor": [tidy(m) for m in monitor if m],
        "claims": [], "relationships": [], "deterministic_precision_facts": dpf or [],
        "why_it_matters": tidy(econ), "investor_interpretation": tidy(interp or econ),
        "key_points": [tidy(k) for k in (key_points or ev[:4])][:4], "evidence_gaps": [],
    }


def dpf(metric: str, value: Any, period: str, meaning: str) -> dict:
    return {"metric": metric, "value": str(value), "period": period, "semantic_meaning": meaning}


class Result:
    def __init__(self, path: str, answer: dict | None = None, reasons: list[str] | None = None, outcome: str | None = None, allow: set[float] | None = None, sources: list[str] | None = None) -> None:
        self.path, self.answer, self.reasons, self.outcome, self.allow, self.sources = path, answer, reasons or [], outcome, allow or set(), sources or []


def defer(reason: str) -> Result:
    return Result("Defer", None, [reason], DEFER)


def block(reason: str) -> Result:
    return Result("Defer", None, [reason], BLOCK)


# ── Family: understand the business (adapt) ──
EARNED = {"sale": "product sales", "usage": "usage-based billing", "interest_spread": "the interest spread on lending", "fee_income": "fees and commissions", "treasury_income": "treasury income", "milestone": "project milestones", "subscription": "subscriptions", "project": "project delivery"}
WATCH = {"sale": "Revenue mix by product or region and receivable and inventory days in the next annual report.", "usage": "Customer-wise or operator-wise revenue concentration and receivable days in the next annual report.", "interest_spread": "Net interest margin, credit costs and the loan and deposit mix in the next annual report.", "milestone": "Order book, customer-wise revenue share and the pace of order conversion in the next annual report."}


def join_list(items: list[str]) -> str:
    items = list(dict.fromkeys(i for i in items if i))
    if len(items) < 2:
        return items[0] if items else ""
    if any(" and " in i for i in items):
        return f"{items[0]}, as well as {items[1]}" if len(items) == 2 else "; ".join(items[:-1]) + f"; and {items[-1]}"
    return ", ".join(items[:-1]) + " and " + items[-1]


ECON_BY_BASIS = {
    "sale": "Product-sale revenue ties profit to pricing, product mix and approvals in each market, and whether profit turns into cash shows in receivable and inventory days.",
    "usage": "Usage-billed revenue moves with customer and operator traffic, and cash timing depends on enterprise and operator payment terms, so customer concentration and receivable days matter.",
    "interest_spread": "A lender earns the spread between what it charges on loans and what it pays for funds, less credit losses, so loan growth, funding cost and loan quality drive results; industrial working-capital measures do not apply to a bank.",
    "milestone": "Milestone-based revenue follows deliveries and customer acceptance, so profit can run ahead of cash; the order book, execution timing and receivable and inventory days matter.",
}


def h_adapt_factual(co: Co, qid: str) -> Result:
    c = co.cards.get(qid)
    if not c:
        return defer("no legacy answer card exists")
    if c["answer_status"] in ("unavailable", "not_supported"):
        return defer(f"legacy card is '{c['answer_status']}'")
    raw = drop_dangling(tidy(c["simple_answer"]))
    cm = co.j("company_model/company_model.json") or {}
    engines = [r for r in (cm.get("revenue_engines") or []) if r.get("description")]
    custs = cm.get("customers") or []
    payers = [tidy(x.get("payer_type") or "") for x in custs]
    users = [tidy(x.get("end_user_type") or "") for x in custs]
    kp: list[str] = []
    if qid == "what-does-company-do":
        simple = f"As described in its own reports, {poss(co.name)} business is: {raw[0].lower() + raw[1:] if raw[:2].isalpha() and raw[1].islower() else raw}"
        simple = simple if simple.endswith(".") else simple + "."
        kp = [k for k in (tidy(k) for k in c["key_points"]) if len(k) >= 30 and " " in k and not k.endswith(("(", ","))]
    elif qid == "who-are-the-customers":
        if not payers:
            return defer("no customer segments in the company model")
        simple = f"{co.name} sells to {join_list(payers)}" + (f"; the end users are {join_list(users)}." if any(users) and users != payers else ".")
        kp = [f"Paying customers: {join_list(payers)}.", f"End users: {join_list(users)}." if any(users) else ""]
        kp = [k for k in kp if k]
        for x in custs[:3]:
            ex = tidy((x.get("evidence") or [{}])[0].get("excerpt") or "")
            if ex and len(ex) > 40 and ex.rstrip(".…") != ex:
                continue
        kp += [k for k in (tidy(k) for k in c["key_points"]) if len(k) >= 30 and " " in k and "concentration" not in k.lower() and not k.startswith(("Who pays", "Who uses")) and not k.endswith(("(", ","))]
    else:
        body = raw[0].lower() + raw[1:] if raw[:2].isalpha() and raw[1].islower() else raw
        names = [EARNED.get(str(r.get("billing_basis")), None) for r in engines]
        descs = [tidy(r["description"]).rstrip(".") for r in engines[:3]]
        simple = f"{co.name} earns revenue through {join_list(list(dict.fromkeys(n for n in names if n)))}: " + "; ".join(d[0].lower() + d[1:] for d in descs) + "." if all(names) and names else f"{co.name} makes money as follows: {body}"
        for r in engines[:3]:
            line = f"Revenue source — {tidy(r['description'])}."
            if len(line) > 30:
                kp.append(line)
        offs = [tidy(o["name"]) for o in (cm.get("offerings") or [])[:4] if o.get("name")]
        if offs:
            kp.append(f"Offerings: {join_list(offs)}.")
        for dv in (cm.get("economic_drivers") or [])[:2]:
            m0 = tidy(str(dv.get("mechanism") or dv.get("driver")))
            trunc = bool(re.search(r"(\.\.\.|…)\s*$", m0))
            m0 = re.sub(r"(\.\.\.|…)\s*$", "", m0).strip()
            if trunc:
                m0 = m0[: m0.rfind(", ")] if ", " in m0 else ""
            if m0.count("(") > m0.count(")"):
                m0 = m0[: m0.rfind("(")].rstrip(" ,;")
            m = whole(m0, 260)
            if len(m) > 40:
                kp.append(m if m.endswith(".") else m + ".")
    kp = [k for k in dict.fromkeys(kp) if not re.search(r"\b[a-z]+_[a-z_]+\b", k)]
    basis0 = str(engines[0].get("billing_basis")) if engines else ""
    imp = ECON_BY_BASIS.get(basis0) or (tidy(engines[0].get("working_capital_implications") or "") if engines else "")
    lead = {"who-are-the-customers": "Who pays shapes the economics. ", "how-does-it-make-money": "", "what-does-company-do": ""}[qid]
    econ = lead + imp
    econ = econ if econ.endswith(".") else econ + "."
    if len(kp) < 2 or not engines:
        return Result("Correct", None, ["the company model and card do not give enough business-specific points"], FIX)
    basis = str(engines[0].get("billing_basis"))
    seg = join_list(payers) if payers else "customer segments"
    unk = {
        "what-does-company-do": f"The records do not show how {poss(co.name)} revenue splits across its activities or how that mix has changed.",
        "who-are-the-customers": f"The records do not say how much revenue comes from any one of {poss(co.name)} customer groups ({seg}) or from named customers.",
        "how-does-it-make-money": f"Margins by revenue source and the split of revenue between sources are not disclosed in the records for {co.name}.",
    }[qid]
    mon = [WATCH.get(basis, "Revenue mix and customer disclosure in the next annual report.")]
    return Result("Adapt", mk_answer(simple, kp[:6], econ, unk, mon), [f"legacy card ('{c['answer_status']}') restructured into the shared answer format; customers, revenue sources and cash-timing implications taken from the company's own model instead of a generic template"], None, sources=["Company model", "Legacy answer card"])


# ── Family: financials ──
def bridge_row(co: Co) -> dict | None:
    d = co.j("financials/investor_financial_modules/owner_earnings_bridge.json") or {}
    rows = [r for r in d.get("bridges", []) if isinstance(r.get("reported_pat"), (int, float))]
    return rows[-1] if rows else None


def h_cash(co: Co, qid: str) -> Result:
    if co.bank:
        return defer("operating cash flow and owner earnings are not meaningful for a bank (they include movements in loans and deposits); bank-specific measures (capital adequacy, asset quality, net interest margin) are not in the structured records")
    r = bridge_row(co)
    if not r or r.get("cfo") is None or r.get("owner_earnings_estimate") is None:
        return defer("no owner-earnings bridge with operating cash flow for the latest year")
    fy = fyn(r["fiscal_year"])
    cc = co.run("cash_conversion", "cfo_to_pat")
    pat, cfo, oe = r["reported_pat"], r["cfo"], r["owner_earnings_estimate"]
    wc = (co.j("financials/investor_financial_modules/working_capital_quality_drilldown.json") or {}).get("drilldown", [])
    last_wc = wc[-1] if wc else {}
    ratio = cfo / pat if pat else None
    if qid == "are-profits-converting-into-cash":
        simple = f"In FY{fy}, reported profit was {inr(pat)} and operating cash flow was {inr(cfo)} ({ratio:.2f}× profit), so profit was {'fully ' if ratio >= 1 else 'only partly '}backed by operating cash. A conservative owner-earnings estimate, after all identified capital spending, is {inr(oe)}."
        ev = [f"FY{fy}: reported profit {inr(pat)}; operating cash flow {inr(cfo)}; estimated owner earnings {inr(oe)} (operating cash flow less all identified capital spending)."]
        if len(cc) >= 3:
            lo, hi = min(cc, key=lambda p: p["v"]), max(cc, key=lambda p: p["v"])
            ev.append(f"Operating cash flow ranged from {lo['v']:.2f}× profit (FY{lo['fy']}) to {hi['v']:.2f}× (FY{hi['fy']}) over FY{cc[0]['fy']}–FY{cc[-1]['fy']} ({cc[0]['basis']} basis).")
        if isinstance(last_wc.get("receivable_days"), (int, float)):
            ev.append(f"Receivable days were {last_wc['receivable_days']:.0f} in FY{fyn(last_wc['fiscal_year'])}; inventory and payable days are not available for the same year, so a full cash conversion cycle cannot be computed." if last_wc.get("inventory_days") is None else f"Receivable days {last_wc['receivable_days']:.0f}, inventory days {last_wc['inventory_days']:.0f} in FY{fyn(last_wc['fiscal_year'])}.")
        if co.series("revenue_and_income", "pat")[-1:] and co.series("revenue_and_income", "pat")[-1]["basis"] == "unknown":
            ev.append(f"The reporting basis (consolidated or standalone) of the FY{fy} figures is not stated in the records.")
        econ = "Profit that turns into cash can be reinvested or distributed; profit that does not has to be financed. Cash conversion is a quality-of-earnings check, not a verdict on the business."
        unp = "The maintenance-versus-growth capital spending split is not disclosed, so owner earnings are an estimate of limited precision. One year of cash conversion does not show whether it is durable."
        mon = ["Operating cash flow relative to profit in the next annual report.", "Disclosure of maintenance versus growth capital spending."]
    else:
        simple = f"Owner earnings are an estimate of the cash an owner could take out of the business after the capital spending needed to run it. For FY{fy} the records support an estimate of {inr(oe)}, against reported profit of {inr(pat)} and operating cash flow of {inr(cfo)}."
        ev = [f"FY{fy}: estimated owner earnings {inr(oe)} = operating cash flow {inr(cfo)} less all identified capital spending {inr(abs(r['total_identified_capex']))}." if isinstance(r.get("total_identified_capex"), (int, float)) else f"FY{fy}: estimated owner earnings {inr(oe)}.", f"The estimate is {oe / pat * 100:.0f}% of reported profit.", "Reported earnings, owner earnings and actual cash generation are three different measures and are shown separately."]
        if co.series("revenue_and_income", "pat")[-1:] and co.series("revenue_and_income", "pat")[-1]["basis"] == "unknown":
            ev.append(f"The reporting basis (consolidated or standalone) of the FY{fy} figures is not stated in the records.")
        econ = "Owner earnings indicate what could be distributed or reinvested without starving the business; they are more conservative than reported profit when capital spending is heavy."
        unp = "The split between maintenance and growth capital spending is not disclosed, so all identified capital spending is deducted. The estimate is therefore conservative and imprecise, and is not an exact free-cash-flow figure."
        mon = ["Disclosure of maintenance versus growth capital spending.", "Owner earnings estimate in the next annual report on the same basis."]
    d = [dpf("Reported profit", f"{pat:,.0f}", f"FY{fy}", "INR crore"), dpf("Operating cash flow", f"{cfo:,.0f}", f"FY{fy}", "INR crore"), dpf("Estimated owner earnings", f"{oe:,.0f}", f"FY{fy}", "INR crore, after all identified capex")]
    allow = {round(ratio, 2) if ratio else 0}
    if qid == "are-profits-converting-into-cash" and len(cc) >= 3:
        allow |= {round(p["v"], 2) for p in cc} | {round(oe / pat * 100)}
    allow |= {round(oe / pat * 100)}
    return Result("Correct", mk_answer(simple, ev, econ, unp, mon, d), [f"rebuilt from the owner-earnings bridge (legacy card rounded and left its uncertainty note generic)"], None, allow, ["Owner-earnings bridge", "Cash-flow statement"])


def h_wc(co: Co, qid: str) -> Result:
    d = co.j("financials/investor_financial_modules/working_capital_quality_drilldown.json") or {}
    if co.bank or d.get("working_capital_applicability") != "applicable":
        return defer(f"working-capital analysis is marked '{d.get('working_capital_applicability')}' for this company in the records ({d.get('applicability_reason') or 'no reason given'}); the legacy card reports a trend anyway")
    rows = d.get("drilldown", [])
    good = [r for r in rows if isinstance(r.get("receivable_days"), (int, float)) and 0 < r["receivable_days"] < 1000]
    if not good:
        return defer("no plausible receivable-days history")
    last = good[-1]
    fy = fyn(last["fiscal_year"])
    status, strain = last.get("working_capital_intensity_status"), last.get("cash_strain_risk")
    rd = co.run("working_capital", "receivable_days")
    if len(rd) < 2 and status in (None, "unknown", "not_applicable"):
        return defer("working-capital history is too thin (no year-on-year comparison and no intensity status)")
    parts = [f"receivable days {last['receivable_days']:.0f}"]
    for k, lab in (("inventory_days", "inventory days"), ("payable_days", "payable days"), ("cash_conversion_cycle", "cash conversion cycle")):
        if isinstance(last.get(k), (int, float)) and 0 < last[k] < 2000:
            parts.append(f"{lab} {last[k]:.0f}")
    verdict = {"severe": "a serious concern", "elevated": "a concern to watch closely", "watch": "a point to watch", "moderate": "a point to watch"}.get(str(status), "not shown to be a concern")
    simple = f"Working capital is {verdict} for {co.name} on the records: in FY{fy} {', '.join(parts)}; the records flag working-capital intensity as '{status}' and cash strain risk as '{strain}'."
    ev = [f"FY{fy}: " + ", ".join(parts) + "."]
    if len(rd) >= 2:
        ev.append(f"Receivable days moved from {rd[0]['v']:.0f} (FY{rd[0]['fy']}) to {rd[-1]['v']:.0f} (FY{rd[-1]['fy']}) on a {rd[0]['basis']} basis.")
    g = last.get("receivables_growth_vs_revenue_growth")  # percentage points: receivables growth minus revenue growth
    prev = good[-2] if len(good) >= 2 and fyn(good[-2]["fiscal_year"]) == fy - 1 else None
    rev = {p["fy"]: p["v"] for p in co.series("revenue_and_income", "revenue")}
    if prev and isinstance(prev.get("receivables"), (int, float)) and isinstance(last.get("receivables"), (int, float)) and rev.get(fy) and rev.get(fy - 1):
        rg, vg = (last["receivables"] / prev["receivables"] - 1) * 100, (rev[fy] / rev[fy - 1] - 1) * 100
        ev.append(f"In FY{fy} receivables grew {rg:.1f}% while revenue grew {vg:.1f}%: receivables grew {abs(rg - vg):.1f} percentage points {'faster' if rg > vg else 'slower'} than revenue.")
        allow_extra = {round(rg, 1), round(vg, 1), round(abs(rg - vg), 1)}
    else:
        allow_extra = set()
    if isinstance(last.get("receivables"), (int, float)):
        ev.append(f"Receivables stood at {inr(last['receivables'])} in FY{fy}" + (f" and inventory at {inr(last['inventory'])}." if isinstance(last.get("inventory"), (int, float)) else "."))
    up = len(rd) >= 2 and rd[-1]["v"] > rd[0]["v"] + 2
    down = len(rd) >= 2 and rd[-1]["v"] < rd[0]["v"] - 2
    econ = "Cash tied up in receivables and inventory has to be financed and is not available for reinvestment or distribution." + (" Receivables that grow faster than sales can leave profit without matching cash." if allow_extra and rg > vg else "")
    unp = ("Whether the lengthening of receivable days reflects customer mix, timing or weaker collection is not established." if up else "Whether the improvement in receivable days is lasting is not established." if down else "The records do not explain what drives the level of working capital.") + " Inventory and payable days are missing for some years, so a continuous cash conversion cycle cannot be built."
    mon = ["Receivable and inventory days in the next annual report.", "Disclosure of ageing of receivables and the share owed by government or related parties."]
    dp = [dpf("Receivable days", f"{last['receivable_days']:.0f}", f"FY{fy}", "days of revenue outstanding")]
    allow = ({round(g, 1)} if isinstance(g, (int, float)) else set()) | allow_extra
    return Result("Correct", mk_answer(simple, ev, econ, unp, mon, dp), ["rebuilt from the working-capital drilldown; the legacy card mixed years and, for one company, started a trend from a zero that is a missing value"], None, allow, ["Working-capital drilldown", "Financial statements"])


def h_eps(co: Co, qid: str) -> Result:
    eps = co.run("per_share", "eps_basic")
    if co.bank:
        return defer("per-share economics for a bank need book value and return measures not present in the records; the legacy card reports 'not yet visible'")
    if len(eps) < 3:
        return defer(f"fewer than three consecutive years of earnings per share on one stated basis ({len(eps)})")
    ps = (co.j("financials/investor_financial_modules/per_share_compounding_analysis.json") or {}).get("analysis", [])
    oeps = [(fyn(r["fiscal_year"]), r["owner_earnings_per_share"]) for r in ps if isinstance(r.get("owner_earnings_per_share"), (int, float))]
    n = eps[-1]["fy"] - eps[0]["fy"]
    cagr = ((eps[-1]["v"] / eps[0]["v"]) ** (1 / n) - 1) * 100 if eps[0]["v"] > 0 and n > 0 else None
    dil = ps[-1].get("dilution_status") if ps else None
    dips = [f"FY{b['fy']}" for a, b in zip(eps, eps[1:]) if b["v"] < a["v"]]
    simple = f"{'Yes, though unevenly' if dips else 'Yes'}, on the reported measure: basic earnings per share rose from ₹{eps[0]['v']:.1f} in FY{eps[0]['fy']} to ₹{eps[-1]['v']:.1f} in FY{eps[-1]['fy']}" + (f", about {cagr:.1f}% a year" if cagr else "") + f" ({eps[0]['basis']} basis)" + (f", with a fall in {', '.join(dips)}" if dips else "") + "."
    ev = [f"Basic EPS: " + " → ".join(f"₹{p['v']:.1f} (FY{p['fy']})" for p in eps) + "."]
    allow = {round(cagr, 1)} if cagr else set()
    if len(oeps) >= 2:
        o0, o1 = oeps[0], oeps[-1]
        oc = ((o1[1] / o0[1]) ** (1 / (o1[0] - o0[0])) - 1) * 100 if o0[1] > 0 and o1[0] > o0[0] else None
        ev.append(f"Estimated owner earnings per share moved from ₹{o0[1]:.1f} (FY{o0[0]}) to ₹{o1[1]:.1f} (FY{o1[0]})" + (f", about {oc:.1f}% a year" if oc else "") + "; it does not move in step with reported EPS.")
        if oc:
            allow.add(round(oc, 1))
    if dil:
        ev.append("No material dilution is detected in the share count." if "no_material" in str(dil) else f"Share-count status: {str(dil).replace('_', ' ')}.")
    econ = "Per-share growth is what a shareholder actually owns; it can differ from company-level growth when shares are issued or bought back."
    unp = "Reported EPS can move for reasons other than operating improvement (one-off items, tax, share count). Owner earnings per share rest on an estimate whose maintenance-capex split is not disclosed."
    mon = ["EPS and owner earnings per share in the next annual report on the same basis.", "Any change in share count from issuance or buybacks."]
    dp = [dpf("Basic EPS", f"{p['v']:.1f}", f"FY{p['fy']}", "INR per share") for p in eps[:: max(1, len(eps) // 3)]][:4]
    return Result("Correct", mk_answer(simple, ev, econ, unp, mon, dp), ["recomputed from the per-share records; the legacy card's figures are retained and its CAGR recomputed"], None, allow, ["Per-share records", "Financial statements"])


# ── Family: promises and delivery (commitment evidence) ──
def hard_commitments(co: Co) -> list[dict]:
    """Hard commitments with their evidence. Sun Pharma: read from its APPROVED answers (the M54.10–M56 corrected evidence).
    Others: the approved commitments register (specific, checkable commitments) — no evidence of progress is linked."""
    out: list[dict] = []
    pr, dl = co.approved("what-has-management-promised"), co.approved("what-did-management-actually-deliver")
    facts = [f for f in (pr or {}).get("deterministic_precision_facts", []) if isinstance(f, str)]
    hard = [re.match(r"^Hard commitment (\d+) — MC-\d+ \((FY\d+)\): (.+)$", f) for f in facts]
    hard = [m for m in hard if m]
    if hard:
        dfacts = [f for f in (dl or {}).get("deterministic_precision_facts", []) if isinstance(f, dict)]

        def toks(s: str) -> set[str]:
            return set(re.findall(r"[a-z]{5,}", s.lower().replace("™", "")))

        for m in hard:
            bits = m.group(3).split("; ")
            promise = tidy(bits[0])
            get = lambda k: next((b[len(k) + 1:] for b in bits if b.startswith(k + "=")), "")  # noqa: E731
            obs = [(int(o.group(3)), float(o.group(1)), bool(o.group(2))) for o in re.finditer(r"(\d+(?:\.\d+)?)%\s*(calculated\s*)?\(FY(\d{2})\)", get("reported progress"))]
            cls = None
            for pat, name in ((r"^Target level reported reached", "reached"), (r"^Partly evidenced", "partly"), (r"^In progress", "in_progress")):
                if any(re.search(pat, str(f.get("metric"))) and toks(promise) & toks(str(f.get("period"))) for f in dfacts):
                    cls = name
            tf = tidy(get("timeframe"))
            due = re.search(r"(20\d{2})", tf)
            extras = [tidy(b) for b in bits[1:] if not re.match(r"^(timeframe|reported progress|register status)=", b)]
            out.append({"period": int(m.group(2)[2:]), "promise": promise, "timeframe": tf, "due_year": int(due.group(1)) if due else None, "observed": obs, "class": cls or "unknown",
                        "has_evidence": bool(obs) or any(re.search(r"filing confirmed", e, re.I) for e in extras), "extras": extras, "target": float(re.search(r"(\d+(?:\.\d+)?)%", promise).group(1)) if re.search(r"(\d+(?:\.\d+)?)%", promise) else None})
        return out
    reg = (co.j("management_commitments/management_commitments.json") or {}).get("commitments", [])
    seen: set[str] = set()
    for c in reg:
        if c.get("verification_applicability") != "APPLICABLE":
            continue
        fp = str(c.get("commitment_fingerprint") or c.get("id"))
        if fp in seen:
            continue
        seen.add(fp)
        tf = str(c.get("expected_timeframe") or "")
        due = re.search(r"(20\d{2})", re.sub(r"FY\s?(\d{4})", r"\1", tf))
        due_year = int(due.group(1)) if due else None
        if due_year and "-" in tf:
            m = re.search(r"(20\d{2})\s*-\s*(\d{2})", tf)
            due_year = 2000 + int(m.group(2)) if m else due_year
        out.append({"period": fyn(c.get("announcement_period")) or 0, "promise": tidy(str(c.get("original_statement"))).rstrip("."), "timeframe": "" if tf in ("", "unspecified", "ongoing") else tf, "due_year": due_year,
                    "observed": [], "class": "unknown", "has_evidence": False, "extras": [], "target": None})
    return sorted(out, key=lambda x: x["period"])


def promise_counts(co: Co) -> dict | None:
    """Statement counts from the APPROVED promises answer (its reconciled counts), across the three formats it appears in."""
    pr = co.approved("what-has-management-promised")
    if not pr:
        return None
    items: list[tuple[str, str]] = []
    for f in pr.get("deterministic_precision_facts", []):
        if isinstance(f, dict):
            items.append((str(f.get("metric", "")), str(f.get("value", ""))))
        else:
            for part in str(f).split(";"):
                if ":" in part:
                    lab, val = part.rsplit(":", 1)
                    items.append((lab.strip(), val.strip()))
    def pick(*pats: str, avoid: str | None = None) -> int | None:
        for lab, val in items:
            if any(re.search(p, lab, re.I) for p in pats) and not (avoid and re.search(avoid, lab, re.I)) and re.fullmatch(r"\d+", val.strip()):
                return int(val)
        return None
    total = pick(r"^Total", r"^Unique management statements")
    hard = pick(r"hard commitments? \(", r"^HARD_COMMITMENT", r"^VERIFIABLE_COMMITMENT", avoid=r"other")
    intents = pick(r"STRATEGIC_INTENT", r"SOFT_INTENT")
    dirs = pick(r"strategic directions", r"^ASPIRATION")
    blob = " ".join(str(x) for x in pr.get("what_evidence_shows", [])) + " " + str(pr.get("simple_answer", ""))
    if hard is None:
        m = re.search(r"\b(\d+) hard commitments", str(pr.get("simple_answer", "")))
        hard = int(m.group(1)) if m else None
    if intents is None:
        m = re.search(r"(\d+) strategic intents?", blob)
        intents = int(m.group(1)) if m else None
    if dirs is None:
        m = re.search(r"(\d+) strategic directions?", blob)
        dirs = int(m.group(1)) if m else None
    if total is None or hard is None:
        return None
    return {"total": total, "hard": hard, "intents": intents, "directions": dirs}


def h_types(co: Co, qid: str) -> Result:
    pc = promise_counts(co)
    if not pc or pc["intents"] is None:
        return defer("approved promises answer does not give a statement-type breakdown")
    rest = pc["total"] - pc["hard"] - pc["intents"] - (pc["directions"] or 0)
    if rest < 0:
        return Result("Correct", None, [f"the approved answer's counts do not add up (total {pc['total']} < parts)"], FIX)
    ranked = sorted([("stated strategic intents", pc["intents"]), ("hard commitments with a specific target and deadline", pc["hard"]), ("strategic directions" if (pc["directions"] or 0) != 1 else "strategic direction", pc["directions"] or 0)] + ([("other statements the register treats as verifiable but without a deadline or measurable target" if co.key == "sun_pharma" else ("other statements (for example a governance declaration)" if rest == 1 else "other statements (for example governance declarations)"), rest)] if rest > 0 else []), key=lambda x: -x[1])
    simple = f"Most of {poss(co.name)} {pc['total']} tracked management statements are {ranked[0][0]} ({ranked[0][1]}). Only {pc['hard']} are hard commitments with a specific target and deadline."
    ev = [f"{pc['total']} statements tracked: " + "; ".join(f"{n} {lab}" for lab, n in ranked if n) + ".", "The breakdown follows the same statement classification as the approved 'What has management promised?' answer."]
    econ = "Statements of intent give direction but cannot be checked; hard commitments can be checked against later results. A ledger dominated by intents gives investors little to hold management to."
    unp = "The classification comes from the wording of each statement and may not match management's own categorisation. It says nothing about whether any statement was or will be delivered."
    mon = ["Whether new hard commitments (specific target and deadline) are made in the next annual report."]
    return Result("Correct", mk_answer(simple, ev, econ, unp, mon, [dpf("Statements tracked", pc["total"], "FY20–latest", "count"), dpf("Hard commitments", pc["hard"], "FY20–latest", "count")]), ["rebuilt from the approved promises answer; the legacy card counted only the register's 'verifiable' subset and contradicts the reconciled counts"], None, set(), ["Approved answer: What has management promised?"])


def lab(c: dict) -> str:
    tf = str(c.get("timeframe") or "")
    return c["promise"] if (not tf or tf.lower() in c["promise"].lower()) else f"{c['promise']} ({tf})"


def deadline_state(c: dict, latest: int) -> str:
    """Passed once the stated deadline year has elapsed — judged against today, not only the latest report. A deadline can
    therefore be past while no report that could confirm delivery exists yet."""
    if c["due_year"] is None:
        return "no_deadline"
    return "passed" if c["due_year"] - 2000 <= max(latest, AS_OF) else "ahead"


def h_overdue(co: Co, qid: str) -> Result:
    cs = hard_commitments(co)
    if not cs:
        return defer("no hard commitments in the records")
    L = co.latest_year
    passed = [c for c in cs if deadline_state(c, L) == "passed"]
    if not passed:
        simple = f"No hard commitment of {co.name} has passed its stated deadline as of the FY{L} annual report; {len(cs)} remain ahead of their deadline or have none."
        ev = [f"{len(cs)} hard commitments tracked; none with a deadline on or before FY{L}."]
    else:
        def line(c: dict) -> str:
            if c["class"] == "reached":
                return f"{lab(c)}: the target level was reported reached"
            if c["has_evidence"]:
                return f"{lab(c)}: progress reported, adherence to the deadline not established"
            return f"{lab(c) if c['timeframe'] else c['promise'] + ' (deadline in ' + str(c['due_year']) + ')'}: no delivery confirmation in the records"
        simple = f"{len(passed)} of {poss(co.name)} {len(cs)} hard commitments {'has' if len(passed) == 1 else 'have'} passed {'its' if len(passed) == 1 else 'their'} stated deadline, but none can be called overdue or missed: " + ("; ".join(line(c) for c in passed[:3])) + "."
        ev = [line(c) for c in passed[:4]] + [f"{len(cs) - len(passed)} further hard commitment{'s have' if len(cs) - len(passed) != 1 else ' has'} a deadline still ahead or none stated."]
    econ = "A passed deadline with no confirmation is a question for management, not a finding of failure; the records can show missing disclosure without showing that nothing was done."
    unp = "Whether each passed deadline was met is not established where no later report states it. An unverified status is not a missed commitment."
    mon = ["Management's statement on delivery of each passed deadline in the next annual report."]
    return Result("Correct", mk_answer(simple, ev, econ, unp, mon, [dpf("Hard commitments past deadline", len(passed), f"as of FY{L}", "count"), dpf("Hard commitments tracked", len(cs), "FY20–latest", "count")]), ["rebuilt from the commitment evidence with deadline logic; the legacy card said 'none overdue' by tracker status alone"], None, set(), ["Approved answers: promises and delivery" if co.key == "sun_pharma" else "Commitments register"])


def h_missed(co: Co, qid: str) -> Result:
    cs = hard_commitments(co)
    if not cs:
        return defer("no hard commitments in the records")
    L = co.latest_year
    passed_all = [c for c in cs if deadline_state(c, L) == "passed"]
    delivered = [c for c in passed_all if c["class"] == "reached"]
    passed = [c for c in passed_all if c["class"] != "reached"]
    fell = [c for c in cs if len(c["observed"]) >= 2 and c["observed"][-1][1] < c["observed"][-2][1]]
    simple = f"The records do not establish that any of {poss(co.name)} {len(cs)} hard commitments was missed. " + (f"{len(passed)} {'has' if len(passed) == 1 else 'have'} passed {'its' if len(passed) == 1 else 'their'} deadline without a confirmation of delivery, which is unverified, not missed." if passed else "None has passed its stated deadline without either a reported result or a confirmation." if passed_all else "None has passed its stated deadline.") + (f" {len(delivered)} passed {'its' if len(delivered) == 1 else 'their'} deadline with the target level reported reached: {'; '.join(lab(c) for c in delivered[:2])}." if delivered else "")
    ev = [f"{len(cs)} hard commitments tracked; none has positive evidence of non-delivery."]
    if fell:
        c = fell[0]
        ev.append(f"One reported figure fell in the latest year ({c['promise']}: {c['observed'][-2][1]}% in FY{c['observed'][-2][0]} to {c['observed'][-1][1]}% in FY{c['observed'][-1][0]}); its deadline ({c['timeframe']}) has not passed, so this is not a miss.")
    if delivered:
        ev.append("Passed deadlines with the target level reported reached: " + "; ".join(lab(c) for c in delivered[:3]) + ".")
    if passed:
        ev.append("Passed deadlines without confirmation: " + "; ".join(lab(c) if c["timeframe"] else f"{c['promise']} ({c['due_year']})" for c in passed[:3]) + ".")
    econ = "Calling a commitment missed needs positive evidence that it was not met after its deadline. Missing disclosure is a gap to ask about, not evidence of failure."
    unp = "Later reports may confirm delivery or non-delivery of the unverified commitments. The records hold no evidence either way for those."
    mon = ["Delivery statements for each passed deadline in the next annual report."]
    return Result("Correct", mk_answer(simple, ev, econ, unp, mon, [dpf("Hard commitments", len(cs), "FY20–latest", "count"), dpf("Confirmed missed", 0, f"as of FY{L}", "count")]), ["rebuilt from the commitment evidence; the legacy card's 'no explicit misses' did not distinguish unverified from missed"], None, set(), ["Approved answers: promises and delivery" if co.key == "sun_pharma" else "Commitments register"])


def h_claims(co: Co, qid: str) -> Result:
    cs = hard_commitments(co)
    if not cs:
        return defer("no hard commitments in the records")
    reached = [c for c in cs if c["class"] == "reached"]
    partly = [c for c in cs if c["class"] == "partly"]
    prog = [c for c in cs if c["class"] == "in_progress"]
    ev_ct = [c for c in cs if c["has_evidence"]]
    if ev_ct:
        simple = f"Partly, and only on reported progress: of {poss(co.name)} {len(cs)} hard commitments, {len(reached)} {'has' if len(reached) == 1 else 'have'} a target level reported reached, {len(partly)} {'is' if len(partly) == 1 else 'are'} partly evidenced and {len(prog)} {'is' if len(prog) == 1 else 'are'} in progress. None has a confirmed economic outcome."
        ev = [f"{c['promise']}" + (f" ({c['timeframe']})" if c["timeframe"] else "") + ": " + (", ".join(f"{v}% in FY{y}" for y, v, _ in c["observed"]) if c["observed"] else "; ".join(c["extras"][:2])) for c in ev_ct]
    else:
        simple = f"The records do not yet show whether {poss(co.name)} {len(cs)} hard commitments came true: none is confirmed delivered and none is confirmed missed."
        ev = [f"{c['promise']} (made FY{c['period']}" + (f", {c['timeframe']}" if c["timeframe"] else "") + "): unable to verify" for c in cs[:5]]
    econ = "A claim that comes true shows management can do what it says; whether it created value is a separate question that the records do not answer for any of these commitments."
    unp = "Delivery of commitments without later evidence is unresolved, not failed. Reported progress is not an economic result, and a regulatory filing is not an approval."
    mon = ["Later-report evidence for each unresolved commitment.", "Any economic outcome management attributes to a delivered commitment."]
    allow = {v for c in cs for _, v, _ in c["observed"]}
    return Result("Correct", mk_answer(simple, ev, econ, unp, mon, [dpf("Hard commitments", len(cs), "FY20–latest", "count"), dpf("Target level reported reached", len(reached), "latest", "count"), dpf("Economic outcomes confirmed", 0, "FY20–latest", "count")]), ["rebuilt from the commitment evidence (Sun Pharma: the corrected, approved evidence); the legacy card used a stale register subset"], None, allow, ["Approved answers: promises and delivery" if co.key == "sun_pharma" else "Commitments register"])


def window_projects(co: Co, lo: int, hi: int) -> list[dict]:
    out = []
    for p in (co.j("projects/projects_registry.json") or {}).get("projects", []):
        st = (p.get("assessment") or {}).get("execution_status")
        ref = (p.get("source_references") or [{}])[0]
        y = fyn(ref.get("period") or (p.get("assessment") or {}).get("period"))
        if st in ("operational", "partially_operational", "commissioned") and y and lo <= y <= hi and len(str(p.get("project_name"))) > 12:
            out.append({"name": pname(str(p["project_name"]), 140), "status": st.replace("_", " "), "fy": y, "page": ref.get("page")})
    return sorted(out, key=lambda x: (-x["fy"], x["name"]))


def h_last3(co: Co, qid: str) -> Result:
    L = co.latest_year
    lo = L - 2
    cs = hard_commitments(co)
    inwin = [c for c in cs if c["has_evidence"] and any(lo <= y <= L for y, _, _ in c["observed"]) or (c["has_evidence"] and not c["observed"] and lo <= c["period"] + 1 <= L)]
    projs = window_projects(co, lo, L)
    deals = [d for d in (co.j("economic_attribution/economic_attribution_intelligence.json") or {}).get("cases", []) if d.get("action_type") == "acquisition" and d.get("deployment_state") == "COMPLETED_TRANSACTION" and any(lo <= (fyn(p) or 0) <= L for p in d.get("deployment_periods", [])) and re.search(r"[A-Z][a-z]+ [A-Z]|Ltd|Limited|Corporation", str(d.get("action_description")))]
    if not (inwin or projs or deals):
        return defer(f"no commitment progress, project or transaction dated FY{lo}–FY{L} in the records")
    bits = []
    if inwin:
        reached = [c for c in inwin if c["class"] == "reached"]
        bits.append(f"{len(inwin)} hard commitment{'s' if len(inwin) != 1 else ''} with figures or filings reported in the window" + (f" ({len(reached)} with the target level reported reached)" if reached else ""))
    if projs:
        bits.append(f"{len(projs)} project{'s' if len(projs) != 1 else ''} reported operational or partly operational")
    if deals:
        bits.append(f"{len(deals)} completed transaction{'s' if len(deals) != 1 else ''}")
    simple = f"In FY{lo}–FY{L}, {poss(co.name)} records show " + ", ".join(bits) + ". None is linked to a confirmed economic outcome, and delivery of commitments is shown only where later reports state progress."
    ev = []
    for c in inwin:
        ev.append(f"{c['promise']}" + (f" ({c['timeframe']})" if c["timeframe"] else "") + ": " + (", ".join(f"{v}% in FY{y}" + (" (calculated)" if cal else "") for y, v, cal in c["observed"] if lo <= y <= L) or "; ".join(c["extras"][:1])) + ".")
    for p in projs[:4]:
        ev.append(f"Reported {p['status']} (FY{p['fy']}): {p['name']}" + (f" — Annual report FY{p['fy']}, p.{p['page']}" if p.get("page") else "") + ".")
    for d in deals[:2]:
        ev.append(f"Completed transaction: {tidy(d['action_description'])[:110]} (FY{fyn(d['deployment_periods'][0])}).")
    econ = "Recent delivery shows what was actually executed in the period investors can still act on; it does not show what the delivery earned."
    unp = "Projects reported operational are not shown to have reached expected output or returns. Delivery of earlier commitments outside the three-year window is not covered by this answer; for the full record see 'What did management actually deliver?'."
    mon = ["Output, utilisation or revenue disclosed for the operational projects.", "Management's delivery statements for commitments whose deadlines fall in the next year."]
    allow = {v for c in inwin for y, v, _ in c["observed"] if lo <= y <= L}
    return Result("Regenerate", mk_answer(simple, ev, econ, unp, mon, [dpf("Window", f"FY{lo}–FY{L}", "last three reported years", "period covered")]), [f"built deterministically for the exact window FY{lo}–FY{L}; the whole-record delivery answer is NOT a substitute"], None, allow, ["Projects registry", "Commitments", "Capital-allocation ledger"])


# ── Family: execution, projects, capacity, commentary ──
SPECULATIVE = re.compile(r"\b(could plausibly|may therefore|may indicate|could convert|are intended to|is intended to|could provide optionality|could reflect|may increase future|may expand|could expand|might)\b", re.I)
GROWTH_LIST = re.compile(r"FY\d{2} [+-]\d+(?:\.\d+)?%")


def money_points(sentence: str) -> list[float]:
    return [float(m.group(1).replace(",", "")) for m in re.finditer(r"₹\s?(\d[\d,]*(?:\.\d+)?)\s*crore", sentence)]


def mixes_reporting_bases(sentence: str, co: Co) -> bool:
    """True if the sentence compares figures that the records report on different (or unstated vs stated) bases."""
    pts = money_points(sentence)
    if len(pts) < 2:
        return False
    bases: set[str] = set()
    for g, m in (("revenue_and_income", "revenue"), ("revenue_and_income", "pat"), ("balance_sheet_strength", "total_assets"), ("balance_sheet_strength", "net_worth")):
        for p in co.series(g, m):
            if any(abs(p["v"] - v) <= max(1.0, p["v"] * 0.004) for v in pts):
                bases.add(p["basis"])
    return len(bases) > 1


def clean_hybrid_text(text: str, co: Co, notes: list[str], where: str) -> str:
    """Keep only sentences the records support: drop speculation about benefits, growth lists that cannot be verified, and
    comparisons across reporting bases. What is dropped is recorded in the candidate's notes."""
    out = []
    for sent in re.split(r"(?<=[.;])\s+(?=[A-Z0-9(])", tidy(text)):
        if SPECULATIVE.search(sent) and not re.search(r"\b(not|no|cannot)\b[^.;]{0,25}\b(?:" + SPECULATIVE.pattern[3:-3] + r")\b", sent, re.I):
            notes.append(f"{where}: removed speculative sentence “{clip(sent, 90)}”")
            continue
        if GROWTH_LIST.search(sent):
            notes.append(f"{where}: removed unverifiable growth list “{clip(sent, 90)}”")
            continue
        if mixes_reporting_bases(sent, co):
            notes.append(f"{where}: removed comparison across reporting bases “{clip(sent, 90)}”")
            continue
        out.append(sent)
    return " ".join(out).replace("-₹", "₹")


def h_review_hybrid(co: Co, qid: str) -> Result:
    """The existing hybrid answers: inspect, then keep only what the evidence supports."""
    e = co.hybrid.get(qid)
    if not e or e.get("status") != "PASS" or e.get("coverage") != "COMPLETE":
        return defer("no PASS/COMPLETE hybrid answer")
    a = copy.deepcopy(e["answer"])
    notes = ["existing hybrid answer reviewed (PASS/COMPLETE is not treated as approval)"]
    rels = a.get("relationships", [])
    keep = [r for r in rels if isinstance(r, dict) and r.get("causal_confidence") == "SUPPORTED" and r.get("acceptance") == "ACCEPT"]
    if len(keep) != len(rels):
        notes.append(f"dropped {len(rels) - len(keep)} of {len(rels)} relationship records that were suppressed, unsupported or only plausible; kept {len(keep)} supported ones")
    a["relationships"] = keep
    claims = a.get("claims", [])
    ck = [c for c in claims if not isinstance(c, dict) or c.get("final_acceptance_status") == "ACCEPT"]
    if len(ck) != len(claims):
        notes.append(f"dropped {len(claims) - len(ck)} claims that were not accepted")
    a["claims"] = ck
    for f in ("simple_answer", "what_may_mean_economically", "what_is_not_yet_proven", "why_it_matters", "investor_interpretation"):
        if isinstance(a.get(f), str):
            a[f] = clean_hybrid_text(a[f], co, notes, f)
    a["what_evidence_shows"] = [t for t in (clean_hybrid_text(x, co, notes, "evidence") for x in a.get("what_evidence_shows", [])) if t]
    a["what_to_monitor"] = [tidy(x) for x in a.get("what_to_monitor", [])]
    a["key_points"] = [t for t in (clean_hybrid_text(x, co, notes, "key point") for x in a.get("key_points", [])) if t]
    framework = "Execution or deployment shows what was done, not what it earned; any link to results has to come from disclosure that ties the action to a measured outcome."
    for f in ("what_may_mean_economically", "why_it_matters", "investor_interpretation"):
        if len(a.get(f, "")) < 60:
            a[f] = (a.get(f, "") + " " + framework).strip()
    # a PACP-incomplete family is validated with the global checks plus the M59 execution guards
    changed = a != e["answer"]
    return Result("Correct" if changed else "Reuse", a, notes, None, set(), ["Existing hybrid answer"])


RETURN_OF_CAPITAL = {"dividend": "dividends", "share_buyback": "share buybacks", "debt_repayment": "debt or lease repayments"}
DEPLOYED_KINDS = {"acquisition", "subsidiary_investment", "organic_capex", "capacity_expansion", "research_and_development", "technology_investment", "working_capital", "equity_issuance", "retained_cash"}


def h_value_created(co: Co, qid: str) -> Result:
    """Capital allocation outcomes: returns of capital are transactions, not demonstrated value creation."""
    cases = [c for c in (co.j("economic_attribution/economic_attribution_intelligence.json") or {}).get("cases", []) if c.get("source_system") == "capital_allocation_outcomes" and c.get("action_type") in RETURN_OF_CAPITAL | {k: k for k in DEPLOYED_KINDS}]
    if len(cases) < 3:
        return defer("fewer than three capital allocations in the ledger")
    ret = [c for c in cases if c["action_type"] in RETURN_OF_CAPITAL]
    dep = [c for c in cases if c["action_type"] not in RETURN_OF_CAPITAL]
    observed = [c for c in dep if str(c.get("operating_outcome_type")) not in ("unknown", "none_disclosed", "None")]
    kinds = join_list(sorted({RETURN_OF_CAPITAL[c["action_type"]] for c in ret}))
    dkinds = join_list(sorted({c["action_type"].replace("_", " ").replace("research and development", "R&D") for c in dep}))
    n, r, d = len(cases), len(ret), len(dep)
    simple = f"The records do not show that any of {poss(co.name)} {n} recorded capital allocations created value." + (f" {r} {'is a' if r == 1 else 'are'} return{'' if r == 1 else 's'} of capital or repayment{'' if r == 1 else 's'} ({kinds}): the cash movement is confirmed, but paying out or repaying is not evidence that the capital earned a return." if r else "") + (f" For the other {d} ({dkinds}), no financial outcome is disclosed." if d else "")
    if observed:
        simple += f" {len(observed)} {'has' if len(observed) == 1 else 'have'} an observed operating effect without a measured financial return."
    ev = []
    if r:
        ev.append(f"Returns of capital and repayments confirmed as transactions ({r} of {n}): {kinds}. These move cash to shareholders or lenders; they do not show what the business earned.")
    if d:
        ev.append(f"Capital deployed with no disclosed financial outcome ({d - len(observed)} of {n}): {dkinds}.")
    if observed:
        ev.append(f"Observed operating effect, no financial return measured ({len(observed)} of {n}): " + "; ".join(clip(tidy(str(c['action_description'])), 100) for c in observed[:2]) + ".")
    ev.append("Reported group results moved over the same years, but the records do not link any of that change to a specific allocation.")
    econ = "Value is created when capital earns more than it costs. Dividends, buybacks and repayments change who holds the cash or reduce obligations, which can be sensible, but they say nothing about what the business earned on the capital it kept."
    unp = "Returns on acquisitions, capex and working capital are not reported at the level of a single allocation, so which investments created value cannot be identified from the records."
    mon = ["Disclosure of the revenue, margin or cash contribution of acquisitions and large capex programmes.", "Return on capital employed on a consistent basis."]
    return Result("Regenerate", mk_answer(simple, ev, econ, unp, mon, [dpf("Capital allocations recorded", n, "FY20–latest", "count"), dpf("Allocations with a measured financial return", 0, "FY20–latest", "count")]), ["rebuilt from the capital-allocation ledger; dividends, buybacks and repayments are no longer counted as demonstrated value creation (the legacy answer called them 'confirmed outcomes')"], None, {n, r, d, len(observed)}, ["Capital-allocation ledger"])


def h_execution(co: Co, qid: str) -> Result:
    e = co.hybrid.get(qid)
    if not e or e.get("status") != "PASS":
        return defer("no PASS/COMPLETE hybrid answer")
    a = e["answer"]
    t = " ".join([a.get("simple_answer", ""), *a.get("what_evidence_shows", [])])
    m_n, m_x = re.search(r"Of (\d+) tracked", t), re.search(r"(\d+) (?:have )?(?:reached )?(?:full execution|completed or operational)", t)
    m_o = re.search(r"(\d+) (?:has|have) an observed operating outcome|(\d+) have an observed operating outcome", t)
    if not (m_n and m_x):
        return defer("the initiative counts cannot be read from the existing answer")
    n, x = int(m_n.group(1)), int(m_x.group(1))
    out = int(next(g for g in (m_o.groups() if m_o else ()) if g) if m_o and any(m_o.groups()) else 0)
    live = [p for p in (co.j("projects/projects_registry.json") or {}).get("projects", []) if (p.get("assessment") or {}).get("execution_status") in ("operational", "partially_operational")]
    simple = f"Of {n} management initiatives tracked for {co.name}, {x} {'is' if x == 1 else 'are'} recorded as completed or operational and {out} {'has' if out == 1 else 'have'} a recorded operating outcome; none has a recorded economic consequence" + (f" (the projects registry separately lists {len(live)} operational or partly operational projects)" if live and x == 0 else "") + ". That describes what the records capture, not proof that nothing else happened: outcomes appear only where a report ties them to an initiative."
    ev = [f"{n} initiatives tracked; {x} recorded as completed or operational, {out} with a recorded operating outcome, 0 with a recorded economic consequence."]
    if live:
        ev.append(f"Separately, the projects registry lists {len(live)} projects as operational or partly operational; the initiative tracker does not link them to initiatives or to results.")
    for line in a.get("what_evidence_shows", []):
        if line.startswith("Operating outcomes observed"):
            ev.append(clean_hybrid_text(line.split(";")[0].replace("Operating outcomes observed: 1 — ", "Operating outcome recorded: "), co, [], "evidence") + ".")
    econ = "Execution shows management did what it set out to do; it becomes evidence of value only when a measured outcome (output, margin, cash) is tied to the initiative. Group results moving over the same period is not that link."
    unp = "The records hold no initiative-level output, margin or cash result, so a missing outcome is a limit of disclosure and tracking, not a finding that nothing happened."
    mon = ["Initiative-level output, utilisation or margin disclosure for completed projects.", "Management statements that link a completed initiative to a measured result."]
    return Result("Correct", mk_answer(simple, ev, econ, unp, mon, [dpf("Initiatives tracked", n, "FY20–latest", "count"), dpf("Initiatives with a recorded economic consequence", 0, "FY20–latest", "count")]), ["rewritten: the legacy answer ('none reached completed execution', 'no outcome observed') conflated absence of recorded outcomes with evidence that none occurred and ignored the operational projects in the registry"], None, {n, x, out, len(live)}, ["Management progression records", "Projects registry"])


def h_projects(co: Co, qid: str) -> Result:
    projs = [p for p in (co.j("projects/projects_registry.json") or {}).get("projects", []) if len(str(p.get("project_name"))) > 12]
    if len(projs) < 3:
        return defer("fewer than three projects in the registry")
    by: dict[str, list[dict]] = defaultdict(list)
    for p in projs:
        by[str((p.get("assessment") or {}).get("execution_status") or "unknown")].append(p)
    underway = [p for k in ("partially_operational", "under_execution", "commissioned", "funded") for p in by.get(k, [])]
    live = by.get("operational", [])
    unver = by.get("unable_to_verify", [])
    other = len(projs) - len(underway) - len(live) - len(unver)
    simple = (f"Of the {len(projs)} projects in {poss(co.name)} records, {len(underway)} {'is' if len(underway) == 1 else 'are'} still in progress or partly operational, {len(live)} {'is' if len(live) == 1 else 'are'} reported operational, and {len(unver)} cannot be verified from the records"
              + (f" ({other} more {'is' if other == 1 else 'are'} paused or superseded)." if other else "."))
    def line(p: dict) -> str:
        ref = (p.get("source_references") or [{}])[0]
        st = str((p.get("assessment") or {}).get("execution_status")).replace("_", " ")
        return f"{pname(str(p['project_name']))} — {st}" + (f" (Annual report FY{fyn(ref.get('period'))}, p.{ref.get('page')})" if ref.get("page") else "")
    key = lambda p: -(fyn(((p.get("source_references") or [{}])[0]).get("period")) or 0)  # noqa: E731
    ev = [line(p) for p in sorted(underway, key=key)[:3]] + [line(p) for p in sorted(live, key=key)[:2]]
    counts = {"in progress or partly operational": len(underway), "operational": len(live), "unable to verify": len(unver)}
    econ = "Projects are where capital becomes capacity or capability; their status shows execution, and their returns show whether the spending was worth it."
    unp = f"{len(unver)} projects cannot be verified from the records. Cost, output, utilisation and returns are not disclosed for the operational projects, so execution is shown but payoff is not."
    mon = ["Commissioning dates, output and utilisation of the operational projects.", "Status updates for projects that cannot currently be verified."]
    return Result("Regenerate", mk_answer(simple, ev, econ, unp, mon, [dpf("Projects tracked", len(projs), "FY20–latest", "count")] + [dpf(k.capitalize(), n, "latest", "count") for k, n in counts.items()]), ["rebuilt from the projects registry; the legacy card listed projects 'with recent execution evidence' without their status"], None, set(), ["Projects registry"])


def h_capacity(co: Co, qid: str) -> Result:
    d = co.j("capacity/capacity_assessments.json") or {}
    items = d.get("assessments", [])
    nonphys = re.compile(r"headcount|field force|employee|skill|training|customer base|workforce", re.I)
    named = [i for i in items if i.get("capacity_name") and i.get("execution_status") not in (None, "") and not nonphys.search(str(i["capacity_name"])) and (fyn(i.get("latest_period")) or 0) >= co.latest_year - 2]
    if len(named) < 2:
        return defer("fewer than two physical capacity records seen in the last three reports")
    by = Counter(str(i["execution_status"]).replace("_", " ") for i in named)
    simple = f"The records track {len(named)} capacity items for {co.name}: " + ", ".join(f"{n} {k}" for k, n in by.most_common()) + ". None shows a demonstrated change in utilisation or a financial effect."
    rank = {"operational": 0, "partially_operational": 1, "delayed": 1, "under_execution": 1, "commissioned": 1, "funded": 2, "announced": 3, "unable_to_verify": 4, "superseded": 5}
    named = sorted(named, key=lambda i: (rank.get(str(i["execution_status"]), 4), -(fyn(i.get("latest_period")) or 0)))
    ev = [f"{clip(tidy(i['capacity_name']), 120)} — {str(i['execution_status']).replace('_', ' ')} (last seen FY{fyn(i.get('latest_period'))})." for i in named[:5]]
    econ = "Capacity changes matter when they convert into output and returns; the records show the capacity actions, not the conversion."
    unp = "Observed business and financial effects of the capacity items are described in the records as too thin to judge. Utilisation, throughput and incremental revenue are not disclosed."
    mon = ["Utilisation or throughput disclosures for the capacity items.", "Commissioning updates for items not yet marked operational."]
    return Result("Regenerate", mk_answer(simple, ev, econ, unp, mon, [dpf("Capacity items tracked", len(named), "FY20–latest", "count")]), ["rebuilt from the capacity assessments; the legacy card substituted unrelated commitments for capacity evidence"], None, set(), ["Capacity registry and assessments"])


def h_commentary(co: Co, qid: str) -> Result:
    d = co.j("management_commentary/commentary_themes.json") or {}
    th = [t for t in d.get("commentary_themes", []) if t.get("current_emphasis")]
    if len(th) < 3:
        return defer("fewer than three commentary themes with a stated emphasis")
    pos = Counter(str(t.get("current_position")).replace("_", " ") for t in th)
    def complete(t: dict) -> str:
        raw = tidy(str(t["current_emphasis"]))
        if not re.search(r"[.!?]$", raw):  # the stored emphasis is cut off; keep only whole sentences or clauses before the cut
            k = max(raw.rfind("; "), raw.rfind(". "))
            raw = raw[:k] if k > 40 else ""
        w = whole(raw, 260) if raw else ""
        w = w if not w or w.endswith((".", "!", "?")) else w + "."
        return w if w and re.search(r"[.!?)]$", w) and len(w) <= 300 and (len(raw) <= 260 or raw.count(". ") or raw.count("; ")) else ""
    ranked = sorted(th, key=lambda t: (str(t.get("current_position")) not in ("stable_priority", "strengthened"), -(fyn(t.get("latest_period")) or 0)))
    top: list[dict] = []
    for t in ranked:
        w = set(re.findall(r"[a-z]{4,}", complete(t).lower()))
        if w and all(len(w & set(re.findall(r"[a-z]{4,}", complete(u).lower()))) / len(w | set(re.findall(r"[a-z]{4,}", complete(u).lower()))) < 0.5 for u in top):
            top.append(t)
        if len(top) == 4:
            break
    if len(top) < 2:
        return defer("the stored commentary emphasis is cut off for too many themes to quote reliably")
    simple = f"Management's commentary across FY{min(fyn(t.get('first_observed_period')) or 99 for t in th)}–FY{co.latest_year} returns to {len(th)} themes; {pos.get('stable priority', 0)} {'is a' if pos.get('stable priority', 0) == 1 else 'are'} stable priorit{'y' if pos.get('stable priority', 0) == 1 else 'ies'}, {pos.get('strengthened', 0)} {'has' if pos.get('strengthened', 0) == 1 else 'have'} strengthened and {pos.get('newly introduced', 0)} {'is' if pos.get('newly introduced', 0) == 1 else 'are'} newly introduced."
    span = lambda t: (f"FY{fyn(t.get('first_observed_period'))}" if fyn(t.get('first_observed_period')) == fyn(t.get('latest_period')) else f"FY{fyn(t.get('first_observed_period'))}–FY{fyn(t.get('latest_period'))}")  # noqa: E731
    ev = [f"{str(t.get('current_position')).replace('_', ' ').replace('observation', 'theme').capitalize()}, {span(t)}: {complete(t)}" for t in top]
    econ = "What management repeats shows where it directs attention and capital; repeated emphasis is a signal of priority, not evidence of delivery."
    unp = "Commentary is management's own account. The records do not show, theme by theme, whether the stated emphasis was followed by execution or results, and newly introduced themes have little follow-through yet."
    mon = ["Whether newly introduced themes are followed by projects, capital or disclosed results.", "Themes that disappear from later commentary."]
    return Result("Regenerate", mk_answer(simple, ev, econ, unp, mon, [dpf("Commentary themes", len(th), "FY20–latest", "count")]), ["rebuilt from the commentary themes; the legacy card quoted a single risk statement as the answer"], None, set(), ["Management commentary themes"])


# ── Family: capital ──
def h_capex_return(co: Co, qid: str) -> Result:
    # The ledger lists organic capex with a multi-year "deployment_periods" span, but its amount is the latest-year
    # cash-flow capex (verified against the owner-earnings bridge). Only a matching single-year figure is used.
    cases = (co.j("economic_attribution/economic_attribution_intelligence.json") or {}).get("cases", [])
    amts = [c["amount_inr_cr"] for c in cases if c.get("action_type") == "organic_capex" and c.get("deployment_state") == "DEPLOYED" and isinstance(c.get("amount_inr_cr"), (int, float)) and c["amount_inr_cr"] > 0]
    ob = co.j("financials/investor_financial_modules/owner_earnings_bridge.json") or {}
    rows = [r for v in ob.values() if isinstance(v, list) for r in v if isinstance(r, dict) and isinstance(r.get("total_identified_capex"), (int, float))]
    match = [(fyn(r["fiscal_year"]), abs(r["total_identified_capex"])) for r in rows if amts and abs(abs(r["total_identified_capex"]) - amts[0]) < 0.5]
    if not amts or not match:
        return defer("the ledger's organic capex amount cannot be tied to a single reporting year in the cash-flow records")
    fy, amt = max(match)
    live = sum(1 for p in (co.j("projects/projects_registry.json") or {}).get("projects", []) if (p.get("assessment") or {}).get("execution_status") in ("operational", "partially_operational"))
    roi = (co.j("financials/investor_financial_modules/capital_allocation_roi_ledger.json") or {}).get("entries", [])
    meas = Counter(str(r.get("roi_measurability_status")) for r in roi).most_common(1)
    rev = co.run("revenue_and_income", "revenue")
    simple = f"The records do not establish a return on {poss(co.name)} capital spending. Capital expenditure in FY{fy} was {inr(amt)}, and {live} project{'s are' if live != 1 else ' is'} reported operational or partly operational, but no output, utilisation or site-level revenue is disclosed."
    ev = [f"Capital expenditure in FY{fy}: {inr(amt)} (cash-flow statement); earlier years are not part of this figure."]
    if meas:
        ev.append(f"The capital-allocation ledger marks the return as '{meas[0][0].replace('_', ' ')}'.")
    if len(rev) >= 3:
        ev.append(f"Over FY{rev[0]['fy']}–FY{rev[-1]['fy']} group revenue moved from {inr(rev[0]['v'])} to {inr(rev[-1]['v'])} on a {rev[0]['basis']} basis; the records do not attribute any of that change to the capital spending.")
    econ = "A return on capex needs the extra profit or cash a project generates compared with its cost; without project-level output and revenue, capital spending and company growth cannot be linked."
    unp = "The maintenance-versus-growth capex split is not disclosed, project costs and outputs are not given, and group results cannot be traced to specific sites. Return on capital employed is not available in the records."
    mon = ["Project-level output, utilisation or revenue for the capacity added.", "Disclosure of maintenance versus growth capex.", "Return on capital employed on a consistent basis."]
    return Result("Regenerate", mk_answer(simple, ev, econ, unp, mon, [dpf("Capital expenditure", f"{amt:,.0f}", f"FY{fy}", "INR crore")]), ["rebuilt from the cash-flow capex; the ledger's multi-year period label does not apply to its amount (it is one year)"], None, {amts[0], amt}, ["Cash-flow statement", "Projects registry"])


def h_incentives(co: Co, qid: str) -> Result:
    own = co.j("ownership_evolution.json") or {}
    ph = [p for p in own.get("promoter_holding", []) if p.get("value") not in (None, "") and 0 < float(p["value"]) <= 100]
    if not ph:
        return defer("no usable promoter-holding history; compensation and ESOP terms are not in the records (the legacy card is 'not supported')")
    ph = sorted(ph, key=lambda p: fyn(p["year"]) or 0)
    pledge = own.get("pledge", [])
    simple = f"Promoters held about {float(ph[-1]['value']):.1f}% of {co.name} in FY{fyn(ph[-1]['year'])}" + ((f", unchanged since FY{fyn(ph[0]['year'])}" if abs(float(ph[0]['value']) - float(ph[-1]['value'])) < 0.05 else f" (FY{fyn(ph[0]['year'])}: {float(ph[0]['value']):.1f}%)") if len(ph) > 1 else "") + ", so ownership is concentrated and promoter interests are tied to the share price. Pay and share-based incentives for management are not in the records, so what management is rewarded for cannot be assessed."
    ev = [f"Promoter holding: " + ", ".join(f"{float(p['value']):.1f}% (FY{fyn(p['year'])})" for p in ph) + " (shareholding pattern).", "No promoter share pledging is recorded." if not pledge else f"{len(pledge)} pledge records are present."]
    econ = "Concentrated ownership can align management with other shareholders, or concentrate control; what management is paid to achieve is the more direct test of incentives."
    unp = "Management remuneration, performance conditions and employee share-option terms are not available, so the incentive structure is unknown. High promoter ownership is not by itself evidence of good alignment."
    mon = ["Management remuneration and performance conditions in the next annual report.", "Any change in promoter holding or pledging."]
    return Result("Correct", mk_answer(simple, ev, econ, unp, mon, [dpf("Promoter holding", f"{float(ph[-1]['value']):.1f}%", f"FY{fyn(ph[-1]['year'])}", "percent of shares")]), ["rebuilt from the ownership records"], None, {float(p["value"]) for p in ph}, ["Shareholding pattern"])


# ── Family: risks and diligence ──
def risk_themes(co: Co) -> list[dict]:
    return (co.j("gold/risk_evolution_timeline.json") or {}).get("risk_themes", [])


def h_regulatory(co: Co, qid: str) -> Result:
    # themes whose SUBJECT is regulation or governance (matched on the theme's own name, never on words inside its description)
    th = [t for t in risk_themes(co) if re.search(r"regulat|governance|complian|legal|litigation|ethic|licens", str(t.get("theme")), re.I)]
    L = co.latest_year
    if not th:
        return Result("Regenerate", mk_answer(f"No regulatory or governance risk theme is recorded for {co.name} in the risk records.", ["The risk record tracks no theme whose subject is regulation, compliance or governance."], "The absence of a recorded risk theme is not evidence that the risk is absent; it shows what the filings emphasised.", "Regulatory exposure that filings mention only briefly may not form a tracked theme.", ["Regulatory disclosures in the next annual report."]), ["no regulatory theme in the records"], None, set(), ["Risk evolution timeline"])
    PAST = {"WORSENING": "worsened", "RECURRING": "recurred", "IMPROVING": "was improving", "NEW": "was disclosed", "NOT_RECONFIRMED": "was disclosed", "MITIGATION_STARTED": "saw mitigation start"}
    NOW = {"WORSENING": "currently worsening", "RECURRING": "recurring", "NEW": "first disclosed in the latest year", "IMPROVING": "improving", "MITIGATION_STARTED": "with mitigation started"}
    def active(t: dict) -> bool:
        return (fyn(t.get("latest_seen_period")) or 0) >= L and str(t.get("current_state")) != "NOT_RECONFIRMED"
    def phrase(t: dict) -> str:
        a, b = fyn(t.get("first_seen_period")), fyn(t.get("latest_seen_period"))
        span = f"FY{a}–FY{b}" if a != b else f"FY{a}"
        st = str(t.get("current_state"))
        if active(t):
            return f"{NOW.get(st, st.lower().replace('_', ' '))}, disclosed {span}"
        return f"{PAST.get(st, 'was disclosed')} in {span}; not reconfirmed since"
    cur = [t for t in th if active(t)]
    old = [t for t in th if not active(t)]
    nm = lambda t: str(t["theme"]).replace("_", " ")  # noqa: E731
    simple = (f"{plural(len(cur), 'of')} {poss(co.name)} {len(th)} regulatory or governance risk theme{'s' if len(th) != 1 else ''} {'is' if len(cur) == 1 else 'are'} active in the FY{L} filings" if False else
              f"{len(cur)} of {poss(co.name)} {len(th)} regulatory or governance risk theme{'s' if len(th) != 1 else ''} {'is' if len(cur) == 1 else 'are'} active in the FY{L} filings")
    simple += (": " + "; ".join(f"{nm(t)} ({phrase(t).split(',')[0]})" for t in cur[:3]) if cur else "")
    simple += (f". {len(old)} {'was' if len(old) == 1 else 'were'} disclosed earlier but not reconfirmed in the latest year, which does not show {'it was' if len(old) == 1 else 'they were'} resolved." if old else ".")
    ev = [f"{nm(t).capitalize()}: {phrase(t)}." for t in th[:6]]
    resp = sum(1 for t in th if any(str(e.get("management_response") or "").strip() for e in t.get("timeline", [])))
    ev.append(f"{resp} of these {len(th)} theme{'s' if len(th) != 1 else ''} {'has' if (resp == 1 or len(th) == 1) else 'have'} a recorded management response.")
    econ = "Regulatory and governance risks can restrict operations or raise costs; whether they matter depends on how exposed the business is and how management responds."
    unp = "The financial impact of these risks is not established in the records, and a risk not reconfirmed in the latest year is not shown to have been resolved."
    mon = ["Whether each active theme is reconfirmed, mitigated or resolved in the next annual report.", "Management responses to the active themes."]
    return Result("Regenerate", mk_answer(simple, ev, econ, unp, mon, [dpf("Regulatory or governance risk themes", len(th), f"FY20–FY{L}", "count"), dpf("Active in latest year", len(cur), f"FY{L}", "count")]), ["rebuilt from the risk-evolution timeline, matching themes on their own names and applying each theme's last-seen year; the legacy card called governance 'worsening' where the approved risk answer says it is not reconfirmed"], None, set(), ["Risk evolution timeline", "Approved answer: What could go wrong?"])


def gaps_for(co: Co) -> list[tuple[str, str, str]]:
    """(gap, why it matters, ask) — each derived from the records, none invented."""
    g: list[tuple[str, str, str]] = []
    br = bridge_row(co)
    if not co.bank and br and str(br.get("maintenance_growth_split_status")) == "missing":
        g.append(("the maintenance versus growth split of capital spending", "owner earnings can only be estimated, not measured", "How much of capital spending maintains existing capacity and how much adds new capacity?"))
    rev = co.series("revenue_and_income", "revenue")
    unk = sum(1 for p in rev if p["basis"] == "unknown")
    if unk:
        g.append((f"the reporting basis (consolidated or standalone) for {unk} of {len(rev)} years of revenue", "year-on-year comparisons across those years cannot be trusted", "Please confirm the basis of each year's reported figures and restate where it changed."))
    if not co.series("return_on_capital", "roce"):
        g.append(("return on capital employed", "returns on all capital cannot be assessed", "What is the return on capital employed, and how has it changed?"))
    m = co.j("company_model/company_model.json") or {}
    if (m.get("economic_engines") or {}).get("coverage_status") != "SUPPORTED":
        g.append(("a revenue breakdown by product, segment or region", "the drivers of growth cannot be sized", "How is revenue split by product, segment and region, and what is each part's growth?"))
    own = co.j("ownership_evolution.json") or {}
    g.append(("management remuneration and share-based incentive terms", "what management is rewarded for is unknown", "What are management's performance conditions and incentive terms?"))
    if not co.bank:
        wc = (co.j("financials/investor_financial_modules/working_capital_quality_drilldown.json") or {}).get("drilldown", [])
        if wc and wc[-1].get("inventory_days") is None:
            g.append(("inventory and payable days for the latest year", "the cash conversion cycle cannot be completed", "Please disclose inventory and payables so the full cash conversion cycle can be computed."))
    cs = hard_commitments(co)
    if any(deadline_state(c, co.latest_year) == "passed" and not c["has_evidence"] for c in cs):
        g.append(("a delivery statement for commitments whose deadline has passed", "the commitments remain unverified, not delivered or missed", "Were the commitments whose deadlines have passed delivered, and what is the evidence?"))
    if co.bank:
        g.append(("bank-specific measures such as capital adequacy, asset quality and net interest margin", "a bank cannot be assessed on industrial cash-flow measures", "What do capital adequacy, asset quality and net interest margin show over time?"))
    return g


def h_disclosure(co: Co, qid: str) -> Result:
    g = gaps_for(co)
    if len(g) < 2:
        return defer("fewer than two documented disclosure gaps")
    simple = f"The most important disclosures missing for {co.name} are " + "; ".join(x[0] for x in g[:3]) + "."
    ev = [f"Missing: {x[0]} — {x[1]}." for x in g[:6]]
    econ = "Missing disclosure limits what any investor can check; each gap below limits a specific kind of judgement rather than showing that something is wrong."
    unp = "These are gaps in the stored records and may exist in documents Prometheus has not processed. A gap is not evidence of concealment."
    mon = ["Whether the next annual report fills any of these gaps."]
    return Result("Regenerate", mk_answer(simple, ev, econ, unp, mon), ["derived from the records' own limitations and warnings, each tied to the check it prevents; the legacy card was shared verbatim across five questions"], None, set(), ["Financial modules", "Company model", "Commitments"])


def h_ir(co: Co, qid: str) -> Result:
    g = gaps_for(co)
    if len(g) < 2:
        return defer("fewer than two grounded questions")
    simple = f"The most useful questions to put to {poss(co.name)} investor relations team are: " + " ".join(f"({i + 1}) {x[2]}" for i, x in enumerate(g[:3]))
    ev = [f"Question {i + 1}: {x[2]} (because {x[1]})." for i, x in enumerate(g[:6])]
    econ = "Good questions target the gaps that limit the most important judgements; answers could move an assessment of earnings quality, returns or management delivery."
    unp = "The questions are prompts drawn from gaps in the records. Management may already have answered some in documents Prometheus has not processed."
    mon = ["Management's answers, and whether they are consistent with the annual report."]
    return Result("Regenerate", mk_answer(simple, ev, econ, unp, mon), ["derived from the same documented gaps, phrased as questions"], None, set(), ["Financial modules", "Company model", "Commitments"])


def h_clarify(co: Co, qid: str) -> Result:
    items: list[str] = []
    cs = hard_commitments(co)
    if co.key == "sun_pharma" and cs:
        fell = [c for c in cs if len(c["observed"]) >= 2 and c["observed"][-1][1] < c["observed"][-2][1]]
        for c in fell:
            items.append(f"Why the reported figure for '{c['promise']}' fell from {c['observed'][-2][1]}% in FY{c['observed'][-2][0]} to {c['observed'][-1][1]}% in FY{c['observed'][-1][0]}, and whether the metric definition changed.")
        items += [f"The filing date and approval status behind '{c['promise']}'." for c in cs if c["class"] == "partly"]
    else:
        passed = [c for c in cs if deadline_state(c, co.latest_year) == "passed" and not c["has_evidence"]]
        items += [f"Whether '{lab(c)}' was delivered." for c in passed[:3]]
    for q in CERTIFIED:
        a = co.approved(q)
        if a and "status disagreement" in json.dumps(a).lower():
            pass
    rev = co.series("revenue_and_income", "revenue")
    if co.key == "ujjivan" and sum(1 for p in rev if p["basis"] == "unknown"):
        items.append("How the FY24 merger affects year-on-year comparisons of reported figures.")
    if len(items) < 2:
        return defer("fewer than two grounded points that need clarification")
    simple = f"Management most needs to clarify, for {co.name}: " + " ".join(f"({i + 1}) {t}" for i, t in enumerate(items[:3]))
    ev = [f"{i + 1}. {t}" for i, t in enumerate(items[:6])]
    econ = "Each point is where management's own disclosures are ambiguous or stop short of a conclusion; a clear answer would let investors resolve it instead of holding it open."
    unp = "The points come from gaps and apparent inconsistencies in what has been disclosed; management may have explained some elsewhere. They are not allegations."
    mon = ["Whether the next annual report or earnings call addresses these points."]
    allow = {v for c in cs for _, v, _ in c["observed"]}
    return Result("Regenerate", mk_answer(simple, ev, econ, unp, mon), ["derived from documented inconsistencies and open items; the legacy card repeated the shared question list"], None, allow, ["Approved answers", "Commitments", "Financial records"])


def h_unresolved(co: Co, qid: str) -> Result:
    pts: list[tuple[str, str]] = []
    for q, lab in (("what-has-management-promised", "Management promises"), ("what-did-management-actually-deliver", "Management delivery"), ("what-could-go-wrong", "Risks"), ("how-is-capital-allocated", "Capital allocation"), ("how-good-is-management", "Management intelligence")):
        a = co.approved(q)
        if a and a.get("what_is_not_yet_proven"):
            s = str(a["what_is_not_yet_proven"])
            sents = [tidy(x) for x in re.split(r"(?<=[.])\s+(?=[A-Z])", s)]
            good = [x for x in sents if len(x) >= 50 and not x.startswith("(") and "≠" not in x and not re.search(r"\w/\d+\s", x)]
            if good:
                g0 = good[0]
                if "…" in g0:  # the stored sentence is cut off; keep only its complete clauses
                    g0 = g0[: g0.find("…")]
                    g0 = g0[: g0.rfind(";") + 1] if ";" in g0 else ""
                g0 = whole(g0, 230) if g0 else ""
                wd = set(re.findall(r"[a-z]{4,}", g0.lower()))
                dup = any(len(wd & set(re.findall(r"[a-z]{4,}", t.lower()))) / max(1, len(wd | set(re.findall(r"[a-z]{4,}", t.lower())))) > 0.45 for _, t in pts)
                if len(g0) >= 40 and not dup:
                    pts.append((lab, g0))
    if len(pts) < 3:
        return defer("fewer than three approved answers with stated unresolved points")
    simple = f"For {co.name}, the open questions the approved answers leave unresolved include: " + "; ".join(f"{lab.lower()} — {t.rstrip('.')}" for lab, t in pts[:3]) + "."
    ev = [f"{lab}: {t}" for lab, t in pts]
    econ = "Unresolved points are where more evidence would change what an investor can conclude; the list below is the evidence-backed agenda."
    unp = "Each point is taken from an approved answer's own statement of what is not yet proven. New filings could resolve or add to them."
    mon = ["Whether the next annual report resolves any of these points."]
    return Result("Regenerate", mk_answer(simple, ev, econ, unp, mon), ["compiled from the approved answers' own 'not yet proven' statements"], None, {v for c in hard_commitments(co) for _, v, _ in c["observed"]}, [f"Approved answer: {lab}" for lab, _ in pts])


def h_blocked_lens(co: Co, qid: str) -> Result:
    c = co.cards.get(qid)
    snippets = []
    if c:
        t = " ".join([c["simple_answer"], *c["key_points"]])
        snippets = re.findall(r"[^.]*\b(?:assessed as (?:weak|strong)|weakening|decisive negative|weak overall|rating)\b[^.]*\.", t, re.I)[:1]
    return block("the legacy answer is a written synthesis of unapproved model-written investor analyses and carries ratings or verdicts" + (f" (e.g. “{tidy(snippets[0])[:120]}”)" if snippets else "") + "; a certifiable answer would have to be rebuilt from approved evidence, and the deterministic Investment Panel already provides that view")


def h_defer_view(co: Co, qid: str) -> Result:
    return defer("answering requires a defined investment view or thesis to test against; none exists in approved intelligence, and a generic list of unknowns is already provided by 'What remains unresolved?'")


def h_break_thesis(co: Co, qid: str) -> Result:  # served by the vetted alias; never a pending pair
    return defer("served by the certified risk answer")


HANDLERS: dict[str, Callable[[Co, str], Result]] = {
    "what-does-company-do": h_adapt_factual, "who-are-the-customers": h_adapt_factual, "how-does-it-make-money": h_adapt_factual,
    "are-profits-converting-into-cash": h_cash, "what-is-owner-earnings": h_cash, "is-working-capital-a-concern": h_wc, "are-per-share-economics-improving": h_eps,
    "what-promise-types-dominate": h_types, "which-promises-are-overdue": h_overdue, "what-was-delivered-last-3-years": h_last3, "what-was-missed": h_missed, "did-past-claims-come-true": h_claims,
    "did-execution-lead-to-outcomes": h_execution, "what-projects-are-underway": h_projects, "how-is-capacity-changing": h_capacity, "what-is-management-commentary-saying": h_commentary,
    "which-investments-created-value": h_value_created, "what-is-the-return-on-capex": h_capex_return, "what-incentives-matter": h_incentives,
    "what-regulatory-risks-remain-active": h_regulatory, "which-disclosure-is-missing": h_disclosure, "what-evidence-would-change-the-view": h_defer_view,
    "what-needs-management-clarification": h_clarify, "what-should-i-ask-ir": h_ir, "what-remains-unresolved": h_unresolved,
    "what-is-committee-direction": h_blocked_lens, "where-does-the-committee-agree": h_blocked_lens, "where-does-the-committee-disagree": h_blocked_lens,
    "what-would-graham-worry-about": h_blocked_lens, "what-would-buffett-focus-on": h_blocked_lens, "where-would-fisher-be-curious": h_blocked_lens,
    "what-would-munger-avoid": h_blocked_lens, "how-would-lynch-explain-it": h_blocked_lens,
}
# Questions where rating language in the legacy card is a defect to *report*, not to reproduce.
FAMILY_OF = {q["id"]: cat["id"] for cat in QUESTION_CATALOG for q in cat["questions"]}
TITLE_OF = {q["id"]: q["title"] for cat in QUESTION_CATALOG for q in cat["questions"]}
FAMILY_TITLE = {cat["id"]: cat["title"] for cat in QUESTION_CATALOG}


def assess(co: Co, qid: str) -> dict:
    base = {"company": co.key, "company_name": co.name, "question_id": qid, "title": TITLE_OF[qid], "family": FAMILY_OF[qid]}
    if qid in VETTED_ALIASES or f"{co.key}:{qid}" in co.registry:
        return {**base, "status": "APPROVED", "path": "—", "reasons": ["already approved and serving" + (f" (via the certified answer {VETTED_ALIASES[qid]})" if qid in VETTED_ALIASES else "")]}
    res = HANDLERS[qid](co, qid)
    if res.answer is None:
        return {**base, "status": res.outcome or DEFER, "path": res.path, "reasons": res.reasons}
    a = res.answer
    v = validate(a, co, qid, res.allow)
    if v["failed"]:
        status = FIX
        reasons = res.reasons + [f"{k}: {v['checks'][k]['detail']}" for k in v["failed"]]
        return {**base, "status": status, "path": res.path, "reasons": reasons, "validation": v["checks"], "pacp": v["pacp"]}
    entry = {"question_id": qid, "answer": a, "status": "PASS", "coverage": "COMPLETE", "word_count": words(a)}
    return {**base, "status": READY, "path": res.path, "reasons": res.reasons, "validation": v["checks"], "pacp": v["pacp"], "sources": res.sources,
            "fingerprint": compute_content_fingerprint(a), "full_artifact_digest": compute_full_artifact_digest(a), "entry": entry}


def run(write: bool) -> list[dict]:
    registry = json.loads((ROOT / "governance" / "approval_registry.json").read_text())["approvals"]
    reg_digest_before = (ROOT / "governance" / "approval_registry.json").read_bytes()
    served_before = {c: (ac.companies_root() / c / "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json").read_bytes() for c in COMPANIES}
    out: list[dict] = []
    cos: dict[str, Co] = {}
    for key in COMPANIES:
        co = cos[key] = Co(key, registry)
        # certified questions that no catalog question genuinely stands for are registered questions in their own right
        for q, title, fam in (("what-did-management-actually-deliver", "What did management actually deliver?", "management"), ("how-good-is-management", "How good is management?", "management")):
            out.append({"company": key, "company_name": co.name, "question_id": q, "title": title, "family": fam, "status": "APPROVED", "path": "—", "reasons": ["already approved and serving"]})
        for qid in [q["id"] for cat in QUESTION_CATALOG for q in cat["questions"]]:
            out.append(assess(co, qid))
    for key, co in cos.items():  # cross-answer contradiction check
        rows_k = [r for r in out if r["company"] == key and r["status"] == READY]
        cs = hard_commitments(co)
        reached = [c for c in cs if c["class"] == "reached"]
        for r in rows_k:
            blob = " ".join([r["entry"]["answer"]["simple_answer"], *r["entry"]["answer"]["what_evidence_shows"]])
            clash = [lab(c) for c in reached if re.search(r"(?:without (?:a )?confirmation|no delivery confirmation|unverified)[^.]*" + re.escape(c["promise"][:40]), blob)]
            if clash:
                r["status"], r["reasons"] = FIX, r["reasons"] + [f"contradicts another answer: '{clash[0]}' is reported reached elsewhere but called unconfirmed here"]
    if write:
        for key in COMPANIES:
            ents = {r["question_id"]: {**r["entry"], "candidate": {"status": READY, "path": r["path"], "fingerprint": r["fingerprint"], "full_artifact_digest": r["full_artifact_digest"], "validation": {k: v["result"] for k, v in r["validation"].items()}, "pacp": r["pacp"]}} for r in out if r["company"] == key and r["status"] == READY}
            doc = {"schema_version": SCHEMA, "company_slug": key, "generated_at": datetime.now(timezone.utc).isoformat(), "mission": "M59", "note": "CANDIDATES ONLY. Not served: the app reads shadow_level3_hybrid_answers.json, and an answer is served only after its exact digest is registered by the owner via answer_certification.py --mode approve.", "ai_calls": 0, "answers": ents}
            (ac.companies_root() / key / "company_memory/ask_intrinsiciq/m59_candidate_answers.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    # safety: nothing governed was touched
    assert (ROOT / "governance" / "approval_registry.json").read_bytes() == reg_digest_before, "approval registry changed"
    for c in COMPANIES:
        assert (ac.companies_root() / c / "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json").read_bytes() == served_before[c], "served answers changed"
    return out


def summarize(rows: list[dict]) -> None:
    c = Counter(r["status"] for r in rows)
    print("pairs", len(rows), dict(c))
    fam: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        fam[r["family"]][r["status"]] += 1
    for f, cc in fam.items():
        print(f"  {f:26}", dict(cc))


# ───────────────────────────── review package ─────────────────────────────
STATUS_ORDER = [READY, FIX, DEFER, BLOCK, "APPROVED"]
STATUS_LABEL = {READY: "READY FOR APPROVAL", FIX: "NEEDS CORRECTION", DEFER: "DEFERRED", BLOCK: "BLOCKED", "APPROVED": "ALREADY APPROVED"}
CELL = {READY: "🟢 Ready", FIX: "🟠 Correct", DEFER: "⚪ Deferred", BLOCK: "🔴 Blocked", "APPROVED": "✅ Approved"}


def write_package(rows: list[dict]) -> None:
    pre = ROOT / "preview"
    pre.mkdir(exist_ok=True)
    slim = [{k: v for k, v in r.items() if k != "entry"} for r in rows]
    for r, sl in zip(rows, slim):
        if r["status"] == READY:
            a = r["entry"]["answer"]
            sl.update({"answer": a["simple_answer"], "evidence": a["what_evidence_shows"], "economics": a["what_may_mean_economically"], "unproven": a["what_is_not_yet_proven"], "monitor": a["what_to_monitor"]})
    (pre / "M59_pairs.json").write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "ai_calls": 0, "pairs": slim}, indent=2, ensure_ascii=False))

    fam_order = [c["id"] for c in QUESTION_CATALOG]
    c_all = Counter(r["status"] for r in rows)
    md = ["# M59 — Owner Review Package", "",
          f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · **AI calls: 0** · nothing registered, approved or served · candidates live in `companies/<company>/company_memory/ask_intrinsiciq/m59_candidate_answers.json`.", "",
          "| Status | Pairs |", "|---|---:|"] + [f"| {STATUS_LABEL[k]} | {c_all.get(k, 0)} |" for k in STATUS_ORDER] + [f"| **Total** | **{len(rows)}** |", "",
          "## How to review", "", "Each READY candidate below shows the investor-facing answer, its evidence, validation result and the **exact digest** that would be registered. To activate a family, authorize its digests: `python3 pipelines/m59_activate.py --families <ids> --owner-authorized \"<your note>\" --apply` (dry-run by default; refuses if any digest differs from this package).", "",
          "Pairs are grouped by question family, then question. `Path` = how the candidate was produced: **Reuse** (existing answer unchanged), **Adapt** (restructured), **Correct** (fixed from existing evidence), **Regenerate** (rebuilt deterministically from canonical records; no AI).", ""]
    by_fam: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_fam[r["family"]].append(r)
    for fam in fam_order:
        fr = by_fam.get(fam, [])
        if not fr:
            continue
        cs = Counter(r["status"] for r in fr)
        md += [f"## {FAMILY_TITLE.get(fam, fam)} — {len(fr)} pairs", "", " · ".join(f"{STATUS_LABEL[k]}: {cs[k]}" for k in STATUS_ORDER if cs.get(k)), ""]
        qids = list(dict.fromkeys(r["question_id"] for r in fr))
        for q in qids:
            qr = [r for r in fr if r["question_id"] == q]
            md += [f"### {qr[0]['title']}  \n`{q}`", ""]
            for r in qr:
                if r["status"] == "APPROVED":
                    md += [f"- **{r['company_name']}** — ✅ already approved and serving", ""]
                    continue
                if r["status"] != READY:
                    md += [f"- **{r['company_name']}** — {CELL[r['status']]} — {r['reasons'][-1] if r['reasons'] else ''}", ""]
                    continue
                a = r["entry"]["answer"]
                v = r["validation"]
                md += [f"<details><summary><strong>{r['company_name']}</strong> — 🟢 ready · {r['path']} · digest <code>{r['full_artifact_digest'][:16]}…</code></summary>", "",
                       f"**Answer.** {a['simple_answer']}", "", "**Evidence.**"] + [f"- {e}" for e in a["what_evidence_shows"][:5]] + ["",
                       f"**Does not establish.** {a['what_is_not_yet_proven']}", "",
                       f"**Sources.** {', '.join(r.get('sources', []))}", "",
                       f"**Validation.** " + "; ".join(f"{k}: {x['result']}" for k, x in v.items()) + f" · PACP: {'family validators' if r['pacp']['family_registered'] else 'global checks only (no PACP validators registered for this family)'}", "",
                       f"**Fingerprint** `{r['fingerprint']}` · **Full digest** `{r['full_artifact_digest']}`", "", f"*Method:* {'; '.join(r['reasons'])}", "", "</details>", ""]
    (pre / "M59_REVIEW_PACKAGE.md").write_text("\n".join(md))

    # questions × companies matrix for the next batch
    qrows = list(dict.fromkeys((r["family"], r["question_id"], r["title"]) for r in rows))
    mm = ["# M59 status matrix — questions × companies", "", "🟢 ready for approval · 🟠 needs correction · ⚪ deferred · 🔴 blocked · ✅ approved", ""]
    for fam in fam_order + [f for f in by_fam if f not in fam_order]:
        fq = [x for x in qrows if x[0] == fam]
        if not fq:
            continue
        mm += [f"## {FAMILY_TITLE.get(fam, fam)}", "", "| Question | " + " | ".join(NAMES[c] for c in COMPANIES) + " |", "|---|" + "---|" * len(COMPANIES)]
        for _, q, t in fq:
            cells = []
            for c in COMPANIES:
                r = next(x for x in rows if x["company"] == c and x["question_id"] == q)
                cells.append(CELL[r["status"]])
            mm.append(f"| {t} | " + " | ".join(cells) + " |")
        mm.append("")
    (pre / "M59_STATUS_MATRIX.md").write_text("\n".join(mm))

    # browsable HTML (self-contained)
    data = json.dumps(slim, ensure_ascii=False).replace("</", "<\\/")
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>M59 Owner Review</title>
<style>:root{{--bg:#f4efe6;--fg:#1d2230;--mut:#6b6f7a;--card:#fffdf8;--bd:#e3dccd;--ac:#2f5d4c;--gold:#f0e2b6}}@media(prefers-color-scheme:dark){{:root{{--bg:#16181d;--fg:#ece8df;--mut:#9a9ca4;--card:#1e2128;--bd:#2f333c;--ac:#7fc3a6;--gold:#3a3322}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 ui-serif,Georgia,serif}}main{{max-width:900px;margin:0 auto;padding:24px 16px 64px}}h1{{font-size:1.8rem;margin:.2em 0}}.mut{{color:var(--mut);font-family:system-ui,sans-serif;font-size:.85rem}}
.bar{{position:sticky;top:0;background:var(--bg);padding:10px 0;display:flex;flex-wrap:wrap;gap:8px;border-bottom:1px solid var(--bd);font-family:system-ui,sans-serif}}input,select{{padding:8px 10px;border:1px solid var(--bd);border-radius:10px;background:var(--card);color:var(--fg);font:inherit}}input{{flex:1;min-width:180px}}
details{{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:10px 14px;margin:8px 0}}summary{{cursor:pointer;font-family:system-ui,sans-serif}}.chip{{display:inline-block;border-radius:99px;padding:1px 9px;font-size:.75rem;background:var(--gold)}}.ready{{background:#cfe6da;color:#143d2c}}.fix{{background:#f6dcc0;color:#6b3c10}}.def{{background:#e4e4e4;color:#444}}.blk{{background:#f1cdcd;color:#6b1c1c}}
code{{font-size:.78rem;word-break:break-all}}h3{{margin:1.4em 0 .2em;font-size:1.05rem}}ul{{padding-left:1.2em}}.q{{font-family:system-ui,sans-serif;font-size:.8rem;color:var(--mut)}}</style></head><body><main>
<h1>M59 — Owner review</h1><p class="mut">Candidate answers for {len(rows) - c_all.get('APPROVED', 0)} pending company-question pairs · AI calls: 0 · nothing is registered or served until you authorize exact digests.</p>
<div class="bar"><input id="q" type="search" placeholder="Search question, company, text…" aria-label="Search"><select id="st" aria-label="Status"><option value="">All statuses</option><option value="READY">Ready for approval</option><option value="NEEDS_CORRECTION">Needs correction</option><option value="DEFERRED">Deferred</option><option value="BLOCKED">Blocked</option></select><select id="co" aria-label="Company"><option value="">All companies</option>{''.join(f'<option>{NAMES[c]}</option>' for c in COMPANIES)}</select><select id="fa" aria-label="Family"><option value="">All families</option>{''.join(f'<option value="{c["id"]}">{c["title"]}</option>' for c in QUESTION_CATALOG)}</select></div>
<p class="mut" id="n"></p><div id="out"></div></main><script>
const D={data};const L={{READY:['ready','Ready'],NEEDS_CORRECTION:['fix','Needs correction'],DEFERRED:['def','Deferred'],BLOCKED:['blk','Blocked'],APPROVED:['','Approved']}};
const F={json.dumps({c['id']: c['title'] for c in QUESTION_CATALOG})};
const esc=s=>String(s??'').replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
function render(){{const q=document.getElementById('q').value.toLowerCase(),st=document.getElementById('st').value,co=document.getElementById('co').value,fa=document.getElementById('fa').value;
const rows=D.filter(r=>r.status!=='APPROVED'&&(!st||r.status===st)&&(!co||r.company_name===co)&&(!fa||r.family===fa)&&(!q||JSON.stringify(r).toLowerCase().includes(q)));
document.getElementById('n').textContent=rows.length+' pairs';let last='',h='';
for(const r of rows){{const key=r.family+r.question_id;if(key!==last){{h+='<h3>'+esc(r.title)+'</h3><div class="q">'+esc(F[r.family]||r.family)+' · '+esc(r.question_id)+'</div>';last=key}}
const l=L[r.status];h+='<details><summary><strong>'+esc(r.company_name)+'</strong> <span class="chip '+l[0]+'">'+l[1]+'</span>'+(r.status==='READY'?' <span class="q">'+esc(r.path)+' · '+r.full_artifact_digest.slice(0,12)+'…</span>':'')+'</summary>';
if(r.status==='READY'){{h+='<p>'+esc(r.answer)+'</p><ul>'+r.evidence.slice(0,5).map(e=>'<li>'+esc(e)+'</li>').join('')+'</ul><p><em>Does not establish:</em> '+esc(r.unproven)+'</p><p class="q">Validation: '+Object.entries(r.validation).map(([k,v])=>k+' '+v.result).join(' · ')+'<br>PACP: '+(r.pacp.family_registered?'family validators':'global checks only')+'<br>Fingerprint <code>'+r.fingerprint+'</code><br>Digest <code>'+r.full_artifact_digest+'</code><br>Method: '+esc(r.reasons.join('; '))+'</p>'}}
else h+='<p>'+r.reasons.map(esc).join('</p><p>')+'</p>';h+='</details>'}}
document.getElementById('out').innerHTML=h}}
['q','st','co','fa'].forEach(i=>document.getElementById(i).addEventListener('input',render));render();</script></body></html>"""
    (pre / "M59_REVIEW.html").write_text(html)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--json", help="write full results JSON here")
    ap.add_argument("--companies-root", required=True, type=Path, help="absolute company-data root (required; no default)")
    ap.add_argument("--authorize-served-write", action="store_true", help="permit --companies-root to be the served companies/ tree")
    ap.add_argument("--package", action="store_true", help="write the owner review package under preview/")
    args = ap.parse_args()
    ac.configure_companies_root(args.companies_root, authorize_served=args.authorize_served_write)
    rows = run(args.write)
    summarize(rows)
    if args.package:
        write_package(rows)
    if args.json:
        slim = [{k: v for k, v in r.items() if k != "entry"} for r in rows]
        Path(args.json).write_text(json.dumps(slim, indent=2, ensure_ascii=False))
