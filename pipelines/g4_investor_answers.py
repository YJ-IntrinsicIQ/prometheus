#!/usr/bin/env python3
"""M63/G4: material-coverage check and evidence-composed CANDIDATE investor answers. Zero AI calls. Candidates only.

What it does, on top of the M59 candidate machinery it reuses (Co, mk_answer, validate, unsupported_numbers):
  1. builds a per-company fact ledger from VERIFIED structured records (financial fact registry, capital-allocation ledger, company model, G2 commitment
     register, progression, risk registry, G3 coverage artifacts). Every fact keeps company, fiscal year, reporting basis, metric definition, source page.
  2. defines, per investor area (Business / Management / Risks / Discoveries), the generic classes of material fact an answer should address, and reports for
     each class SUPPORTED / PARTIALLY_SUPPORTED / NOT_EXTRACTED / NOT_DISCLOSED_WITH_SEARCH_EVIDENCE / NOT_APPLICABLE. A gap is never turned into an absence claim:
     it is stated as a gap, with the G3 coverage verdict behind it.
  3. composes candidate answers in the existing answer schema from the ledger, and scores any answer (old or new) with the same omission detector.

It never writes under companies/, never touches the approval registry or the served answers, and promotes nothing.

    python3 pipelines/g4_investor_answers.py --root /path/to/candidate/root --out /private/tmp/.../g4
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipelines import m59_question_batch as m59  # noqa: E402

def _tidy_exact(text: Any) -> str:
    """M59's tidy() minus its rounding of rupee amounts to whole crore: G4.1 answers carry statement-precision figures (e.g. ₹44.23 crore)."""
    t = str(text or "")
    t = m59.ID_RE.sub("", t)
    t = m59.ENUM_RE.sub(lambda m: m.group(0).lower().replace("_", " "), t)
    t = m59.FY_RE.sub(lambda m: f"FY{m.group(1)}", t)
    t = re.sub(r"\bH([12])CY(\d{2})\b", r"H\1 20\2", t)
    t = re.sub(r"\bINR\s?(\d[\d,]*(?:\.\d+)?)\s?(?:crore|cr|Cr)\b", r"₹\1 crore", t)
    t = re.sub(r"\bUTV\b", "unable to verify", t)
    t = re.sub(r"\bcanonical\b", "recorded", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    return t.strip()


m59.tidy = _tidy_exact

SUPPORTED, PARTIAL, NOT_EXTRACTED, NOT_DISCLOSED, NOT_APPLICABLE = "SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_EXTRACTED", "NOT_DISCLOSED_WITH_SEARCH_EVIDENCE", "NOT_APPLICABLE"
STATUSES = (SUPPORTED, PARTIAL, NOT_EXTRACTED, NOT_DISCLOSED, NOT_APPLICABLE)
AREAS = ("BUSINESS", "MANAGEMENT", "RISK", "DISCOVERY")
QUESTION_FOR_AREA = {"BUSINESS": "what-does-company-do", "MANAGEMENT": "what-has-management-promised", "RISK": "what-could-go-wrong", "DISCOVERY": "are-profits-converting-into-cash"}


@dataclass
class Fact:
    id: str
    label: str
    text: str                       # the figure as an investor reads it, with its definition
    num: float | None = None
    unit: str = ""
    fy: str = ""
    basis: str = "unknown"
    page: int | None = None
    source: str = ""
    kind: str = "REPORTED"          # REPORTED | MANAGEMENT_HIGHLIGHT | DERIVED | RECORD
    aliases: list[str] = field(default_factory=list)   # other renderings of the same figure, for the omission detector

    def cite(self) -> str:
        bits = [self.source or "filing"]
        if self.fy:
            bits.append(self.fy.upper())
        if self.page:
            bits.append(f"p.{self.page}")
        return ", ".join(bits)


def money(n: float) -> str:
    body = f"₹{abs(n):,.0f} crore" if abs(n) >= 100 else f"₹{abs(n):,.1f} crore"
    return f"−{body}" if n < 0 else body


def pct(n: float) -> str:
    return f"{n:.1f}%"


def renderings(num: float | None, unit: str) -> list[str]:
    """Ways the same figure may be written in an answer (used only to detect whether an answer already carries it)."""
    if num is None:
        return []
    a = abs(num)
    out = {f"{a:,.0f}", f"{a:,.1f}", f"{a:,.2f}", f"{a:.1f}", f"{a:.2f}", f"{a:.0f}"}
    if unit == "%":
        out |= {f"{a:.1f}%", f"{a:.0f}%"}
    if a < 10:
        out.discard(f"{a:.0f}")
    if a < 100:
        out.add(f"{a:.0f}")
    return sorted(x for x in out if len(x) >= 2 or "." in x)


class Ledger:
    def __init__(self, key: str, root: Path) -> None:
        self.key, self.root = key, Path(root)
        self.cdir = self.root / "companies" / key
        self.mem = self.cdir / "company_memory"
        self.bank = key in m59.BANKS
        self.name = m59.NAMES[key]
        self._c: dict[str, Any] = {}
        self.facts: dict[str, Fact] = {}
        self.fy = self._latest_fy()
        self._build()

    # ── loading ──
    def j(self, path: Path) -> Any:
        k = str(path)
        if k not in self._c:
            try:
                self._c[k] = json.loads(path.read_text())
            except Exception:
                self._c[k] = None
        return self._c[k]

    def m(self, rel: str) -> Any:
        return self.j(self.mem / rel)

    def fin(self, fy: str, name: str) -> Any:
        return self.j(self.cdir / fy / "financials" / name)

    def _latest_fy(self) -> str:
        years = sorted(p.name for p in self.cdir.glob("fy??") if (p / "financials" / "financial_fact_registry.json").exists())
        for fy in reversed(years):
            if self.registry(fy).get("revenue") or self.registry(fy).get("net_interest_income"):
                return fy
        return years[-1] if years else "fy26"

    def prev(self, fy: str | None = None) -> str:
        return f"fy{int((fy or self.fy)[2:]) - 1:02d}"

    def registry(self, fy: str) -> dict[str, dict]:
        d = self.fin(fy, "financial_fact_registry.json") or {}
        out: dict[str, dict] = {}
        rank = {"consolidated": 2, "standalone": 1}
        for f in (d.get("available_facts") or []) + (d.get("derived_facts") or []):
            if f.get("fiscal_year") != fy or f.get("value") is None:
                continue
            cur = out.get(f["metric_id"])
            key = (bool(f.get("usable_downstream", True)), f.get("availability_status") == "present_direct", rank.get(f.get("basis"), 0))
            if cur is None or key > cur["_k"]:
                out[f["metric_id"]] = {**f, "_k": key}
        return out

    # ── fact construction ──
    def add(self, fact: Fact) -> Fact:
        fact.aliases = fact.aliases or renderings(fact.num, fact.unit)
        self.facts[fact.id] = fact
        return fact

    def reg_fact(self, metric: str, label: str, fy: str | None = None, unit: str = "INR crore", sign: int = 1, kind: str = "REPORTED") -> Fact | None:
        fy = fy or self.fy
        f = self.registry(fy).get(metric)
        if not f:
            return None
        v = sign * float(f["value"])
        text = money(v) if unit == "INR crore" else pct(v) if unit == "%" else f"{v:,.2f}"
        k = "MANAGEMENT_HIGHLIGHT" if f.get("source_statement") == "management_highlights" else kind
        return self.add(Fact(f"{metric}@{fy}", label, text, v, unit, fy, f.get("basis") or "unknown", f.get("source_page"), "Annual report", k))

    def _build(self) -> None:
        fy, p = self.fy, self.prev()
        spec = [("revenue", "Revenue from operations" if not self.bank else "Interest earned"), ("pat", "Profit after tax"), ("eps_basic", "Basic EPS"), ("cfo", "Operating cash flow"),
                ("net_worth", "Net worth"), ("cash_and_equivalents", "Cash and cash equivalents"), ("other_bank_balances", "Other bank balances"), ("total_debt", "Borrowings"),
                ("total_income", "Total income"), ("net_interest_income", "Net interest income"), ("net_interest_margin", "Net interest margin"), ("total_deposits", "Total deposits"),
                ("capital_adequacy_ratio", "Capital adequacy ratio"), ("gross_npa_ratio", "Gross NPA ratio"), ("net_npa_ratio", "Net NPA ratio"), ("roe", "Return on equity"), ("roa", "Return on assets"),
                ("management_cash_and_liquid_investments", "Cash and liquid investments (management definition)")]
        for metric, label in spec:
            unit = "%" if metric.endswith(("_ratio", "_margin")) or metric in ("roe", "roa") else "INR" if metric == "eps_basic" else "INR crore"
            self.reg_fact(metric, label, unit=unit)
            if metric in ("revenue", "pat", "cfo", "net_interest_income", "total_deposits", "net_worth", "gross_npa_ratio", "net_npa_ratio", "net_interest_margin", "capital_adequacy_ratio", "roe"):
                self.reg_fact(metric, label + " (prior year)", fy=p, unit=unit)
        for metric, label, sign in (("capex", "Capital expenditure (PPE and intangibles)", -1), ("fcf", "Free cash flow (operating cash flow less capex)", 1), ("dividends_paid", "Dividends paid", -1), ("buyback_paid", "Cash paid for share buyback", -1)):
            self.reg_fact(metric, label, sign=sign)
            if metric in ("capex", "fcf"):
                self.reg_fact(metric, label + " (prior year)", fy=p, sign=sign)
        self._company_model()
        self._capital()
        self._management()
        self._risks()
        self._contingent()
        self._working_capital()
        self._cashflow_drivers()
        self._comparatives()
        self._statutory_ratios()
        self._concentration()

    def _company_model(self) -> None:
        cm = self.m("company_model/company_model.json") or {}
        bm = cm.get("current_business_model") or {}
        if bm.get("what_it_sells") or cm.get("offerings"):
            names = [o.get("name") for o in cm.get("offerings") or [] if o.get("name")] or list(bm.get("what_it_sells") or [])
            self.add(Fact("offerings", "What the company sells", "; ".join(names[:4]), kind="RECORD", source="Company model", fy=bm.get("source_period") or "", aliases=[n.lower() for n in names[:4]]))
        if bm.get("who_pays"):
            self.add(Fact("payers", "Who pays", "; ".join(bm["who_pays"][:4]), kind="RECORD", source="Company model", fy=bm.get("source_period") or "", aliases=[w.lower() for w in bm["who_pays"][:4]]))
        if bm.get("how_revenue_happens") or bm.get("economic_mechanism"):
            self.add(Fact("mechanism", "How revenue happens", str(bm.get("how_revenue_happens") or ""), kind="RECORD", source="Company model", fy=bm.get("source_period") or "",
                          aliases=[str(bm.get("economic_mechanism") or "")[:60].lower()]))
        eng = [e for e in (cm.get("economic_engines") or {}).get("engines") or [] if e.get("engine_type") == "geography"]
        mix = []
        for e in eng:
            h = [x for x in e.get("history") or [] if x.get("revenue_share") is not None]
            if h:
                last = max(h, key=lambda x: str(x.get("reporting_period")))
                mix.append((e["engine_name"], last["revenue_share"] * 100, last.get("growth_rate"), last.get("reporting_period"), (last.get("evidence_references") or {}).get("page")))
        if mix:
            mix.sort(key=lambda x: -x[1])
            txt = ", ".join(f"{n} {s:.1f}%" + (f" ({g * 100:+.1f}% growth)" if g is not None else "") for n, s, g, *_ in mix)
            self.add(Fact("geography_mix", "Revenue by geography", txt, mix[0][1], "%", str(mix[0][3]), "consolidated", mix[0][4], "Annual report", "REPORTED", aliases=[f"{s:.1f}%" for _, s, *_ in mix]))
        unc = [u.get("question") for u in cm.get("uncertainties") or [] if u.get("question")]
        if unc:
            self.add(Fact("model_uncertainties", "Open business questions", " | ".join(unc[:4]), kind="RECORD", source="Company model"))
        drv = [d.get("mechanism") for d in cm.get("economic_drivers") or [] if d.get("mechanism")]
        if drv:
            self.add(Fact("drivers", "Value mechanism as the company describes it", drv[0], kind="RECORD", source="Company model"))

    def _capital(self) -> None:
        d = self.m("capital_allocation_outcomes/capital_allocation_outcomes.json") or {}
        for a in d.get("allocations") or []:
            cat, nm = a.get("allocation_category"), str(a.get("allocation_name") or "")
            if a.get("transaction_status"):
                self.add(Fact("pending_transaction", f"{nm}", f"{nm}: terms as stated {a.get('transaction_terms') or 'not stated'}; the filing states the transaction {a.get('transaction_status_basis') or 'is not completed'}",
                              kind="RECORD", fy=(a.get("deployment_periods") or [""])[0], source="Annual report", aliases=[(a.get("transaction_terms") or "")[:30].lower()]))
            elif cat == "share_buyback" and a.get("amount"):
                self.add(Fact("buyback_consideration", "Buyback consideration", money(a["amount"]), float(a["amount"]), "INR crore", a.get("amount_period") or "", "consolidated", None, "Annual report", "REPORTED"))

    def _management(self) -> None:
        reg = self.m("management_commitments/management_commitments.json") or {}
        cs = reg.get("commitments") or []
        self._commitments = cs
        by = {}
        for c in cs:
            by[c.get("commitment_class")] = by.get(c.get("commitment_class"), 0) + 1
        self.counts = by
        hard = [c for c in cs if c.get("hard_commitment")]
        self.hard = hard
        self.add(Fact("commitment_counts", "Recorded management statements by kind", ", ".join(f"{n} {k.lower().replace('_', ' ')}" for k, n in sorted(by.items(), key=lambda x: -x[1])), kind="RECORD", source="Commitment register"))
        for c in hard:
            dl = (c.get("commitment_basis") or {}).get("deadline_text") or c.get("expected_timeframe") or ""
            self.add(Fact(f"hard:{c['commitment_fingerprint'][:8]}", "Hard commitment", f"“{str(c.get('original_statement')).rstrip('.')}” ({dl}; announced {str(c.get('announcement_period')).upper()}; status {str(c.get('status')).lower()})",
                          kind="RECORD", source="Commitment register", fy=str(c.get("announcement_period") or ""), aliases=[str(c.get("original_statement"))[:40].lower()]))
        prog = self.m("management_progression/management_progression.json") or {}
        items = prog.get("progression_items") or []
        st: dict[str, int] = {}
        for it in items:
            st[it.get("current_status")] = st.get(it.get("current_status"), 0) + 1
        self.progress = st
        if items:
            self.add(Fact("progression", "Management initiatives tracked", f"{len(items)} initiatives: " + ", ".join(f"{n} {str(k).replace('_', ' ')}" for k, n in sorted(st.items(), key=lambda x: -x[1])), len(items), kind="RECORD", source="Management progression"))
        q = self.m("management_quality/management_quality_summary.json") or {}
        if q.get("overall_view"):
            self.add(Fact("mq_view", "Prior evidence-based management assessment", f"overall view {q['overall_view']}; strongest dimension {str(q.get('strongest_dimension')).replace('_', ' ')}; weakest {str(q.get('weakest_dimension')).replace('_', ' ')}", kind="RECORD", source="Management-quality summary"))
        self.unresolved = [u if isinstance(u, str) else (u.get("question") or u.get("text") or "") for u in (q.get("unresolved_questions") or [])][:4]

    def _risks(self) -> None:
        rs = (self.m("risks/risk_registry.json") or {}).get("risks") or []
        order = {"increasing": 0, "persistent": 1, "recurring": 2, "emerging": 3, "reducing": 4}
        rs = sorted(rs, key=lambda r: (order.get(r.get("current_status"), 5), str(r.get("latest_period", "")) == "", str(r.get("latest_period"))), reverse=False)
        rs.sort(key=lambda r: (order.get(r.get("current_status"), 5), -int(re.sub(r"\D", "", str(r.get("latest_period") or "0")) or 0)))
        self.risks = rs
        self.evo = {r["risk_id"]: r for r in (self.m("multi_year/risk_evolution.json") or {}).get("risks") or [] if r.get("risk_id")}

    def _contingent(self) -> None:
        f = self.registry(self.fy).get("contingent_liabilities")
        if f:
            self.add(Fact(f"contingent_liabilities@{self.fy}", "Contingent liabilities (claims not acknowledged as debt)", money(float(f["value"])), float(f["value"]), "INR crore", self.fy, f.get("basis") or "unknown", f.get("source_page"), "Annual report", "REPORTED"))
        seg = self.registry(self.fy).get("reportable_segment_count")
        if seg:
            n = int(seg["value"])
            self.add(Fact(f"segments@{self.fy}", "Reportable segments", f"{n} reportable segment" + ("" if n == 1 else "s") + " (the company's own statement)", float(n), "count", self.fy, seg.get("basis") or "unknown", seg.get("source_page"), "Annual report", "REPORTED",
                          aliases=["single segment", "one segment", "single reportable segment", "one reportable segment", "reportable segment"]))
        dps = self.registry(self.fy).get("dividend_per_share")
        if dps:
            self.add(Fact(f"dps@{self.fy}", "Dividend per share", f"₹{float(dps['value']):,.2f} per share", float(dps["value"]), "INR", self.fy, dps.get("basis") or "unknown", dps.get("source_page"), "Annual report", "REPORTED"))


    # ── G4.1: period-true working capital and statement-visible cash-flow drivers ──
    def _working_capital(self) -> None:
        d = self.m("financials/investor_financial_modules/working_capital_quality_drilldown.json") or {}
        self.wc_applicability = d.get("working_capital_applicability")
        self.wc = {r["fiscal_year"]: r for r in d.get("drilldown") or [] if r.get("fiscal_year")}

    def row_page(self, fy: str, table: str, pattern: str) -> int | None:
        t = (self.fin(fy, "raw_financial_tables.json") or {})
        for r in (t.get("tables", t) or {}).get(table) or []:
            if re.search(pattern, str(r.get("line_item_raw", "")), re.I) and r.get("values") and r.get("page"):
                return int(r["page"])
        return None

    def _cashflow_drivers(self) -> None:
        """Operating-cash-flow components and deposit movements, read from the cash-flow statement rows the financial stage already extracted.
        The statement's own unit is recovered by matching its operating-cash-flow row to the registry's (a figure that fails to match is not used)."""
        self.cfd: dict[str, Fact] = {}
        raw = self.fin(self.fy, "raw_financial_tables.json") or {}
        rows = (raw.get("tables", raw) or {}).get("cash_flow") or []
        if not rows:
            return

        def num(v: Any) -> float | None:
            s = str(v or "").strip()
            neg = s.startswith("(") and s.endswith(")")
            s = re.sub(r"[^\d.]", "", s)
            try:
                x = float(s)
            except ValueError:
                return None
            return -x if neg else x

        def col(r: dict, i: int) -> float | None:
            vals = r.get("values") or []
            return num(vals[i].get("raw_value", vals[i].get("value"))) if len(vals) > i and isinstance(vals[i], dict) else (num(vals[i]) if len(vals) > i else None)

        def val(r: dict, i: int) -> float | None:
            vals = r.get("values") or []
            if len(vals) <= i:
                return None
            v = vals[i]
            return num(v[1]) if isinstance(v, (list, tuple)) else num(v.get("raw") or v.get("value_raw") or v.get("value") or v.get("raw_value")) if isinstance(v, dict) else num(v)

        cfo_row = next((r for r in rows if re.search(r"net cash.*operating activities", str(r.get("line_item_raw", "")), re.I) and val(r, 0) is not None), None)
        reg_cfo = self.registry(self.fy).get("cfo")
        if not cfo_row or not reg_cfo:
            return
        raw_cfo = val(cfo_row, 0)
        if not raw_cfo:
            return
        factor = float(reg_cfo["value"]) / raw_cfo
        if not any(abs(factor / f - 1) < 0.01 for f in (1, 0.1, 0.01, 0.001, 10, 100)):
            return
        factor = min((f for f in (1, 0.1, 0.01, 0.001, 10, 100)), key=lambda f: abs(factor / f - 1))
        op_end = rows.index(cfo_row)
        op_rows = [r for r in rows[:op_end] if r.get("page") == cfo_row.get("page")]
        spec = [("receivables", r"trade receivables", "Change in trade receivables (cash effect)"), ("inventories", r"inventor", "Change in inventories (cash effect)"),
                ("payables", r"trade payables", "Change in trade payables (cash effect)"), ("other_liabilities", r"(?:increase|decrease).*liabilit|other liabilities", "Change in other liabilities (cash effect)"),
                ("taxes", r"income tax(?:es)? \(?paid|net income tax|taxes paid", "Income taxes paid")]
        basis = (self.registry(self.fy).get("cfo") or {}).get("basis") or "unknown"
        prev_ok = False
        reg_prev = self.registry(self.prev()).get("cfo")
        raw_prev = val(cfo_row, 1)
        if reg_prev and raw_prev and abs(raw_prev * factor / float(reg_prev["value"]) - 1) < 0.01:
            prev_ok = True
        for mid, pat, label in spec:
            hits = [r for r in op_rows if re.search(pat, str(r.get("line_item_raw", "")), re.I) and val(r, 0) is not None]
            if mid == "other_liabilities":
                hits = [r for r in hits if not re.search(r"write back|lease|before changes|trade payables|trade receivables", str(r.get("line_item_raw", "")), re.I)]
            r = max(hits, key=lambda x: abs(val(x, 0) or 0)) if mid == "other_liabilities" and hits else (hits[0] if hits else None)
            if r:
                v = val(r, 0) * factor
                self.add(Fact(f"cfd:{mid}@{self.fy}", label, money(v), v, "INR crore", self.fy, basis, r.get("page"), "Annual report", "REPORTED", aliases=renderings(abs(v), "INR crore") + [f"{abs(v):.2f}"]))
                if prev_ok and val(r, 1) is not None:
                    vp = val(r, 1) * factor
                    self.add(Fact(f"cfd:{mid}@{self.prev()}", label + " (prior year)", money(vp), vp, "INR crore", self.prev(), basis, r.get("page"), "Annual report", "REPORTED", aliases=renderings(abs(vp), "INR crore") + [f"{abs(vp):.2f}"]))
        dep = next((r for r in rows[op_end + 1:] if re.search(r"fixed deposit|bank balances|margin money", str(r.get("line_item_raw", "")), re.I) and val(r, 0) is not None), None)
        if dep:
            v = val(dep, 0) * factor
            self.add(Fact(f"cfd:deposits@{self.fy}", "Net movement in fixed deposits / other bank balances (investing; positive = released)", money(v), v, "INR crore", self.fy, basis, dep.get("page"), "Annual report", "REPORTED", aliases=renderings(abs(v), "INR crore") + [f"{abs(v):.2f}"]))


    def _comparatives(self) -> None:
        """When the current year's own statement presents both years in adjacent columns, the prior-year figure is on the same basis as the current one. The prior-year registry
        fact may carry a different or unstated basis label because it was read from the earlier report; the paired columns of one statement settle it."""
        self.comparative: dict[str, int] = {}
        raw = self.fin(self.fy, "raw_financial_tables.json") or {}
        rows = (raw.get("tables", raw) or {}).get("profit_and_loss") or []
        cur, prv = self.facts.get(f"pat@{self.fy}"), self.facts.get(f"pat@{self.prev()}")
        if not cur or not prv:
            return
        for r in rows:
            if not re.search(r"net profit|profit for the year|profit after tax", str(r.get("line_item_raw", "")), re.I):
                continue
            vals = [v.get("value_crore") for v in r.get("values") or [] if isinstance(v, dict)]
            if len(vals) >= 2 and vals[0] is not None and vals[1] is not None and abs(vals[0] - cur.num) <= 0.005 * abs(cur.num) and abs(vals[1] - prv.num) <= 0.005 * abs(prv.num):
                self.comparative["pat"] = int(r.get("page") or 0)
                if prv.basis in ("unknown", "") or prv.basis != cur.basis:
                    prv.basis = cur.basis
                prv.page = prv.page or r.get("page")
                return


    def _statutory_ratios(self) -> None:
        """A ratio the management highlights state AND the statutory business-ratio table also states, with both years. If they differ beyond rounding the two are kept side by side."""
        self.stat: dict[str, dict] = {}
        raw = self.fin(self.fy, "raw_financial_tables.json") or {}
        for rows in (raw.get("tables", raw) or {}).values():
            for r in rows or []:
                if re.match(r"net interest margin", str(r.get("line_item_raw", "")).strip(), re.I) and "net_interest_margin" not in self.stat:
                    vals = [float(re.sub(r"[^\d.]", "", str(v.get("value_raw") or "")) or "nan") for v in r.get("values") or [] if isinstance(v, dict) and "%" in str(v.get("value_raw") or "")]
                    if len(vals) >= 2:
                        self.stat["net_interest_margin"] = {"cur": vals[0], "prev": vals[1], "page": r.get("page")}

    # ── G5: customer / depositor concentration disclosed in the report, with entity, year, numerator and denominator ──
    def section_basis(self, page: int) -> str:
        """Standalone or consolidated, from the nearest preceding financial-statement heading or note wording in the report (looking back up to 80 pages)."""
        pg: dict[int, list[str]] = {}
        for c in (self.j(self.cdir / self.fy / "extracted" / "clean_chunks.json") or {}).get("chunks") or []:
            pg.setdefault(int(c.get("page") or 0), []).append(str(c.get("text") or ""))
        for p in range(page, max(0, page - 80), -1):
            t = " ".join(" ".join(pg.get(p, [])).split())
            ms = list(re.finditer(r"(?:Notes? to the|Statement of|Balance Sheet|Independent Auditor.s Report on the|Financial Statements? of)[^.]{0,60}?\b(Standalone|Consolidated)\b|\b(Standalone|Consolidated)\b (?:Financial Statements|financial statements|Balance Sheet|Statement)|audited (standalone|consolidated) financial statements", t, re.I))
            if ms:
                m = ms[-1]
                return next(g for g in m.groups() if g).lower()
        return "unknown"

    def _concentration(self) -> None:
        """Parse the report's own concentration note when it has one of four recognised shapes (table of major customers; sentence with customer count and aggregate share; bank
        concentration-of-deposits/advances table; single-customer threshold sentence). Other shapes fall back to the quoted passage in the answer."""
        self.extra_numbers: list[float] = getattr(self, "extra_numbers", [])
        fy = self.fy
        chunks = (self.j(self.cdir / fy / "extracted" / "clean_chunks.json") or {}).get("chunks") or []

        def num(x: str) -> float:
            return float(x.replace(",", ""))

        def cr2(v: float) -> str:
            return f"₹{v:,.2f} crore"
        for ch in chunks:
            t = re.sub(r"\s+", " ", re.sub(r"[\x00-\x08\x0b-\x1f•]", " ", str(ch.get("text") or "")))
            page = ch.get("page")
            m = re.search(r"No\.? of customers? ([\d.]+) ([\d.]+) Revenue from operations ([\d,.]+) ([\d,.]+) Trade receivables ([\d,.]+) ([\d,.]+)", t)
            if m and "major customers" in t.lower() and "customer_conc" not in self.facts:
                n0, n1, r0, r1, c0, c1 = (num(x) for x in m.groups())
                basis = self.section_basis(page)
                rev, rec = self.facts.get(f"revenue@{fy}"), (self.wc.get(fy) or {}).get("receivables")
                same = rev and rev.basis == basis
                share = f", about {r0 / rev.num * 100:.2f}% of {basis} revenue of {cr2(rev.num)}" if same else ""
                rshare = f", about {c0 / rec * 100:.2f}% of trade receivables of {cr2(rec)}" if same and rec else ""
                txt = (f"Customer concentration ({basis}, {fy.upper()}, p.{page}): {int(n0)} customers each above 10% of revenue contributed {cr2(r0)}{share}; their trade receivables were {cr2(c0)}{rshare}. "
                       f"Prior year ({int(n1)} customers): revenue {cr2(r1)}, trade receivables {cr2(c1)}. No customer names, payment behaviour or consequences are inferred here")
                self.extra_numbers += [n0, n1, r0, r1, c0, c1] + ([round(r0 / rev.num * 100, 2), rev.num] if same else []) + ([round(c0 / rec * 100, 2), rec] if same and rec else [])
                self.add(Fact("customer_conc", "Customer concentration", txt, r0, "INR crore", fy, basis, page, "Annual report note", "REPORTED", aliases=["customer concentration"]))
                return
            m = re.search(r"There are (\d+) customers? \((\d+) customers? in FY [\d-]+\) individually contributing more than (\d+)% and in aggregate contributing to more than (\d+)% of the Company.s total revenue during the years? ended [A-Za-z]+ \d+, (\d{4}) \((\d+)% of", t)
            if m and "customer_conc" not in self.facts:
                n0, n1, th, p0, yr, p1 = (num(x) for x in m.groups())
                basis = self.section_basis(page)
                rev = self.facts.get(f"revenue@{fy}")
                warn = f"; the Company's own revenue is the denominator, so this is not a group-wide figure (consolidated revenue is {cr2(rev.num)})" if rev and rev.basis != basis else ""
                txt = (f"Customer concentration ({basis} Company, {fy.upper()}, p.{page}): {int(n0)} customers each above {int(th)}% of revenue together contributed more than {int(p0)}% of the Company's revenue (FY25: {int(n1)} customers, {int(p1)}%){warn}. "
                       f"Who the customers are, including whether any is a group company, is not established by this note")
                self.extra_numbers += [n0, n1, th, p0, p1] + ([rev.num] if rev else [])
                self.add(Fact("customer_conc", "Customer concentration", txt, p0, "%", fy, basis, page, "Annual report note", "REPORTED", aliases=["customer concentration"]))
                return
            m = re.search(r"No customer contributed more than ([\d.]+)% of total revenues for the year ended ([A-Za-z]+ \d+, \d{4}) and ([A-Za-z]+ \d+, \d{4})", t)
            if m and "customer_conc" not in self.facts:
                basis = self.section_basis(page)
                txt = (f"Customer concentration ({basis}, {fy.upper()}, p.{page}): the note states that no customer contributed more than {m.group(1)}% of total revenues in the years ended {m.group(2)} and {m.group(3)}. "
                       f"That is a single-customer threshold; it gives no top-ten or aggregate distribution")
                self.extra_numbers += [num(m.group(1))]
                self.add(Fact("customer_conc", "Customer concentration", txt, num(m.group(1)), "%", fy, basis, page, "Annual report note", "REPORTED", aliases=["customer concentration"]))
                return
            m = re.search(r"Total Deposits of the twenty largest Depositors ([\d,.]+) ([\d,.]+) Percentage of Deposits of twenty largest Depositors to Total Deposits of the Bank ([\d.]+)% ([\d.]+)%", t)
            if m and "customer_conc" not in self.facts:
                d0, d1, q0, q1 = (num(x) for x in m.groups())
                hdr = re.findall(r"As on ([A-Za-z]+ \d+, \d{4})", t)
                cur, prv = (hdr[0], hdr[1]) if len(hdr) >= 2 else (fy.upper(), "the prior year")
                cur, prv = (re.sub(r"([A-Za-z]+) (\d+), (\d{4})", r"\2 \1 \3", x) for x in (cur, prv))
                adv = re.search(r"Total Advances to the twenty largest Borrowers ([\d,.]+) ([\d,.]+) Percentage of Advances of twenty largest Borrowers to Total Advances of the Bank ([\d.]+)% ([\d.]+)%", t)
                advtxt = f" The same note gives advances to the twenty largest borrowers of {cr2(num(adv.group(1)))}, {adv.group(3)}% of total advances (credit-exposure basis)." if adv else ""
                txt = (f"Deposit funding concentration ({fy.upper()}, p.{page}): the twenty largest depositors held {cr2(d0)}, {q0}% of total deposits, at {cur} ({cr2(d1)}, {q1}% at {prv}). "
                       f"This is funding concentration, not revenue from customers.{advtxt}").rstrip(".")
                self.extra_numbers += [d0, d1, q0, q1] + ([num(adv.group(1)), num(adv.group(3))] if adv else [])
                self.add(Fact("customer_conc", "Deposit funding concentration", txt, q0, "%", fy, "unknown", page, "Annual report note", "REPORTED", aliases=["deposit funding concentration", "concentration"]))
                return

    # ── coverage verdicts from G3 ──
    def family(self, name: str) -> dict:
        d = self.fin(self.fy, "financial_anchor_coverage.json") or {}
        return (d.get("families") or {}).get(name) or {}

    def gap(self, family: str, applicable: bool = True) -> tuple[str, str]:
        if not applicable:
            return NOT_APPLICABLE, "does not apply to this kind of business"
        fam = self.family(family)
        st = fam.get("status")
        s = fam.get("search") or {}
        if st == "NOT_DISCLOSED_WITH_SEARCH_EVIDENCE":
            topic = FAMILY_TOPIC.get(family)
            if topic and anchor_hits(self, topic)["chunks_matching"]:          # the family search missed wording the independent anchor finds: not 'not disclosed'
                return NOT_EXTRACTED, (txn_why(self) if topic == "transactions" else f"the filing mentions it in {anchor_hits(self, topic)['chunks_matching']} sections (pages {', '.join(map(str, anchor_hits(self, topic)['example_pages'][:4]))})")
            return NOT_DISCLOSED, f"{s.get('chunks_searched')} sections of the filing searched; no match"
        if st == "NOT_EXTRACTED" and family == "material_transactions" and transaction_status(self)["completed"]:
            return NOT_EXTRACTED, txn_why(self)
        if st == "NOT_EXTRACTED":
            return NOT_EXTRACTED, f"the filing mentions it in {s.get('chunks_matching')} sections (pages {', '.join(map(str, (s.get('example_pages') or [])[:4]))})"
        if st == "FOUND":
            return PARTIAL, "extracted in part"
        return NOT_EXTRACTED, "no coverage verdict is available for this family"

    def get(self, id_: str) -> Fact | None:
        return self.facts.get(id_)

    def g(self, metric: str, prior: bool = False) -> Fact | None:
        return self.facts.get(f"{metric}@{self.prev() if prior else self.fy}")


# ───────────────────────────── material-coverage classes ─────────────────────────────
@dataclass
class Cls:
    id: str
    area: str
    label: str
    ids: Callable[[Ledger], list[str]]       # fact ids that satisfy the class (any/all per `need`)
    need: str = "all"                         # all | any
    family: str | None = None                 # G3 anchor family consulted when no fact exists
    applicable: Callable[[Ledger], bool] = lambda L: True
    search: Any = ()                          # filing-text search used to separate NOT_EXTRACTED from NOT_DISCLOSED when no G3 family fits
    absence_words: tuple[str, ...] = ()       # words that mark a sentence as being about this class (omission / absence-claim detector)
    detect: str = ""                           # qualitative classes: a text pattern that shows the answer addresses the class (figures are matched by value instead)


def _f(L: Ledger, *ids: str) -> list[str]:
    return [i for i in ids if i in L.facts]


def _m(L: Ledger, m: str, prior: bool = False) -> str:
    return f"{m}@{L.prev() if prior else L.fy}"


FAMILY_TOPIC = {"material_transactions": "transactions", "segments_and_geography": "segment_mix", "risks_and_contingencies": "contingent", "guidance_and_commitments": "guidance"}

CUSTOMER_CONC = (r"no\s+customer\s+contribut\w+\s+more\s+than", r"(?:contribut\w+|account\w*)\s+(?:individually\s+)?(?:to\s+)?(?:for\s+)?more\s+than\s+10\s?%", r"top\s+(?:five|ten|\d+)\s+(?:customers?|clients?)\s+(?:account|contribut|represent)", r"largest\s+(?:\d+\s+)?(?:customers?|clients?)", r"(?:customer|client|revenue)\s+concentration|concentration\s+of\s+(?:revenue|customers|clients)",
                 r"single\s+(?:external\s+)?(?:customer|client)", r"(?:major|key)\s+customers?", r"(?:more|greater)\s+than\s+10\s?%\s+of\s+(?:the\s+)?(?:[\w’']+\s+){0,3}?(?:total\s+)?revenue", r"customers?\s+contribut\w+\s+(?:individually\s+)?(?:to\s+)?more\s+than\s+10")
BANK_CONC = (r"twenty\s+largest\s+depositors|largest\s+(?:twenty|\d+)\s+(?:depositors|borrowers)", r"concentration\s+of\s+(?:deposits|advances|exposures|borrowers|depositors)", r"top\s+(?:ten|twenty|\d+)\s+(?:depositors|borrowers)", r"large\s+exposures?")

CLASSES: list[Cls] = [
    # BUSINESS
    Cls("b_offer", "BUSINESS", "What the company sells", lambda L: ["offerings"], absence_words=("sells", "products", "offering")),
    Cls("b_payers", "BUSINESS", "Who pays", lambda L: ["payers"], absence_words=("customers", "pays", "borrowers", "payers")),
    Cls("b_mechanism", "BUSINESS", "How it makes money", lambda L: ["mechanism"], absence_words=("revenue", "earns", "makes money")),
    Cls("b_scale", "BUSINESS", "Scale and profitability", lambda L: [_m(L, "net_interest_income"), _m(L, "total_deposits"), _m(L, "pat")] if L.bank else [_m(L, "revenue"), _m(L, "pat")], absence_words=("revenue", "profit")),
    Cls("b_mix", "BUSINESS", "Mix by segment or geography", lambda L: _f(L, "geography_mix", f"segments@{L.fy}"), need="any", family="segments_and_geography", absence_words=("segment", "geograph", "region", "split", "mix", "breakdown")),
    Cls("b_visibility", "BUSINESS", "Forward visibility (order book / backlog)", lambda L: [], search=(r"order\s*book", r"order\s+backlog", r"orders?\s+in\s+hand"),
        applicable=lambda L: not L.bank and bool(re.search(r"project|order|milestone", str((L.facts.get("mechanism") or Fact("x", "x", "")).text), re.I)), absence_words=("order book", "backlog")),
    Cls("b_returns", "BUSINESS", "Returns on capital", lambda L: _f(L, _m(L, "roe")), absence_words=("return on", "roe", "roce")),
    Cls("b_concentration", "BUSINESS", "Customer concentration", lambda L: _f(L, "customer_conc"), search=lambda L: BANK_CONC if L.bank else CUSTOMER_CONC, absence_words=("concentration", "largest customer", "depositor", "borrower")),
    # MANAGEMENT
    Cls("m_commit", "MANAGEMENT", "What management has committed to (classified)", lambda L: ["commitment_counts"], family="guidance_and_commitments", absence_words=("commitment", "promise", "promised"), detect=r"commitment|promis|pledge|targets? (?:set|stated)"),
    Cls("m_capital", "MANAGEMENT", "Capital decisions in the year", lambda L: _f(L, _m(L, "dividends_paid"), _m(L, "buyback_paid"), "buyback_consideration", _m(L, "capex")), need="any", family="capital_allocation", absence_words=("dividend", "buyback", "capex", "capital allocation")),
    Cls("m_transaction", "MANAGEMENT", "Transactions and their completion status", lambda L: ["pending_transaction"], family="material_transactions", absence_words=("acquisition", "transaction", "deal")),
    Cls("m_exec", "MANAGEMENT", "Execution progress", lambda L: ["progression"], absence_words=("execution", "delivered", "progress"), detect=r"initiatives?|execution|delivered|in progress|progress"),
    Cls("m_unresolved", "MANAGEMENT", "What remains unresolved", lambda L: [], absence_words=("unresolved", "unproven"), detect=r"unresolved|not established|not (?:yet )?(?:proven|shown|verified)|unproven|unable to verify|cannot be (?:determined|verified)"),
    # RISK
    Cls("r_registry", "RISK", "Recorded business risks with mechanism", lambda L: [i for i in L.facts if i.startswith("riskx:")][:4], need="any", absence_words=("risk",), detect=r"mechanism|could worsen|exposure"),
    Cls("r_balance", "RISK", "Balance-sheet and liquidity exposure", lambda L: [_m(L, "capital_adequacy_ratio"), _m(L, "gross_npa_ratio")] if L.bank else _f(L, _m(L, "total_debt"), _m(L, "cash_and_equivalents")), absence_words=("debt", "borrowing", "liquidity", "npa", "capital adequacy")),
    Cls("r_contingent", "RISK", "Contingent liabilities", lambda L: _f(L, f"contingent_liabilities@{L.fy}"), family="risks_and_contingencies", absence_words=("contingent",)),
    Cls("r_transaction", "RISK", "Pending-transaction exposure", lambda L: ["pending_transaction"], family="material_transactions", absence_words=("acquisition", "transaction")),
    Cls("r_cash", "RISK", "Cash conversion", lambda L: [_m(L, "cfo"), _m(L, "pat")], applicable=lambda L: not L.bank, absence_words=("cash conversion", "operating cash flow"), detect=r"cash conversion|receivable days"),
    # DISCOVERY
    Cls("d_cash", "DISCOVERY", "Profit versus cash generation", lambda L: [_m(L, "cfo"), _m(L, "pat")] + ([] if L.bank else [_m(L, "fcf")]), absence_words=("cash flow", "profit")),
    Cls("d_returns", "DISCOVERY", "Shareholder returns versus cash generated", lambda L: _f(L, _m(L, "dividends_paid")) + ([_m(L, "fcf")] if not L.bank else []), applicable=lambda L: not L.bank, absence_words=("dividend", "buyback")),
    Cls("d_capex", "DISCOVERY", "Capital intensity versus growth", lambda L: [_m(L, "capex"), _m(L, "revenue")], applicable=lambda L: not L.bank, absence_words=("capex", "capital expenditure"), detect=r"capital intensity|% of revenue"),
    Cls("d_bank", "DISCOVERY", "Bank earnings quality (margin, credit cost, capital)", lambda L: [_m(L, "net_interest_margin"), _m(L, "gross_npa_ratio"), _m(L, "capital_adequacy_ratio"), _m(L, "pat"), _m(L, "pat", True)], applicable=lambda L: L.bank, absence_words=("margin", "npa", "capital adequacy")),
]


def chunk_search(L: Ledger, patterns: tuple[str, ...]) -> dict:
    p = L.cdir / L.fy / "extracted" / "clean_chunks.json"
    chunks = L.j(p) or []
    chunks = chunks if isinstance(chunks, list) else chunks.get("chunks", [])
    pages, n = [], 0
    for c in chunks:
        t = " ".join(str(c.get("text", "")).split()).lower()
        if any(re.search(x, t) for x in patterns):
            n += 1
            if isinstance(c.get("page"), int) and len(pages) < 6:
                pages.append(c["page"])
    return {"chunks_searched": len(chunks), "patterns": list(patterns), "chunks_matching": n, "example_pages": pages}


def class_status(L: Ledger, c: Cls) -> dict:
    """The ledger's verdict for one class: what is known, or exactly why it is not."""
    if not c.applicable(L):
        return {"class": c.id, "area": c.area, "label": c.label, "status": NOT_APPLICABLE, "facts": [], "why": "does not apply to this kind of business" if L.bank or c.id.startswith("d_") else "not applicable"}
    ids = [i for i in c.ids(L)]
    have = [i for i in ids if i in L.facts]
    if c.id == "m_unresolved":
        have = ["unresolved"] if (L.unresolved or L.hard or L.facts.get("pending_transaction")) else []
    if c.id.startswith("m_commit") and "commitment_counts" in L.facts:
        have = ["commitment_counts"]
    full = bool(ids) and len(have) == len(ids) if c.need == "all" else bool(have)
    if c.id == "m_unresolved":
        full = bool(have)
    if full:
        return {"class": c.id, "area": c.area, "label": c.label, "status": SUPPORTED, "facts": have, "why": ""}
    if have:
        return {"class": c.id, "area": c.area, "label": c.label, "status": PARTIAL, "facts": have, "why": "available: " + ", ".join(have) + "; missing: " + ", ".join(i for i in ids if i not in L.facts)}
    if c.family:
        st, why = L.gap(c.family)
        return {"class": c.id, "area": c.area, "label": c.label, "status": st if st != PARTIAL else NOT_EXTRACTED, "facts": [], "why": why}
    if c.search:
        ev = chunk_search(L, c.search(L) if callable(c.search) else c.search)
        if ev["chunks_matching"]:
            return {"class": c.id, "area": c.area, "label": c.label, "status": NOT_EXTRACTED, "facts": [], "why": f"the filing mentions it in {ev['chunks_matching']} sections (pages {', '.join(map(str, ev['example_pages'][:4]))})"}
        return {"class": c.id, "area": c.area, "label": c.label, "status": NOT_DISCLOSED, "facts": [], "why": f"{ev['chunks_searched']} sections searched; no match"}
    return {"class": c.id, "area": c.area, "label": c.label, "status": NOT_EXTRACTED, "facts": [], "why": "no structured record carries it"}


def ledger_coverage(L: Ledger, area: str) -> list[dict]:
    return [class_status(L, c) for c in CLASSES if c.area == area]


# ── scoring any answer text (candidate or existing) with the same omission detector ──
ABSENCE = re.compile(r"(?:records?|filings?|reports?)\s+(?:do(?:es)?\s+not|don.t)\s+(?:show|state|disclose|contain|say|break)|not\s+(?:disclosed|available|reported|stated)|no\s+(?:disclosure|breakdown|evidence)|(?:is|are)\s+(?:silent|missing)|cannot\s+be\s+(?:determined|sized)", re.I)


def answer_text(a: dict) -> str:
    parts = [a.get("simple_answer", ""), *a.get("what_evidence_shows", []), a.get("what_may_mean_economically", ""), a.get("what_is_not_yet_proven", ""), *a.get("what_to_monitor", []),
             *[str(x.get("value", "")) + " " + str(x.get("metric", "")) for x in a.get("deterministic_precision_facts", []) if isinstance(x, dict)], *[str(x) for x in a.get("key_points", [])]]
    return " ".join(str(p) for p in parts)


def covers(L: Ledger, fact_id: str, text: str) -> bool:
    f = L.facts.get(fact_id)
    if not f:
        return False
    low = text.lower()
    for al in f.aliases:
        al = (al or "").lower()
        if len(al) < 2:
            continue
        if re.fullmatch(r"[\d,.]+%?", al):
            if re.search(r"(?<![\d.,])" + re.escape(al) + r"(?![\d]|,\d)", low):
                return True
        elif al in low:
            return True
    return False


def score_answer(L: Ledger, area: str, a: dict) -> dict:
    text = answer_text(a)
    rows = []
    for c in CLASSES:
        if c.area != area:
            continue
        st = class_status(L, c)
        row = {"class": c.id, "label": c.label, "available": st["status"], "carried": None, "absence_claim": False}
        if st["status"] in (SUPPORTED, PARTIAL):
            hit = [i for i in st["facts"] if covers(L, i, text)]
            if c.detect and re.search(c.detect, text, re.I):
                hit = list(st["facts"])
            if c.need == "any":
                row["carried"] = "yes" if hit else "no"
            else:
                row["carried"] = "yes" if st["facts"] and len(hit) == len(st["facts"]) else "partly" if hit else "no"
        elif st["status"] in (NOT_EXTRACTED, NOT_DISCLOSED):
            for sent in re.split(r"(?<=[.;])\s+", text):
                if ABSENCE.search(sent) and any(w in sent.lower() for w in c.absence_words):
                    # an absence claim is legitimate only for NOT_DISCLOSED_WITH_SEARCH_EVIDENCE and only when it says it searched
                    if st["status"] == NOT_EXTRACTED or "search" not in sent.lower():
                        row["absence_claim"] = True
        rows.append(row)
    omitted = [r for r in rows if r["available"] in (SUPPORTED, PARTIAL) and r["carried"] in ("no", "partly")]
    confident_absence = [r for r in rows if r["absence_claim"]]
    avail = [r for r in rows if r["available"] in (SUPPORTED, PARTIAL)]
    return {"rows": rows, "omitted": [r["class"] for r in omitted], "absence_claims_on_gaps": [r["class"] for r in confident_absence],
            "carried_pct": round(100 * sum(1 for r in avail if r["carried"] == "yes") / max(1, len(avail)), 1), "classes_available": len(avail)}


# ───────────────────────────── composition ─────────────────────────────
def growth(L: Ledger, metric: str) -> float | None:
    """Year-on-year change, only when both years are on the same stated basis (never across a basis change or an unknown basis)."""
    a, b = L.g(metric), L.g(metric, prior=True)
    if not a or not b or a.num is None or b.num is None or b.num == 0 or a.basis != b.basis or a.basis == "unknown":
        return None
    if a.num <= 0 or b.num <= 0:
        return None
    return (a.num / b.num - 1) * 100


def lc_first(x: str) -> str:
    x = x.strip()
    return x if (len(x) > 1 and x[:2].isupper()) or x.split(' ')[0].isupper() else x[:1].lower() + x[1:]


def fy_label(fy: str) -> str:
    return fy.upper()


def dp(L: Ledger, fid: str, meaning: str) -> dict | None:
    f = L.facts.get(fid)
    if not f:
        return None
    d = m59.dpf(f.label, f.text, f.fy.upper() if f.fy else "", meaning)
    d.update({"basis": f.basis, "source": f.cite(), "kind": f.kind})
    return d


def gaps_text(L: Ledger, area: str, skip: tuple[str, ...] = ()) -> list[str]:
    out = []
    for r in ledger_coverage(L, area):
        if r["class"] in skip:
            continue
        if r["status"] in (NOT_EXTRACTED, NOT_DISCLOSED):
            kind = "mentioned in the filing but not yet extracted into the records" if r["status"] == NOT_EXTRACTED else "not found after searching the filing"
            out.append(f"{r['label']}: {kind} ({r['why'].replace('in 1 sections', 'in 1 section')}).")
    return out


# ───────────────────────────── G5: claim-level absence integrity ─────────────────────────────
# Contract states: NOT_EXTRACTED (the filing carries it, the records do not), NOT_DISCLOSED (searched, the filing does not carry it) and NOT_APPLICABLE.
# A negative claim is detected structurally (a negation, a source or disclosure subject, and no analytic-unknown content), bound to claim-specific provenance by topic,
# and the state is checked against the filing with anchor patterns that are independent of the search that produced it.
TXN_ANCHOR = re.compile(r"(?:scheme of )?(?:amalgamation|merger|demerger)\b|share purchase agreement|business transfer agreement|slump sale|scheme of arrangement|definitive agreement"
                        r"|acquir\w+ (?:\d+(?:\.\d+)?\s?%|the entire|all the|a controlling|a majority|a stake)|(?:completed|consummat\w+) the acquisition|effective date of the (?:scheme|merger|amalgamation)", re.I)
TXN_DONE = re.compile(r"effective date|became effective|came into effect|has been completed|was completed|consummated|completed the acquisition", re.I)
TXN_PENDING = re.compile(r"subject to (?:[\w\s,]{0,40})approval|proposed (?:acquisition|merger|amalgamation|transaction)|yet to be completed|expected to (?:be )?(?:complete|close)|pending (?:completion|approval)", re.I)

CAPEX_SPLIT_PATTERNS = (r"maintenance\s+(?:capex|capital\s+expenditure)", r"growth\s+(?:capex|capital\s+expenditure)", r"(?:capex|capital\s+expenditure)[^.]{0,40}\b(?:maintenance|expansion)\b", r"maintenance\s+and\s+(?:growth|expansion)", r"expansion\s+capex")
GUIDANCE_PATTERNS = (r"\bguidance\b", r"\boutlook\b", r"(?:we|the\s+company)\s+(?:plan|aim|intend|expect|will)\s+to")
ANCHORS: dict[str, tuple] = {
    "concentration": CUSTOMER_CONC + BANK_CONC,
    "transactions": (TXN_ANCHOR.pattern,),
    "capex_split": CAPEX_SPLIT_PATTERNS,
    "guidance": GUIDANCE_PATTERNS,
    "segment_mix": (r"segment", r"geograph", r"revenue\s+by\s+(?:region|geography|market)"),
    "order_book": (r"order\s*book", r"order\s+backlog", r"orders?\s+in\s+hand"),
    "contingent": (r"contingent\s+liabilit",),
    "credit_cost": (r"provisions?\s+(?:and|&)\s+contingenc", r"credit\s+cost", r"provisions?\s+for\s+(?:non[- ]performing|bad|doubtful)"),
}
TOPIC_RX = [("capex_split", r"capex|capital expenditure|maintenance|upkeep"), ("transactions", r"transaction|amalgamation|merger|acquisition|\bdeals?\b|completion status"),
            ("guidance", r"guidance|commitment"), ("concentration", r"concentrat|customer|buyer|depositor|borrower|client"), ("segment_mix", r"\bmix\b|segment|geograph|revenue split|breakdown"),
            ("order_book", r"order book|backlog|orders in hand"), ("contingent", r"contingent"), ("credit_cost", r"credit cost|provision")]
CLASS_TOPIC = {"b_mix": "segment_mix", "b_visibility": "order_book", "b_concentration": "concentration", "r_contingent": "contingent", "r_transaction": "transactions", "m_transaction": "transactions", "m_commit": "guidance"}

SRC_AGENT = r"(?:annual report|report|filing|statements?|notes?|accounts|company|management|bank|register|disclosures?)"
CLAIM_A = re.compile(rf"\b{SRC_AGENT}\s+(?:\w+\s+){{0,3}}?(?:do(?:es)? not|did not|never|(?:has|have|provides?|gives?|offers?|contains?) (?:no|nothing)|omitted|is silent|are silent)\b", re.I)      # a source subject with a negated disclosure verb
CLAIM_B = re.compile(r"\bno\s+(?:[\w-]+\s+){0,4}(?:disclosures?|figures?|data|information|breakdown|split)\b", re.I)                                                                  # negated existence of a disclosure
CLAIM_C = re.compile(r"\b(?:is|are|was|were)\s+(?:unavailable|absent|missing|silent|unreported|undisclosed)\b|\bonly partl\w+ captured\b|\blacks?\b", re.I)                         # predicate that says it is not there
CLAIM_D = re.compile(r"\bnot\s+(?:yet\s+)?(?:extracted|carried)\b|\bdo(?:es)? not carry\b|\bnot (?:yet )?captured\b|\bnot in the (?:extracted )?records\b", re.I)                       # record-level gap
CLAIM_E = re.compile(r"\b(?:is|are|was|were)\s+not\s+(?:\w+\s+){0,2}?(?:disclosed|stated|reported|provided|given|available|shown|recorded)\b|\b(?:records?|register|extracts?)\s+(?:hold|holds|show|shows|say|says|contain|contains|record|records)\s+(?:no|nothing)\b|\bmissing\b|\bnot found\b|\bwas not located\b|\bno\s+(?:\w+\s+){0,3}(?:was|were)\s+(?:located|found)\b", re.I)  # passive "is not disclosed", "the records hold no…"
CLAIM_F = re.compile(r"\b(?:concentration|order book|backlog|segment mix|guidance|breakdown|split|revenue mix)\b[^.;]{0,40}\b(?:is|are)\s+(?:not (?:known|sized|shown|determined|stated)|unknown)\b", re.I)  # a named disclosure topic that "is not known"
ANALYTICW = re.compile(r"\b(?:why|cause[sd]?|drove|driven|explain\w*|attribut\w*|reasons?|whether|outcome|impact|effect|economic|funded|funding|absorbed|created value|established|proven|verif\w*|judged|adoption|commercial|which source|known|unknown)\b", re.I)
METHODW = re.compile(r"matching passage|risk record|lexical|text search|paraphrase|linked evidence|linked in the register|search of later filings|none exists|reconfirmed|states? that no\b|reports? that no\b|discloses? that no\b", re.I)
SRC_ABSENCE = re.compile(r"\b(?:filing|annual report|report|statements?|note|company|management)\b", re.I)
RECORD_WORDS = re.compile(r"record|register|extract", re.I)


def claim_kind(sentence: str) -> str | None:
    """'disclosure_absence' (a source or the records lack a disclosure), 'analytic_unknown' (a cause, outcome or attribution is not established), 'method' (about our own search or
    a source's stated negative) or None. Quoted filing text is not our claim and is ignored."""
    s = " ".join(re.sub(r"“[^”]*”", " ", str(sentence)).split())
    if METHODW.search(s):
        return "method"
    claim = bool(CLAIM_A.search(s) or CLAIM_B.search(s) or CLAIM_C.search(s) or CLAIM_D.search(s) or CLAIM_E.search(s) or CLAIM_F.search(s))
    if not claim:
        return "analytic_unknown" if ANALYTICW.search(s) and re.search(r"\b(?:not|no)\b", s, re.I) else None
    if ANALYTICW.search(s) and not (CLAIM_C.search(s) or CLAIM_F.search(s) or re.search(r"extracted|carr(?:y|ied)|captured", s, re.I)):
        return "analytic_unknown"
    return "disclosure_absence"


def claim_topic(sentence: str) -> str:
    """Topic of the clause that makes the absence claim (a long sentence can carry unrelated topics in its other clauses)."""
    clauses = re.split(r"[;()]", re.sub(r"“[^”]*”", " ", sentence))
    full = sentence
    clause = next((c for c in clauses if any(rx.search(c) for rx in (CLAIM_A, CLAIM_B, CLAIM_C, CLAIM_D, CLAIM_E, CLAIM_F))), sentence)
    for text in ((clause, full) if CLAIM_D.search(clause) else (clause,)):   # a record-gap clause ("…not yet extracted") takes its topic from the label before it
        for topic, rx in TOPIC_RX:
            if re.search(rx, text, re.I):
                return topic
    return "other"


def rendered_text(a: dict) -> str:
    """Every investor-facing string of an answer object, not only the main narrative fields."""
    parts: list[str] = []
    for f in ("simple_answer", "what_may_mean_economically", "what_is_not_yet_proven", "why_it_matters", "investor_interpretation"):
        parts.append(str(a.get(f) or ""))
    for f in ("what_evidence_shows", "what_to_monitor", "key_points", "evidence_gaps"):
        parts += [str(x) for x in (a.get(f) or [])]
    for d in a.get("deterministic_precision_facts") or []:
        if isinstance(d, dict):
            v = str(d.get("value") or "")
            parts += [str(d.get("semantic_meaning") or "")] + ([] if v.startswith("“") else [v])
    return "\n".join(p for p in parts if p)


def anchor_hits(L: Ledger, topic: str) -> dict:
    return chunk_search(L, ANCHORS[topic]) if topic in ANCHORS else {"chunks_matching": 0, "example_pages": [], "chunks_searched": 0}


def transaction_status(L: Ledger) -> dict:
    """Corporate actions the report itself discloses, split into completed (an effective or completion statement) and pending (subject to approval, proposed). A completed
    action says nothing about whether any other transaction is pending."""
    key = f"txn:{L.fy}"
    if key in L._c:
        return L._c[key]
    out: dict = {"completed": [], "pending": []}
    for ch in (L.j(L.cdir / L.fy / "extracted" / "clean_chunks.json") or {}).get("chunks") or []:
        body = re.sub(r"\s+", " ", re.sub(r"[\x00-\x08\x0b-\x1f•]", " ", str(ch.get("text") or "")))
        if not TXN_ANCHOR.search(body):
            continue
        for sent in re.split(r"(?<=[.;])\s+(?=[A-Z0-9(‘“])", body):
            if len(sent) > 600:
                continue
            if TXN_DONE.search(sent) and re.search(r"scheme|amalgamat|merger|acqui|agreement|NCLT", sent, re.I):
                out["completed"].append({"page": ch.get("page"), "text": sent.strip()})
            elif TXN_PENDING.search(sent) and TXN_ANCHOR.search(sent):
                out["pending"].append({"page": ch.get("page"), "text": sent.strip()})
    L._c[key] = out
    return out


def txn_why(L: Ledger) -> str:
    st = transaction_status(L)
    ev = chunk_search(L, ANCHORS["transactions"])
    pages = ", ".join(map(str, ev["example_pages"][:4]))
    if st["completed"]:
        c = sorted(st["completed"], key=lambda x: not re.search(r"effective date", x["text"], re.I))[0]
        return f"the filing discloses a completed corporate action, p.{c['page']}: “{clean_clip(c['text'], 240)}”; whether any other transaction is pending is not established here"
    return f"the filing mentions it in {ev['chunks_matching']} sections (pages {pages})"


def note_absence(L: Ledger, topic: str, patterns: tuple, label: str, topic_key: str = "") -> str:
    """Write an absence statement for a topic the answer says the records lack, with its state taken from the filing text: mentioned there (NOT_EXTRACTED, pages given) or not
    found after searching it (NOT_DISCLOSED). The state and the claim's topic are recorded with the answer."""
    ev = chunk_search(L, patterns)
    topic_key = topic_key or topic
    if ev["chunks_matching"]:
        state, why = NOT_EXTRACTED, f"the filing mentions it in {ev['chunks_matching']} section{'s' if ev['chunks_matching'] != 1 else ''} (pages {', '.join(map(str, ev['example_pages'][:4]))})"
        phrase = f"{label}: mentioned in the filing but not yet extracted into the records ({why})"
    else:
        state, why = NOT_DISCLOSED, f"{ev['chunks_searched']} sections searched; no match"
        phrase = f"{label}: not found after searching the filing ({why})"
    L.__dict__.setdefault("_absence_notes", []).append({"class": "note:" + topic, "label": label, "state": state, "why": why, "topic": topic_key})
    return phrase


def family_absence(L: Ledger, family: str, label: str, topic_key: str, class_id: str) -> str:
    """Absence sentence for a G3 anchor family (guidance, transactions…), state from the family verdict after the independent re-check in Ledger.gap()."""
    st, why = L.gap(family)
    if st == PARTIAL:
        st, why = NOT_EXTRACTED, "extracted in part"
    kind = "mentioned in the filing but not yet extracted into the records" if st == NOT_EXTRACTED else "not found after searching the filing"
    L.__dict__.setdefault("_absence_notes", []).append({"class": class_id, "label": label, "state": st, "why": why, "topic": topic_key})
    return f"{label}: {kind} ({why})"


ABS_EXTR = re.compile(r"not yet extracted|do(?:es)? not carry|not extracted|not in the (?:extracted )?records|captured in the register", re.I)
ABS_DISC = re.compile(r"found after searching|sections? (?:of the filing )?searched|searched; no match", re.I)
ABS_NA = re.compile(r"does not apply|not applicable", re.I)
ABS_BAD = re.compile(r"records? (?:are|is) silent|does not disclose|do not disclose|not disclosed|undisclosed|no disclosure|silent (?:on|about)", re.I)


def audit_absence(L: Ledger, a: dict) -> dict:
    """Claim-level audit (contract G5). Every disclosure-absence claim in any rendered field must be bound by topic to a provenance entry of its own; a source-level absence
    ('the report provides no…') needs a NOT_DISCLOSED entry; every NOT_DISCLOSED entry needs an anchor review (a defined topic) and is contradicted if the filing carries the
    disclosure; unrelated entries do not count. Analytic unknowns are not disclosure claims."""
    entries = list(a.get("g5_absence") or [])
    untagged, misworded, contradicted, unsupported, linked = [], [], [], [], 0
    seen_topics: set[str] = set()
    for sent in re.split(r"(?<=[.;])\s+(?=[A-Z“\d])", rendered_text(a)):
        if claim_kind(sent) != "disclosure_absence":
            continue
        topic = claim_topic(sent)
        mine = [e for e in entries if e.get("topic") == topic]
        source_level = bool(SRC_ABSENCE.search(sent)) and not RECORD_WORDS.search(sent) and not ABS_EXTR.search(sent) and not ABS_NA.search(sent)
        if ABS_BAD.search(sent) and not any(e["state"] == NOT_DISCLOSED for e in mine):
            misworded.append(sent[:140])
        if not mine:
            untagged.append(sent[:140])
            if topic in ANCHORS and source_level and anchor_hits(L, topic)["chunks_matching"]:
                contradicted.append(sent[:140])
            continue
        linked += 1
        if source_level and not any(e["state"] == NOT_DISCLOSED for e in mine):
            misworded.append(sent[:140])
        if ABS_DISC.search(sent) and not any(e["state"] == NOT_DISCLOSED for e in mine):
            misworded.append(sent[:140])
    for e in entries:
        if e["state"] == NOT_DISCLOSED:
            t = e.get("topic")
            if t not in ANCHORS:
                unsupported.append(e["label"])
            elif anchor_hits(L, t)["chunks_matching"] or (t == "concentration" and find_disclosure(L, BANK_CONC if L.bank else CUSTOMER_CONC)):
                contradicted.append(e["label"])
    return {"untagged": untagged, "misworded": misworded, "contradicted": contradicted, "unsupported": unsupported, "claims_linked": linked, "entries": len(entries)}


def finish(L: Ledger, area: str, qid: str, simple: str, evidence: list[str], econ: str, unproven: str, monitor: list[str], dpfs: list[str | tuple[str, str]], skip_gaps: tuple[str, ...] = ()) -> dict:
    a = m59.mk_answer(simple, evidence, econ, unproven, monitor, [d for d in (dp(L, f, m) for f, m in dpfs) if d])
    a["evidence_gaps"] = gaps_text(L, area, skip_gaps)
    a["g4_coverage"] = ledger_coverage(L, area)
    a["g5_absence"] = [{"class": r["class"], "label": r["label"], "state": r["status"], "why": r["why"], "topic": CLASS_TOPIC.get(r["class"], "bank_measure" if r["status"] == NOT_APPLICABLE else r["class"])} for r in a["g4_coverage"] if r["status"] in (NOT_EXTRACTED, NOT_DISCLOSED, NOT_APPLICABLE)] + list({(n["class"], n["topic"]): n for n in L.__dict__.get("_absence_notes", [])}.values())
    a["g4_basis_note"] = f"Reporting basis follows each figure: {', '.join(sorted({f.basis for f in L.facts.values() if f.basis != 'unknown'})) or 'as stated'}."
    return a


# ───────────────────────────── G4.1 shared helpers ─────────────────────────────
def m2(n: float) -> str:
    """Statement-precision money (two decimals below ₹1,000 crore), for the figures an investor will check against the filing."""
    body = f"₹{abs(n):,.2f} crore" if abs(n) < 1000 else f"₹{abs(n):,.0f} crore"
    return f"−{body}" if n < 0 else body


def clean_clip(t: Any, limit: int = 0) -> str:
    """A complete clause, never a fragment: strips upstream ellipses, drops a trailing incomplete clause, and (with `limit`) cuts at a clause boundary."""
    t = " ".join(str(t or "").split())
    cut = t.endswith(("...", "…"))
    t = t.rstrip(". …")
    if cut:
        i = max(t.rfind("; "), t.rfind(", "), t.rfind(" — "))
        t = t[:i] if i > 40 else re.sub(r"\s+\S*$", "", t)
    if limit and len(t) > limit:
        head = t[:limit]
        i = max(head.rfind("; "), head.rfind(", "), head.rfind(" — "))
        t = head[:i] if i > limit * 0.5 else re.sub(r"\s+\S*$", "", head)
    while t.count("(") > t.count(")"):
        i = t.rfind("(")
        t = t[:i].rstrip(" ,;—-")
    if limit:
        t = re.sub(r"(?:\s+(?:for|the|of|and|to|in|a|an|with|by|on|as|that|which|or|from|into))+$", "", t)
    return t.strip(" ,;")


def fyn(x: Any) -> int:
    m = re.search(r"(\d{2})", str(x or ""))
    return int(m.group(1)) if m else 0


def FY(x: Any) -> str:
    return f"FY{fyn(x):02d}" if fyn(x) else ""


def series(L: Ledger, metric: str) -> list[tuple[str, float, str]]:
    """(fy, value, basis) across every year with a registry fact for the metric, on the latest year's basis only."""
    out = []
    for p in sorted(L.cdir.glob("fy??")):
        f = L.registry(p.name).get(metric)
        if f:
            out.append((p.name, float(f["value"]), f.get("basis") or "unknown"))
    cur = next((b for fy, _, b in out if fy == L.fy), None)
    return [x for x in out if x[2] == cur] if cur and cur != "unknown" else out


def model(L: Ledger) -> dict:
    return L.m("company_model/company_model.json") or {}


BILLING = {"milestone": "as projects reach agreed milestones and the customer accepts them", "usage": "in proportion to usage", "sale": "per unit sold", "interest_spread": "as the spread between what it earns on loans and what it pays for funds",
           "subscription": "through recurring subscriptions", "licence": "through licences"}


# ───────────────────────────── Business ─────────────────────────────
def business(L: Ledger) -> dict:
    n, g = L.name, L.facts.get
    fy = L.fy.upper()
    cm = model(L)
    bm = cm.get("current_business_model") or {}
    sells, payers = g("offerings"), g("payers")

    def lst(f, k=3):
        return [x.strip() for x in f.text.split(";")][:k] if f else []
    sl, pl = lst(sells), lst(payers)
    funders = [x for x in pl if re.search(r"deposit", x, re.I)] if L.bank else []
    pl = [x for x in pl if x not in funders]
    engines = cm.get("revenue_engines") or []
    eng = engines[0] if engines else {}
    pay_how = BILLING.get(str(eng.get("billing_basis") or ""), f"on a {eng.get('billing_basis')} basis" if eng.get("billing_basis") else "")
    simple = f"{n} sells " + (" and ".join(lc_first(x) for x in sl[:2]) if sl else "products and services described in its filings") + (f" to {', '.join(lc_first(x) for x in pl[:2])}" if pl else "")
    if pay_how:
        simple += f", and is paid {pay_how}"
    if funders:
        simple += f"; its lending is funded by {lc_first(funders[0])}"
    simple += "."
    ev: list[str] = []
    if sells and payers:
        ev.append(f"What it sells: {sells.text}. Who pays: {'; '.join(pl) or payers.text}" + (f" (funded by {', '.join(funders)})" if funders else "") + ". (company model, built from the company's own descriptions)")
    revdesc = [clean_clip(e.get("description")) for e in engines if e.get("description")]
    if revdesc:
        wc = clean_clip(eng.get("working_capital_implications") or "")
        ev.append(f"How it earns: {'; '.join(revdesc[:3])}." + (f" The model's note on cash timing: {lc_first(wc)}." if wc and not L.bank else ""))
    p_prev = g(_m(L, "pat", True))
    if L.bank:
        nii, dep, pat, nim, car = g(_m(L, "net_interest_income")), g(_m(L, "total_deposits")), g(_m(L, "pat")), g(_m(L, "net_interest_margin")), g(_m(L, "capital_adequacy_ratio"))
        nip, dpp, nimp = g(_m(L, "net_interest_income", True)), g(_m(L, "total_deposits", True)), g(_m(L, "net_interest_margin", True))
        bits = [f"net interest income {nii.text}" if nii else "", f"deposits {dep.text}" if dep else "", f"profit after tax {pat.text}" if pat else "", f"net interest margin {nim.text}" if nim else ""]
        ev.append(f"Scale in {fy} (as the bank reports it): " + "; ".join(b for b in bits if b) + ".")
        moved = []
        if nii and nip and nii.basis == nip.basis != "unknown" and nip.num:
            moved.append(f"net interest income {(nii.num / nip.num - 1) * 100:+.0f}%")
        if dep and dpp and dep.basis == dpp.basis != "unknown" and dpp.num:
            moved.append(f"deposits {(dep.num / dpp.num - 1) * 100:+.0f}%")
        if nim and nimp:
            moved.append(f"net interest margin {nimp.text} to {nim.text}" + stat_note(L, "net_interest_margin", nim))
        if pat and p_prev and pat.num and p_prev.num:
            if L.comparative.get("pat"):
                moved.append(f"net profit {m2d(p_prev.num)} to {m2d(pat.num)} ({(pat.num / p_prev.num - 1) * 100:+.1f}%, both years in the same audited statement, p.{L.comparative['pat']})".replace("(-", "(−"))
            else:
                moved.append(f"profit after tax {p_prev.text} to {pat.text}" + ("" if pat.basis == p_prev.basis != "unknown" else " (the two years are labelled on different or unstated bases, so treat the change as indicative)"))
        if moved:
            ev.append("Change on the prior year: " + "; ".join(moved) + ".")
    else:
        rev, pat = g(_m(L, "revenue")), g(_m(L, "pat"))
        rp, pp = g(_m(L, "revenue", True)), g(_m(L, "pat", True))
        if rev and pat:
            margin = pat.num / rev.num * 100 if rev.num else None
            gr, gp = growth(L, "revenue"), growth(L, "pat")
            line = f"Scale in {fy} ({rev.basis}): revenue {rev.text}, profit after tax {pat.text}" + (f" ({margin:.1f}% of revenue)" if margin is not None else "")
            if gr is not None:
                line += f"; revenue grew {gr:.1f}%" + (f" and profit {gp:.1f}%" if gp is not None else "") + " on the same basis"
            ev.append(line + ".")
            if rp and pp and rp.num and pp.num and rp.basis == pp.basis == rev.basis != "unknown" and gr is not None and gp is not None:
                m0, m1 = pp.num / rp.num * 100, margin
                if abs(m1 - m0) >= 1.0:
                    ev.append(f"Profit as a share of revenue moved from {m0:.1f}% to {m1:.1f}%: " + (f"profit grew more slowly than revenue ({gp:.1f}% against {gr:.1f}%); the records do not say which costs or items absorbed the difference." if m1 < m0 else f"profit grew faster than revenue ({gp:.1f}% against {gr:.1f}%); the records do not say whether operating leverage or lower charges explain it."))
    mix, seg = g("geography_mix"), g(f"segments@{L.fy}")
    if mix:
        parts = [x for x in re.split(r", (?=[A-Z])", mix.text)]
        line = f"Revenue mix by geography, {mix.fy.upper()} ({mix.basis}): {mix.text}."
        gr = [(re.match(r"(.+?) [\d.]+%", x).group(1), float(re.search(r"\(([+-][\d.]+)% growth\)", x).group(1))) for x in parts if re.search(r"\(([+-][\d.]+)% growth\)", x) and re.match(r"(.+?) [\d.]+%", x)]
        if len(gr) >= 3:
            gr.sort(key=lambda x: -x[1])
            line += f" Growth was fastest in {gr[0][0]} ({gr[0][1]:+.1f}%) and slowest in {gr[-1][0]} ({gr[-1][1]:+.1f}%), so the mix is moving toward the faster-growing regions."
        ev.append(line)
    elif seg:
        ev.append(f"Segments: {seg.text}; one reportable segment does not mean one economic revenue stream.")
    cf_ = g("customer_conc")
    if cf_:
        ev.append(cf_.text + ".")
    roe = g(_m(L, "roe"))
    if roe:
        ev.append(f"Return on equity in {fy}: {roe.text} ({roe.basis}), profit after tax over net worth.")
    mech_full = clean_clip(bm.get("economic_mechanism") or "")
    drv = [d.get("mechanism") for d in cm.get("economic_drivers") or [] if d.get("mechanism")]
    econ = f"What drives profit, in the company's own words: {lc_first(mech_full)}." if mech_full else ""
    if L.bank:
        econ += " A lender earns the spread between loan yields and funding cost, less credit losses, so asset quality, funding cost and capital headroom decide results; industrial working-capital and free-cash-flow measures do not apply."
    elif eng.get("billing_basis") == "milestone":
        econ += " Billing follows milestones and customer acceptance, so profit can be reported before cash is collected; the cash-conversion answer reads that gap."
    elif eng.get("billing_basis"):
        econ += " Revenue timing and cash timing can differ, which is why cash conversion is read separately."
    cov = {r["class"]: r for r in ledger_coverage(L, "BUSINESS")}
    pages = lambda r: ("pages " + re.search(r"pp\.([\d, ]+)", r["why"]).group(1).strip(", ") if re.search(r"pp\.([\d, ]+)", r["why"]) else "in several sections")
    sent = []
    if cov["b_mix"]["status"] in (NOT_EXTRACTED, PARTIAL):
        sent.append(f"Revenue mix by segment or geography: the filing discusses it ({pages(cov['b_mix'])}) but the records do not carry the figures, so the mix is not shown here.")
    if cov["b_visibility"]["status"] == NOT_EXTRACTED:
        sent.append(f"Order book: the filing discusses it ({pages(cov['b_visibility'])}) but the records do not carry the figure, so forward revenue visibility is not sized here.")
    cc = cov["b_concentration"]
    cdisc = None if cf_ else find_disclosure(L, BANK_CONC if L.bank else CUSTOMER_CONC) if cc["status"] == NOT_EXTRACTED else None
    cpages = (f"p.{cdisc['page']}: “{cdisc['text']}”" if cdisc else pages(cc)) if cc["status"] == NOT_EXTRACTED else ""
    if L.bank:
        sent.append({NOT_EXTRACTED: f"Borrower and depositor concentration: the filing discloses it ({cpages}); the records do not carry the full figures.",
                     NOT_DISCLOSED: "Borrower and depositor concentration: no concentration-of-deposits, advances or large-exposure disclosure was found after searching the filing, so it cannot be sized here."}.get(cc["status"], ""))
    else:
        sent.append({NOT_EXTRACTED: f"Customer concentration: the filing discloses it ({cpages}); the records do not carry the full figures.",
                     NOT_DISCLOSED: "Customer concentration: no top-customer, largest-customer or more-than-10%-of-revenue disclosure was found after searching the filing, so it cannot be sized here."}.get(cc["status"], ""))
    diff = clean_clip(drv[1], 200) if len(drv) > 1 else ""
    if diff:
        ev.append(f"The company's own account of what sets it apart (a company claim, not independently tested here): {lc_first(diff)}.")
    sent.append("Whether any advantage earns above-average returns is not shown here; the answer does not rank the company against competitors.")
    unproven = " ".join(x for x in sent if x)
    monitor = ["Customer or segment concentration disclosures in the next annual report.", "Whether growth continues to come with cash generation (see the cash-conversion answer)."]
    if L.bank:
        monitor = ["Net interest margin, credit cost and the quality of the loan book each quarter.", "Deposit growth and funding cost relative to loan growth."]
    dpfs = [(_m(L, "revenue"), "Scale of the business"), (_m(L, "pat"), "Profit"), ("geography_mix", "Where revenue comes from"), (_m(L, "net_interest_income"), "Core bank earnings"), (_m(L, "total_deposits"), "Funding base"), (_m(L, "roe"), "Return on equity")]
    a = finish(L, "BUSINESS", "what-does-company-do", simple, ev, econ, unproven, monitor, dpfs)
    a["key_points"] = [m59.tidy(x) for x in (ev[1] if len(ev) > 1 else "", ev[2] if len(ev) > 2 else "", ev[3] if len(ev) > 3 else "") if x][:3]
    return a


# ───────────────────────────── Management ─────────────────────────────
CLASS_PLAIN = {"HARD_COMMITMENT": "hard commitment (measurable and dated)", "VERIFIABLE_UNDATED": "measurable intention with no date", "DATED_UNVERIFIABLE": "dated intention with no measurable test",
               "OUTLOOK_NOT_COMMITMENT": "outlook, not a promise (the register's paraphrase of management's wording)", "OBSERVATION": "management-reported result (an observation of what already happened, not a promise)", "NOT_TRACKABLE": "stated intention (not testable)"}
BOILERPLATE = re.compile(r"human[- ]rights|\bGRI\b|BRSR|IIRC|\bESG\b|disclos|sustainab|inclusive|culture|compensation|grievance|oversight|carbon|LEED|stakeholder|divers|human resources|\bHR\b|legal education|student|assurance|reporting standards|monitor operations", re.I)
BUSINESS_TERMS = re.compile(r"revenue|margin|growth|launch|expan|capex|deposit|loan|lending|customer|wallet|platform|product|market|acqui|capacity|invest|insurance|pipeline|programme|international|profitab|cash|deploy", re.I)
STOP_WORDS = set("achieve achieved reduction reduce compared baseline year with from that this the and for our company across about their these those which have been will would should into over under more than less target targets plan plans aims aim continue continued focus enhance expand expansion increase improve improvement ensure through towards toward within while also other such between during after before launch build offer develop provide introduce implement strengthen maintain grow".split())
ACHIEVED = re.compile(r"achiev|co-?process(?:ed)|reduc(?:ed|tion)|validated|submitted|\bfiled\b|launched|completed|reached|opened|established|stood at|increased|grew|approved|signed|entered into|commenced|operationali[sz]ed|\d+ (?:new )?(?:RACs?|branches|centres|centers)", re.I)


def stems(stmt: str) -> list[str]:
    out = []
    for t in re.findall(r"[A-Za-z][A-Za-z\-™®]{3,}|\b[A-Z]{3,}s?\b", stmt):
        tl = t.lower().strip("™®")
        if tl not in STOP_WORDS:
            out.append(tl[:6])
    return list(dict.fromkeys(out))


def proper_stems(stmt: str) -> list[str]:
    return list(dict.fromkeys(t.lower().strip("™®")[:6] for t in re.findall(r"\b[A-Z][a-z]{3,}[™®]?", stmt)[1:] if t.lower().strip("™®") not in STOP_WORDS))


def fy_dirs(L: Ledger) -> list[str]:
    return sorted(p.name for p in L.cdir.glob("fy??") if (p / "extracted" / "clean_chunks.json").exists())


def find_disclosure(L: Ledger, patterns: tuple, limit: int = 230) -> dict | None:
    """The report's own sentence that carries a disclosure the structured records lack: the earliest pattern in the priority order that matches, preferring a sentence that
    contains a number. Returned verbatim with its page; the caller states that the records do not carry the figures."""
    best = None
    for ch in (L.j(L.cdir / L.fy / "extracted" / "clean_chunks.json") or {}).get("chunks") or []:
        body = re.sub(r"\s+", " ", re.sub(r"[\x00-\x08\x0b-\x1f•]", " ", str(ch.get("text") or "")))
        for sent in re.split(r"(?<=[.;])\s+(?=[A-Z0-9(])", body):
            for rank, pat in enumerate(patterns):
                m = re.search(pat, sent, re.I)
                if m:
                    key = (rank, 0 if re.search(r"\d", sent[max(0, m.start() - 60): m.end() + 160]) else 1, len(sent))
                    if best is None or key < best[0]:
                        best = (key, ch.get("page"), sent, m.start())
                    break
    if not best:
        return None
    sent, at = best[2], best[3]
    if len(sent) > limit:
        lo = max(0, at - 40)
        piece = sent[lo:lo + limit]
        piece = re.sub(r"^\S*\s", "", piece) if lo else piece
        sent = fix_brackets(re.sub(r"\s\S*$", "", piece))
    sent = sent.strip()
    return {"page": best[1], "text": sent + ("" if re.search(r"[.;!?]$", sent) else "…")}


def fix_brackets(q: str) -> str:
    """Drop an unmatched opening bracket at the end or closing bracket at the start of a cropped window; list enumerators such as 'b)' are not brackets."""
    t = re.sub(r"(?<![\w)])[a-z]\)", lambda m: "#" * len(m.group()), q)
    while t.count("(") > t.count(")"):
        i = t.rfind("(")
        q, t = q[:i].rstrip(" ,;"), t[:i]
    while t.count(")") > t.count("("):
        i = t.find(")")
        q, t = q[i + 1:].lstrip(" ,;"), t[i + 1:]
    return q


def progress(L: Ledger, c: dict, limit_chars: int = 150) -> list[dict]:
    """Later (or same-year) annual-report sentences that report an outcome for this statement, found by lexical match on its distinctive terms, with the outcome
    wording within 150 characters of those terms. They are retrieved, not linked in the commitment register, and the answer says so. A statement that is not
    itself measurable needs a stricter match. Quotes are verbatim windows with their page."""
    stmt = str(c.get("original_statement") or "")
    st, pr = stems(stmt), set(proper_stems(stmt))
    strict = c.get("commitment_class") not in ("HARD_COMMITMENT",)
    need = max(3, -(-len(st) * 3 // 4)) if strict else max(2, len(st) // 2)
    own_nums = set(re.findall(r"\d+(?:\.\d+)?", stmt))
    ann = str(c.get("announcement_period") or "")
    df = {x: 0 for x in st}
    for fy in fy_dirs(L):
        for ch in (L.j(L.cdir / fy / "extracted" / "clean_chunks.json") or {}).get("chunks") or []:
            tl = str(ch.get("text") or "").lower()
            for x in st:
                if x in tl:
                    df[x] += 1
    seen_stems = [x for x in st if df[x] > 0]
    pool = [x for x in seen_stems if x in pr] or seen_stems
    rare = min(pool, key=lambda x: df[x]) if pool else None     # the statement's most distinctive term must appear in any matching sentence
    cands: list[tuple] = []
    for fy in fy_dirs(L):
        if fy < (f"fy{fyn(ann) - 1:02d}" if not strict else ann):
            continue
        chunks = (L.j(L.cdir / fy / "extracted" / "clean_chunks.json") or {}).get("chunks") or []
        for ch in chunks:
            text = re.sub(r"\s+", " ", re.sub(r"[\x00-\x08\x0b-\x1f•]", " ", str(ch.get("text") or "")))
            for s in re.split(r"(?<=[.;])\s+(?=[A-Z0-9(])", text):
                if len(s) > 900:
                    continue
                sl = s.lower()
                hit = [x for x in st if x in sl]
                pn = [x for x in pr if x in sl]
                nums = {x for x in re.findall(r"\d+(?:\.\d+)?", s) if x not in own_nums and not re.fullmatch(r"(?:19|20)\d\d", x)}
                if re.search(rf"(?:{MONTHS})(?:\s+\d{{1,2}},?)?\s+(?:19|20)\d\d", s):
                    nums.add("date")
                if (not nums and not (rare in pr)) or not ((len(hit) >= need) or (not strict and pn)) or (rare and rare not in sl):
                    continue
                keys = [m.start() for m in re.finditer("|".join(map(re.escape, (pn or hit))), sl)]
                if not keys:
                    continue
                key = sl.find(rare) if rare and rare in sl else keys[0]
                outs = [m.start() for m in ACHIEVED.finditer(s)]
                if not outs:
                    continue
                mo = min(outs, key=lambda o: abs(o - key))
                if abs(key - mo) > 150:
                    continue
                score = len(hit) + (2 if pn else 0) + (1 if "%" in s else 0) - (9 if re.search(r"expected to|will be|plans? to|aims? to|intends? to|targets? to", s[max(0, key - 80):key + 120], re.I) else 0)
                numre = rf"\d+(?:\.\d+)?\s?%|\d+\.\d+|\d{{1,3}}(?:,\d{{3}})+(?!\d)|(?:{MONTHS})(?:\s+\d{{1,2}},?)?\s+(?:19|20)\d\d"
                nums_in = [m for m in re.finditer(numre, s) if m.group().strip("% ") not in own_nums and not re.fullmatch(r"(?:19|20)\d\d", m.group())]
                near = [m for m in nums_in if abs(m.start() - key) <= 60] or [m for m in nums_in if abs(m.start() - mo) <= 60 and abs(m.start() - key) <= 220]
                if not near and not (rare in pr and re.search(r"entered into|signed|validated|approved|launched|filed", s[max(0, key - 200):key + 120], re.I)):
                    continue      # a named event (a partner, a product) can be reported without a figure; anything else needs one
                m_ = min(near, key=lambda m: abs(m.start() - key)) if near else None
                anchor = max(m_.end() if m_ else 0, key + 12, mo + 20)
                tail_end = re.search(r"[,.;)]", s[anchor:anchor + 25])
                lo, hi = max(0, min(key, mo, m_.start() if m_ else key) - 25), min(len(s), anchor + (tail_end.start() if tail_end else 10))
                hi = min(hi, lo + 280)
                dates = {re.sub(r"\s+", " ", d.group()) for d in re.finditer(rf"(?:{MONTHS})(?:\s+\d{{1,2}},?)?\s+(?:19|20)\d\d", s[lo:hi])}
                q = s[lo:hi]
                if lo and s[lo - 1] != " ":
                    q = re.sub(r"^\S*\s", "", q)
                cut_mid = hi < len(s) and s[hi:hi + 1] not in (".", ";", ",", ")")
                if hi < len(s) and s[hi:hi + 1] not in (" ", ".", ";", ",", ")"):
                    q = re.sub(r"\s\S*$", "", q)
                q = fix_brackets(q)
                sig = {x for x in re.findall(r"\d+(?:\.\d+)?(?=\s?%)|\d+\.\d+", q)}
                cands.append((score, fy, int(ch.get("page") or 0), ("…" if lo else "") + q.strip() + ("…" if cut_mid else ""), sig, dates))
    cap = 4 if not strict else 2
    # passages that carry a date are kept when their dates differ (so a conflict cannot be hidden); otherwise the best passage of each year
    cands.sort(key=lambda c: (-c[0], 0 if c[4] else 1, len(c[3])))
    chosen, seen_dates = [], set()
    for c in cands:
        if c[5] and not c[5] <= seen_dates:
            chosen.append(c)
            seen_dates |= c[5]
    years = {c[1] for c in chosen}
    for c in cands:
        if c[1] not in years:
            chosen.append(c)
            years.add(c[1])
    chosen = sorted(chosen, key=lambda c: (c[1], c[2]))[-cap:]
    out = [{"fy": fy, "page": page, "quote": q, "score": score} for score, fy, page, q, sig, dates in chosen]
    return sorted(out, key=lambda x: (x["fy"], x["page"]))


MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def date_conflict(quotes: list[dict]) -> str:
    """Different dates attached to the same event verb in different places are reported as a conflict, never reconciled."""
    for verb in ("validat", "submitted", r"\bfiled\b", "approved", "launched"):
        ds = {}
        for q in quotes:
            if re.search(verb, q["quote"], re.I):
                for m in re.finditer(rf"((?:{MONTHS})(?:\s+\d{{1,2}},?)?\s+\d{{4}})", q["quote"]):
                    ds.setdefault(re.sub(r"\s+", " ", m.group(1)), q)
        if len({re.sub(r"\d{1,2},?\s", "", d) for d in ds}) >= 2:
            return "Reported dates differ and are not reconciled here: " + "; ".join(f"{d} ({FY(q['fy'])} p.{q['page']})" for d, q in ds.items()) + "."
    return ""


def named_score(c: dict) -> float:
    s = str(c.get("original_statement") or "")
    return (2 if re.search(r"\d", s) else 0) + len(BUSINESS_TERMS.findall(s)) * 0.7 + len(proper_stems(s)) * 0.5 - (3 if BOILERPLATE.search(s) else 0)


def featured(L: Ledger) -> list[dict]:
    cs = L._commitments
    hard = [c for c in cs if c.get("commitment_class") == "HARD_COMMITMENT"]
    key = lambda c: (-named_score(c), -fyn(c.get("announcement_period")))
    testable = sorted([c for c in cs if c.get("commitment_class") in ("VERIFIABLE_UNDATED", "DATED_UNVERIFIABLE") and named_score(c) >= 0.0], key=key)
    outlook = sorted([c for c in cs if c.get("commitment_class") == "OUTLOOK_NOT_COMMITMENT" and named_score(c) >= 0.0], key=key)
    named = sorted([c for c in cs if c.get("commitment_class") == "NOT_TRACKABLE" and named_score(c) >= 1.0], key=key)
    obs = sorted([c for c in cs if c.get("commitment_class") == "OBSERVATION" and named_score(c) >= 1.0 and re.search(r"\d", str(c.get("original_statement")))], key=key)
    return hard + testable[:3] + outlook[:2] + named[:2] + obs[:2]


def short_stmt(stmt: str, words: int = 7) -> str:
    w = str(stmt).rstrip(".").split()
    return " ".join(w[:words]) + (" …" if len(w) > words else "")


import datetime as _dt

AS_OF = _dt.date(2026, 10, 13)       # the explicit assessment date; set with --as-of, never inferred from the latest filing


def fy_end(fy: Any) -> _dt.date:
    return _dt.date(2000 + fyn(fy), 3, 31)          # Indian fiscal year ends 31 March


def deadline_date(text: str) -> _dt.date | None:
    """The calendar date a stated deadline falls on: 'FY 2025-26' is 31 March 2026, 'H1 2024' is 30 June 2024, 'by 2025' is 31 December 2025. None when it cannot be read."""
    t = str(text or "")
    m = re.search(r"FY\s?(\d{4})\s?[-–]\s?(\d{2,4})", t, re.I)
    if m:
        return _dt.date(int(m.group(1)) + 1, 3, 31)
    m = re.search(r"\bFY\s?(\d{2})\b", t, re.I)
    if m:
        return _dt.date(2000 + int(m.group(1)), 3, 31)
    m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d\d)\b", t, re.I)
    if m:
        mo = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"].index(m.group(1).lower()) + 1
        nxt = _dt.date(int(m.group(2)) + (mo == 12), mo % 12 + 1, 1)
        return nxt - _dt.timedelta(days=1)
    m = re.search(r"\bH([12])\s?(?:CY)?\s?(?:20)?(\d{2})\b", t, re.I)
    if m:
        return _dt.date(2000 + int(m.group(2)), 6 if m.group(1) == "1" else 12, 30 if m.group(1) == "1" else 31)
    m = re.search(r"\b(20\d\d)\b", t)
    if m:
        return _dt.date(int(m.group(1)), 12, 31)
    return None


def fmt_date(d: _dt.date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def achievement(c: dict, pr: list[dict]) -> dict | None:
    """For a quantified target whose later filings report a figure for the same measure: the latest reported value against the target. Values are read from the retrieved
    passages themselves; a target stated as a ceiling is not judged this way."""
    stmt = str(c.get("original_statement") or "")
    if (c.get("commitment_basis") or {}).get("verifiable_outcome") != "quantified_target" or re.search(r"below|under|less than|at most|no more than|maximum", stmt, re.I):
        return None
    t = re.search(r"(\d+(?:\.\d+)?)\s?%", stmt)
    if not t or not pr:
        return None
    T = float(t.group(1))
    for q in sorted(pr, key=lambda q: (fyn(q["fy"]), q["page"]), reverse=True):
        vals = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s?%", q["quote"]) if float(x) != T]
        if vals:
            return {"value": vals[0], "target": T, "fy": q["fy"], "page": q["page"], "met": vals[0] >= T}
    return None


def commitment_block(L: Ledger, c: dict) -> tuple[str, list[dict], dict]:
    cls = c.get("commitment_class")
    stmt = clean_clip(str(c.get("original_statement")).rstrip("."), 240 if cls == "OBSERVATION" else 110 if cls == "HARD_COMMITMENT" else 150)
    ref = (c.get("source_references") or [{}])[0]
    basis = c.get("commitment_basis") or {}
    dl = str(basis.get("deadline_text") or (c.get("expected_timeframe") if str(c.get("expected_timeframe")).lower() not in ("unspecified", "") else "")).strip()
    dd = deadline_date(dl)
    dl_show = (dl[:1].lower() + dl[1:]) if dl and re.match(r"[A-Z][a-z]", dl) else dl
    head = f"“{stmt}” — {CLASS_PLAIN.get(cls, cls)}; {'reported' if cls == 'OBSERVATION' else 'announced'} {FY(c.get('announcement_period'))}" + (f" p.{ref.get('page')}" if ref.get("page") else "") + (f", deadline {dl_show}" if dl_show else "") + "."
    pr = progress(L, c)
    tail = ""
    if pr:
        tail += " Later filings: " + " | ".join(f"{FY(q['fy'])} p.{q['page']} “{q['quote']}”" for q in pr) + "."
        conflict = date_conflict(pr)
        if conflict:
            tail += " " + conflict
    elif cls in ("HARD_COMMITMENT", "VERIFIABLE_UNDATED", "DATED_UNVERIFIABLE"):
        tail += (" No later outcome sentence found." if getattr(L, "_miss_said", False) else " No later sentence reporting an outcome was found by text search (lexical, so not proof none exists).")
        L._miss_said = True
    info: dict = {"deadline": dd, "state": None}
    prev_v = None
    if pr:
        olds = [achievement(c, [q for q in pr if fyn(q["fy"]) < fyn(x["fy"])]) for x in pr]
        prev_v = max((o for o in olds if o), key=lambda o: fyn(o["fy"]), default=None)
    regulatory = bool(pr) and any(re.search(r"validat|submission|\bfiled\b|authori[sz]ation|approv", q["quote"], re.I) for q in pr)
    ach = achievement(c, pr) if cls == "HARD_COMMITMENT" else None
    evidence_end = fy_end(L.fy)
    if cls in ("HARD_COMMITMENT", "DATED_UNVERIFIABLE") and dd:
        if dd > AS_OF:
            tail += f" The deadline ({fmt_date(dd)}) is after the assessment date ({fmt_date(AS_OF)}), so delivery cannot be judged yet."
            info["state"] = "future"
            if ach:
                tail += f" Latest reported figure: {ach['value']:g}% against the {ach['target']:g}% target ({FY(ach['fy'])} p.{ach['page']}); " + ("it is ahead of target." if ach["met"] else "it is below target" + (f" and below the {prev_v['value']:g}% reported for {FY(prev_v['fy'])}; the cause is not stated." if prev_v and prev_v["value"] > ach["value"] else "."))
        else:
            tail += f" The deadline ({fmt_date(dd)}) has passed as of {fmt_date(AS_OF)}."
            if ach and ach["met"] and fy_end(ach["fy"]) <= dd:
                tail += f" Management reports the target met: {ach['value']:g}% against {ach['target']:g}% in {FY(ach['fy'])} (p.{ach['page']}). This is management-reported, not independently assured, and no economic outcome is shown."
                info["state"] = "met_reported"
            elif regulatory:
                tail += " The passages report a regulatory step; compliance with the stated date, approval and any commercial return are separate questions that are not established."
                info["state"] = "regulatory"
            elif ach:
                tail += f" The latest reported figure ({ach['value']:g}% against {ach['target']:g}%, {FY(ach['fy'])} p.{ach['page']}) does not show the target met."
                info["state"] = "short"
            else:
                tail = tail.replace(" No later sentence reporting an outcome was found by text search (lexical, so not proof none exists).", "").replace(" No later outcome sentence found.", "")
                tail += " Delivery outcome unknown: " + (f"the latest annual report held ({FY(L.fy)}, year to {fmt_date(evidence_end)}) predates the deadline" if evidence_end < dd else f"no outcome sentence was found in the latest annual report held ({FY(L.fy)})") + ("." if getattr(L, "_unknown_said", False) else "; unknown is not a miss.")
                L._unknown_said = True
                info["state"] = "unknown_after_deadline"
    elif cls in ("HARD_COMMITMENT", "DATED_UNVERIFIABLE"):
        info["state"] = "undated"
        if dl:
            tail += " The deadline wording is not a calendar date, so it is not judged as passed or ahead."
    return head + tail, pr, info




STATUS_PLAIN = {"delivered": "delivered", "partially_delivered": "partially delivered", "in_progress": "in progress"}


def execution_items(L: Ledger, cap: int = 3) -> list[dict]:
    """Named initiatives the progression tracker has moved past 'announced', each with its latest dated event, verification status and the tracker's own note.
    Generic category headings and exchange-filing headers are not initiatives and are skipped."""
    prog = L.m("management_progression/management_progression.json") or {}
    out = []
    for it in prog.get("progression_items") or []:
        st = it.get("current_status")
        theme = clean_clip(it.get("theme") or "", 230)
        if st not in STATUS_PLAIN or len(theme) < 40 or re.match(r"(?:SEC|SE)/|\d+ About|Capital Allocation|Leadership|International Expansion", theme) or BOILERPLATE.search(theme) \
                or re.search(r"cited as|referenced as|described as|commission(?:ed|ing)|independent (?:assessment|research)|IPSOS|survey|\((?:Dividend|part of)", theme, re.I):
            continue
        evs = [e for e in it.get("events") or [] if e.get("event_type") and e.get("verification_status")]
        if not evs:
            continue
        last = max(evs, key=lambda e: (fyn(e.get("event_period") or e.get("source_period")), 1 if e.get("role") in ("completion", "milestone", "outcome") else 0))
        note = next((clean_clip(last.get(k), 130) for k in ("operational_outcome", "financial_or_business_outcome", "action_taken") if last.get(k) and str(last.get(k)).strip()), "")
        if note.startswith("[") or len(note) < 15 or re.search(r"earnings release|mode of fund", note, re.I):
            note = ""
        note = re.sub(r"not yet visible", "not visible so far", note)
        score = (1.0 if re.search(r"\d", note) else 0) + {"delivered": 3, "partially_delivered": 2.5, "in_progress": 1.5}[st] + named_score({"original_statement": theme}) * 0.5 + 0.3 * fyn(last.get("event_period") or last.get("source_period")) / 10
        out.append({"theme": theme, "status": STATUS_PLAIN[st], "fy": last.get("event_period") or last.get("source_period"), "verification": str(last.get("verification_status")).replace("_", " "), "note": note, "score": score})
    out.sort(key=lambda x: -x["score"])
    return out[:cap]


def management(L: Ledger) -> dict:
    L._miss_said = L._unknown_said = False
    n, g, fy = L.name, L.facts.get, L.fy.upper()
    feats = featured(L)
    hard = [c for c in feats if c.get("commitment_class") == "HARD_COMMITMENT"]
    PRIO = {"HARD_COMMITMENT": 0, "VERIFIABLE_UNDATED": 1, "DATED_UNVERIFIABLE": 1, "OUTLOOK_NOT_COMMITMENT": 4, "OBSERVATION": 5, "NOT_TRACKABLE": 6}
    items: list[tuple[int, str]] = []
    prog, infos = {}, {}
    for c in feats:
        text, pr, info = commitment_block(L, c)
        items.append((PRIO.get(c.get("commitment_class"), 6), text))
        prog[c["commitment_fingerprint"][:8]] = pr
        infos[c["commitment_fingerprint"][:8]] = info
    execs = execution_items(L)
    for e in execs:
        done = e["status"] == "delivered"
        later = bool(re.search(r"future|subsequent|next phase|later phase", e["note"], re.I))
        items.append((2, f"Tracker evidence, not primary-source proof: “{e['theme']}” is marked {e['status']} (latest event {FY(e['fy'])}, tracker verification: {e['verification']})" + (f"; tracker note: {lc_first(e['note'])}" if e["note"] else "") + "."
                      + (" The note also points to later phases, so what is complete is unresolved." if later else "") + ("" if done else " Completion is not established.")))
    L.quote_numbers = sorted({float(x.replace(",", "")) for ps in prog.values() for q in ps for x in re.findall(r"\d[\d,]*\.?\d*", q["quote"]) if x.replace(",", "").replace(".", "").isdigit()})
    cnt = L.counts
    total = sum(cnt.values())
    found = any(prog[c["commitment_fingerprint"][:8]] for c in hard)
    if hard:
        simple = (f"{n} has {len(hard)} hard (measurable and dated) commitment" + ("" if len(hard) == 1 else "s") + f" among {total} recorded statements; "
                  + ("later filings report progress on " + ("all" if all(prog[c['commitment_fingerprint'][:8]] for c in hard) else "some") + " of them, shown below with pages, though the commitment register has not linked that evidence." if found
                     else "the register has no linked evidence on them and the search of later filings found none, which does not show none exists."))
    else:
        simple = f"{n} has no measurable-and-dated commitment among {total} recorded statements; the named intentions and tracked initiatives below, what later filings report on them, and what management did with capital are the evidence on management."
    head = f"Register classes: {L.facts['commitment_counts'].text}. “Unable To Verify” means no evidence is linked in the register, not that none exists; outlooks, observations and external targets are not hard commitments."
    tail_ev = []
    cap = []
    div, bb, bbc, cx = g(_m(L, "dividends_paid")), g(_m(L, "buyback_paid")), g("buyback_consideration"), g(_m(L, "capex"))
    if div:
        cap.append(f"dividends paid {m2(div.num)}")
    if bbc and bb:
        cap.append(f"a buyback with consideration {bbc.text} (cash outflow including costs {bb.text}; two different measures)")
    elif bb and (bb.num or 0) > 50:
        cap.append(f"cash paid for share buyback {bb.text}")
    if cx:
        cap.append(f"capital expenditure {m2(cx.num)}")
    if cap:
        tail_ev.append(f"What management did with cash in {fy}: " + "; ".join(cap) + ".")
    tx = g("pending_transaction")
    if tx:
        tail_ev.append(f"Transaction status: {tx.text}. Signed is not completed, so no integration or financial effect is assessable yet.")
    states = {v["state"] for v in infos.values()}
    econ_parts = []
    if "met_reported" in states:
        econ_parts.append("A management-reported achievement is not independent assurance or an economic result.")
    if "future" in states:
        econ_parts.append("With the deadline ahead, a figure that moves backward may reflect a changed base and is progress to explain, not a miss.")
    if "regulatory" in states:
        econ_parts.append("A regulatory milestone is a step, not an approval or a commercial return.")
    if "unknown_after_deadline" in states:
        econ_parts.append("Where a deadline has passed and no later filing is held, the outcome is unknown, not missed.")
    if execs:
        econ_parts.append("Tracker labels are tracker evidence and show no adoption, commercial use or economic result.")
    if not econ_parts:
        econ_parts.append("The named intentions carry no testable outcome yet; what was done with cash and what later filings report are the evidence on management.")
    econ = " ".join(econ_parts)
    unproven = " ".join(x for x in (
        "Whether the initiatives above produced revenue or margin is not established.",
        (family_absence(L, "guidance_and_commitments", "Management guidance", "guidance", "m_guidance") + ".") if L.gap("guidance_and_commitments")[0] in (NOT_EXTRACTED, NOT_DISCLOSED) else "",
        ("Transactions mentioned in the filing are not all extracted, so completed and pending deals may be incomplete here." if L.gap("material_transactions")[0] == NOT_EXTRACTED and not tx else ""),
    ) if x)
    monitor = []
    for c in hard[:3]:
        st = infos[c["commitment_fingerprint"][:8]]
        nm = f"“{short_stmt(c['original_statement'], 6)}”"
        dd = st.get("deadline")
        if st["state"] == "met_reported":
            monitor.append(f"Whether the reported result on {nm} holds after the deadline on the commitment's own definition, and whether any independent assurance exists.")
        elif st["state"] == "unknown_after_deadline":
            monitor.append(f"The first annual report after {fmt_date(dd)} on {nm}: completed, partly completed or missed.")
        elif st["state"] == "regulatory":
            monitor.append(f"The original filing date and any approval decision for {nm}.")
        elif st["state"] == "future":
            monitor.append(f"The next disclosure of the same measure on {nm}, with the cause of any reversal.")
        else:
            monitor.append(f"Delivery evidence on {nm}, on the commitment's own definition.")
    if tx:
        monitor.append("Completion status and terms of the announced transaction.")
    soft = [c for c in feats if c.get("commitment_class") != "HARD_COMMITMENT"]
    if soft and len(monitor) < 4:
        monitor.append("Whether later filings report a measurable outcome for the named intentions above, starting with " + " and ".join(f"“{short_stmt(c['original_statement'], 5)}”" for c in soft[:2]) + ".")
    if execs and len(monitor) < 4:
        e0 = execs[0]
        monitor.append(f"Evidence of adoption, commercial use or economic results for “{short_stmt(e0['theme'], 6)}”." if e0["status"] == "delivered" else f"Verified completion and downstream effect of “{short_stmt(e0['theme'], 6)}”.")
    dpfs = [(f"hard:{h['commitment_fingerprint'][:8]}", "A measurable, dated management commitment") for h in hard] + [("commitment_counts", "How management statements are classified"), (_m(L, "dividends_paid"), "Cash returned"), ("buyback_consideration", "Buyback consideration"), (_m(L, "capex"), "Capital invested"), ("pending_transaction", "Transaction state")]

    def build(its: list[tuple[int, str]]) -> dict:
        return finish(L, "MANAGEMENT", "what-has-management-promised", simple, [head] + [t for _, t in sorted(its, key=lambda x: x[0])] + tail_ev, econ, unproven, monitor[:4], dpfs)
    keep = list(items)
    a = build(keep)
    # stay inside the word budget: drop the lowest-priority items, then the guidance-gap sentence, then the cash line; never a hard commitment
    while m59.words(a) > 598 and any(p > 0 for p, _ in keep):
        worst = max(range(len(keep)), key=lambda i: (keep[i][0], i))
        keep.pop(worst)
        a = build(keep)
    if m59.words(a) > 598:
        i = unproven.find("Management guidance:")
        if i >= 0:
            j = unproven.find(")).", i)
            unproven = (unproven[:i] + (unproven[j + 3:] if j >= 0 else "")).strip()
        a = build(keep)
    if m59.words(a) > 598 and tail_ev and tail_ev[0].startswith("What management did with cash"):
        tail_ev = tail_ev[1:]
        a = build(keep)
    while m59.words(a) > 598 and len(monitor) > 2:
        monitor.pop()
        a = build(keep)
    shown = [t for _, t in sorted(keep, key=lambda x: x[0])]
    a["key_points"] = [m59.tidy(simple)] + [m59.tidy(b.split(" Later filings")[0].split(" No later sentence")[0]) for b in shown[:2]]
    a["g41_progress"] = prog
    a["g41_execution_items"] = execs
    return a


# ───────────────────────────── Risks ─────────────────────────────
# The channel is decided from the filing's own risk wording (not from the registry's generic category label, which is often a template), and the
# consequence is stated conditionally and only for what that wording supports. A risk whose wording supports no channel is shown with that limit.
SOCIAL_PROGRAMME = re.compile(r"beneficiar|scholarship|students?\b|education|low[- ]income|underserved communit|remote (?:and|communit)|communities|\bcsr\b|text[- ]alert|access to (?:quality )?healthcare|healthcare (?:access|services)|philanthrop", re.I)
INDUSTRY_CONTEXT = re.compile(r"across the industry|industry[- ]wide|sector[- ]wide|economy[- ]wide|in the (?:microfinance|banking|nbfc) sector|macro-?economic|market liquidity crunch|adverse market", re.I)
CHANNELS: list[dict] = [
    {"id": "cyber", "label": "Cyber-security and platform continuity", "re": r"cyber|information security|data breach|security risk|outage|business continuity", "bank": None,
     "then": "A breach or prolonged outage can bring service credits, customer loss and regulatory action.", "unk": "any realised incident or loss in the records read here",
     "mon": "Any disclosed security incident, regulator action or service-level penalty."},
    {"id": "carrier_terms", "label": "Carrier commercial terms and revenue sharing", "re": r"carrier|revenue-share|interconnect|multi-carrier", "bank": None,
     "then": "If carrier terms or revenue-share arrangements change, the share of each unit of traffic revenue the company keeps changes with them; this is a commercial-terms exposure, separate from whether a partner's service keeps running.", "unk": "current terms, any renegotiation and the revenue share at stake",
     "mon": "Carrier contract renewals and any change in revenue-share terms."},
    {"id": "partner", "label": "Third-party service dependency", "re": r"third-party (?:service|ecosystem)|non-substitutable|ecosystem partner|partnership dependence|single technology vendor|exclusive third|hardware suppliers", "bank": None,
     "then": "If a non-substitutable partner's service fails or is withdrawn, delivery of the dependent product stops until it is restored; management's disclosed mitigation and escalation limit but do not remove this.", "unk": "any realised disruption and the revenue that depends on the partner",
     "mon": "Any service-disruption event, partner concentration and the effectiveness of the disclosed escalation protocols."},
    {"id": "quality_reg", "label": "Quality systems and regulatory standing", "re": r"quality system|quality[- ]system|regulatory|inspection|compliance|warning letter|\bfda\b|shortcoming", "bank": False,
     "then": "A quality or compliance lapse can draw regulator action that delays approvals, interrupts supply or adds remediation cost, depending on the sites involved.", "unk": "which sites or products are affected, and any financial effect",
     "mon": "Inspection outcomes, regulator observations and any product recall or supply interruption."},
    {"id": "tech_obsolescence", "label": "Technology change and product obsolescence", "re": r"obsolete|obsolescence|technological advancements?|render existing", "bank": False,
     "then": "Faster technology change can leave existing products less competitive, requiring more development spend or lower pricing; the filing ties the exposure to the company's continued innovation.", "unk": "the share of revenue from products near the end of their cycle",
     "mon": "New-product launches, development spend and the age profile of the revenue base."},
    {"id": "scalability", "label": "Platform scalability and the cost of scaling", "re": r"scalab|near[- ]zero incremental|incremental (?:operational )?costs?|platform (?:upgrade|capabilit)|upgrades? and reliance on engineering|enhance platform capabilit", "bank": False,
     "then": "If the cost of serving more volume does not stay near the low level management cites, margins narrow as revenue grows.", "unk": "any cost increase attributable to scaling",
     "mon": "Gross margin and technology cost against revenue growth."},
    {"id": "intl_execution", "label": "Execution of international expansion", "re": r"international expansion|expansion blueprint|local deployment|monetisation|monetization|commerciali[sz]ation", "bank": False,
     "then": "Expansion abroad needs local deployments and customers before it adds revenue; delay leaves cost without matching income.", "unk": "revenue by region and the contribution of new markets",
     "mon": "Revenue outside India, new-market customer wins and deployment milestones."},
    {"id": "import_dependence", "label": "Dependence on non-domestic technology", "re": r"non-?indigenous|foreign technology|import(?:ed)? dependence|dependen\w* on (?:foreign|imported|non-domestic)", "bank": False,
     "then": "Where domestic alternatives are limited, delivery depends on foreign-sourced technology, exposing cost, availability and export-control risk; the content affected is not shown.", "unk": "the share of content or revenue that depends on non-domestic technology",
     "mon": "Import share of key components and any change in availability or export-control terms."},
    {"id": "supply", "label": "Supply continuity and key-input dependence", "re": r"supply[- ]chain|supplier|yield issues|intermediates|insufficient inventory|continuity of supply|(?:input|material|component)s? availability", "bank": False,
     "then": "A key-input or single-supplier interruption can stop shipments of the dependent product, in proportion to the revenue it carries.", "unk": "the share of revenue exposed to the dependent input",
     "mon": "Supplier concentration, input availability and inventory cover."},
    {"id": "pricing", "label": "Price erosion and customer bargaining power", "re": r"price erosion|pricing pressure|bargaining power|downward pricing|price competition|price cuts", "bank": False,
     "then": "Lower realisations on existing products cut revenue and margin in the affected market unless volume or mix offsets them.", "unk": "the profit effect of price erosion",
     "mon": "Price and volume trends and gross margin in the affected market."},
    {"id": "concentration", "label": "Revenue concentration", "re": r"concentration|vulnerability in the (?:us|u\.s\.)|(?:us|u\.s\.) market|dependence on (?:defen[cs]e|a few|key)|sector priorities|large share of total", "bank": False,
     "then": "", "unk": "", "mon": "Revenue by product, market and customer in the next annual report."},
    {"id": "project_execution", "label": "Project approval and delivery timing", "re": r"project approval|project (?:expected|delay)|delivery timing|execution and delivery|slippage|commissioning|approval received after", "bank": False,
     "then": "A late approval or delivery pushes revenue recognition, customer acceptance and the cash that follows into later periods; the effect depends on contract terms the records do not show.", "unk": "the amount and timing of revenue exposed to the delay",
     "mon": "Project milestones achieved, approvals received and delivery dates met against plan."},
    {"id": "orders", "label": "Order inflow and capacity utilisation", "re": r"order inflow|inflow of|winning large contracts|capacity utili[sz]ation|development and production orders", "bank": False,
     "then": "Revenue depends on a continuing flow of development and production orders; a gap leaves capacity idle and delays cost recovery.", "unk": "the size and timing of orders in hand",
     "mon": "New orders, order book and capacity utilisation."},
    {"id": "gov_policy", "label": "Government spending and policy", "re": r"government (?:spending|policy|procurement|contracts)|reliance on government|defen[cs]e regulations|regulations/policy|policy changes", "bank": False,
     "then": "Where government is the main buyer, budget timing, procurement rules and approval cycles set when revenue arrives and how much of it there is.", "unk": "the share of revenue from government customers",
     "mon": "Defence budget allocations, procurement-rule changes and order-award timing."},
    {"id": "legal", "label": "Contingent liabilities and litigation", "re": r"contingent liabilit|litigation|patent|claims|legal|judge?ments?|uncertainty of future cash outflows", "bank": None,
     "then": "An adverse ruling or settlement would be a cash outflow outside normal operations.", "unk": "timing and probability of any outflow",
     "mon": "Contingent-liability notes and the outcome of pending proceedings."},
    {"id": "talent", "label": "Skilled-talent capacity", "re": r"talent|workforce|recruit|retain|upskill|attrition", "bank": None,
     "then": "Scarce skilled people slow delivery and raise cost where output depends on specialists.", "unk": "attrition and hiring-cost effects",
     "mon": "Attrition, hiring and employee cost against revenue."},
    {"id": "inflation", "label": "Input and operating-cost inflation", "re": r"inflation|input and operating costs|cost inflation|cost normali[sz]ation", "bank": False,
     "then": "Higher input and operating costs narrow margin unless contracts let them be passed on, which the records do not show.", "unk": "pass-through terms",
     "mon": "Gross and operating margin through the cost cycle."},
    {"id": "currency", "label": "Currency exposure", "re": r"foreign (?:exchange|currency)|currency risk|exchange[- ]rate|exchange fluctuation", "bank": None,
     "then": "Revenue, costs and borrowings in other currencies move reported results (translation) and cash flows (transaction) when exchange rates move; hedging and local sourcing reduce but do not remove this. International revenue share is not the same as net currency exposure.", "unk": "the net exposure after hedging and any realised effect",
     "mon": "Reported currency effects and hedging disclosures."},
    # bank-specific
    {"id": "credit", "label": "Borrower credit quality", "re": r"over-?indebted|multiple[- ]lending|credit risk|asset quality|\bnpa\b|credit offtake|non-payment|borrower", "bank": True,
     "then": "Borrower stress raises provisions and writes-offs, which cut profit directly and consume capital; the effect shows in credit cost, gross/net NPA and capital adequacy together.", "unk": "credit cost and its trend (asset-quality ratios are the available proxy)",
     "mon": "Gross and net NPA, credit cost and collection efficiency."},
    {"id": "funding", "label": "Funding mix and cost of funds", "re": r"institutional deposits|wholesale|liability providers|cost of funds|fixed deposit rates|savings \(7%\)|deposit growth|shift in customer behavio|bank deposits to other|funding", "bank": True,
     "then": "If deposits grow slowly or cost more, the bank leans on costlier wholesale funding or accepts lower margin.", "unk": "the share of wholesale funding and its cost",
     "mon": "Deposit growth, CASA and retail-deposit share, and cost of funds against loan yields."},
    {"id": "margin", "label": "Margin compression", "re": r"margin compression|profitability margin|yield and nim|nim declined|interest rate margin", "bank": True,
     "then": "If yields fall or funding cost rises faster than loan yields reprice, net interest margin narrows and takes profit with it.", "unk": "the split of the margin change between yield and funding cost",
     "mon": "Net interest margin, yield on advances and cost of funds."},
    {"id": "sector_growth", "label": "Sector-wide slowdown in lending", "re": r"decline in assets under management|curtailed disbursements|negative growth|disbursement", "bank": True,
     "then": "A sector-wide slowdown in microfinance lending lowers loan growth and fee income for lenders in it; whether the bank itself is affected shows in its own advances and disbursement figures.", "unk": "the bank's own advances and disbursement growth (not in the extracted records)",
     "mon": "Gross advances growth, disbursements and assets under management against the sector."},
    {"id": "distribution", "label": "Branch and channel dependence", "re": r"branch|physical reach|digital|channel|fintech|adoption", "bank": True,
     "then": "A franchise built on branches grows only as fast as it can add and staff them; a shift to digital channels can change cost and customer behaviour.", "unk": "cost per branch and the digital share",
     "mon": "Branch additions, digital share of transactions and cost-to-income."},
]
CHANNEL_BY_ID = {c["id"]: c for c in CHANNELS}
CONC_KINDS = [("customer", r"customer|buyer|client", "Customer concentration: the filing wording is about customers, so revenue could swing on the loss or repricing of a major customer; the share of revenue is not quantified here."),
              ("product", r"product|radar|electronic warfare|\bew\b|segment", "Product-line concentration: a large share of revenue sits in a few product lines, so a setback there moves total revenue more than it would for a diversified range. This is about products, not customers; customer concentration is a separate question the records do not size."),
              ("market", r"market|geograph|region|\bus\b|u\.s\.", "Market concentration: a large share of revenue comes from one market, so a downturn or price change there weighs on the total; the filing wording does not give the share."),
              ("sector", r"sector|defen[cs]e", "Sector concentration: revenue depends on one sector's priorities and budgets, so a change in them moves total revenue; the share is not quantified here.")]


OPPORTUNITY = re.compile(r"opportunit|tailwind|growth potential|strengthen\w*|diversif\w*|indigenous|expand\w* (?:our|the|its) |competitive advantage|creates? (?:value|growth)", re.I)
ADVERSE = re.compile(r"risk|vulnerab|depend|relian|\brely|disrupt|failure|\bfail|inability|shortfall|uncertain|delay|strain|declin|erosion|threat|expos|adverse|\bloss|shortage|pressure|volatil|fluctuat|obsole|breach|non-?compliance|penalt|shortcoming|constraint|downtime", re.I)


def classify(text: str, bank: bool) -> dict | None:
    """The economic channel the wording supports. Wording that describes an opportunity or a strength, with no adverse premise, supports no risk channel."""
    if OPPORTUNITY.search(text) and not ADVERSE.search(text):
        return None
    t = text.lower()
    for ch in CHANNELS:
        if ch["bank"] is True and not bank:
            continue
        if ch["bank"] is False and bank:
            continue
        if re.search(ch["re"], t):
            return ch
    return None


def latest_mention(L: Ledger, r: dict) -> dict:
    """The risk's most recent dated wording WITH its own page, from the multi-year evolution record the registry points to. A registry risk is a merge of several
    years' wording; its summary text and 'latest period' do not belong together, so neither is used as a dated fact."""
    best = None
    for ref in r.get("source_references") or []:
        ev = L.evo.get(ref.get("item_id")) if str(ref.get("artifact", "")).endswith("risk_evolution.json") else None
        for m in (ev or {}).get("source_mentions") or []:
            key = (fyn(m.get("source_year")), {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(str(m.get("severity")).lower(), 0))
            if m.get("value") and (best is None or key > best[0]):
                best = (key, m, ref.get("item_id"))
    if best:
        m = best[1]
        return {"fy": str(m["source_year"]), "page": m.get("source_page"), "text": clean_clip(m["value"].rstrip(".")), "severity": str(m.get("severity") or "").lower(), "evo": best[2]}
    txt = re.sub(r";?\s*[^;]*\d[^;]*", "", str(r.get("risk_mechanism") or "")).strip(" ;,")
    return {"fy": str(r.get("latest_period") or ""), "page": None, "text": clean_clip(txt), "severity": str(r.get("evo_latest_severity") or "").lower()}


GENERIC_CAPS = {"Value", "Chain", "Partners", "Company", "Board", "Policy", "Policies", "Risk", "Management", "Governance", "Directors", "Code", "Conduct", "Business", "Group", "Limited"}


def earlier_named(L: Ledger, r: dict, latest: dict) -> dict | None:
    """An older wording of the same risk that names a specific exposure (a product, a counterparty), kept so a specific dependence is not lost behind a later generic sentence."""
    best = None
    for ref in r.get("source_references") or []:
        ev = L.evo.get(ref.get("item_id")) if str(ref.get("artifact", "")).endswith("risk_evolution.json") else None
        for m in (ev or {}).get("source_mentions") or []:
            t = clean_clip(str(m.get("value") or "").rstrip("."))
            names = [w for w in re.findall(r"(?<![.:] )(?<!^)\b[A-Z][a-z]{3,}\b", t) if w not in GENERIC_CAPS]
            fam = lambda x: {"supply": "dep", "partner": "dep", "carrier_terms": "dep"}.get((classify(x, L.bank) or {}).get("id"), (classify(x, L.bank) or {}).get("id"))
            same = fam(t) == fam(latest["text"])
            if t and same and t != latest["text"] and fyn(m.get("source_year")) < fyn(latest["fy"]) and len(names) >= 2 and m.get("source_page") and (best is None or fyn(m["source_year"]) > fyn(best["fy"])):
                best = {"fy": str(m["source_year"]), "page": m["source_page"], "text": t}
    return best


def risk_eligible(r: dict) -> bool:
    sq = r.get("semantic_quality") or {}
    return sq.get("eligibility", "eligible") != "quarantined" and sq.get("relevance_outcome", "KEEP") not in ("DEMOTE", "QUARANTINE") and sq.get("investor_relevance", "core") != "excluded"


MACRO_CONTEXT = re.compile(r"food|commodity|economy|macro|inflation|geopolit|monsoon|weather|pandemic|interest rate environment", re.I)
EXPOSURE_WORDS = r"risk|exposure|dependen|disrupt|fluctuat|mitigat|hedg|derivativ|escalat"


def review_demoted(L: Ledger, r: dict, m: dict, ch: dict | None) -> dict | None:
    """Source-grounded review of a record the relevance filter marked DEMOTE ('valid but secondary'), not QUARANTINE or excluded. It is put back only when (a) the
    latest dated wording supports a company-operational channel and is not economy-wide context, and (b) a passage of that year's report on the same subject
    describes the exposure itself, together with either a high or critical recorded severity or a stated mitigation. The filter stays in force for everything else."""
    sq = r.get("semantic_quality") or {}
    if sq.get("relevance_outcome") != "DEMOTE" or sq.get("investor_relevance") == "excluded" or not ch or ch["id"] in ("talent", "inflation", "legal") or MACRO_CONTEXT.search(m["text"]):
        return None
    loc = locate_passage(L, m["fy"], m["text"], need_re=f"(?:{ch['re']})(?=.*(?:{EXPOSURE_WORDS}))|(?:{EXPOSURE_WORDS}).*(?:{ch['re']})", prefer_page=m["page"], min_overlap=0.3, boost_re=r"mitigat|hedg|derivativ|forward contract|escalat|actively managed", anchor_re=ch["re"])
    if not loc:
        return None
    mitigated = bool(re.search(r"mitigat|hedg|derivativ|escalat|actively managed|local sourcing", page_text(L, m["fy"], loc["page"]), re.I))
    if m["severity"] in ("high", "critical") or mitigated:
        return {"page": loc["page"], "text": loc["text"], "severity": m["severity"], "mitigated": mitigated}
    return None


# ───────────────────────────── G4 final: source attribution ─────────────────────────────
# PRIMARY_QUOTE: exact words found on the cited annual-report page. SOURCE_PARAPHRASE: a risk-record summary of source content, never put in quotation marks.
# ANALYST_INFERENCE: the conditional economic reading, always labelled as analysis. A risk-record sentence is never presented as a filing quotation.
def nrm(t: str) -> str:
    t = str(t).replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def page_text(L: Ledger, fy: str, page: Any) -> str:
    key = f"pg:{fy}:{page}"
    if key not in L._c:
        chunks = (L.j(L.cdir / fy / "extracted" / "clean_chunks.json") or {}).get("chunks") or []
        L._c[key] = " ".join(re.sub(r"\s+", " ", re.sub(r"[\x00-\x08\x0b-\x1f•]", " ", str(c.get("text") or ""))) for c in chunks if c.get("page") == page)
    return L._c[key]


def verify_quote(L: Ledger, fy: str, page: Any, text: str) -> bool:
    return bool(text and page and nrm(text) and nrm(text) in nrm(page_text(L, fy, page)))


WEAK = set("that this with from have been which their there while into over under more than also such other these those risk risks could would should".split())


def content_stems(t: str) -> set:
    return {w.rstrip("s")[:5] for w in re.findall(r"[a-z]{4,}", nrm(t)) if w not in WEAK}


def locate_passage(L: Ledger, fy: str, text: str, need_re: str = "", prefer_page: Any = None, limit: int = 160, min_overlap: float = 0.4, boost_re: str = "", anchor_re: str = "") -> dict | None:
    """The sentence of that year's report that best supports a risk-record summary: most content words in common, optionally required to match a channel pattern."""
    toks = content_stems(re.split(r"\s\(|;", text)[0])      # the first clause carries the claim; trailing qualifiers dilute the match
    if len(toks) < 5:
        toks = content_stems(text)
    if len(toks) < 3:
        return None
    best = None
    for ch in (L.j(L.cdir / fy / "extracted" / "clean_chunks.json") or {}).get("chunks") or []:
        body = re.sub(r"\s+", " ", re.sub(r"[\x00-\x08\x0b-\x1f•]", " ", str(ch.get("text") or "")))
        for sent in re.split(r"(?<=[.;])\s+(?=[A-Z0-9(])", body):
            if len(sent) > 1800 or (need_re and not re.search(need_re, sent, re.I)):
                continue
            common = toks & content_stems(sent)
            ov = len(common) / len(toks)
            if len(common) < 3 or ov < min_overlap:
                continue
            rank = ov - (0.2 if len(sent) < 110 or re.search(r"following table|Amount in|notional", sent, re.I) else 0) + (0.1 if boost_re and re.search(boost_re, sent, re.I) else 0) + (0.08 if ch.get("page") == prefer_page else 0) + (0.02 if ch.get("page") and ch["page"] > 200 else 0) + (0.04 if L.facts.get(f"revenue@{L.fy}") is not None and L.facts[f"revenue@{L.fy}"].basis == "consolidated" and re.search(r"\bGroup\b", sent) else 0)
            if best is None or rank > best[0]:
                best = (rank, ch.get("page"), sent, ov)
    if not best:
        return None
    sent = best[2]
    if len(sent) > limit:        # keep the window of the sentence that holds the most matching words
        words = list(re.finditer(r"\S+", sent))
        hit = [1 if re.sub(r"[^a-z]", "", w.group().lower()).rstrip("s")[:5] in toks else 0 for w in words]
        bi, bs, bj = 0, -1, len(words)
        for i, w in enumerate(words):
            j = i
            while j < len(words) and words[j].end() - w.start() <= limit:
                j += 1
            sc = sum(hit[i:j])
            if anchor_re and not re.search(anchor_re, sent[w.start():words[j - 1].end()], re.I):
                sc -= 100          # a window must contain the subject the passage is meant to evidence
            if boost_re and not re.search(boost_re, sent[w.start():words[j - 1].end()], re.I):
                sc -= 10
            if sc > bs:
                bi, bs, bj = i, sc, j
        idx = [k for k in range(bi, bj) if hit[k]]
        lo_i, hi_i = max(bi, (idx[0] - 3) if idx else bi), min(bj - 1, (idx[-1] + 5) if idx else bj - 1)
        piece = sent[words[lo_i].start():words[hi_i].end()]
        piece = re.split(r"\s(?:Positive|Negative|Neutral):", piece)[0]
        sent = fix_brackets(re.sub(r"(?:\s+(?:for|the|of|and|to|in|a|an|with|by|on|as|that|which|or|from|into|serves|while))+$", "", piece))
    sent = sent.strip()
    return {"page": best[1], "text": sent + ("" if re.search(r"[.;!?]$", sent) else "…"), "overlap": round(best[3], 2)}


def attribute(L: Ledger, fy: str, page: Any, text: str, need_re: str = "") -> dict:
    """PRIMARY_QUOTE when the record's own words are on the cited page; otherwise the record text is a SOURCE_PARAPHRASE and the best verbatim passage is shown beside it
    (first on the cited page, then anywhere in that year's report, with a stricter match); with no passage the record text stays a labelled paraphrase."""
    if verify_quote(L, fy, page, text):
        return {"kind": "PRIMARY_QUOTE", "quote": text, "page": page, "locator": page, "paraphrase": ""}
    loc = None
    for pg in (page, None):
        cand = locate_passage(L, fy, text, need_re=need_re, prefer_page=page, min_overlap=0.4 if pg else 0.62, anchor_re=need_re)
        if cand and (cand["page"] == page or pg is None):
            loc = cand
            break
    if loc:
        return {"kind": "PRIMARY_QUOTE", "quote": loc["text"], "page": loc["page"], "locator": page, "paraphrase": text}
    return {"kind": "SOURCE_PARAPHRASE", "quote": "", "page": None, "locator": page, "paraphrase": text}


def severity_path(L: Ledger, m: dict) -> str:
    """The risk record's own year-by-year severity, shown only when it changed over at least three recorded years."""
    sv = (L.evo.get(m.get("evo")) or {}).get("severity_by_year") or {}
    pts = [(fy, v) for fy, v in sorted(sv.items()) if str(v) not in ("unknown", "not specified", "None")]
    if len(pts) >= 3 and len({v for _, v in pts}) > 1:
        return "Recorded severity by year: " + ", ".join(f"{FY(fy)} {v}" for fy, v in pts) + "."
    return ""


def pick_risks(L: Ledger) -> dict:
    cur = fyn(L.fy)
    cands, excluded, social, reinstated, nomech = [], [], [], [], []
    for r in L.risks:
        m = latest_mention(L, r)
        eligible = risk_eligible(r)
        text = (m["text"] or "") + " " + str(r.get("risk_name") or "")
        if eligible and (not m["text"] or SOCIAL_PROGRAMME.search(m["text"])):
            social.append(r)
            continue
        if m["page"] is None or not m["text"]:          # no filing passage behind it: a registry summary, not a disclosure to quote
            if not eligible:
                excluded.append(r)
            continue
        ch = classify(m["text"], L.bank)
        review = None
        if not eligible:
            review = review_demoted(L, r, m, ch)
            if not review or SOCIAL_PROGRAMME.search(m["text"]):
                excluded.append(r)
                continue
            reinstated.append(r)
        if ch is None and re.search(r"working[- ]capital|receivable|development cycles|upfront costs|gestation", text, re.I):
            ch = {"id": "working_capital"}
        if ch is None:          # the wording supports no economic channel: it is not shown with a filler mechanism (an opportunity or a scarcity is not a stated dependence)
            nomech.append({"risk": r.get("risk_name"), "fy": m["fy"], "page": m["page"], "wording": m["text"]})      # kept for observability: fail-closed must not be silent
            continue
        if L.bank and ch and ch["id"] == "working_capital":
            continue
        mat = {"high": 3, "medium": 2, "low": 1}.get(str((r.get("materiality") or {}).get("level")), 1)
        sev = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(m["severity"], 1)
        status = {"increasing": 2, "persistent": 1.5, "recurring": 1.5, "emerging": 1, "reducing": 0.5}.get(r.get("current_status"), 0.5)
        recent = fyn(m["fy"]) >= cur - 1
        score = mat + sev + status + (1.5 if ch else -1) + (2 if recent else -3) - (1.5 if ch and ch['id'] in ('talent', 'currency', 'inflation') else 0) + (1.5 if review else 0)
        cands.append({"r": r, "m": m, "ch": ch, "score": score, "recent": recent, "industry": bool(INDUSTRY_CONTEXT.search(m["text"])), "reviewed": review})
    cands.sort(key=lambda c: -c["score"])
    eligible = sorted([c for c in cands if not c["reviewed"]], key=lambda c: -c["score"])
    el_channels = {(c["ch"] or {}).get("id") for c in eligible if c["recent"]}
    picked, used = [], set()
    for c in sorted([c for c in cands if c["reviewed"] and c["recent"]], key=lambda c: -c["score"]):      # a restored record never displaces an eligible record on the same channel
        cid = (c["ch"] or {}).get("id")
        if cid and cid not in el_channels and cid not in used and len(picked) < 2:
            used.add(cid)
            picked.append(c)
    for c in eligible:
        if not c["recent"] or len(picked) >= 5:
            continue
        cid = c["ch"]["id"] if c["ch"] else f"x:{c['m']['text'][:30]}"
        if cid in used:
            continue
        used.add(cid)
        picked.append(c)
    picked.sort(key=lambda c: -c["score"])
    hist = [c for c in cands if not c["recent"] and (c["ch"] or {}).get("id") not in used][:5]
    return {"picked": picked, "historical": hist, "excluded": excluded, "social": social, "reinstated": reinstated, "nomech": nomech}


def wc_line(L: Ledger) -> tuple[str, list[str]]:
    """Average-receivable-day series from the investor working-capital module (average receivables / revenue x 365), each year labelled with its own year."""
    if L.bank or L.wc_applicability in (None, "not_economically_meaningful", "not_applicable"):
        return "", []
    rows = [(fy, r) for fy, r in sorted(L.wc.items()) if r.get("receivable_days") not in (None, 0.0) and fyn(fy) >= fyn(L.fy) - 4]
    if len(rows) < 2:
        return "", []
    ser = ", ".join(f"{FY(fy)} {r['receivable_days']:.1f}" for fy, r in rows)
    last_fy, last = rows[-1]
    if last_fy != L.fy:
        return "", []
    rev = L.registry(last_fy).get("revenue")
    rec = last.get("receivables")
    pg = L.row_page(last_fy, "balance_sheet", r"trade receivables")
    base = L.facts.get(f"revenue@{last_fy}")
    inv = [(fy, r["inventory_days"]) for fy, r in rows if r.get("inventory_days")]
    inv_txt = (" Average inventory days (average inventory ÷ cost of materials × 365): " + ", ".join(f"{FY(fy)} {v:.1f}" for fy, v in inv) + ".") if len(inv) >= 3 else ""
    line = (f"Average receivable days ({base.basis if base else 'as reported'}; average of opening and closing trade receivables ÷ revenue × 365): {ser}." + inv_txt
            + (f" {FY(last_fy)} closing trade receivables {m2(rec)}" + (f" (balance sheet p.{pg})" if pg else "") + (f" on revenue {m2(float(rev['value']))}" if rev else "") + "." if rec else "")
            + (f" No value is available for {FY(L.fy)} in the working-capital records." if last_fy != L.fy else "") + " Years without a computed value are omitted; the series is not a straight line, and receivable days do not show ageing or overdue balances.")
    return line, [f"{r['receivable_days']:.4f}" for _, r in rows]


def risks(L: Ledger) -> dict:
    sel = pick_risks(L)
    while True:
        for k in [k for k in L.facts if k.startswith("riskx:")]:
            del L.facts[k]
        a = risks_compose(L, sel)
        # inside the word budget by dropping the lowest-scored pick that was not put back by source-grounded review, never below three risks
        drop = [c for c in sel["picked"] if not c["reviewed"] and not c["industry"]]
        if m59.words(a) <= 598 or len(sel["picked"]) <= 3 or not drop:
            return a
        sel = {**sel, "picked": [c for c in sel["picked"] if c is not min(drop, key=lambda c: c["score"])]}


def risks_compose(L: Ledger, sel: dict) -> dict:
    n, g, fy = L.name, L.facts.get, L.fy.upper()
    ev, monitor, points, shown_sel = [], [], [], []
    for i, c in enumerate(sel["picked"], 1):
        m, ch = c["m"], c["ch"]
        if ch and ch["id"] == "concentration":
            kind = next((k for k in CONC_KINDS if re.search(k[1], m["text"], re.I)), CONC_KINDS[1])
            then, unk, mon, label = kind[2], "", ch["mon"], "Revenue concentration"
        elif ch and ch["id"] == "working_capital":
            line, _ = wc_line(L)
            then, unk, mon, label = (line or "Working capital is flagged in the filing; the receivable series is not available for this company."), "", "Receivable days against revenue growth, and any ageing or collection disclosure.", "Working-capital and cash-cycle pressure"
        elif ch:
            then, unk, mon, label = ch["then"], f"Not established here: {ch['unk']}." if ch["unk"] else "", ch["mon"], ch["label"]
        else:
            then, unk, mon, label = "The filing records this risk but its wording does not state an economic mechanism, so none is asserted here.", "", "Further disclosure on this item from management.", clean_clip(c["r"].get("risk_name") or "Risk", 50)
        sev = f", severity {m['severity']}" if m["severity"] else ""
        prefix = "Industry context, not company-specific evidence: " if c["industry"] else ""
        rv = c["reviewed"]
        if rv:
            at = {"kind": "PRIMARY_QUOTE", "quote": rv["text"], "page": rv["page"], "locator": m["page"], "paraphrase": m["text"], "reviewed": True}
        else:
            at = attribute(L, m["fy"], m["page"], m["text"], (ch or {}).get("re", ""))
        if at["kind"] == "PRIMARY_QUOTE" and not at["paraphrase"]:
            src = f"the filing states “{at['quote']}” (p.{at['page']})."
        elif at["kind"] == "PRIMARY_QUOTE":
            redundant = len(content_stems(at["paraphrase"]) & content_stems(at["quote"])) >= 0.75 * max(1, len(content_stems(at["paraphrase"])))
            src = f"source passage p.{at['page']}: “{at['quote']}”." + ("" if redundant else f" Risk record (paraphrase, p.{at['locator']}): {at['paraphrase']}.")
        else:
            src = f"risk record (paraphrase, p.{at['locator']}; no matching passage located): {at['paraphrase']}."
        em = earlier_named(L, c["r"], m) if not c["industry"] else None
        em_txt = ""
        if em:
            emv = verify_quote(L, em["fy"], em["page"], em["text"])
            em_txt = f" Earlier record ({FY(em['fy'])} p.{em['page']}) names a specific exposure" + (f": “{em['text']}”" if emv else f" (paraphrase): {em['text']}") + (f" ({next(k[0] for k in CONC_KINDS if re.search(k[1], em['text'], re.I))}-level concentration, which is not the same as customer concentration)." if re.search(r"concentration", em["text"], re.I) and not re.search(r"customer|buyer|client", em["text"], re.I) else ".")
        txt = f"{i}. {prefix}{label} ({FY(m['fy'])}{sev}{', restored after source review' if rv else ''}): {src} {'Computed from the statements: ' if (ch or {}).get('id') == 'working_capital' else 'Analyst inference (conditional): '}{then if (ch or {}).get('id') == 'working_capital' else lc_first(then)}".strip() + (f" Not established here: {ch['unk']}." if rv and ch and ch.get("unk") else "") + (" " + severity_path(L, m) if i == 1 and severity_path(L, m) else "") + em_txt
        ev.append(txt)
        points.append(f"{label} ({FY(m['fy'])}): {clean_clip(then, 150) if then else 'no mechanism stated'}.")
        monitor.append(mon)
        shown_sel.append({"channel": (ch or {}).get("id"), "fy": m["fy"], "locator_page": m["page"], "attribution": at["kind"], "passage_page": at.get("page"), "passage": at.get("quote", ""), "paraphrase": at.get("paraphrase", ""), "restored_after_review": bool(rv), "score": round(c["score"], 1)})
        L.add(Fact(f"riskx:{i}", label, (f"“{at['quote']}”" if at["kind"] == "PRIMARY_QUOTE" else f"paraphrase: {at['paraphrase']}"), None, "", m["fy"], "n/a", at.get("page") or m["page"], "Annual report page text" if at["kind"] == "PRIMARY_QUOTE" else "Risk record (paraphrase)", "RECORD", aliases=[label.lower(), m["text"].lower()[:40]]))
    if L.bank:
        car, gn, nn = g(_m(L, "capital_adequacy_ratio")), g(_m(L, "gross_npa_ratio")), g(_m(L, "net_npa_ratio"))
        gnp, nnp, carp, nimp, nim = g(_m(L, "gross_npa_ratio", True)), g(_m(L, "net_npa_ratio", True)), g(_m(L, "capital_adequacy_ratio", True)), g(_m(L, "net_interest_margin", True)), g(_m(L, "net_interest_margin"))

        def mv(a, b):
            if a and b and a.num is not None and b.num is not None:
                return f"{b.text} to {a.text} ({a.num - b.num:+.1f} pt)".replace("-", "−")
            return a.text if a else ""
        bits = [x for x in (f"capital adequacy {mv(car, carp)}" if car else "", f"gross NPA {mv(gn, gnp)}" if gn else "", f"net NPA {mv(nn, nnp)}" if nn else "", f"net interest margin {mv(nim, nimp)}{stat_note(L, 'net_interest_margin', nim)}" if nim and nimp else "") if x]
        if bits:
            ev.append(f"Company evidence against the sector risks, {fy} (bank-reported, prior year to current): {', '.join(bits)}. Sector-wide funding or credit stress would show first in these company figures; a capital ratio well above the minimum gives room to absorb credit losses but does not remove credit-cycle risk in a microfinance-heavy book.")
    else:
        debt, cash, ob = g(_m(L, "total_debt")), g(_m(L, "cash_and_equivalents")), g(_m(L, "other_bank_balances"))
        if debt is not None and cash:
            line = f"Balance sheet, {fy}: borrowings {'nil' if debt.num == 0 else debt.text}, cash and equivalents {m2(cash.num)}" + (f", other bank balances {m2(ob.num)}" if ob else "") + (f" ({debt.basis})" if debt.basis != 'unknown' else "")
            if debt.num == 0:
                line += ". The financial-borrowings line is explicitly nil; this does not cover lease liabilities or other liabilities, and it does not release cash tied up in receivables"
            ev.append(line + ".")
        elif cash:
            ev.append(f"Liquidity, {fy}: cash and equivalents {m2(cash.num)}" + (f" and other bank balances {m2(ob.num)}" if ob else "") + "; total borrowings are not established in the records, so net cash is not stated.")
        wl, _ = wc_line(L)
        cfo, pat = g(_m(L, "cfo")), g(_m(L, "pat"))
        if wl and not any(c["ch"] and c["ch"]["id"] == "working_capital" for c in sel["picked"]):
            ev.append(wl)
        if cfo and pat and pat.num and not wl:
            ev.append(f"Cash conversion, {fy}: operating cash flow {m2(cfo.num)} against profit after tax {m2(pat.num)} ({cfo.num / pat.num * 100:.0f}% of profit).")
    cl, nw = g(f"contingent_liabilities@{L.fy}"), g(_m(L, "net_worth"))
    if cl and nw and nw.num:
        ev.append(f"Contingent liabilities (claims not acknowledged as debt), {fy}: {cl.text}, about {cl.num / nw.num * 100:.1f}% of net worth {nw.text} ({cl.basis}).")
    tx = g("pending_transaction")
    if tx:
        ev.append(f"Transaction exposure: {tx.text}. Until completion the price, funding and integration outcome are not part of reported results.")
    if sel["historical"]:
        seen_l, hist = set(), []
        for c in sel["historical"]:
            lab = (c["ch"] or {}).get("label") or clean_clip(c["r"].get("risk_name"), 40)
            if lab not in seen_l:
                seen_l.add(lab)
                hist.append(f"{lab} (last {FY(c['m']['fy'])})")
        ev.append("Recorded earlier, not reconfirmed since (a missing later mention does not show the risk ended): " + "; ".join(hist[:3]) + ".")
    names = [(c["ch"] or {}).get("label") or clean_clip(c["r"].get("risk_name"), 40) for c in sel["picked"] if not c["industry"]]
    ind_names = [(c["ch"] or {}).get("label") for c in sel["picked"] if c["industry"]]
    cushion = "The bank-reported capital and asset-quality ratios are the offset." if L.bank else ("An explicitly nil financial-borrowings line is a real offset." if (g(_m(L, "total_debt")) is not None and g(_m(L, "total_debt")).num == 0) else "")
    simple = (f"The exposures {n}'s filings put most weight on, with the economic channel each one supports, are " + "; ".join(x.lower() if not x[:2].isupper() else x for x in names) + ("; and a signed transaction that has not completed" if tx else "") + ". " + (f"Industry context, not company-specific evidence: {'; '.join(x.lower() for x in ind_names)}. " if ind_names else "") + cushion).strip()
    econ = "Each exposure matters through revenue, cost or cash outflow outside the plan, or less balance-sheet room. Passages are exact filing text; 'Risk record' lines are paraphrases; 'Analyst inference' lines are conditional readings, not filing claims."
    unproven = ("For each risk above, the realised impact and the revenue or cost exposed are not quantified in the records read here. " + " ".join(x for x in gaps_text(L, "RISK", ("r_registry", "r_balance", "r_cash")) if x)).strip()
    if sel["excluded"] or sel["social"]:
        k = len(sel["excluded"]) + len(sel["social"])
        unproven += f" {k} other recorded item{'s are' if k != 1 else ' is'} still withheld by the relevance filter after source review."
    dpfs = [(f"riskx:{i}", "Risk shown, with its own filing year and page") for i in range(1, len(sel["picked"]) + 1)] + [(_m(L, "total_debt"), "Borrowings"), (_m(L, "cash_and_equivalents"), "Liquidity"), (_m(L, "capital_adequacy_ratio"), "Capital buffer"), (_m(L, "gross_npa_ratio"), "Asset quality"),
            (f"contingent_liabilities@{L.fy}", "Claims not acknowledged as debt"), ("pending_transaction", "Pending transaction")]
    def build(evl: list[str]) -> dict:
        return finish(L, "RISK", "what-could-go-wrong", simple, evl, econ, unproven, monitor + (["Completion of the announced transaction."] if tx else []), dpfs, ("r_transaction",) if tx else ())
    a = build(ev)
    for step in ("sev", "earlier", "Recorded earlier", "Cash conversion", "Liquidity", "Balance sheet"):      # least important content goes first if the answer would exceed the word budget
        if m59.words(a) > 598:
            if step == "sev":
                ev = [re.sub(r" Recorded severity by year:[^.]*\.", "", e) for e in ev]
            elif step == "earlier":
                ev = [re.sub(r" Earlier record \(.*$", "", e) if len(ev) > 5 and not re.search(r"Cassiopea|exclusive", e) else e for e in ev]
            else:
                ev = [e for e in ev if not e.startswith(step)]
            a = build(ev)
    a["key_points"] = [m59.tidy(p) for p in points[:3]]
    a["g41_risk_selection"] = {"shown": shown_sel, "withheld_by_filter": [r["risk_name"] for r in sel["excluded"]], "social_programme": [r["risk_name"] for r in sel["social"]], "restored_after_review": [r["risk_name"] for r in sel.get("reinstated", [])], "withheld_no_mechanism": sel.get("nomech", [])}
    return a


# ───────────────────────────── Discoveries ─────────────────────────────
def first_sentence(t: str, limit: int = 220) -> str:
    t = " ".join(str(t).split())
    m = re.match(r"(.+?[.;])(?:\s|$)", t)
    return clean_clip(m.group(1) if m else t, limit).rstrip(".;") + "."


def stat_note(L: Ledger, metric: str, cur: Fact | None) -> str:
    st = getattr(L, "stat", {}).get(metric)
    if not st or not cur or cur.num is None or abs(st["cur"] - cur.num) <= 0.06:
        return ""
    return f" (statutory business-ratio note p.{st['page']}: {st['prev']:.2f}% to {st['cur']:.2f}%; the two definitions are not reconciled)"


def m2d(n: float) -> str:
    """Always two decimals: the form the audited statement prints (₹ crore)."""
    return f"₹{abs(n):,.2f} crore" if n >= 0 else f"−₹{abs(n):,.2f} crore"


def m2s(n: float) -> str:
    """Signed statement-precision amount without the unit word (used inside lists that state the unit once)."""
    body = f"{abs(n):,.2f}" if abs(n) < 1000 else f"{abs(n):,.0f}"
    return f"−₹{body}" if n < 0 else f"₹{body}"


DRIVER_LABEL = {"receivables": "trade receivables", "other_liabilities": "other liabilities", "taxes": "income taxes paid", "payables": "trade payables", "inventories": "inventories"}


def discovery(L: Ledger) -> dict:
    n, g, fy = L.name, L.facts.get, L.fy.upper()
    cfo, pat, fcf, cx = g(_m(L, "cfo")), g(_m(L, "pat")), g(_m(L, "fcf")), g(_m(L, "capex"))
    rev = g(_m(L, "revenue"))
    ev: list[str] = []
    mon: list[str] = []
    if L.bank:
        nim, gn, car, pat_p = g(_m(L, "net_interest_margin")), g(_m(L, "gross_npa_ratio")), g(_m(L, "capital_adequacy_ratio")), g(_m(L, "pat", True))
        nimp, gnp, nn, nnp, carp, roe, roep = g(_m(L, "net_interest_margin", True)), g(_m(L, "gross_npa_ratio", True)), g(_m(L, "net_npa_ratio")), g(_m(L, "net_npa_ratio", True)), g(_m(L, "capital_adequacy_ratio", True)), g(_m(L, "roe")), g(_m(L, "roe", True))
        nii, niip, dep, depp = g(_m(L, "net_interest_income")), g(_m(L, "net_interest_income", True)), g(_m(L, "total_deposits")), g(_m(L, "total_deposits", True))
        if pat and pat_p and pat.num and pat_p.num:
            same = pat.basis == pat_p.basis != "unknown"
            ch = (pat.num / pat_p.num - 1) * 100
            if L.comparative.get("pat"):
                ev.append(f"Net profit was {m2d(pat.num)} in {fy} against {m2d(pat_p.num)} in the prior year ({ch:+.1f}%, both years in the same audited statement, p.{L.comparative['pat']}).".replace("(-", "(−") + " The records do not apportion the change between margin, credit cost and growth.")
            else:
                ev.append(f"Profit after tax was {pat.text} in {fy} against {pat_p.text} a year earlier ({ch:+.0f}%".replace("-", "−") + ("" if same else "; the two years are labelled on different or unstated bases, so the change is indicative") + "). The records do not apportion the change between margin, credit cost and growth.")

        def pair(a, b):
            if a and b and a.num is not None and b.num is not None:
                return f"{b.text} to {a.text} ({a.num - b.num:+.1f} pt)".replace("-", "−")
            return a.text if a else ""
        parts = [x for x in (f"net interest margin {pair(nim, nimp)}{stat_note(L, 'net_interest_margin', nim)}" if nim else "", f"gross NPA {pair(gn, gnp)}" if gn else "", f"net NPA {pair(nn, nnp)}" if nn else "", f"capital adequacy {pair(car, carp)}" if car else "", f"return on equity {pair(roe, roep)}" if roe else "") if x]
        if parts:
            ev.append("Margin, credit quality and capital, prior year to current: " + "; ".join(parts) + ".")
        grow = []
        if nii and niip and nii.basis == niip.basis != "unknown" and niip.num:
            grow.append(f"net interest income {(nii.num / niip.num - 1) * 100:+.0f}% to {nii.text}")
        if dep and depp and dep.basis == depp.basis != "unknown" and depp.num:
            grow.append(f"deposits {(dep.num / depp.num - 1) * 100:+.0f}% to {dep.text}")
        if grow:
            ev.append("Franchise growth on the same basis: " + "; ".join(grow).replace("-", "−") + ".")
        if nim and gn and car:
            ev.append("A wide margin is partly compensation for lending to a high-risk segment, so margin alone does not show attractive risk-adjusted economics; what matters is whether margin minus credit cost stays adequate on a capital base that remains well above the minimum.")
        if cfo:
            ev.append(f"Operating cash flow of {m2(cfo.num)} moves with deposits and loans for a lender, so it is not read as earnings quality; industrial cash-conversion and free-cash-flow ratios are not applied.")
        simple = (f"{n}'s profit " + (f"fell from {m2d(pat_p.num)} to {m2d(pat.num)}" if pat and pat_p and pat.num < pat_p.num else f"moved from {m2d(pat_p.num)} to {m2d(pat.num)}" if pat and pat_p else "is the starting point") + "; the useful question is whether margin, credit quality and capital together support that earnings level, not how profit converts to free cash flow.")
        econ = "For a lender, profit is margin earned on loans less what bad loans cost, on a capital base that must stay adequate. If gross NPA is falling and capital is stable while margin narrows, earnings are being repaired by credit quality; if margin is wide but NPA is rising, earnings are being paid for by risk."
        unproven = note_absence(L, "credit cost", (r"provisions? (?:and|&) contingenc", r"credit cost", r"provisions? for (?:non[- ]performing|bad|doubtful)"), "Credit cost (provisions as a share of loans)", "credit_cost") + ". The split of the profit change between margin, credit cost and growth is therefore not established here."
        mon = ["Investigate next: credit cost and provisions in the latest filing, to separate the margin effect from the credit-loss effect on profit.", "Investigate next: whether deposit and wholesale funding cost is rising faster than loan yields."]
        dpfs = [(_m(L, "pat"), "Profit"), (_m(L, "net_interest_margin"), "Net interest margin"), (_m(L, "gross_npa_ratio"), "Gross NPA ratio"), (_m(L, "capital_adequacy_ratio"), "Capital adequacy"), (_m(L, "roe"), "Return on equity")]
        a = finish(L, "DISCOVERY", "are-profits-converting-into-cash", simple, ev, econ, unproven, mon, dpfs)
        a["key_points"] = [m59.tidy(first_sentence(e)) for e in ev[:3]]
        return a
    # ── industrial / services ──
    cp, pp, fp, cxp = g(_m(L, "cfo", True)), g(_m(L, "pat", True)), g(_m(L, "fcf", True)), g(_m(L, "capex", True))
    div, bb = g(_m(L, "dividends_paid")), g(_m(L, "buyback_paid"))
    divn = div.num if div else 0.0
    bbn = bb.num if bb and (bb.num or 0) > 50 else 0.0
    ret = divn + bbn
    cf = {k: g(f"cfd:{k}@{L.fy}") for k in ("receivables", "inventories", "payables", "other_liabilities", "taxes", "deposits")}
    cfp = {k: g(f"cfd:{k}@{L.prev()}") for k in ("receivables", "inventories", "payables", "other_liabilities", "taxes")}
    if cfo and pat and pat.num:
        ratio = cfo.num / pat.num * 100
        line = f"Operating cash flow was {m2(cfo.num)} against profit after tax {m2(pat.num)} in {fy} ({ratio:.0f}% of profit)"
        if cp and pp and pp.num and cp.basis == cfo.basis != "unknown":
            line += f"; a year earlier {m2(cp.num)} against {m2(pp.num)} ({cp.num / pp.num * 100:.0f}%)".replace("(-", "(−")
        ev.append(line + ".")
    dcfo = (cfo.num - cp.num) if (cfo and cp and cfo.basis == cp.basis != "unknown") else None
    if fcf and cx is not None:
        line = f"After capital expenditure of {m2(cx.num)} (property, plant and intangibles), free cash flow was {m2(fcf.num)}"
        if fp:
            line += f" against {m2(fp.num)} a year earlier"
        if fp and cfo and cp and cx and cxp and len({fcf.basis, fp.basis, cfo.basis, cp.basis}) == 1 and fcf.basis != "unknown":
            line += f": a change of {m2(fcf.num - fp.num)}, of which operating cash flow {m2(cfo.num - cp.num)} and the change in capital expenditure {m2(-(cx.num - cxp.num))} (effects on free cash flow)"
        ev.append(line + ".")
    # operating-cash-flow lines, prior year to current (cash effect), largest year-on-year movers first
    movers = []
    for k, label in DRIVER_LABEL.items():
        c_, p_ = cf.get(k), cfp.get(k)
        if c_ and abs(c_.num) >= max(1.0, 0.05 * abs(cfo.num if cfo else 0)) or (c_ and p_ and abs(c_.num - p_.num) >= max(1.0, 0.05 * abs(cfo.num if cfo else 0))):
            movers.append((abs((c_.num - p_.num) if p_ else c_.num), k, label, c_, p_))
    movers.sort(key=lambda x: -x[0])
    if movers:
        pg = next((m[3].page for m in movers if m[3].page), None)
        if all(m[4] for m in movers[:5]):
            ev.append(f"Operating cash flow lines, cash effect {L.prev().upper()} → {fy} (₹ crore, {fy}" + (f" p.{pg}" if pg else "") + "): " + "; ".join(f"{m[2]} {m2s(m[4].num)} → {m2s(m[3].num)}" for m in movers[:5]) + ".")
        else:
            ev.append(f"Operating cash flow lines in {fy}" + (f" (p.{pg})" if pg else "") + ": " + "; ".join(f"{m[2]} {'absorbed' if m[3].num < 0 else 'released'} {m2(abs(m[3].num))}" for m in movers[:4]) + ".")
        top = movers[0]
        if dcfo and top[4] and abs(top[0]) >= 0.6 * abs(dcfo) and (top[3].num - top[4].num) * dcfo > 0:
            ev.append(f"The largest single movement, {top[2]} ({m2(top[3].num - top[4].num)}), is about {abs(top[0] / dcfo) * 100:.0f}% of the {m2(dcfo)} change in operating cash flow.")
    funding = []
    cash, ob = g(_m(L, "cash_and_equivalents")), g(_m(L, "other_bank_balances"))
    if cash:
        funding.append(f"cash and equivalents {m2(cash.num)}" + (f" and other bank balances {m2(ob.num)}" if ob else "") + " at year end")
    if cf.get("deposits") and cf["deposits"].num > 0:
        funding.append(f"net release of bank deposits {m2(cf['deposits'].num)} in the year")
    gap = ret - (fcf.num if fcf else 0)
    if fcf and ret:
        head = f"Shareholder cash returned in {fy} was {m2(ret)}" + (f" (dividends {m2(divn)}" + (f", buyback cash {m2(bbn)})" if bbn else ")") if bbn else "") + f" against free cash flow of {m2(fcf.num)}"
        if gap > 0 and fcf.num > 0:
            head += f": a gap of {m2(gap)} ({ret / fcf.num * 100:.0f}% of free cash flow)"
        elif fcf.num <= 0:
            head += ": free cash flow did not cover the payout"
        else:
            head += f", about {ret / fcf.num * 100:.0f}% of it"
        if gap > 0 and funding:
            head += f". The statements show these possible sources of the difference: {'; '.join(funding)}"
        ev.append(head + ". A payout above one year's free cash flow does not by itself show the distribution is unsustainable.")
    cfo_s, pat_s = series(L, "cfo"), series(L, "pat")
    pm = dict((fy_, v) for fy_, v, _ in pat_s)
    conv = [(fy_, v / pm[fy_] * 100) for fy_, v, _ in cfo_s if pm.get(fy_) and pm[fy_] > 0 and v is not None]
    if len(conv) >= 4:
        lo, hi = min(conv, key=lambda x: x[1]), max(conv, key=lambda x: x[1])
        ev.append(f"Over {FY(conv[0][0])}–{FY(conv[-1][0])} operating cash flow ranged from {lo[1]:.0f}% of profit ({FY(lo[0])}) to {hi[1]:.0f}% ({FY(hi[0])}), so {FY(L.fy)} at {conv[-1][1]:.0f}% is ".replace("from -", "from −") + ("inside" if lo[1] <= conv[-1][1] <= hi[1] else "outside") + " that range.")
    wl, _ = wc_line(L)
    if wl:
        ev.append(wl)
    if cx and rev and rev.num:
        gr = growth(L, "revenue")
        ev.append(f"Capital expenditure was {cx.num / rev.num * 100:.1f}% of revenue" + (f" in a year when revenue grew {gr:.1f}%" if gr is not None else "") + ". " + note_absence(L, "capex split", CAPEX_SPLIT_PATTERNS, "Maintenance versus growth capex", "capex_split") + "; how much of the spending adds capacity is therefore not shown.")
    fcf_move = (fcf.num - fp.num) if (fcf and fp and fcf.basis == fp.basis != "unknown") else None
    if fcf and ret and gap > 0 and fcf.num > 0:
        simple = f"{n} returned {m2(ret)} to shareholders in {fy} against free cash flow of {m2(fcf.num)}, a {m2(gap)} gap; the open question is what funded it and whether cash generation is recovering."
    elif fcf_move is not None and fp and abs(fcf_move) >= 0.1 * abs(fp.num):
        why = f" (operating cash flow {m2(dcfo)}" + (f", capital expenditure {m2(-(cx.num - cxp.num))}" if cx and cxp else "") + ")" if dcfo is not None else ""
        simple = f"{n}'s free cash flow {'fell' if fcf_move < 0 else 'rose'} {m2(abs(fcf_move))} to {m2(fcf.num)} in {fy}{why}" + (f", while shareholder payouts took {ret / fcf.num * 100:.0f}% of it" if ret and fcf.num > 0 else "") + "; the open question is whether that is timing or a new level."
    elif dcfo is not None and cp and abs(dcfo) >= 0.1 * abs(cp.num):
        simple = (f"{n}'s operating cash flow {'fell' if dcfo < 0 else 'rose'} {m2(abs(dcfo))} to {m2(cfo.num)} in {fy}" + (f" while profit {('was flat' if pp and pat and abs(pat.num / pp.num - 1) < 0.02 else 'moved ' + format((pat.num / pp.num - 1) * 100, '+.1f') + '%')}" if pat and pp and pp.num else "")
                  + (f"; after capital expenditure of {m2(cx.num)} including intangibles, free cash flow was {m2(fcf.num)}" if fcf and cx else "") + (f", and shareholder payouts took {ret / fcf.num * 100:.0f}% of it" if ret and fcf and fcf.num > 0 else "") + "; the open question is whether that is timing or a new level.")
    elif cfo and pat and pat.num:
        simple = f"{n} turned {cfo.num / pat.num * 100:.0f}% of {fy} profit into operating cash flow" + (f" ({m2(fcf.num)} of free cash flow after capital spending)" if fcf else "") + "; the open question is what lay behind the difference between profit and cash."
    else:
        simple = f"For {n}, the link between profit and cash is the starting point."
    rec = cf.get("receivables")
    meaning = []
    if rec and rec.num < 0 and pat and pat.num and abs(rec.num) >= 0.2 * pat.num:
        meaning.append("Receivables absorbing this much cash means revenue is being billed faster than it is collected; if that reflects " + ("milestone or acceptance timing it can reverse as projects are billed and paid" if any(str(e.get("billing_basis")) == "milestone" for e in (model(L).get("revenue_engines") or [])) else "billing timing it can reverse as invoices are paid") + ", and if it reflects slower collection it is a lasting drag on cash")
    top_k = movers[0][1] if movers else ""
    if top_k == "taxes" and movers and movers[0][4] and movers[0][3].num < movers[0][4].num:
        meaning.append("A higher tax payment lowers operating cash flow without changing profit before tax; whether it is a timing catch-up, a settlement or a new run-rate is not shown")
    if dcfo is not None and dcfo < 0 and pat and pp and pat.num >= pp.num:
        meaning.append("Operating cash flow fell while profit held up, so earnings were backed by less cash than a year earlier")
    econ = ". ".join(meaning) + "." if meaning else "The relationship between profit, cash and payouts is measured from the statements; its economic meaning depends on working-capital and tax timing the records do not explain."
    unproven = " ".join(x for x in (
        "What drove each movement (billing timing, collection speed, tax settlements, advances) is not stated in the records.",
        "Which source funded the shareholder payout is not shown." if ret else "",
        "Free cash flow here is operating cash flow less capex; it is not owner earnings.",
        "None of these relationships establishes cause.") if x)
    milestone = any(str(e.get("billing_basis")) == "milestone" for e in (model(L).get("revenue_engines") or []))
    if rec and rec.num < 0 and (not movers or any(m_[1] == "receivables" for m_ in movers[:3])):
        mon.append("Investigate next: ageing and collection terms for receivables" + (", and whether the build reverses once milestones are accepted and billed." if milestone else "."))
    if top_k == "taxes":
        mon.append("Investigate next: the tax note, to see whether the higher payment is a one-off settlement or a higher run-rate.")
    if ret and gap > 0:
        mon.append("Investigate next: how the payout was funded and how the payout policy relates to profit or to cash.")
    if dcfo is not None and dcfo < 0 and len(mon) < 3:
        mon.append("Investigate next: which operating lines reverse in the next filing and whether the fall in operating cash flow is timing or lasting.")
    mon.append("Investigate next: what capacity or revenue the capital spending is meant to add, as the company discloses it.")
    dpfs = [(_m(L, "cfo"), "Operating cash flow"), (_m(L, "pat"), "Profit after tax"), (_m(L, "fcf"), "Free cash flow"), (_m(L, "capex"), "Capital expenditure"), (_m(L, "dividends_paid"), "Dividends paid")] + [(f"cfd:{k}@{L.fy}", "Cash-flow statement line") for k in cf if cf[k]]
    a = finish(L, "DISCOVERY", "are-profits-converting-into-cash", simple, ev, econ, unproven, mon[:4], dpfs)
    a["key_points"] = [m59.tidy(simple)] + [m59.tidy(first_sentence(e)) for e in ev[2:4]]
    return a



COMPOSERS = {"BUSINESS": business, "MANAGEMENT": management, "RISK": risks, "DISCOVERY": discovery}


# ───────────────────────────── validation on candidate evidence ─────────────────────────────
class CoG4(m59.Co):
    """M59's company context, pointed at a candidate root. Its numeric pool is the CANDIDATE evidence only (never the served approved answers, which carry the
    figures G1-G3 corrected), so a stale figure cannot validate a candidate."""

    def __init__(self, key: str, registry: dict, root: Path) -> None:
        super().__init__(key, registry)
        self.dir = Path(root) / "companies" / key / "company_memory"
        self.root = Path(root)

    @property
    def numbers(self) -> list[float]:
        if "g4numbers" not in self._cache:
            nums: set[float] = set()

            def walk(o: Any) -> None:
                if isinstance(o, bool):
                    return
                if isinstance(o, (int, float)):
                    nums.add(float(o))
                elif isinstance(o, str):
                    for mm in re.finditer(r"-?\d[\d,]*\.?\d*", o):
                        try:
                            nums.add(float(mm.group().replace(",", "")))
                        except ValueError:
                            pass
                elif isinstance(o, dict):
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)

            for sub in ["financials", "capital_allocation_outcomes", "economic_attribution", "management_progression", "management_commitments", "company_model", "risks", "gold"]:
                for f in (self.dir / sub).rglob("*.json"):
                    try:
                        walk(json.loads(f.read_text()))
                    except Exception:
                        pass
            for fy in sorted(p.name for p in (self.root / "companies" / self.key).glob("fy??")):
                for name in ("financial_fact_registry.json", "financial_headline_metrics.json", "financial_transaction_disclosures.json"):
                    p = self.root / "companies" / self.key / fy / "financials" / name
                    if p.exists():
                        walk(json.loads(p.read_text()))
            nums |= {float(x) for x in getattr(self, "extra", [])}
            self._cache["g4numbers"] = sorted(nums)
        return self._cache["g4numbers"]


def derivable(n: float, vals: list[float]) -> str | None:
    """Explain a figure that is not itself in the records as arithmetic on two recorded figures (share, ratio, change, difference, sum). None if it cannot be derived."""
    def close(x: float) -> bool:
        return abs(x - n) <= max(abs(n) * 0.006, 0.06)
    vs = [v for v in vals if v]
    for a in vs:
        for b in vs:
            if a == b:
                continue
            if close(a / b * 100) or close(a / b) or close((a / b - 1) * 100) or close(abs(a - b)) or close(a + b):
                return f"{a:g} vs {b:g}"
    for a in vs:
        for b in vs:
            for c in vs:
                if c and close((a + b) / c * 100):
                    return f"({a:g}+{b:g})/{c:g}"
    return None


def audit_numbers(L: Ledger, a: dict, co: CoG4) -> dict:
    text = answer_text(a)
    vals = sorted({abs(f.num) for f in L.facts.values() if f.num is not None})
    pool_bad = m59.unsupported_numbers(text, co, set())
    derived, bad = {}, []
    for tok in pool_bad:
        n = float(tok.replace(",", ""))
        d = derivable(n, vals)
        if d:
            derived[tok] = d
        else:
            bad.append(tok)
    return {"unsupported": bad, "derived": derived}


def validate_candidate(L: Ledger, area: str, a: dict, co: CoG4) -> dict:
    qid = QUESTION_FOR_AREA[area]
    nb = audit_numbers(L, a, co)
    allow = {float(t.replace(",", "")) for t in nb["derived"]}
    # Verbatim filing quotes are attributed and bracketed by quotation marks: the causal-wording, rating-wording and cut-off guards apply to Prometheus's own
    # sentences, so quotes are masked for them (the numbers inside quotes are audited separately above, against the quote text itself).
    mask = lambda t: re.sub(r"“[^”]*”", "“[filing text]”", t) if isinstance(t, str) else t
    ma = dict(a)
    for f in ("simple_answer", "what_may_mean_economically", "what_is_not_yet_proven"):
        ma[f] = mask(a.get(f))
    for f in ("what_evidence_shows", "what_to_monitor", "key_points"):
        ma[f] = [mask(x) for x in a.get(f, [])]
    v = m59.validate(ma, co, qid, allow)
    if m59.words(a) > 600 and "word_budget" not in v["failed"]:
        v["failed"].append("word_budget")
    return {"validation": v, "numbers": nb}


def run(root: Path, out: Path) -> dict:
    registry = json.loads((REPO / "governance" / "approval_registry.json").read_text())["approvals"]
    out.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"root": str(root), "answers": []}
    for key in m59.COMPANIES:
        L = Ledger(key, root)
        co = CoG4(key, registry, root)
        served = m59.Co(key, registry)            # the approved answers as they are served today (read-only)
        for area in AREAS:
            qid = QUESTION_FOR_AREA[area]
            L.__dict__["_absence_notes"] = []
            new = COMPOSERS[area](L)
            co.extra = list(getattr(L, "quote_numbers", [])) + list(getattr(L, "extra_numbers", [])) + [abs(f.num) for f in L.facts.values() if f.num is not None]
            co._cache.pop("g4numbers", None)
            old = served.approved(qid)
            vc = validate_candidate(L, area, new, co)
            row = {
                "company": key, "area": area, "question_id": qid, "fy": L.fy,
                "new": {"score": score_answer(L, area, new), "words": m59.words(new), "failed": vc["validation"]["failed"], "numbers": vc["numbers"], "pacp": vc["validation"]["pacp"].get("overall")},
                "old": {"score": score_answer(L, area, old) if old else None, "words": m59.words(old) if old else None},
                "coverage": ledger_coverage(L, area),
            }
            if old:
                ov = m59.validate(old, co, qid, set())
                row["old"]["failed"] = ov["failed"]
                row["old"]["numbers"] = audit_numbers(L, old, co)
            result["answers"].append(row)
            (out / f"{key}__{qid}.candidate.json").write_text(json.dumps({"question_id": qid, "company": key, "answer": new}, indent=1, ensure_ascii=False))
    (out / "g4_results.json").write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--as-of", default=AS_OF.isoformat(), help="assessment date used to judge deadlines (default 2026-10-13)")
    args = ap.parse_args()
    AS_OF = _dt.date.fromisoformat(args.as_of)
    reg_before = (REPO / "governance" / "approval_registry.json").read_bytes()
    res = run(Path(args.root), Path(args.out))
    assert (REPO / "governance" / "approval_registry.json").read_bytes() == reg_before
    for r in res["answers"]:
        n, o = r["new"], r["old"]
        print(f"{r['company']:13} {r['area']:10} new: carried {n['score']['carried_pct']:>5}% omitted={n['score']['omitted']} absence-on-gaps={n['score']['absence_claims_on_gaps']} failed={n['failed']} badnum={n['numbers']['unsupported']} | old: carried {o['score']['carried_pct'] if o['score'] else '—'}% omitted={o['score']['omitted'] if o['score'] else '—'} absence-on-gaps={o['score']['absence_claims_on_gaps'] if o['score'] else '—'}")
