"""Semantic verification of a financial fact against the original filing (annual-report PDF under data/Processed/<company>/<fy>/annual_report/).

A fact is VERIFIED only when ALL of these hold; failing any one leaves it PROVISIONAL (a lead to follow up, never a certificate) or REJECTED:
  1. METRIC MEANING   the fact's source line passes the registry's metric-meaning contracts (knowledge/financials/semantic_contracts.py): a total is not a residual, a component is
                      not a total, authorised is not paid-up, an accumulated balance is not an annual charge, a sentence is not a line.
  2. SOURCE IDENTITY  the PDF is chosen by what it states (its own fiscal year), its SHA-256 is recorded, and the page text is read from that file.
  3. STATEMENT / ROW  the cited page (or, failing that, another page) is the statement the metric belongs to, and the row's label words appear in order on it.
  4. YEAR / COLUMN    the amount is read from the current-year column, or from the comparative column of the NEXT year's report when the year has no report of its own.
  0. RECORD IDENTITY  before any page is read, the RECORD must itself be the fact it claims: its fiscal year is the one being verified, its period is that year's annual period (not a
                      quarter, half-year or other year), its period role fits the metric (flow / closing balance), its unit is the canonical one (INR crore, or INR per share), and it
                      asserts a basis. The filing can only confirm a number; it cannot repair a record that names the wrong year, unit, duration or basis.
  1b. ROW CONTRACT   the source label must be a recognised source row of THIS metric (the mapper's positive vocabulary), not merely pass negative exclusions: a revenue row cannot
                      certify PAT, an employee-cost row cannot certify depreciation, "Other income" cannot certify operating revenue.
  5. BASIS            consolidated / standalone is read from the statement's own heading; a heading that names neither takes the report's entity basis (counted from the report's own
                      "standalone / consolidated financial statements" wording) and a report that cannot settle it leaves the fact PROVISIONAL.
  6. UNIT AND SCALE   the unit is the one the page declares nearest above the row (crore, million, lakh, thousand); no other scale is tried.
  7. SIGN AND PRECISION  printed brackets / minus decide the sign (metrics whose registry convention is "outflow" may be compared on magnitude, by name, not by default); the
                      comparison tolerance is half a unit in the last printed decimal, not a percentage.
  8. DERIVED FACTS    are re-derived by THIS module's own definition of the metric from the CANONICAL registry facts it names (resolved here by metric and fiscal year, never from
                      numbers supplied with the fact); the stored value must equal the recomputation, and the fact is DERIVED_VERIFIED only if every input is itself VERIFIED. A derived fact
                      never has more authority than its weakest input; a derivation this module does not define stays DERIVED_UNVERIFIED.

Usage (library): verify_fact(fact_dict, company=..., fy=..., registry_facts=[...]) -> Verdict dict.
CLI census:      python3 tools/verify_vs_filing.py census <candidate_companies_root> <out.json> [--companies a,b]    (every usable fact, changed or not)
CLI stamp:       python3 tools/verify_vs_filing.py stamp <candidate_companies_root>    (per-year verification file + verification_status on truth-pack metrics)
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from knowledge.financials.semantic_contracts import semantic_problems          # noqa: E402
from knowledge.financials.line_item_mapper import map_line_item              # noqa: E402
from knowledge.financials.fact_registry_schema import FinancialFact           # noqa: E402

DATA = ROOT / "data" / "Processed"
_NUMBER = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")

STATEMENT_OF_METRIC = {
    **{m: "profit_and_loss" for m in ("revenue", "pat", "pbt", "tax", "other_income", "finance_cost", "employee_cost", "depreciation", "other_expenses", "cost_of_materials", "total_income",
                                      "eps_basic", "eps_diluted", "ebit", "ebitda")},
    **{m: "balance_sheet" for m in ("short_term_debt", "long_term_debt", "total_debt", "payables", "receivables", "inventories", "inventory", "investments", "reserves", "equity_share_capital",
                                    "fixed_assets", "cwip", "total_assets", "total_liabilities", "other_bank_balances", "other_assets", "net_worth")},
    **{m: "cash_flow" for m in ("cfo", "cfi", "cff", "capex", "tax_paid", "dividends_paid", "buyback_paid", "dividends_received", "dividends_paid_to_non_controlling_interests", "interest_paid",
                                "capex_ppe_cwip_cash_outflow", "capex_intangible_cash_outflow", "capex_ppe_and_intangible_cash_outflow")},
    "cash_and_equivalents": "balance_sheet_or_cash_flow",
}
# metrics the registry stores as signed outflows: the filing prints them in brackets under "payments", so magnitude is compared by name
PER_SHARE_NOTE_PAGE = {"eps_basic": re.compile(r"earnings\s+per\s+(?:equity\s+)?share", re.I), "eps_diluted": re.compile(r"earnings\s+per\s+(?:equity\s+)?share", re.I)}
PER_SHARE = {"eps_basic", "eps_diluted", "face_value", "book_value_per_share"}      # rupees per share: no crore / million scale applies
OUTFLOW_CONVENTION = {"capex", "tax_paid", "dividends_paid", "buyback_paid", "dividends_paid_to_non_controlling_interests", "interest_paid", "capex_ppe_cwip_cash_outflow", "capex_intangible_cash_outflow",
                      "capex_ppe_and_intangible_cash_outflow"}
# Profit-and-loss figures that the indirect cash-flow statement restates on its first lines ("Net profit after taxation", "Tax adjustment", "Depreciation"): the same reported number, so
# the reconciliation page is an accepted statement for them - by this explicit list, and recorded as such in the evidence.
CASH_FLOW_RESTATED = {"pat", "pbt", "tax", "depreciation"}
_TITLE = {
    "balance_sheet": re.compile(r"balance\s+sheet|statement\s+of\s+financial\s+position|schedule\s*\d+", re.I),
    "cash_flow": re.compile(r"cash\s+flows?", re.I),
    "profit_and_loss": re.compile(r"profit\s+and\s+loss|statement\s+of\s+profit|income\s+statement|schedule\s*1[3-6]", re.I),
}
_CCY = r"(?:[`₹]\s*|inr\s+|rs\.?\s*)?"
_UNIT_DECLARATION = [
    (re.compile(rf"\bin\s+{_CCY}millions?\b", re.I), 0.1, "million"),
    (re.compile(rf"\bin\s+{_CCY}(?:lakhs?|lacs?)\b", re.I), 0.01, "lakh"),
    (re.compile(rf"\bin\s+{_CCY}(?:crores?|cr\b)", re.I), 1.0, "crore"),
    (re.compile(rf"\bin\s+{_CCY}(?:'?000'?s?\b|thousands?)", re.I), 1e-4, "thousand"),
    (re.compile(r"\bin\s+(?:indian\s+)?rupees\b", re.I), 1e-7, "rupee"),
]
_YEAR_ENDED = re.compile(r"(?:year|period)\s+ended\s+(?:on\s+)?(?:March\s+31,?\s+|31\s*[/.-]\s*0?3\s*[/.-]\s*)(20\d\d)", re.I)


def _next_year(fy: str) -> str:
    return f"fy{int(fy[2:]) + 1:02d}"


@lru_cache(maxsize=64)
def _pages(path: str) -> Tuple[str, ...]:
    return tuple(page.get_text() for page in pymupdf.open(path))


@lru_cache(maxsize=64)
def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=64)
def report_fiscal_year(path: str) -> Optional[int]:
    """The fiscal year a report is about: the most frequent 'year ended March 31, YYYY' in its statements. A file can hold the next year's report (the FY2023-24 report filed under fy23)."""
    counts: Dict[int, int] = {}
    for text in _pages(path):
        for match in _YEAR_ENDED.finditer(text):
            counts[int(match.group(1))] = counts.get(int(match.group(1)), 0) + 1
    return max(counts, key=counts.get) if counts else None


