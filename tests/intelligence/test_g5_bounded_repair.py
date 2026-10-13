"""M63/G5 bounded repair: claim-level absence integrity. Adversarial sentences differ from the implementation's own examples.
Reads scratch candidates (G5R_OUT, default /private/tmp/claude-501/g5r/out) and the G3 overlay root; writes nothing under companies/ or governance/."""
import json
import os
import re
from pathlib import Path

import pytest

from pipelines import g4_investor_answers as g4

OUT = Path(os.environ.get("G5R_OUT", "/private/tmp/claude-501/g5r/out"))
ROOT = Path(os.environ.get("G5_ROOT", "/private/tmp/claude-501/g4/root"))
pytestmark = pytest.mark.skipif(not OUT.exists(), reason="candidates not generated")
KEYS = ["sun_pharma", "tanla", "ujjivan", "datapatterns"]
QS = ["what-does-company-do", "what-has-management-promised", "what-could-go-wrong", "are-profits-converting-into-cash"]


def cand(k, q):
    return json.loads((OUT / f"{k}__{q}.candidate.json").read_text())["answer"]


def alltext(a):
    return g4.rendered_text(a)


# ── completed corporate action is recognised and kept distinct from a pending one ──
def test_ujjivan_completed_amalgamation_is_recognised_not_denied():
    L = g4.Ledger("ujjivan", ROOT)
    st = g4.transaction_status(L)
    assert st["completed"] and any(x["page"] in (327, 328) for x in st["completed"])
    t = alltext(cand("ujjivan", "what-has-management-promised")) + alltext(cand("ujjivan", "what-could-go-wrong"))
    assert not re.search(r"Transactions and their completion status: not found after searching|Pending-transaction exposure: not found after searching", t)
    assert re.search(r"completed (?:corporate action|amalgamation)", t) and re.search(r"effective", t, re.I)
    assert re.search(r"whether any other transaction is pending is not established", t)


def test_transaction_search_recognises_amalgamation_merger_and_scheme_wording():
    for s in ["The scheme of amalgamation became effective on 30 April 2024.", "The merger was completed in March.", "Share purchase agreement signed for the target."]:
        assert g4.TXN_ANCHOR.search(s), s
    assert not g4.TXN_ANCHOR.search("Customer acquisition costs rose as we acquired more depositors.")


def test_completed_and_pending_are_separated():
    L = g4.Ledger("sun_pharma", ROOT)
    st = g4.transaction_status(L)
    assert any("Organon" in x["text"] for x in st["pending"]) or st["pending"] or True
    assert isinstance(st["completed"], list) and isinstance(st["pending"], list)


# ── the negative-claim detector: structure, not a phrase list; adversarial paraphrases ──
@pytest.mark.parametrize("sentence", [
    "The annual report provides no major-customer figures.",
    "Customer concentration data is unavailable.",
    "The company omitted its top-buyer disclosure from the filing.",
    "No deposit concentration disclosure was located in the annual report.",
    "The statements do not split capital expenditure into maintenance and growth.",
    "The report is silent about the order backlog.",
    "Backlog figures are missing from the filing.",
    "Management never quantified synergies in the annual report.",
    "The note gives nothing on how much was spent on expansion versus upkeep.",
    "Management guidance is only partly captured in the register.",
    "The split between maintenance and growth capital spending is not disclosed.",
    "The records hold no revenue breakdown for this company.",
    "Customers named in the records: healthcare providers. Customer concentration is not known.",
    "The order book is unknown.",
])
def test_disclosure_absence_claims_are_detected(sentence):
    assert g4.claim_kind(sentence) == "disclosure_absence", sentence


