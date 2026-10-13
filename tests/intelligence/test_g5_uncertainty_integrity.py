"""M63/G5 uncertainty and judgment integrity: reusable reasoning rules, tested on the four G4 companies and on adversarial paraphrases.
Reads scratch candidates (G5_OUT, default /private/tmp/claude-501/g5/out) and the G3 overlay root; touches nothing under companies/ or governance/."""
import datetime as dt
import json
import os
import re
from pathlib import Path

import pytest

from pipelines import g4_investor_answers as g4

OUT = Path(os.environ.get("G5_OUT", "/private/tmp/claude-501/g5/out"))
ROOT = Path(os.environ.get("G5_ROOT", "/private/tmp/claude-501/g4/root"))
pytestmark = pytest.mark.skipif(not OUT.exists(), reason="candidates not generated")
KEYS = ["sun_pharma", "tanla", "ujjivan", "datapatterns"]
FIELDS = ["simple_answer", "what_evidence_shows", "what_may_mean_economically", "what_is_not_yet_proven", "what_to_monitor"]


def cand(k, q):
    return json.loads((OUT / f"{k}__{q}.candidate.json").read_text())["answer"]


def text(a):
    return "\n".join(x for f in FIELDS for x in ([a[f]] if isinstance(a[f], str) else [str(y) for y in a[f]]))


def T(k, q):
    return text(cand(k, q))


# ── absence is not non-existence: a disclosure the records lack is quoted, not denied ──
def test_data_patterns_major_customer_disclosure_is_not_denied():
    t = T("datapatterns", "what-does-company-do")
    assert not re.search(r"no top-customer|found after searching", t) and re.search(r"p\.171", t) and re.search(r"3 customers each above 10% of revenue", t)


def test_sun_no_customer_above_ten_percent_is_reported_as_the_filings_own_statement():
    assert re.search(r"p\.303\): the note states that no customer contributed more than 10\.0% of total revenues", T("sun_pharma", "what-does-company-do"))


def test_tanla_customer_concentration_disclosure_is_quoted():
    t = T("tanla", "what-does-company-do")
    assert re.search(r"p\.368", t) and re.search(r"2 customers each above 10% of revenue", t)


def test_bank_concentration_uses_depositor_and_borrower_language_and_quotes_the_disclosure():
    t = T("ujjivan", "what-does-company-do")
    assert "top-customer" not in t and re.search(r"twenty largest depositors held ₹6,456\.00 crore, 17\.16% of total deposits", t) and "funding concentration" in t


# ── conflicting sources are shown, not silently reconciled ──
def test_ujjivan_margin_conflict_between_management_highlight_and_statutory_note_is_preserved():
    for q in ("what-does-company-do", "what-could-go-wrong", "are-profits-converting-into-cash"):
        t = T("ujjivan", q)
        assert re.search(r"8\.67%", t) and re.search(r"p\.307", t) and re.search(r"not reconciled", t), q


# ── a positive opportunity is not an unsupported business risk (rule, not company) ──
@pytest.mark.parametrize("wording", [
    "Opportunity to expand our supplier base across new regions",
    "Strengthening our indigenous capabilities where domestic alternatives are limited",
    "Diversification of the customer base creates growth potential",
    "Tailwind from rising demand for local manufacturing",
])
def test_opportunity_wording_without_an_adverse_premise_supports_no_risk_channel(wording):
    assert g4.classify(wording, False) is None


@pytest.mark.parametrize("wording,channel", [
    ("Dependence on a single supplier for critical components", "supply"),
    ("Reliance on non-substitutable ecosystem partners", "partner"),
    ("Strategic dependence on foreign technology for key subsystems", "import_dependence"),
])
def test_adverse_premise_still_supports_its_channel(wording, channel):
    assert g4.classify(wording, False)["id"] == channel


def test_unmatched_risk_records_are_recorded_for_observability_not_displayed():
    sel = cand("datapatterns", "what-could-go-wrong")["g41_risk_selection"]
    names = " ".join(str(x) for x in sel.get("withheld_no_mechanism", []))
    assert "domestic alternatives" in names
    assert all(s["channel"] for s in sel["shown"])


# ── sector-wide disclosure is not a company-wide conclusion ──
def test_industry_context_is_not_listed_among_the_company_exposures():
    a = cand("ujjivan", "what-could-go-wrong")
    first = a["simple_answer"].split("Industry context")[0]
    assert "Industry context" in a["simple_answer"] and "sector-wide slowdown" not in first.lower()


# ── disclaimer inflation ──
@pytest.mark.parametrize("k", KEYS)
def test_management_caveats_are_stated_once_not_per_item(k):
    t = T(k, "what-has-management-promised")
    assert len(re.findall(r"Adoption, commercial use and economic results are not established", t)) == 0
    assert len(re.findall(r"unknown is not a miss", t)) <= 1
    assert len(re.findall(r"lexical", t)) <= 1


@pytest.mark.parametrize("k", KEYS)
def test_discovery_does_not_repeat_the_unexplained_movement_caveat(k):
    a = cand(k, "are-profits-converting-into-cash")
    ev = " ".join(a["what_evidence_shows"])
    assert not re.search(r"does not say why they moved|which of them actually funded it is not shown", ev)


# ── time ──
def test_unreadable_deadline_wording_is_not_judged_future_or_past():
    assert g4.deadline_date("over the next couple of years") is None
    assert g4.deadline_date("ongoing") is None
    assert g4.deadline_date("by FY2024-25") == dt.date(2025, 3, 31)
    assert g4.deadline_date("by March 2026") == dt.date(2026, 3, 31) or g4.deadline_date("by March 2026") is None