@lru_cache(maxsize=16)
def _all_reports(company: str) -> Tuple[str, ...]:
    return tuple(sorted(str(p) for p in (DATA / company).glob("fy*/annual_report/*.pdf")))


def reports_for(company: str, fy: str) -> List[str]:
    target = 2000 + int(fy[2:])
    by_content = [r for r in _all_reports(company) if report_fiscal_year(r) == target]
    return by_content or sorted(str(p) for p in (DATA / company / fy / "annual_report").glob("*.pdf"))


@lru_cache(maxsize=64)
def report_bases(path: str) -> frozenset:
    """Bases whose statements this report contains, read from statement TITLES only (a title line at the top of a page: "Consolidated Balance Sheet", "Standalone Statement of Cash
    Flows") - not from an auditor's report or a note that mentions the other basis."""
    found = set()
    for text in _pages(path):
        head = text[:400]
        if _STRICT_TITLE.search(head):
            lowered = head.lower()
            for basis in ("consolidated", "standalone"):
                if basis in lowered:
                    found.add(basis)
    return frozenset(found)


def _label_parts(label: str) -> Tuple[List[str], Optional[re.Pattern]]:
    """(section words, item pattern). A statement prints a section heading and then lettered rows, so a stored label such as "Non-current assets (b) Capital work-in-progress" is the
    section "non current assets" and the item "capital work in progress"; the item is matched in order, the section must precede it on the page."""
    raw = re.sub(r"^derived:\s*", "", label, flags=re.I)
    marker = list(re.finditer(r"\(\s*(?:[ivx]{1,4}|[a-z]|\d)\s*\)", raw, flags=re.I))
    section_words: List[str] = []
    item = raw
    # a marker that ENDS the label ("Net cash generated from operating activities (A)", "Total tax expense (VIII)") labels the row; it does not introduce an item
    while marker and not raw[marker[-1].end():].strip(" :;-."):
        raw = raw[: marker[-1].start()]
        item = raw
        marker = marker[:-1]
    if marker:
        head, item = raw[: marker[-1].start()], raw[marker[-1].end():]
        section_words = re.findall(r"[a-z]+", head.lower())[-3:]
    tokens = re.findall(r"[a-z&]+", item.lower())
    while tokens and re.fullmatch(r"[ivx]+|[a-z]", tokens[0]):
        tokens = tokens[1:]
    tokens = [("and" if t == "&" else t) for t in tokens][-6:]
    pattern = re.compile(r"[\W_]+".join(re.escape(t) for t in tokens), re.I) if tokens else None
    return section_words, pattern


def _label_pattern(label: str) -> Optional[re.Pattern]:
    return _label_parts(label)[1]


def _amounts(segment: str, count: int = 5) -> List[Tuple[float, int, bool]]:
    """(value, printed decimals, negative) for the amounts after a label. Note references are not amounts: a small integer, and a cell of the Note column - which the PDF text
    prints without the padding its amount cells carry ("8.1" beside " 329.75 "), so a short unpadded cell followed by padded amount cells is a reference."""
    lines = segment.split("\n")
    padded_cells = [ln for ln in lines[:8] if ln.strip() and (ln.startswith(" ") or ln.endswith(" ")) and (_NUMBER.fullmatch(ln.strip()) or ln.strip() in {"-", "\u2013", "\u2014"})]
    out: List[Tuple[float, int, bool]] = []
    for position, line in enumerate(lines):
        if line.strip() in {"-", "\u2013", "\u2014"}:
            out.append((0.0, 0, False))              # a nil cell is a printed zero in that column
            if len(out) == count:
                return out
            continue
        for token in _NUMBER.findall(line):
            negative = token.startswith("(") or token.startswith("-")
            bare = token.strip("()").replace(",", "").lstrip("-")
            if not bare:
                continue
            if "," not in token and "." not in token and len(bare) <= 2:
                continue                                        # a note reference
            unpadded_cell = line.strip() == token and not (line.startswith(" ") or line.endswith(" "))
            if unpadded_cell and not out and padded_cells and not negative and re.fullmatch(r"\d{1,2}\.\d", bare) and "," not in token:
                continue                                        # the Note column's cell
            decimals = len(bare.split(".")[1]) if "." in bare else 0
            out.append((float(bare), decimals, negative))
            if len(out) == count:
                return out
    return out