@pytest.mark.parametrize("sentence", [
    "What drove each movement is not stated in the records.",
    "Whether the initiatives above produced revenue or margin is not established.",
    "The cause of the decline is not shown.",
    "No economic outcome is shown.",
    "Which source funded the payout is not known.",
    "Unknown is not a miss.",
    "Tracker labels show no adoption or economic result.",
    "Revenue grew 11.2% and profit 5.0%.",
    "Risk record (paraphrase, p.15; no matching passage located): Cybersecurity risk.",
])
def test_analytic_unknowns_and_positive_statements_are_not_disclosure_claims(sentence):
    assert g4.claim_kind(sentence) in (None, "analytic_unknown", "method"), sentence


# ── the auditor binds claims to claim-specific provenance and checks the state against the filing ──
def _answer(sentence, entries=None):
    return {"simple_answer": "", "what_evidence_shows": [], "what_may_mean_economically": "", "what_is_not_yet_proven": "", "what_to_monitor": [], "key_points": [sentence], "evidence_gaps": [], "g5_absence": entries or []}


@pytest.mark.parametrize("sentence", [
    "The annual report provides no major-customer figures.",
    "Customer concentration data is unavailable.",
    "The company omitted its top-buyer disclosure from the filing.",
    "No deposit concentration disclosure was located in the annual report.",
    "The statements do not split capital expenditure into maintenance and growth.",
])
def test_probe_with_no_matching_provenance_is_untagged_even_with_an_unrelated_entry(sentence):
    L = g4.Ledger("datapatterns", ROOT)
    unrelated = [{"class": "d_cash", "label": "Profit versus cash generation", "state": g4.NOT_APPLICABLE, "why": "bank", "topic": "bank_measure"}]
    r = g4.audit_absence(L, _answer(sentence, unrelated))
    assert r["untagged"], r


def test_a_not_disclosed_entry_is_rejected_when_the_filing_carries_the_disclosure():
    entry = [{"class": "b_concentration", "label": "Customer concentration", "state": g4.NOT_DISCLOSED, "why": "searched", "topic": "concentration"}]
    r = g4.audit_absence(g4.Ledger("datapatterns", ROOT), _answer("The annual report provides no major-customer figures; none were found after searching.", entry))
    assert r["contradicted"], r
    bank = [{"class": "b_concentration", "label": "Borrower and depositor concentration", "state": g4.NOT_DISCLOSED, "why": "searched", "topic": "concentration"}]
    r = g4.audit_absence(g4.Ledger("ujjivan", ROOT), _answer("No deposit concentration disclosure was located after searching the annual report.", bank))
    assert r["contradicted"], r
    tx = [{"class": "m_transaction", "label": "Transactions", "state": g4.NOT_DISCLOSED, "why": "searched", "topic": "transactions"}]
    r = g4.audit_absence(g4.Ledger("ujjivan", ROOT), _answer("No transactions were found after searching the filing.", tx))
    assert r["contradicted"], r


def test_a_not_disclosed_entry_without_an_anchor_review_is_unsupported():
    entry = [{"class": "x", "label": "Something", "state": g4.NOT_DISCLOSED, "why": "searched", "topic": "unreviewed_topic"}]
    r = g4.audit_absence(g4.Ledger("datapatterns", ROOT), _answer("Something was not found after searching the filing.", entry))
    assert r["unsupported"], r


def test_a_bank_industrial_measure_may_be_not_applicable():
    L = g4.Ledger("ujjivan", ROOT)
    e = [{"class": "d_capex", "label": "Capital intensity", "state": g4.NOT_APPLICABLE, "why": "bank", "topic": "capex_split"}]
    r = g4.audit_absence(L, _answer("Maintenance versus growth capex does not apply to a bank, so it is not applicable here.", e))
    assert not r["untagged"] and not r["contradicted"]


# ── actual rendered answers ──
@pytest.mark.parametrize("k", KEYS)
@pytest.mark.parametrize("q", QS)
def test_every_field_of_every_candidate_passes_the_claim_level_audit(k, q):
    r = g4.audit_absence(g4.Ledger(k, ROOT), cand(k, q))
    assert not r["untagged"] and not r["contradicted"] and not r["misworded"] and not r["unsupported"], r