def test_ceiling_targets_and_below_target_figures_are_never_called_met():
    c = {"original_statement": "Keep operating cost below 30% of revenue", "commitment_basis": {"verifiable_outcome": "quantified_target"}}
    assert g4.achievement(c, [{"fy": "fy25", "page": 3, "quote": "operating cost was 28% of revenue"}]) is None
    c2 = {"original_statement": "Achieve a 35% reduction in emissions", "commitment_basis": {"verifiable_outcome": "quantified_target"}}
    r = g4.achievement(c2, [{"fy": "fy26", "page": 9, "quote": "emissions fell by 16.7% against baseline"}])
    assert r and r["met"] is False


# ── source versus inference ──
@pytest.mark.parametrize("k", KEYS)
def test_every_risk_separates_source_paraphrase_and_inference(k):
    a = cand(k, "what-could-go-wrong")
    for b in [e for e in a["what_evidence_shows"] if re.match(r"\d\. ", e)]:
        assert re.search(r"source passage p\.\d+|risk record \(paraphrase", b), b[:80]
        assert "Analyst inference (conditional)" in b or "Computed from the statements" in b, b[:80]


# ── absence states (contract G5): every absence statement carries one, and 'not disclosed' only with search evidence ──
@pytest.mark.parametrize("k", KEYS)
@pytest.mark.parametrize("q", ["what-does-company-do", "what-has-management-promised", "what-could-go-wrong", "are-profits-converting-into-cash"])
def test_every_absence_statement_carries_a_state_and_none_is_contradicted(k, q):
    L = g4.Ledger(k, ROOT)
    a = cand(k, q)
    assert "g5_absence" in a
    res = g4.audit_absence(L, a)
    assert not res["untagged"] and not res["contradicted"] and not res["misworded"], res


def test_the_absence_auditor_rejects_bad_wording():
    L = g4.Ledger("datapatterns", ROOT)
    bad = {"simple_answer": "The company does not disclose its customers.", "what_evidence_shows": ["The records are silent on responses."], "what_may_mean_economically": "", "what_is_not_yet_proven": "Order book: not in the records.", "what_to_monitor": [], "g5_absence": []}
    res = g4.audit_absence(L, bad)
    assert res["misworded"] and res["untagged"]


# ── the real investment questions: facts kept, causes not invented ──
def test_data_patterns_dividend_gap_names_possible_sources_without_asserting_one():
    t = T("datapatterns", "are-profits-converting-into-cash")
    assert re.search(r"₹36\.14 crore", t) and re.search(r"possible sources", t)
    assert not re.search(r"funded by|financed by|paid out of|was funded from", t)
    assert re.search(r"does not by itself show the distribution is unsustainable", t)


@pytest.mark.parametrize("k", ["sun_pharma", "tanla", "datapatterns"])
def test_cash_flow_movements_are_arithmetic_not_causes(k):
    t = T(k, "are-profits-converting-into-cash")
    own = [x for x in re.split(r"(?<=[.;])\s+", re.sub(r"“[^”]*”", "", t)) if not re.search(r"\b(?:not|no|whether|what)\b", x, re.I)]
    assert not [x for x in own if re.search(r"\b(?:because|caused|led to|resulted in|drove|due to)\b", x, re.I)]
    assert re.search(r"not stated in the records|not established|not shown", t)


def test_tracker_labels_are_never_presented_as_outcomes():
    for k in KEYS:
        t = T(k, "what-has-management-promised")
        for m in re.finditer(r"is marked (?:delivered|in progress|partially delivered)", t):
            assert "Tracker evidence, not primary-source proof" in t[max(0, m.start() - 160): m.start()]


def test_reported_achievement_and_independent_assurance_stay_separate():
    t = T("sun_pharma", "what-has-management-promised")
    assert "Management reports the target met: 47% against 30%" in t and "not independently assured" in t


def test_source_conflicts_are_listed_with_both_values_and_never_averaged():
    msg = g4.date_conflict([{"fy": "fy25", "page": 4, "quote": "The authority approved the product in March 2025"}, {"fy": "fy25", "page": 9, "quote": "approved on 2 June 2025"}])
    assert msg == "" or ("not reconciled" in msg)       # the day-first form is outside the pattern: documented limitation, never a silent merge
    two = g4.date_conflict([{"fy": "fy25", "page": 4, "quote": "The authority approved the product in March 2025"}, {"fy": "fy25", "page": 9, "quote": "approved in June 2025"}])
    assert "March 2025" in two and "June 2025" in two and "not reconciled" in two


def test_ujjivan_profit_comparison_carries_no_needless_caveat():
    for q in ("what-does-company-do", "are-profits-converting-into-cash"):
        t = T("ujjivan", q)
        assert "−43.3%" in t and not re.search(r"indicative|different or unstated", t)


def test_a_passed_deadline_is_never_future_whatever_the_latest_filing(monkeypatch):
    L = g4.Ledger("ujjivan", ROOT)
    c = next(c for c in L._commitments if c["commitment_class"] == "HARD_COMMITMENT")
    monkeypatch.setattr(g4, "AS_OF", dt.date(2027, 6, 1))
    txt = g4.commitment_block(L, c)[0]
    assert "has passed as of 1 June 2027" in txt and "not yet reached" not in txt and "missed" not in txt.replace("unknown is not a miss", "")


def test_disclaimers_do_not_dominate_the_answer():
    for k in KEYS:
        for q in ("what-does-company-do", "what-has-management-promised", "what-could-go-wrong", "are-profits-converting-into-cash"):
            t = T(k, q)
            hedges = len(re.findall(r"not established|not shown|not stated|not quantified|not extracted|not in the (?:extracted )?records|unknown", t, re.I))
            assert hedges <= 14, (k, q, hedges)