def _declared_unit(text: str, position: int) -> Tuple[Optional[float], Optional[str]]:
    """The unit the page declares nearest above the row (else the first declaration on the page)."""
    best = None
    for pattern, scale, name in _UNIT_DECLARATION:
        for match in pattern.finditer(text):
            if match.start() <= position and (best is None or match.start() > best[0]):
                best = (match.start(), scale, name)
    if best is None:
        for pattern, scale, name in _UNIT_DECLARATION:
            match = pattern.search(text)
            if match and (best is None or match.start() < best[0]):
                best = (match.start(), scale, name)
    return (best[1], best[2]) if best else (None, None)


# A statement page is recognised by its title in the first 1,500 characters or, when the title sits on the previous page or in a header image, by three or more of the statement's own
# structural lines (a note table or a segment table rarely carries three).
_ANCHORS = {
    "balance_sheet": ("total assets", "equity and liabilities", "capital and liabilities", "non-current assets", "non current assets", "total current liabilities", "total equity", "total non-current liabilities", "current assets", "current liabilities", "other equity", "share capital", "financial assets"),
    "profit_and_loss": ("revenue from operations", "total income", "total expenses", "profit before tax", "earnings per equity share", "interest earned", "interest expended", "tax expense", "other expenses", "employee benefit", "finance costs", "depreciation and amortisation", "depreciation and amortization"),
    "cash_flow": ("operating activities", "investing activities", "financing activities", "cash and cash equivalents at the end"),
}


def _statement_ok(expected: str, text: str) -> bool:
    head = text[:1500]
    if expected == "balance_sheet_or_cash_flow":
        return _statement_ok("balance_sheet", text) or _statement_ok("cash_flow", text)
    if expected not in _TITLE:
        return False
    if _TITLE[expected].search(head):
        return True
    lowered = text.lower()
    return sum(1 for anchor in _ANCHORS[expected] if anchor in lowered) >= 3


_STRICT_TITLE = re.compile(r"(?:^|\n)\s*(?:consolidated\s+|standalone\s+)?(?:balance\s+sheet|statement\s+of\s+(?:financial\s+position|profit\s+and\s+loss|cash\s+flows?|changes\s+in\s+equity)|cash\s+flow\s+statement|"
                           r"profit\s+and\s+loss\s+account)\b", re.I)


_DECLARES_STANDALONE = re.compile(r"\bthese\s+standalone\s+(?:ind\s*as\s+)?financial\s+statements|\bstandalone\s+(?:ind\s*as\s+)?financial\s+statements\s+of\s+the\s+(?:company|bank)|no\s+requirement\s+to\s+prepare\s+consolidated|"
                                  r"does\s+not\s+have\s+any\s+subsidiar", re.I)
_DECLARES_CONSOLIDATED = re.compile(r"\bthese\s+consolidated\s+(?:ind\s*as\s+)?financial\s+statements|\bconsolidated\s+financial\s+statements\s+of\s+the\s+(?:group|company)", re.I)


@lru_cache(maxsize=64)
def report_entity_basis(path: str) -> str:
    """The basis of a report whose statement titles do not name one, from the report's own declaration ('These standalone financial statements have been prepared...', 'no
    requirement to prepare consolidated financial statements'). standalone | consolidated | both | unknown. Boilerplate that merely asks whether a disclosure is standalone or
    consolidated is not a declaration."""
    text = " ".join(_pages(path))
    standalone, consolidated = bool(_DECLARES_STANDALONE.search(text)), bool(_DECLARES_CONSOLIDATED.search(text))
    return "both" if standalone and consolidated else "standalone" if standalone else "consolidated" if consolidated else "unknown"


def _basis_state(fact_basis: str, text: str, report: str, page_number: int = 0) -> str:
    """match | mismatch | unresolved | not_asserted. The basis is read from the statement's own title; a continuation page (no title of its own) takes the title of the nearest preceding
    statement page within six pages - a statement title only, never an auditor's report or a note that happens to say 'consolidated'. A title that names no basis takes the report's
    ENTITY basis; when the report cannot settle it the requested basis is not confirmed (a single-basis report is not 'a match for either')."""
    if fact_basis not in {"consolidated", "standalone"}:
        return "not_asserted"
    head = text[:900].lower()
    named = [b for b in ("consolidated", "standalone") if b in head]
    if not named and not _STRICT_TITLE.search(text[:400]) and page_number:
        pages = _pages(report)
        for back in range(1, 7):
            index = page_number - 1 - back
            if index < 0:
                break
            if _STRICT_TITLE.search(pages[index][:400]):
                named = [b for b in ("consolidated", "standalone") if b in pages[index][:900].lower()]
                break
    if named:
        return "match" if fact_basis in named else "mismatch"
    entity = report_entity_basis(report)
    if entity in {"standalone", "consolidated"}:
        return "match" if entity == fact_basis else "mismatch"
    return "unresolved"


def _tolerance(decimals: int, scale: float) -> float:
    return 0.5 * (10 ** -decimals) * scale * 1.0001 + 1e-9