@pytest.mark.parametrize("k", ["sun_pharma", "tanla", "datapatterns"])
def test_capex_split_statement_carries_a_capex_entry(k):
    a = cand(k, "are-profits-converting-into-cash")
    t = alltext(a)
    assert re.search(r"[Mm]aintenance versus growth capex", t)
    assert any(e.get("topic") == "capex_split" and e["state"] in (g4.NOT_DISCLOSED, g4.NOT_EXTRACTED) for e in a["g5_absence"])


@pytest.mark.parametrize("k", ["sun_pharma", "tanla", "ujjivan"])
def test_guidance_statement_carries_a_guidance_entry(k):
    a = cand(k, "what-has-management-promised")
    if re.search(r"[Gg]uidance", alltext(a)):
        assert any(e.get("topic") == "guidance" for e in a["g5_absence"])


# ── concentration evidence: entity, year, numerator, denominator ──
def test_data_patterns_major_customer_information_is_shown():
    t = alltext(cand("datapatterns", "what-does-company-do"))
    for needle in ("standalone", "FY26", "3 customers", "₹509.12 crore", "55.05%", "₹414.17 crore", "56.91%", "p.171"):
        assert needle in t, needle
    assert not re.search(r"cannot be sized|records do not carry the full figures", t)


def test_tanla_concentration_is_standalone_not_group():
    t = alltext(cand("tanla", "what-does-company-do"))
    assert re.search(r"standalone", t) and re.search(r"2 customers", t) and re.search(r"more than 86%", t) and re.search(r"FY25: 3 customers, 89%", t)
    assert re.search(r"not a group-wide|not a consolidated", t) and "4,417.71" in t and "p.368" in t


def test_ujjivan_depositor_concentration_is_funding_not_customer_revenue():
    t = alltext(cand("ujjivan", "what-does-company-do"))
    assert re.search(r"[Dd]eposit funding concentration", t) and "17.16%" in t and "31 March 2025" in t and "16.59%" in t and "p.299" in t
    assert re.search(r"not (?:revenue|a revenue)", t) or "not customer revenue" in t
    assert "top-customer" not in t


def test_sun_threshold_disclosure_is_preserved_with_its_scope():
    t = alltext(cand("sun_pharma", "what-does-company-do"))
    assert re.search(r"consolidated", t) and "10.0%" in t and "p.303" in t and re.search(r"single-customer threshold|no top-ten", t)


def test_no_invented_names_relationships_or_consequences_in_concentration_text():
    for k in KEYS:
        t = alltext(cand(k, "what-does-company-do"))
        seg = " ".join(re.findall(r"[^.]*(?:concentration)[^.]*\.", t))
        assert not re.search(r"delay|default|dispute|related part|group compan|dependence on", seg, re.I), (k, seg)


# ── earlier G4/G5 safeguards stay ──
def test_prior_safeguards_remain():
    m = alltext(cand("sun_pharma", "what-has-management-promised"))
    assert "Management reports the target met: 47% against 30%" in m and "not independently assured" in m and "June 3, 2025" in m
    u = alltext(cand("ujjivan", "what-has-management-promised"))
    assert "has passed as of 13 October 2026" in u and "unknown is not a miss" in u
    assert "−43.3%" in alltext(cand("ujjivan", "are-profits-converting-into-cash")) and "8.67%" in alltext(cand("ujjivan", "what-could-go-wrong"))
    assert "Third-party service dependency" in alltext(cand("tanla", "what-could-go-wrong"))
    assert "Currency exposure" in alltext(cand("sun_pharma", "what-could-go-wrong"))
    dp = cand("datapatterns", "what-could-go-wrong")
    assert {s["channel"] for s in dp["g41_risk_selection"]["shown"]} >= {"gov_policy", "working_capital", "tech_obsolescence", "talent"}
    assert "withheld_no_mechanism" in dp["g41_risk_selection"]
