#!/usr/bin/env python3
"""
M59.2 — final investor trust gate over the M59.1 candidates. Zero AI calls. Idempotent.

Applies the small, evidence-backed corrections found when the candidates were checked against the original annual reports,
excludes the candidates whose central claim the filings contradict, recomputes digests and fingerprints, and writes the single
final authorization manifest. It never touches the approval registry or the served-answers files.

    python3 pipelines/m59_2_trust_gate.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipelines import m59_question_batch as m  # noqa: E402
from pipelines.answer_certification import compute_content_fingerprint as fingerprint, compute_full_artifact_digest as digest  # noqa: E402

CAND = "companies/{c}/company_memory/ask_intrinsiciq/m59_candidate_answers.json"
PAIRS = ROOT / "preview" / "M59_pairs.json"
PRIOR = ROOT / "preview" / "M59_2_FINAL_AUTHORIZATION_MANIFEST.json"   # frozen record of the M59.2 decision
MANIFEST = ROOT / "preview" / "M59_3_FINAL_AUTHORIZATION_MANIFEST.json"
M591 = ROOT / "preview" / "M59_1_AUTHORIZATION_MANIFEST.json"

# ── exclusions: the filings contradict (or the record cannot support) the central claim ──
GAPS = "claims disclosures are missing that the annual reports contain (management remuneration, ESOP terms, segment and inventory/payables data, and for Tanla a reported ROCE of 24.2%); the gap is in Prometheus's records, not in the company's disclosure"
EXCLUDE: dict[tuple[str | None, str], str] = {
    (None, "which-disclosure-is-missing"): GAPS,
    (None, "what-should-i-ask-ir"): "its questions are built from the same record gaps (remuneration, ROCE, reporting basis, inventory) that the annual reports actually disclose",
    ("sun_pharma", "what-incentives-matter"): "says remuneration, performance conditions and share-option terms are 'not available'; the FY26 annual report contains the remuneration policy and ESOP disclosures",
    ("ujjivan", "what-is-management-commentary-saying"): "evidence includes an extraction artefact ('not detailed in the provided text') and a four-year-old FY21 ratio presented as a current theme; low investor value",
}

# ── corrections: (company or None, question or None, old, new, regex?) ──
S = "Direction labels (worsening, improving, recurring) classify the wording of each year's risk disclosures; they are not measured changes."
CORR: list[tuple[str | None, str | None, str, str, bool]] = [
    (None, None, "Inventory and payable days are missing for some years, so a continuous cash conversion cycle cannot be built.", "A cash conversion cycle is not built here.", False),
    ("sun_pharma", None, "inventory and payable days are not available for the same year, so a full cash conversion cycle cannot be computed.", "a full cash conversion cycle is not built here.", False),
    (None, "what-is-the-return-on-capex", " Return on capital employed is not available in the records.", "", False),
    (None, "what-is-the-return-on-capex", "no output, utilisation or site-level revenue is disclosed.", "no output, utilisation or site-level revenue is given in the project records.", False),
    (None, "what-is-the-return-on-capex", "project costs and outputs are not given, and", "project costs and outputs are not given in the project records, and", False),
    (None, "what-projects-are-underway", "Cost, output, utilisation and returns are not disclosed for the operational projects,", "Cost, output, utilisation and returns are not given in the project records for the operational projects,", False),
    ("ujjivan", "how-is-capacity-changing", "Utilisation, throughput and incremental revenue are not disclosed.", "Utilisation, throughput and incremental revenue are not given in the capacity records.", False),
    ("datapatterns", None, "The reporting basis (consolidated or standalone) of the FY26 figures is not stated in the records.", "Data Patterns has no subsidiaries and publishes standalone financial statements only (FY26 annual report), so these figures are on a standalone basis.", False),
    (None, "what-regulatory-risks-remain-active", r"\d+ of these \d+ themes? (?:has|have) a recorded management response\.", "The risk records capture no management response for these themes.", True),
    ("sun_pharma", "what-regulatory-risks-remain-active", "Regulatory: recurring, disclosed FY20–FY26.", "Regulatory: recurring, disclosed FY20–FY26; the FY26 entry concerns environmental compliance (waste, water use and disposal).", False),
    ("tanla", "what-regulatory-risks-remain-active", "regulatory (currently worsening)", "regulatory (the risk record classifies it as worsening)", False),
    ("tanla", "what-regulatory-risks-remain-active", "Regulatory: currently worsening, disclosed FY20–FY26.", "Regulatory: disclosed FY20–FY26 and classified in the risk record as worsening; the FY26 entry concerns data-protection and consent rules (DPDPA, TRAI TCCCPR), which the FY26 annual report discusses.", False),
    ("ujjivan", "what-regulatory-risks-remain-active", "regulatory (currently worsening)", "regulatory (the risk record classifies it as worsening)", False),
    ("ujjivan", "what-regulatory-risks-remain-active", "Regulatory: currently worsening, disclosed FY21–FY25.", "Regulatory: disclosed FY21–FY25 and classified in the risk record as worsening; the FY25 entry concerns stronger regulatory oversight and microfinance lending guardrails, which the record links to higher delinquencies (FY25 annual report).", False),
    ("datapatterns", "what-regulatory-risks-remain-active", "regulatory (improving)", "regulatory (the risk record classifies it as improving)", False),
    ("datapatterns", "what-regulatory-risks-remain-active", "Regulatory: improving, disclosed FY22–FY26.", "Regulatory: disclosed FY22–FY26; the FY25 and FY26 annual reports list changes in regulation, export controls or compliance requirements among the threats in the same terms, so the 'improving' label in the risk record is not a measured change.", False),
    ("sun_pharma", "what-is-the-return-on-capex", "Capital expenditure in FY26: ₹3,609 crore (cash-flow statement); earlier years are not part of this figure.", "Capital expenditure in FY26: ₹3,609 crore, being payments for property, plant and equipment including capital work-in-progress and intangible assets (FY26 annual report cash-flow statement, PDF p.246), against ₹2,129 crore in FY25; earlier years are not part of this figure.", False),
    ("sun_pharma", "what-needs-management-clarification", "The filing date and approval status behind 'File Nidlegy™ with EMA for melanoma'.", "The filing date and approval status behind 'File Nidlegy™ with EMA for melanoma' (a partner product; the partner, Philogen, reported an updated application resubmitted to the EMA on 27 July 2026, after the FY26 report).", False),
]
DROP_ITEMS = {("ujjivan", "what-was-delivered-last-3-years"): "Liability products and funding sources expansion"}  # cited page does not contain it
EXTRA_APPEND = {"what-regulatory-risks-remain-active": ("what_is_not_yet_proven", S)}
REPLACE_FIELDS = {
    ("ujjivan", "who-are-the-customers"): {
        "simple_answer": "Ujjivan Small Finance Bank lends to mass-market retail borrowers and to MSME and small-business borrowers, who pay it interest and fees, and it takes retail deposits to fund that lending; the end users of its credit are underserved retail and micro-banking customers and self-employed and small-business customers.",
        "what_evidence_shows": ["Paying customers (borrowers): mass-market retail borrowers; MSME and small-business borrowers.", "Funding customers: retail depositors, who fund the lending rather than pay for a product.", "End users of credit: underserved retail and micro-banking customers; self-employed and small-business customers."],
        "what_is_not_yet_proven": "The records do not say how much revenue comes from any one borrower group (mass-market retail or MSME and small business) or from named customers.",
    },
}


# ── M59.3 commitment integrity ──
# "Hard commitment" is reserved for a statement with BOTH a checkable target (a number, a named milestone, or a measured improvement) AND an explicit deadline.
# Verified against the registry and the annual reports: Sun Pharma 3 (co-processing 30% by 2025, Nidlegy EMA filing H1 2024, Scope 1+2 -35% by 2030),
# Tanla 1 (MC-0019 satisfaction score by 2025), Ujjivan 1 (MC-0043: 9 more retail asset centres by FY 2025-26) plus 1 dated but unquantified (MC-0025),
# Data Patterns 0. The register's "verifiable" tier (Tanla 3, Ujjivan 8, Data Patterns 2) includes statements with no deadline.
TANLA_NOTE = "the FY25 annual report says the company remains on track to improve its employee satisfaction score by 2025; the FY26 annual report gives an overall employee engagement score at 80.6%, against 73.2% in the previous two years (a related measure; the satisfaction score itself is not reported)"
UJ_MSE = "FY22 and FY23 annual reports describe MSE lending products (term loan, overdraft, cash credit) and MSME asset centres being launched, but do not say whether this meets the commitment"
UJ_RAC = "the FY25 report cites 16 retail asset centres for the housing business and 23 for the whole bank (18 in FY24), so progress towards the 9 additional centres cannot be measured on one basis, and the FY26 report is not in the records"


def _a(simple, ev, econ, unp, mon, facts):
    return m.mk_answer(simple, ev, econ, unp, mon, [m.dpf(*x) for x in facts])


ECON_TYPES = "Intent gives direction but cannot be checked; a target with a deadline can be checked later. A ledger dominated by intents gives investors little to hold management to."
UNP_TYPES = "The classification comes from the wording of each statement and may not match management's own categorisation. It says nothing about whether any statement was or will be delivered."
ECON_OVERDUE = "A passed deadline without direct confirmation is a question for management, not a finding of failure; a related measure moving the right way is encouraging but is not the committed measure."
ECON_MISSED = "Calling a commitment missed needs positive evidence that it was not met after its deadline. Missing disclosure is a gap to ask about, not evidence of failure."
ECON_CLAIMS = "A claim that comes true shows management can do what it says; whether it created value is a separate question that the records do not answer."
OVERRIDES: dict[tuple[str, str], object] = {
    ("tanla", "what-promise-types-dominate"): lambda: _a("Most of Tanla's 27 tracked management statements are stated strategic intents (22). Only 1 carries both an explicit target and a deadline: improving the employee satisfaction score by 2025.",
        ["27 statements tracked: 22 strategic intents; 3 that the register treats as verifiable; 1 strategic direction; 1 governance policy declaration.", "Of the 3 verifiable statements, 1 has a target and a deadline (employee satisfaction score by 2025); the other 2 (a profitability and cash-flow focus, and customer-relationship expansion) state no deadline and no measurable level.", "The statement counts follow the approved 'What has management promised?' answer; 'hard commitment' is used here only for a statement with both a target and a deadline."],
        ECON_TYPES, UNP_TYPES, ["Whether statements with a measurable target and a deadline appear in the next annual report."],
        [("Statements tracked", 27, "FY20–latest", "count"), ("Statements with an explicit target and deadline", 1, "FY20–latest", "count")]),
    ("ujjivan", "what-promise-types-dominate"): lambda: _a("Most of Ujjivan Small Finance Bank's 51 tracked management statements are stated strategic intents (43). Only 1 carries both an explicit numeric target and a deadline: establishing 9 more retail asset centres by FY 2025-26.",
        ["51 statements tracked: 43 strategic intents; 8 that the register treats as verifiable.", "Of the 8 verifiable statements, 1 has a numeric target and a deadline (9 more retail asset centres by FY 2025-26); 1 has a deadline but no measurable target (launch more relevant MSE products, FY 2022-23); 6 state no deadline (NRI acquisition, a mobile app, fintech and API banking, insurance distribution).", "The statement counts follow the approved 'What has management promised?' answer; 'hard commitment' is used here only for a statement with both a target and a deadline."],
        ECON_TYPES, UNP_TYPES, ["Whether statements with a measurable target and a deadline appear in the next annual report."],
        [("Statements tracked", 51, "FY20–latest", "count"), ("Statements with an explicit target and deadline", 1, "FY20–latest", "count")]),
    ("datapatterns", "what-promise-types-dominate"): lambda: _a("Most of Data Patterns' 16 tracked management statements are stated strategic intents (13). None carries both an explicit target and a deadline.",
        ["16 statements tracked: 13 strategic intents; 2 that the register treats as verifiable; 1 strategic direction.", "The 2 verifiable statements are a pit-stop readiness review ahead of the next growth phase (FY24, no deadline) and offering complete mission-critical systems under one roof (FY25, described as ongoing); neither states a measurable level or a deadline.", "The statement counts follow the approved 'What has management promised?' answer."],
        ECON_TYPES, UNP_TYPES, ["Whether statements with a measurable target and a deadline appear in the next annual report."],
        [("Statements tracked", 16, "FY22–latest", "count"), ("Statements with an explicit target and deadline", 0, "FY22–latest", "count")]),
    ("tanla", "which-promises-are-overdue"): lambda: _a(f"One of Tanla's tracked commitments has both a stated target and a deadline (improve the employee satisfaction score by 2025) and that deadline has passed, but it cannot be called overdue or missed: {TANLA_NOTE}.",
        ["Employee satisfaction score improvement (made FY25, deadline 2025): the FY25 annual report says the company remains on track.", "FY26 annual report: overall employee engagement score 80.6%, against 73.2% in the previous two years; this is a related measure, and the satisfaction score is not given.", "The other 2 tracked commitments (a profitability and cash-flow focus, and customer-relationship expansion) state no deadline, so they cannot have passed one."],
        ECON_OVERDUE, "Whether the satisfaction score itself improved by 2025 is not reported; the engagement score is a different measure. An unverified status is not a missed commitment.", ["Whether the next annual report states the employee satisfaction score against its baseline."],
        [("Commitments with a target and deadline", 1, "FY20–latest", "count"), ("Of which past deadline", 1, "FY26", "count")]),
    ("tanla", "what-was-missed"): lambda: _a("Nothing in the records or the filings shows that any Tanla commitment was missed. The one commitment with a target and a deadline (employee satisfaction score by 2025) is unconfirmed rather than missed, and the nearest reported measure, employee engagement, rose to 80.6% in FY26 from 73.2%.",
        ["1 commitment with a target and a deadline; the deadline has passed without a direct confirmation, and the related engagement score improved.", "The other 2 tracked commitments state no deadline, so none can be judged missed."],
        ECON_MISSED, "A later report that discloses the satisfaction score could confirm or contradict delivery. The records hold no evidence of non-delivery.", ["Whether the satisfaction score is disclosed against its baseline."],
        [("Commitments with a target and deadline", 1, "FY20–latest", "count"), ("Confirmed missed", 0, "FY26", "count")]),
    ("tanla", "did-past-claims-come-true"): lambda: _a("Not established. Tanla's only commitment with a target and a deadline is to improve its employee satisfaction score by 2025; the FY26 report shows a related engagement score at 80.6% (73.2% before), which points the right way but is not the committed measure. Its other 2 tracked commitments state no deadline or measurable level, so they cannot be tested.",
        ["Employee satisfaction score by 2025 (made FY25): on track per the FY25 report; FY26 engagement score 80.6% against 73.2%; satisfaction score not reported.", "Profitability and cash-flow focus (made FY22) and customer-relationship expansion (made FY24): statements of focus without a deadline or measurable level."],
        ECON_CLAIMS, "Delivery of a commitment without a directly comparable later figure is unresolved, not failed. A related measure improving is not an economic result.", ["Disclosure of the satisfaction score, and of any measurable target management attaches to its stated priorities."],
        [("Commitments with a target and deadline", 1, "FY20–latest", "count"), ("Economic outcomes confirmed", 0, "FY20–latest", "count")]),
    ("ujjivan", "which-promises-are-overdue"): lambda: _a(f"Two of Ujjivan Small Finance Bank's tracked commitments state a deadline and both deadlines have passed, but neither can be called overdue or missed. (1) Launch more relevant MSE products by FY 2022-23: the {UJ_MSE}. (2) Establish 9 more retail asset centres by FY 2025-26: {UJ_RAC}.",
        ["MSE products commitment (made FY22, deadline FY 2022-23): no measurable target; the FY22 and FY23 reports describe MSE product and asset-centre launches without saying whether they fulfil it.", "Retail asset centres (made FY25, 9 more by FY 2025-26): the FY25 report cites 16 for housing and 23 for the whole bank; the FY26 report is not in the records.", "The other 6 tracked commitments (NRI acquisition, a mobile app, fintech and API banking, insurance distribution) state no deadline, so they cannot have passed one."],
        ECON_OVERDUE, "Whether each passed deadline was met is not established where no later report states it. An unverified status is not a missed commitment.", ["The FY26 annual report's retail asset centre count on the same basis as the plan, and a statement on MSE product delivery."],
        [("Commitments with a stated deadline", 2, "FY20–latest", "count"), ("Of which past deadline", 2, "FY26", "count")]),
    ("ujjivan", "what-was-missed"): lambda: _a("Nothing in the records or the filings shows that any Ujjivan commitment was missed. Two commitments state a deadline and both deadlines have passed (MSE products by FY 2022-23; 9 more retail asset centres by FY 2025-26); both are unconfirmed rather than missed.",
        ["8 tracked verifiable commitments; 2 state a deadline, both passed without a direct confirmation; none has positive evidence of non-delivery.", "The other 6 state no deadline, so none can be judged missed."],
        ECON_MISSED, "Later reports, including the FY26 report that is not in the records, may confirm delivery or non-delivery. The records hold no evidence either way.", ["Delivery statements for the two dated commitments in the next annual report."],
        [("Commitments with a stated deadline", 2, "FY20–latest", "count"), ("Confirmed missed", 0, "FY26", "count")]),
    ("ujjivan", "did-past-claims-come-true"): lambda: _a(f"Not established. Of Ujjivan Small Finance Bank's 8 tracked commitments only 1 has a numeric target and a deadline (9 more retail asset centres by FY 2025-26), and {UJ_RAC}. One more has a deadline without a measurable target (MSE products, FY 2022-23), and the other 6 state no deadline.",
        ["Retail asset centres (made FY25): 16 housing centres at the time, 9 more planned by FY 2025-26; FY25 year-end count across the bank was 23 (18 in FY24).", "MSE products (made FY22, deadline FY 2022-23): MSE launches are described in the FY22 and FY23 reports; fulfilment of the commitment is not stated.", "NRI acquisition, a mobile app, fintech and API banking, and insurance distribution (made FY21–FY24): statements of plan without a deadline."],
        ECON_CLAIMS, "Delivery of a commitment without a directly comparable later figure is unresolved, not failed. Reported activity is not an economic result.", ["Retail asset centre counts on one basis in the next report, and delivery statements for the dated commitments."],
        [("Commitments with a target and deadline", 1, "FY20–latest", "count"), ("Economic outcomes confirmed", 0, "FY20–latest", "count")]),
    ("ujjivan", "what-needs-management-clarification"): lambda: _a("Management most needs to clarify, for Ujjivan Small Finance Bank: (1) Whether the FY 2022-23 commitment to launch more relevant MSE products was met, and which products count towards it. (2) How many retail asset centres were planned by FY 2025-26 on a bank-wide basis (the FY25 report cites 16 for housing and 23 for the bank), and whether the 9 additional centres were established. (3) How the FY24 merger affects year-on-year comparisons of reported figures.",
        ["1. Whether the FY 2022-23 commitment to launch more relevant MSE products was met, and which products count towards it.", "2. How many retail asset centres were planned by FY 2025-26 on a bank-wide basis (the FY25 report cites 16 for housing and 23 for the bank), and whether the 9 additional centres were established.", "3. How the FY24 merger affects year-on-year comparisons of reported figures."],
        "Each point is where management's own disclosures are ambiguous or stop short of a conclusion; a clear answer would let investors resolve it instead of holding it open.", "The points come from gaps and apparent inconsistencies in what has been disclosed; management may have explained some elsewhere. They are not allegations.", ["Whether the next annual report or earnings call addresses these points."], []),
    ("datapatterns", "which-promises-are-overdue"): lambda: _a("No Data Patterns commitment can be overdue: neither of its 2 tracked verifiable commitments states a deadline (one is described as ongoing) or a measurable target.",
        ["Pit-stop readiness review to enable the next growth phase (made FY24): no deadline.", "Offer complete, mission-critical systems under one roof (made FY25): described as ongoing; no measurable target."],
        "When management states no measurable targets or deadlines, investors have nothing to hold it to; that is itself informative about how much of its direction can be tested.", "A commitment with no deadline cannot be late, but it also cannot be confirmed as delivered. Silence on timing is not evidence that nothing was done.", ["Whether management attaches measurable targets and dates to its growth plans in the next annual report."],
        [("Commitments with a target and deadline", 0, "FY22–latest", "count")]),
    ("datapatterns", "what-was-missed"): lambda: _a("No Data Patterns commitment can be shown to have been missed: neither of its 2 tracked verifiable commitments states a deadline or a measurable target.",
        ["2 tracked verifiable commitments; neither has a deadline or a measurable target against which a miss could be judged."],
        ECON_MISSED, "Without a stated target and date, delivery or non-delivery cannot be established from the records.", ["Measurable targets and dates in the next annual report."],
        [("Commitments with a target and deadline", 0, "FY22–latest", "count"), ("Confirmed missed", 0, "FY26", "count")]),
    ("datapatterns", "did-past-claims-come-true"): lambda: _a("Not testable. Data Patterns' 2 tracked verifiable commitments (a readiness review ahead of the next growth phase, and offering complete mission-critical systems under one roof) state no measurable target or deadline, so the records cannot show whether they came true.",
        ["Pit-stop readiness review (made FY24): no deadline and no measurable outcome stated.", "Complete mission-critical systems under one roof (made FY25): described as ongoing; no measurable outcome stated."],
        ECON_CLAIMS, "Delivery cannot be established for a commitment with no measurable target. This is a limit of what management committed to, not evidence of non-delivery.", ["Measurable targets and dates in the next annual report."],
        [("Commitments with a target and deadline", 0, "FY22–latest", "count")]),
}
OVERRIDE_ALLOW = {80.6, 73.2, 9.0, 16.0, 18.0, 23.0, 25.0, 51.0, 43.0, 8.0, 6.0, 27.0, 22.0, 13.0, 3.0, 2.0, 1.0, 0.0}
CORR += [
    ("tanla", "what-remains-unresolved", "Delivery of all 3 hard commitments is unconfirmed", "Delivery of the one commitment with a target and a deadline (employee satisfaction score by 2025) is unconfirmed", False),
    ("ujjivan", "what-remains-unresolved", "Delivery of all 8 hard commitments is unconfirmed", "Delivery of the two commitments with stated deadlines (MSE products by FY 2022-23; 9 more retail asset centres by FY 2025-26) is unconfirmed", False),
]

ARTEFACTS = re.compile(r"provided text|the provided|the excerpt|in the text\b|stored records|progression records|register records", re.I)

SRC = {  # source-verification status by question type
    "fig": "VERIFIED — every ₹ and % figure traced to the annual reports; derived values recomputed from them",
    "sun_commit": "VERIFIED — commitment wording, targets and progress checked in the FY24–FY26 annual reports (hazardous waste 28.34% / 47% / 5,157 of 8,609 tonnes; Scope 1+2 21.85% / 24.69% / 16.7%; Nidlegy EMA validation June 2024)",
    "commit_strict": "VERIFIED — commitment wording and deadlines checked in the register and the annual reports (FY22–FY26); 'hard' reserved for a target plus a deadline; FY26 engagement figures read directly from the filing",
    "other_commit": "PARTIAL — commitment text spot-checked in the annual reports; the 'hard commitment' classification is inherited from the approved promises answers and is not independently re-derived",
    "projects": "SAMPLED — status citations checked against the cited annual-report pages (33 of 34 matched; the one that did not was removed)",
    "business": "VERIFIED — business description and product terms found in the latest annual report; customer grouping is a company-model inference",
    "risk": "PARTIAL — risk wording found in the latest annual report; direction labels are classifications of disclosure wording and cannot be verified as measured trends",
    "capital": "RECORD-BASED — capital-allocation ledger and projects registry; transaction types not re-extracted from the filings (Sun capex amount verified)",
    "derived": "DERIVED — built from approved answers and records already in force",
    "commentary": "SAMPLED — quoted themes are whole sentences from stored commentary; figures in them traced to the reports",
    "execution": "RECORD-BASED — counts from the management progression records and projects registry",
}
KIND = {
    "are-profits-converting-into-cash": "fig", "what-is-owner-earnings": "fig", "is-working-capital-a-concern": "fig", "are-per-share-economics-improving": "fig", "what-is-the-return-on-capex": "fig",
    "what-does-company-do": "business", "who-are-the-customers": "business", "how-does-it-make-money": "business",
    "what-promise-types-dominate": "commit", "which-promises-are-overdue": "commit", "what-was-missed": "commit", "did-past-claims-come-true": "commit", "what-needs-management-clarification": "commit",
    "what-was-delivered-last-3-years": "projects", "what-projects-are-underway": "projects", "how-is-capacity-changing": "projects",
    "what-regulatory-risks-remain-active": "risk", "which-investments-created-value": "capital", "did-execution-lead-to-outcomes": "execution",
    "what-remains-unresolved": "derived", "what-is-management-commentary-saying": "commentary", "what-incentives-matter": "fig",
}
QUALITY = {
    "fig": "Answers directly with the company's own verified figures and states what cannot be concluded",
    "business": "Specific to the company's model; economics follow its revenue type (banking logic for Ujjivan)",
    "commit": "Separates reached, unconfirmed and missed; never treats missing evidence as failure",
    "projects": "Shows status and cites the filing page; says execution is not payoff",
    "risk": "States which themes are active and what is classification rather than measurement",
    "capital": "Payouts and repayments are not presented as value created",
    "execution": "Distinguishes absence of recorded outcomes from outcomes that did not occur",
    "derived": "Agenda of open points taken from approved answers",
    "commentary": "Management's own account, labelled as such; no implied delivery",
}
LIMITS = {
    "sun_pharma": "Consolidated basis. Capex is payments for PP&E incl. CWIP and intangibles (not split into maintenance vs growth).",
    "datapatterns": "Standalone only (no subsidiaries in FY26). Commitments carry no stated deadline; 'hard commitment' wording is inherited from the approved promises answer.",
    "tanla": "Commitment classification inherited from the approved promises answer (only one of three carries a stated target and deadline).",
    "ujjivan": "Bank: industrial working-capital and cash-conversion measures do not apply. Commitment classification inherited from the approved promises answer; pre-FY24 figures not comparable (merger).",
}


def walk(o, fn):
    if isinstance(o, str):
        return fn(o)
    if isinstance(o, list):
        return [walk(x, fn) for x in o]
    if isinstance(o, dict):
        return {k: (v if k == "deterministic_precision_facts" else walk(v, fn)) for k, v in o.items()}
    return o


def excluded(c: str, q: str) -> str | None:
    return EXCLUDE.get((c, q)) or EXCLUDE.get((None, q))


def correct(c: str, q: str, a: dict) -> tuple[dict, list[str]]:
    log: list[str] = []
    b = json.loads(json.dumps(a))
    for co, qq, old, new, rx in CORR:
        if (co and co != c) or (qq and qq != q):
            continue
        changed = [0]

        def f(s: str, old=old, new=new, rx=rx, changed=changed) -> str:
            t = re.sub(old, new, s) if rx else s.replace(old, new)
            changed[0] += t != s
            return t
        b = walk(b, f)
        if changed[0]:
            log.append(f"replaced: {old[:70]!r}")
    if q in EXTRA_APPEND and EXTRA_APPEND[q][1] not in b[EXTRA_APPEND[q][0]]:
        fld, txt = EXTRA_APPEND[q]
        b[fld] = b[fld].rstrip() + " " + txt
        log.append("appended direction-label caveat")
    if (c, q) in DROP_ITEMS:
        w = DROP_ITEMS[(c, q)]
        for fld in ("what_evidence_shows", "key_points"):
            n = len(b[fld]); b[fld] = [x for x in b[fld] if w not in x]
            if len(b[fld]) != n:
                log.append(f"removed unsupported {fld} item: {w}")
    for fld, val in REPLACE_FIELDS.get((c, q), {}).items():
        if b[fld] != val:
            b[fld] = val; log.append(f"rewrote {fld}")
    if (c, q) in REPLACE_FIELDS:
        b["key_points"] = list(b["what_evidence_shows"])[:4]
    return b, log


# ── M59.3: replacement candidates for the approved answers whose headline overstates "hard commitment" ──
# The approved answers use the governed taxonomy label (HARD_COMMITMENT = VERIFIABLE_COMMITMENT) but describe it to the reader as
# "specific target and deadline". They are NOT edited. A replacement is prepared per answer, validated, and left for separate reapproval.
REPL_TAIL = {
    "tanla": " Only one of these, the employee satisfaction target by 2025, carries both a measurable target and a deadline; the other two are statements of focus with no deadline.",
    "ujjivan": " Only one of these, establishing 9 more retail asset centres by FY 2025-26, carries both a numeric target and a deadline; one more (MSE products, FY 2022-23) has a deadline without a measurable target and six state no deadline.",
    "datapatterns": " Neither states a deadline or a measurable target.",
}
REPL_RULES = [
    ("(specific targets, milestones or deadlines)", "(statements the register treats as checkable; none states a deadline)"),
    ("verifiable commitments (specific targets/milestones)", "verifiable commitments (checkable statements)"),
    ("(verifiable targets or milestones)", "(checkable statements, none with a stated deadline)"),
    ("HARD_COMMITMENT (VERIFIABLE_COMMITMENT)", "VERIFIABLE_COMMITMENT (register tier)"),
    ("Hard commitment", "Verifiable commitment"), ("hard commitment", "verifiable commitment"),
]
REPL_QUESTIONS = ("what-has-management-promised", "what-did-management-actually-deliver")


def _deep(o, fn):
    if isinstance(o, str):
        return fn(o)
    if isinstance(o, list):
        return [_deep(x, fn) for x in o]
    if isinstance(o, dict):
        return {k: _deep(v, fn) for k, v in o.items()}
    return o


def build_replacements(registry: dict, cos: dict) -> list[dict]:
    import copy
    from pipelines import pacp_adversarial as pa
    out = []
    for c in ("tanla", "ujjivan", "datapatterns"):
        doc = {"schema_version": "m59_3_replacements_v1", "company_slug": c, "mission": "M59.3", "ai_calls": 0,
               "note": "REPLACEMENT CANDIDATES ONLY. Not served. They supersede approved answers and need separate, explicit reapproval; the existing approvals are untouched.", "answers": {}}
        for q in REPL_QUESTIONS:
            rec = registry[f"{c}:{q}"]
            cur = json.loads((ROOT / "companies" / c / "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json").read_text())["answers"][q]["answer"]
            assert digest(cur) == rec["full_artifact_digest"], f"{c}:{q} approved answer no longer matches the registry"

            def fx(t: str, c=c) -> str:
                for a, b in REPL_RULES:
                    t = t.replace(a, b if not (a.startswith("(specific") and c != "datapatterns") else "(statements the register treats as checkable; not all state a deadline)")
                return t
            new = _deep(copy.deepcopy(cur), fx)
            new["simple_answer"] = new["simple_answer"].rstrip() + REPL_TAIL[c]
            before = pa.run_adversarial_suite(cur, c, q)
            after = pa.run_adversarial_suite(new, c, q)
            ok = after["overall"] == before["overall"] or after["overall"] in ("PASS", "WARN")
            if not ok or after["fails"]:
                raise SystemExit(f"replacement {c}:{q} fails PACP: {after['fails']}")
            d, f = digest(new), fingerprint(new)
            doc["answers"][q] = {"question_id": q, "answer": new, "status": "PASS", "coverage": "COMPLETE", "word_count": m.words(new),
                                 "supersedes": {"full_artifact_digest": rec["full_artifact_digest"], "fingerprint": rec["fingerprint"]},
                                 "replacement": {"full_artifact_digest": d, "fingerprint": f, "pacp_before": before["overall"], "pacp_after": after["overall"], "pacp_fails": after["fails"]}}
            out.append({"company": c, "question_id": q, "approved_digest": rec["full_artifact_digest"], "replacement_digest": d, "replacement_fingerprint": f, "pacp": f"{before['overall']} -> {after['overall']}",
                        "why": "headline 'hard commitment(s)' (described as specific target and deadline) overstates what the register's verifiable tier contains"})
        (ROOT / "companies" / c / "company_memory/ask_intrinsiciq/m59_3_replacement_candidates.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    return out


def main() -> int:
    registry = json.loads((ROOT / "governance/approval_registry.json").read_text())["approvals"]
    reg_before = (ROOT / "governance/approval_registry.json").read_bytes()
    served_before = {c: (ROOT / "companies" / c / "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json").read_bytes() for c in m.COMPANIES}
    pairs_doc = json.loads(PAIRS.read_text())
    pairs = {(p["company"], p["question_id"]): p for p in pairs_doc["pairs"]}
    prev = json.loads(M591.read_text())
    ready_in = [(e["company"], e["question_id"]) for e in prev["pairs"]]
    prev_digest = {(e["company"], e["question_id"]): e["full_artifact_digest"] for e in prev["pairs"]}
    prior = {(e["company"], e["question_id"]): e["full_artifact_digest"] for e in json.loads(PRIOR.read_text())["pairs"]}
    cos = {k: m.Co(k, registry) for k in m.COMPANIES}
    out: list[dict] = []
    excl: list[dict] = []
    for c in m.COMPANIES:
        path = ROOT / CAND.format(c=c)
        doc = json.loads(path.read_text())
        ans = doc["answers"]
        for q in [q for (cc, q) in ready_in if cc == c]:
            p = pairs[(c, q)]
            override = OVERRIDES.get((c, q))
            if q not in ans and not override:  # already excluded by an earlier run of this script
                if p["status"] == "EXCLUDED_M592":
                    excl.append({"company": c, "question_id": q, "title": p["title"], "reason": p["m592_reason"]})
                continue
            why = None if override else excluded(c, q)
            if why:
                excl.append({"company": c, "question_id": q, "title": p["title"], "reason": why})
                doc.setdefault("m592_excluded", {})[q] = {"reason": why, "former_digest": ans[q]["candidate"]["full_artifact_digest"]}
                del ans[q]
                p["status"], p["m592_reason"] = "EXCLUDED_M592", why
                continue
            old_digest = prev_digest[(c, q)]
            if override:  # M59.3: rebuilt on the strict definition of a hard commitment
                new, log = override(), []
                entry = ans.setdefault(q, {"question_id": q, "status": "PASS", "coverage": "COMPLETE", "word_count": 0, "candidate": {"status": "READY", "path": p.get("path", "Correct")}})
                p["status"] = "READY"; p.pop("m592_reason", None)
                doc.get("m592_excluded", {}).pop(q, None)
            else:
                entry = ans[q]
                new, log = correct(c, q, entry["answer"])
            blob = json.dumps(new, ensure_ascii=False)
            log = (["commitment integrity: rebuilt on the strict definition (explicit target and deadline)"] if override else []) + [f"corrected: {nw[:90]}" for co, qq, _o, nw, rx in CORR if not rx and (not co or co == c) and (not qq or qq == q) and nw and nw in blob] + (["removed unsupported project line"] if (c, q) in DROP_ITEMS else []) + (["rewrote customer wording (depositors fund, borrowers pay)"] if (c, q) in REPLACE_FIELDS else []) + (["direction-label caveat and management-response wording"] if q in EXTRA_APPEND else [])
            # re-validate the corrected text with the same checks that gated it before
            nums = set(cos[c].numbers) | {2128.58, 2129.0} | (OVERRIDE_ALLOW if override else set())
            v = m.validate(new, cos[c], q, nums)
            art = ARTEFACTS.findall(json.dumps(new, ensure_ascii=False))
            if v["failed"] or art:
                raise SystemExit(f"{c}:{q} fails after correction: {v['failed']} {art}")
            d, f = digest(new), fingerprint(new)
            verdict = "CORRECTED" if d != old_digest else "APPROVE-READY"
            entry["answer"] = new
            entry["word_count"] = m.words(new)
            entry["candidate"].update({"m591_digest": old_digest, "fingerprint": f, "full_artifact_digest": d, "validation": {k: x["result"] for k, x in v["checks"].items()}, "pacp": v["pacp"], "m592_verdict": verdict, "m592_corrections": log})
            kind = KIND[q]
            src = SRC["commit_strict"] if override else SRC["sun_commit"] if kind == "commit" and c == "sun_pharma" else SRC["other_commit"] if kind == "commit" else SRC[kind]
            p.update({"answer": new["simple_answer"], "evidence": new["what_evidence_shows"], "economics": new["what_may_mean_economically"], "unproven": new["what_is_not_yet_proven"], "monitor": new["what_to_monitor"], "fingerprint": f, "full_artifact_digest": d, "validation": v["checks"], "pacp": v["pacp"]})
            if "entry" in p:
                p["entry"]["answer"] = new
            out.append({"company": c, "question_id": q, "family": p["family"], "title": p["title"], "verdict": verdict, "full_artifact_digest": d, "fingerprint": f, "m592_digest": prior.get((c, q)), "m593_status": "REINSTATED" if (c, q) not in prior else "CORRECTED" if prior[(c, q)] != d else "UNCHANGED", "source_verification": src, "investor_quality": QUALITY.get("commit" if kind == "commit" else kind, ""), "limitation": LIMITS[c], "corrections": log, "candidate_file": CAND.format(c=c)})
        doc["generated_note"] = "CANDIDATES ONLY. M59.3 final gate applied: excluded pairs removed; see preview/M59_3_FINAL_AUTHORIZATION_MANIFEST.json."
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    PAIRS.write_text(json.dumps(pairs_doc, indent=2, ensure_ascii=False))
    out.sort(key=lambda e: (e["company"], e["question_id"]))
    replacements = build_replacements(registry, cos)
    body = {"mission": "M59.3", "activated": False, "ai_calls": 0, "approved_unchanged": sorted(registry),
            "governance": {"approval_registry_sha256": hashlib.sha256(reg_before).hexdigest(), "sun_served_answers_sha256": hashlib.sha256(served_before["sun_pharma"]).hexdigest()},
            "counts": {"approve_ready": sum(e["verdict"] == "APPROVE-READY" for e in out), "corrected": sum(e["verdict"] == "CORRECTED" for e in out), "excluded": len(excl), "blocked": 0, "reviewed": len(ready_in), "m593_corrected": sum(e["m593_status"] == "CORRECTED" for e in out), "m593_reinstated": sum(e["m593_status"] == "REINSTATED" for e in out), "m593_unchanged": sum(e["m593_status"] == "UNCHANGED" for e in out)},
            "pairs": out, "excluded": sorted(excl, key=lambda e: (e["company"], e["question_id"])), "approved_answers_needing_separate_correction": replacements}
    body["pairs_sha256"] = hashlib.sha256(json.dumps([[e["company"], e["question_id"], e["full_artifact_digest"], e["fingerprint"]] for e in out]).encode()).hexdigest()
    MANIFEST.write_text(json.dumps(body, indent=2, ensure_ascii=False))
    assert (ROOT / "governance/approval_registry.json").read_bytes() == reg_before, "registry changed"
    for c in m.COMPANIES:
        assert (ROOT / "companies" / c / "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json").read_bytes() == served_before[c], "served answers changed"
    print(body["counts"], "manifest sha256", hashlib.sha256(MANIFEST.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