def _fact_object(fact: Dict[str, Any]) -> FinancialFact:
    return FinancialFact(metric_id=fact["metric_id"], metric_name=fact.get("metric_name") or fact["metric_id"], fiscal_year=fact.get("fiscal_year") or "", period=fact.get("period") or "",
                         value=fact.get("value"), unit=fact.get("unit") or "", basis=fact.get("basis") or "unknown", source_statement=fact.get("source_statement") or "",
                         source_artifact=fact.get("source_artifact") or "", source_line_item=fact.get("source_line_item") or "", source_page=fact.get("source_page"),
                         confidence=fact.get("confidence") or "", availability_status=fact.get("availability_status") or "present_direct", derived=bool(fact.get("derived")),
                         formula=fact.get("formula") or "", inputs_used=fact.get("inputs_used") or [], usable_downstream=bool(fact.get("usable_downstream")), period_role=fact.get("period_role") or "")


def _verdict(status: str, reasons: List[str], **evidence: Any) -> Dict[str, Any]:
    return {"status": status, "reasons": reasons, "evidence": evidence}


_MONEY_UNITS = {"inr crore", "₹ crore", "rs crore", "rs. crore", "inr cr", "crore"}
_PER_SHARE_UNITS = {"inr per share", "per share", "₹/share", "rupees per share", "inr/share", "rs per share"}
_NON_ANNUAL = re.compile(r"quarter|half[\s-]*year|six\s+months|nine\s+months|three\s+months|\bq[1-4]\b|\bh[12]\b|cumulative|year[\s-]*to[\s-]*date|\bytd\b|trailing|\bttm\b", re.I)
_EXPECTED_ROLE = {"profit_and_loss": "annual_flow", "cash_flow": "annual_flow", "balance_sheet": "closing_balance", "balance_sheet_or_cash_flow": "closing_balance"}
# metrics the mapper names differently from the registry, but which are the same quantity
_CAPEX_FAMILY = {"capex", "capex_ppe_cwip_cash_outflow", "capex_intangible_cash_outflow", "capex_ppe_and_intangible_cash_outflow"}
_SAME_QUANTITY = {**{m: _CAPEX_FAMILY for m in _CAPEX_FAMILY}, "inventories": {"inventories", "inventory"},
                  "inventory": {"inventories", "inventory"}, "pat": {"pat"}, "tax": {"tax", "tax_paid"}, "tax_paid": {"tax_paid", "tax"}}
_ROW_TABLES = ("profit_and_loss", "balance_sheet", "cash_flow", "eps", "share_capital", "borrowings", "fixed_assets", "revenue", "tax")
_HEADER_YEAR = re.compile(r"(?:march\s*31\s*,?|31(?:st)?\s+march\s*,?|31\s*[./-]\s*0?3\s*[./-])\s*(20\d\d)", re.I)


def _record_problems(fact: Dict[str, Any], fy: str, metric: str, expected: str) -> Optional[Tuple[str, List[str]]]:
    """The record must itself be the fact it claims, before the filing is consulted. REJECTED = the record contradicts the identity it is being verified for; PROVISIONAL = it does not
    assert enough identity to be certified."""
    target = 2000 + int(fy[2:])
    record_fy = str(fact.get("fiscal_year") or "").strip().lower()
    if record_fy and record_fy != fy:
        return "REJECTED", [f"the record is for {record_fy}, but {fy} is being verified: a filing cannot certify another year's record"]
    period = str(fact.get("period") or "")
    if _NON_ANNUAL.search(period):
        return "REJECTED", [f"the record's period {period!r} is not an annual period: an annual statement cannot prove it"]
    years = {int(y) for y in re.findall(r"20\d\d", period)} | {2000 + int(y) for y in re.findall(r"fy\s*(\d\d)\b", period, re.I)}
    if years and target not in years:
        return "REJECTED", [f"the record's period {period!r} does not end in the fiscal year {fy} being verified"]
    role = str(fact.get("period_role") or "").strip().lower()
    want = _EXPECTED_ROLE.get(expected, "annual_flow")
    if role and role != want:
        if role in {"other", "derived", ""}:
            return "PROVISIONAL", [f"the record's period role is {role!r}, not the {want!r} this metric requires"]
        return "REJECTED", [f"the record's period role {role!r} is not {want!r}: the statement row cannot prove it"]
    if not role:
        return "PROVISIONAL", [f"the record does not assert its period role (needs {want!r})"]
    unit = str(fact.get("unit") or "").strip().lower()
    canonical = _PER_SHARE_UNITS if metric in PER_SHARE else _MONEY_UNITS
    if unit and unit not in canonical:
        return "REJECTED", [f"the record's unit {fact.get('unit')!r} is not the canonical {'INR per share' if metric in PER_SHARE else 'INR crore'}: its value is not on the scale the filing is being converted to"]
    if not unit:
        return "PROVISIONAL", ["the record does not assert its unit"]
    if str(fact.get("basis") or "").strip().lower() not in {"consolidated", "standalone"}:
        return "PROVISIONAL", [f"the record does not assert a reporting basis ({fact.get('basis')!r}): consolidated and standalone are different facts"]
    return None


def _label_fields(label: str) -> set:
    raw = re.sub(r"^derived:\s*", "", str(label or ""), flags=re.I)
    fields: set = set()
    for table in _ROW_TABLES:
        fields |= {m.canonical_field for m in map_line_item(table_type=table, line_item_raw=raw)}
    return fields


_CAPEX_ROW = re.compile(r"\b(?:purchase|purchases|payment|payments|acquisition|acquire|addition|additions|expenditure|investment)\b.*\b(?:property|plant|equipment|intangibles?|fixed\s+assets?|capital\s+work|software|tangible)\b", re.I)


def _row_contract(metric: str, label: str) -> Optional[Tuple[str, List[str]]]:
    """The source label must be a recognised source row of THIS metric. Negative exclusions (semantic_contracts) say what a row is not; this says what it is."""
    fields = _label_fields(label)
    ok = {metric} | _SAME_QUANTITY.get(metric, set())
    if fields & ok:
        return None
    if metric in _CAPEX_FAMILY and not fields and _CAPEX_ROW.search(label):
        return None                       # a cash-flow row that buys property, plant, equipment or intangibles is a capex-family row (the component rows of a split capex)
    if fields:
        return "REJECTED", [f"the source row {label!r} is a {'/'.join(sorted(fields))} row, not a {metric} row"]
    return "PROVISIONAL", [f"the source row {label!r} is not a recognised source row of {metric}"]


def _column_years(text: str) -> List[int]:
    seen: List[int] = []
    for year in (int(y) for y in _HEADER_YEAR.findall(text[:2500])):
        if year not in seen:
            seen.append(year)
    return seen


def verify_fact(fact: Dict[str, Any], *, company: str, fy: str, bank_format: bool = False, canonical: Optional["CanonicalRegistry"] = None,
                registry_verdicts: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Statuses: VERIFIED | VERIFIED_AS_COMPARATIVE | PROVISIONAL | REJECTED | DERIVED_VERIFIED | DERIVED_UNVERIFIED | NO_FILING.
    A derived fact is bound to `canonical` (the company's registry facts, by metric and fiscal year); without it a derived fact cannot be verified. `registry_verdicts` (verdicts
    supplied by the caller, which an earlier version trusted by name) is accepted for compatibility and IGNORED: supplied verdicts and supplied numbers are not evidence."""
    value = fact.get("value")
    metric = fact["metric_id"]
    reasons: List[str] = []
    obj = _fact_object(fact)
    problems = semantic_problems(obj, bank_format=bank_format)
    if problems:
        return _verdict("REJECTED", problems)                                            # 1. metric meaning (what the row is not)
    if fact.get("derived") or str(fact.get("source_line_item") or "").lower().startswith("derived"):
        return _verify_derived(fact, company=company, fy=fy, canonical=canonical)
    if not isinstance(value, (int, float)):
        return _verdict("PROVISIONAL", ["no numeric value to verify"])
    expected = STATEMENT_OF_METRIC.get(metric)
    if expected is None:
        return _verdict("PROVISIONAL", [f"{metric}: no statement is defined for this metric, so the row's statement cannot be confirmed"])
    identity = _record_problems(fact, fy, metric, expected)                              # 0. the record's own identity
    if identity:
        return _verdict(identity[0], identity[1])
    contract = _row_contract(metric, str(fact.get("source_line_item") or ""))            # 1b. what the row is
    if contract:
        return _verdict(contract[0], contract[1])
    section_words, pattern = _label_parts(str(fact.get("source_line_item") or ""))
    if pattern is None:
        return _verdict("PROVISIONAL", ["the source line has no label words to find"])
    reports = reports_for(company, fy)
    column, comparative = 0, False
    if not reports:
        reports, column, comparative = reports_for(company, _next_year(fy)), 1, True
        if not reports:
            return _verdict("NO_FILING", ["no filing for this year or the next"])
    accepted = [expected] + (["cash_flow"] if metric in CASH_FLOW_RESTATED else [])
    cited = fact.get("source_page")
    best: Optional[Dict[str, Any]] = None
    for report in reports:                                                              # 2. source identity: chosen by content, hash recorded
        reported = report_fiscal_year(report)
        col = column if not reported else max(0, min(reported - (2000 + int(fy[2:])), 3))
        pages = list(enumerate(_pages(report), start=1))
        pages.sort(key=lambda item: (item[0] != cited, item[0]))                         # the cited page first
        for number, text in pages:
            page_statement = next((st for st in accepted if _statement_ok(st, text)), None)  # 3. statement
            if page_statement is None and metric in PER_SHARE_NOTE_PAGE and PER_SHARE_NOTE_PAGE[metric].search(text):
                page_statement = "per_share_note"             # the earnings-per-share note states the same figures as the statement
            if page_statement is None:
                continue
            header = _column_years(text)
            for match in pattern.finditer(text):
                if section_words and " ".join(section_words) not in " ".join(re.findall(r"[a-z]+", text[max(0, match.start() - 700): match.start()].lower())):
                    continue
                amounts = _amounts(text[match.end(): match.end() + 260])
                if len(amounts) <= col:
                    continue
                scale, unit_name = (1.0, "per share") if metric in PER_SHARE else _declared_unit(text, match.start())
                if scale is None:
                    best = best or _verdict("PROVISIONAL", ["the page declares no unit near the row, so the amount cannot be converted without guessing"], file=Path(report).name, page=number)
                    continue
                printed, decimals, negative = amounts[col]
                signed = -printed if negative else printed
                converted = signed * scale
                tol = _tolerance(decimals, scale)
                if metric in OUTFLOW_CONVENTION:
                    equal = abs(abs(converted) - abs(value)) <= tol                       # 7. outflow convention, by name
                else:
                    equal = abs(converted - value) <= tol
                if not equal:
                    other = amounts[1 - col] if len(amounts) > 1 and col in (0, 1) else None
                    if other and abs((-other[0] if other[2] else other[0]) * scale - value) <= _tolerance(other[1], scale):
                        best = best or _verdict("REJECTED", ["the value is the other year's column, not this year's"], file=Path(report).name, page=number, report_sha256=_sha256(report))
                    continue
                if len(header) >= 2 and col < len(header) and header[col] != 2000 + int(fy[2:]):
                    best = best or _verdict("PROVISIONAL", [f"the page's column headers read {header}: column {col} is {header[col]}, not the fiscal year {fy} being verified"], file=Path(report).name, page=number)
                    continue
                basis_state = _basis_state(str(fact.get("basis") or ""), text, report, number)   # 5. basis
                if basis_state == "mismatch":
                    best = best or _verdict("REJECTED", [f"the statement is not {fact.get('basis')}"], file=Path(report).name, page=number)
                    continue
                if basis_state == "unresolved":
                    best = best if best and best["status"] == "VERIFIED" else _verdict("PROVISIONAL", ["neither the statement heading nor the report's own wording settles whether this page is consolidated or standalone"], file=Path(report).name, page=number)
                    continue
                status = "VERIFIED_AS_COMPARATIVE" if comparative or col else "VERIFIED"
                if cited and number != cited:
                    reasons = [f"found on page {number}, not the cited page {cited}"]
                return _verdict(status, reasons, file=Path(report).name, report_sha256=_sha256(report), page=number, row=match.group(0), column=col, unit=unit_name, scale_to_crore=scale,
                                printed=("-" if negative else "") + f"{printed}", basis_state=basis_state, statement=page_statement, column_year=(header[col] if len(header) > col else None),
                                record_unit=fact.get("unit"), period_role=fact.get("period_role"), company=company, fiscal_year=fy,
                                restated_on_cash_flow_page=(page_statement == "cash_flow" and expected != "cash_flow"))
    return best or _verdict("PROVISIONAL", ["no row on a matching statement page carries this amount in the current-year column"])


# ---- derived facts: re-derived here, from canonical registry facts resolved by identity -------------------------------------------------------------------------------------------------

def _cap(cfo, capex):
    return cfo + capex if capex <= 0 else cfo - capex


def _safe_div(a, b):
    return None if not b else a / b


# metric -> ([(input metric, fiscal-year offset)], function of the input values). The definitions are this module's own; the stored formula text is never executed or trusted.
DERIVATIONS: Dict[str, Tuple[List[Tuple[str, int]], Any]] = {
    "total_debt": ([("short_term_debt", 0), ("long_term_debt", 0)], lambda a, b: a + b),
    "net_debt": ([("total_debt", 0), ("cash_and_equivalents", 0)], lambda d, c: d - c),
    "debt_to_equity": ([("total_debt", 0), ("net_worth", 0)], _safe_div),
    "net_debt_to_equity": ([("net_debt", 0), ("net_worth", 0)], _safe_div),
    "net_worth": ([("equity_share_capital", 0), ("reserves", 0)], lambda a, b: a + b),
    "total_liabilities": ([("total_assets", 0), ("net_worth", 0)], lambda a, b: a - b),
    "payables": ([("msme_trade_payables", 0), ("other_trade_payables", 0)], lambda a, b: a + b),
    "capex": ([("capex_ppe_cwip_cash_outflow", 0), ("capex_intangible_cash_outflow", 0)], lambda a, b: a + b),
    "npm": ([("pat", 0), ("revenue", 0)], lambda p, r: None if not r else p / r * 100),
    "cfo_to_pat": ([("cfo", 0), ("pat", 0)], _safe_div),
    "fcf": ([("cfo", 0), ("capex", 0)], _cap),
    "fcf_after_total_identified_capex": ([("cfo", 0), ("capex", 0)], _cap),
    "fcf_after_ppe_cwip_capex": ([("cfo", 0), ("capex_ppe_cwip_cash_outflow", 0)], _cap),
    "fcf_margin": ([("fcf", 0), ("revenue", 0)], lambda f, r: None if not r else f / r * 100),
    "fcf_to_pat": ([("fcf", 0), ("pat", 0)], _safe_div),
    "payout_ratio": ([("dividends_paid", 0), ("pat", 0)], lambda d, p: None if not p else abs(d) / p * 100),
    "gross_margin": ([("revenue", 0), ("cost_of_materials", 0)], lambda r, c: None if not r else (r - c) / r * 100),
    "roe": ([("pat", 0), ("net_worth", 0), ("net_worth", -1)], lambda p, n1, n0: None if not (n1 + n0) else p / ((n1 + n0) / 2) * 100),
    "roa": ([("pat", 0), ("total_assets", 0), ("total_assets", -1)], lambda p, a1, a0: None if not (a1 + a0) else p / ((a1 + a0) / 2) * 100),
    "receivable_days": ([("receivables", 0), ("receivables", -1), ("revenue", 0)], lambda r1, r0, rev: None if not rev else (r1 + r0) / 2 / rev * 365),
    "inventory_days": ([("inventories", 0), ("inventories", -1), ("cost_of_materials", 0)], lambda i1, i0, c: None if not c else (i1 + i0) / 2 / c * 365),
    "payable_days": ([("payables", 0), ("payables", -1), ("cost_of_materials", 0)], lambda p1, p0, c: None if not c else (p1 + p0) / 2 / c * 365),
}
for _base in ("revenue", "pat", "cfo", "capex", "fcf", "net_worth", "total_debt", "receivables", "inventory", "payables", "reserves", "eps_basic", "eps_diluted"):
    DERIVATIONS[f"{_base}_growth"] = ([(_base, 0), (_base, -1)], lambda cur, prev: None if not prev else (cur - prev) / abs(prev) * 100)
_AUTHORITATIVE = {"VERIFIED", "VERIFIED_AS_COMPARATIVE", "DERIVED_VERIFIED"}
_RANK = {"VERIFIED": 3, "VERIFIED_AS_COMPARATIVE": 3, "DERIVED_VERIFIED": 2}


def input_fingerprint(fact: Dict[str, Any]) -> str:
    keys = ("metric_id", "fiscal_year", "value", "basis", "unit", "source_line_item", "source_page", "availability_status", "usable_downstream")
    return hashlib.sha256(json.dumps({k: fact.get(k) for k in keys}, sort_keys=True, default=str).encode()).hexdigest()


class CanonicalRegistry:
    """The company's canonical registry facts by (fiscal year, metric), with the verdict of each (computed here, once). A derived fact's inputs are resolved only through this object."""

    def __init__(self, company: str, registries: Dict[str, Dict[str, Any]], bank_format: bool = False):
        self.company, self.bank_format = company, bank_format
        self.facts: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for year, registry in registries.items():
            for key in ("available_facts", "derived_facts", "partial_facts"):
                for f in registry.get(key) or []:
                    self.facts[(year, f["metric_id"])] = f
        self._verdicts: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def resolve(self, year: str, metric: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        fact = self.facts.get((year, metric))
        if fact is None:
            return None, None
        if (year, metric) not in self._verdicts:
            self._verdicts[(year, metric)] = {"status": "DERIVED_UNVERIFIED", "reasons": ["cyclic derivation"]}      # guards a self-referencing derivation
            self._verdicts[(year, metric)] = verify_fact(fact, company=self.company, fy=year, bank_format=self.bank_format, canonical=self)
        return fact, self._verdicts[(year, metric)]


def _verify_derived(fact: Dict[str, Any], *, company: str, fy: str, canonical: Optional[CanonicalRegistry]) -> Dict[str, Any]:
    metric = fact["metric_id"]
    spec = DERIVATIONS.get(metric)
    if spec is None:
        return _verdict("DERIVED_UNVERIFIED", [f"{metric}: this module defines no independent derivation for the metric"])
    if canonical is None:
        return _verdict("DERIVED_UNVERIFIED", ["no canonical registry was supplied: the derivation's inputs cannot be resolved by identity, and supplied numbers are not evidence"])
    if not isinstance(fact.get("value"), (int, float)):
        return _verdict("DERIVED_UNVERIFIED", ["no numeric value to check"])
    inputs, function = spec
    bound, values, weakest, pending = [], [], "VERIFIED", []
    for input_metric, offset in inputs:
        year = f"fy{int(fy[2:]) + offset:02d}"
        found, verdict = canonical.resolve(year, input_metric)
        if found is None or not isinstance(found.get("value"), (int, float)):
            return _verdict("DERIVED_UNVERIFIED", [f"input {input_metric} for {year} is not a canonical registry fact with a value"])
        status = verdict["status"]
        usable = bool(found.get("usable_downstream"))
        bound.append({"metric": input_metric, "fiscal_year": year, "value": found["value"], "status": status, "usable": usable, "source_page": found.get("source_page"), "fingerprint": input_fingerprint(found)})
        values.append(float(found["value"]))
        if not usable or status not in _AUTHORITATIVE:
            pending.append(f"input {input_metric} ({year}) is {status}{'' if usable else ' and not usable'}")
        elif _RANK[status] < _RANK[weakest if weakest in _RANK else "VERIFIED"]:
            weakest = status
    recomputed = function(*values)
    if recomputed is None:
        return _verdict("DERIVED_UNVERIFIED", ["the canonical inputs give no defined result (a zero denominator)"], inputs=bound)
    stored = float(fact["value"])
    if abs(recomputed - stored) > 0.0051 + 5e-4 * abs(recomputed):
        if any(offset for _m, offset in inputs):
            # a growth rate or an average is computed against the PRIOR year as the CURRENT report restates it; the canonical registry holds the prior year as originally filed
            return _verdict("DERIVED_UNVERIFIED", [f"the stored {metric} {stored} differs from its recomputation on the canonical prior-year inputs ({recomputed:.6g}); the calculator uses the current "
                                                    "report's restated comparatives"], inputs=bound, recomputed=recomputed)
        return _verdict("REJECTED", [f"the stored value {stored} is not the {metric} of its canonical inputs ({recomputed:.6g})"], inputs=bound, recomputed=recomputed)
    if pending:
        return _verdict("DERIVED_UNVERIFIED", pending, inputs=bound, recomputed=recomputed)
    return _verdict("DERIVED_VERIFIED", [], inputs=bound, recomputed=recomputed, weakest_input=weakest)


def verify_registry(company: str, fy: str, registry: Dict[str, Any], *, bank_format: bool = False, registries: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Dict[str, Any]]:
    """Verdicts for every fact in a year's registry that the registry keeps as available / derived / partial (usable or not). `registries` = the company's other years' registries
    (prior-year inputs of averages and growth are resolved there)."""
    canonical = CanonicalRegistry(company, {**(registries or {}), fy: registry}, bank_format=bank_format)
    facts = [f for key in ("available_facts", "derived_facts", "partial_facts") for f in (registry.get(key) or [])]
    return {f["metric_id"]: canonical.resolve(fy, f["metric_id"])[1] for f in facts}


def company_registries(company_dir: Path) -> Dict[str, Dict[str, Any]]:
    return {y.name: json.loads((y / "financials" / "financial_fact_registry.json").read_text(encoding="utf-8")) for y in sorted(company_dir.glob("fy*"))
            if (y / "financials" / "financial_fact_registry.json").exists()}


# Metrics an investor decision leans on. One of these that is usable but NOT independently checked against the filing (PROVISIONAL, or a derivation from such inputs) is flagged
# `must_qualify` in the truth pack and named in its precision limits, which the Ask answers and the panel read: the uncertainty travels with the figure.
HIGH_IMPACT = frozenset({"revenue", "pat", "cfo", "capex", "fcf", "cash_and_equivalents", "total_debt", "net_debt", "net_worth", "equity_share_capital", "reserves", "total_assets", "payables", "receivables",
                         "inventories", "shares_outstanding", "weighted_avg_shares", "weighted_average_basic_shares", "debt_to_equity", "roe", "book_value_per_share", "eps_basic", "eps_diluted",
                         "total_deposits", "finance_cost", "ebit", "ebitda", "dividends_paid", "buyback_paid"})
_FULL = {"VERIFIED", "VERIFIED_AS_COMPARATIVE", "DERIVED_VERIFIED"}
_LIMIT_PREFIX = "Not independently checked against the filing"


def stamp(companies_root: Path, companies: Optional[List[str]] = None) -> Dict[str, int]:
    """Write each year's verdicts to financials/financial_fact_verification.json and annotate the company truth pack's metrics with `verification_status`. Eligibility is untouched:
    a fact the registry keeps stays usable whatever its status, and a rejected one stays rejected; the status is the separate statement of how far the filing has been checked."""
    counts: Dict[str, int] = {}
    for company_dir in sorted(p for p in Path(companies_root).iterdir() if p.is_dir() and (not companies or p.name in companies)):
        by_year: Dict[str, Dict[str, str]] = {}
        registries = company_registries(company_dir)
        for year_dir in sorted(p for p in company_dir.glob("fy*") if (p / "financials" / "financial_fact_registry.json").exists()):
            registry = json.loads((year_dir / "financials" / "financial_fact_registry.json").read_text(encoding="utf-8"))
            try:
                normalized = json.loads((year_dir / "financials" / "normalized_fundamentals.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                normalized = {}
            verdicts = verify_registry(company_dir.name, year_dir.name, registry, bank_format=bool((normalized.get("registry_context") or {}).get("bank_format")), registries=registries)
            (year_dir / "financials" / "financial_fact_verification.json").write_text(json.dumps({"company": company_dir.name, "year": year_dir.name, "verdicts": verdicts}, indent=1, default=str), encoding="utf-8")
            by_year[year_dir.name] = {metric: v["status"] for metric, v in verdicts.items()}
            for v in verdicts.values():
                counts[v["status"]] = counts.get(v["status"], 0) + 1
        pack_path = company_dir / "company_memory" / "financials" / "financial_truth_pack.json"
        if pack_path.exists():
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            weak = set()
            for key in ("usable_current_metrics", "usable_derived_metrics", "partial_metrics"):
                for item in pack.get(key) or []:
                    if isinstance(item, dict):
                        item["verification_status"] = (by_year.get(str(item.get("fiscal_year"))) or {}).get(str(item.get("metric_id")), "NOT_INDEPENDENTLY_VERIFIED")
                        item["reliance"] = "full" if item["verification_status"] in _FULL else "qualified"
                        item.pop("must_qualify", None)
                        if item["reliance"] == "qualified" and item.get("metric_id") in HIGH_IMPACT:
                            item["must_qualify"] = True
                            weak.add((str(item.get("metric_id")), str(item.get("fiscal_year"))))
            limits = [x for x in (pack.get("precision_limits") or []) if not str(x).startswith(_LIMIT_PREFIX)]
            if weak:
                listed = ", ".join(f"{m} {fy}" for m, fy in sorted(weak)[:12]) + (f" and {len(weak) - 12} more" if len(weak) > 12 else "")
                limits.append(f"{_LIMIT_PREFIX}: {len(weak)} high-impact figures ({listed}) are used as extracted; qualify them when relied on.")
            pack["precision_limits"] = limits
            pack["verification_policy"] = ("verification_status states how far the filing has been checked for a metric (VERIFIED, VERIFIED_AS_COMPARATIVE, DERIVED_VERIFIED, PROVISIONAL, DERIVED_UNVERIFIED, "
                                           "NOT_INDEPENDENTLY_VERIFIED); it never changes whether the registry lets the metric be used")
            pack_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return counts


def census(companies_root: Path, out_path: Path, companies: Optional[List[str]] = None) -> Dict[str, Any]:
    """Verdicts for ALL facts of every year (changed or not)."""
    rows: List[Dict[str, Any]] = []
    for company_dir in sorted(p for p in Path(companies_root).iterdir() if p.is_dir() and (not companies or p.name in companies)):
        registries = company_registries(company_dir)
        for year_dir in sorted(p for p in company_dir.glob("fy*") if (p / "financials" / "financial_fact_registry.json").exists()):
            registry = json.loads((year_dir / "financials" / "financial_fact_registry.json").read_text(encoding="utf-8"))
            try:
                normalized = json.loads((year_dir / "financials" / "normalized_fundamentals.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                normalized = {}
            bank = bool((normalized.get("registry_context") or {}).get("bank_format"))
            verdicts = verify_registry(company_dir.name, year_dir.name, registry, bank_format=bank, registries=registries)
            keep = {f["metric_id"]: f for key in ("available_facts", "derived_facts", "partial_facts") for f in (registry.get(key) or [])}
            for metric, verdict in verdicts.items():
                f = keep[metric]
                rows.append({"company": company_dir.name, "fy": year_dir.name, "metric": metric, "value": f.get("value"), "basis": f.get("basis"), "line": f.get("source_line_item"),
                             "page": f.get("source_page"), "usable_downstream": f.get("usable_downstream"), "status": verdict["status"], "reasons": verdict["reasons"], "evidence": verdict["evidence"]})
    summary: Dict[str, int] = {}
    for row in rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    out_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, default=str), encoding="utf-8")
    return summary


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "stamp":
        print(json.dumps(stamp(Path(sys.argv[2])), indent=1))
    elif len(sys.argv) >= 4 and sys.argv[1] == "census":
        only = sys.argv[sys.argv.index("--companies") + 1].split(",") if "--companies" in sys.argv else None
        print(json.dumps(census(Path(sys.argv[2]), Path(sys.argv[3]), only), indent=1))
    else:
        print(__doc__)
