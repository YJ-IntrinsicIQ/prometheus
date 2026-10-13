"""M63/G4.1 acceptance tests, written red-first against the four blockers of the independent G4 audit.
They read the generated candidate JSON (G41_OUT, default /private/tmp/claude-501/g5/out) and the risk registry flags; nothing here touches companies/."""
import json
import os
import re
from pathlib import Path

import pytest

OUT = Path(os.environ.get("G41_OUT", "/private/tmp/claude-501/g5/out"))
ROOT = Path(os.environ.get("G41_ROOT", "/private/tmp/claude-501/g4/root"))
pytestmark = pytest.mark.skipif(not OUT.exists(), reason="candidates not generated")
FIELDS = ["simple_answer", "what_evidence_shows", "what_may_mean_economically", "what_is_not_yet_proven", "what_to_monitor", "key_points", "evidence_gaps"]


def cand(key, qid):
    return json.loads((OUT / f"{key}__{qid}.candidate.json").read_text())["answer"]


def text(a):
    out = []
    for f in FIELDS:
        v = a.get(f)
        out += [v] if isinstance(v, str) else [str(x) for x in (v or [])]
    return "\n".join(out)


def risk_text(key):
    return text(cand(key, "what-could-go-wrong"))


# ── blocker A: quarantined / unsupported macro risk, relevance ──
def test_tanla_food_price_macro_risk_is_not_a_company_risk():
    t = risk_text("tanla").lower()
    assert not re.search(r"food|commodity|input cost", t)


def test_tanla_material_platform_risks_are_restored():
    t = risk_text("tanla").lower()
    for pat in (r"cyber|security", r"carrier|revenue-share", r"scal|platform", r"international"):
        assert re.search(pat, t), pat


@pytest.mark.parametrize("key", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_no_quarantined_or_demoted_risk_is_displayed_as_a_company_risk(key):
    reg = json.loads((ROOT / "companies" / key / "company_memory/risks/risk_registry.json").read_text())["risks"]
    a = cand(key, "what-could-go-wrong")
    shown = text(a).lower()
    restored = set(a["g41_risk_selection"].get("restored_after_review", []))
    for r in reg:
        sq = r.get("semantic_quality") or {}
        if (sq.get("eligibility") == "quarantined" or sq.get("relevance_outcome") in ("DEMOTE", "QUARANTINE")) and r["risk_name"] not in restored:
            mech = str(r["risk_mechanism"]).lower()[:60]
            assert mech not in shown, (r["risk_name"], mech)
    assert not any(re.search(r"food|talent pipeline|customer satisfaction", n, re.I) for n in restored), restored


# ── blocker D: generic category lens must not invent a mechanism ──
def test_sun_quality_risk_is_not_technology_obsolescence_and_access_is_not_order_book():
    t = risk_text("sun_pharma").lower()
    assert not re.search(r"obsolescen|keeping its technology ahead|order[- ]book|order-book conversion", t)


def test_ujjivan_has_no_invented_regional_concentration():
    t = risk_text("ujjivan").lower()
    assert not re.search(r"regional (shock|downturn)|regions that dominate", t)


def test_data_patterns_product_concentration_is_not_buyer_concentration():
    t = risk_text("datapatterns").lower()
    assert not re.search(r"few buyers|loss or repricing of a major customer", t)


def test_tanla_carrier_dependence_is_not_buyer_concentration():
    assert not re.search(r"few buyers|major customer", risk_text("tanla").lower())


@pytest.mark.parametrize("key", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_every_displayed_risk_cites_its_own_source_year_and_page(key):
    a = cand(key, "what-could-go-wrong")
    shown = [e for e in a["what_evidence_shows"] if re.match(r"\d\. ", e) and re.search(r"\(FY\d\d", e) and re.search(r"p\.\d+", e)]
    assert len(shown) == len(a["g41_risk_selection"]["shown"]) and shown, "displayed risks carry their own FY and page"
    first = a["deterministic_precision_facts"][0] if a["deterministic_precision_facts"] else {}
    if first and "Risk" in str(first.get("metric", "")):
        assert str(first.get("metric", "")).lower()[:20] in text(a).lower()


# ── blocker C: metric identity and period ──
def test_data_patterns_receivable_days_keep_their_own_period():
    t = risk_text("datapatterns")
    assert re.search(r"261\.3", t)
    for m in re.finditer(r"233\.8|233\.75", t):
        assert re.search(r"FY23", t[max(0, m.start() - 80): m.end() + 80]), t[max(0, m.start() - 80): m.end() + 80]
    assert not re.search(r"receivable days 233\b", t)
    assert re.search(r"average of opening and closing trade receivables", t, re.I)


@pytest.mark.parametrize("key", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_registry_embedded_figures_are_not_republished_without_their_year(key):
    reg = json.loads((ROOT / "companies" / key / "company_memory/risks/risk_registry.json").read_text())["risks"]
    shown = risk_text(key)
    for r in reg:
        m = re.search(r"receivable days (\d+)", str(r["risk_mechanism"]))
        if m:
            for x in re.finditer(rf"\b{m.group(1)}\b", shown):
                assert re.search(r"FY\d\d", shown[max(0, x.start() - 90): x.end() + 90]), (key, m.group(1))


def test_bank_has_no_receivable_days_or_industrial_working_capital_claim():
    t = risk_text("ujjivan").lower() + text(cand("ujjivan", "are-profits-converting-into-cash")).lower()
    assert not re.search(r"receivable days|free cash flow of|working-capital intensity", t.replace("industrial free-cash-flow", ""))


# ── blocker B: management memory ──
def test_sun_management_restores_sourced_progress_and_does_not_misdefine_unable_to_verify():
    t = text(cand("sun_pharma", "what-has-management-promised"))
    for pat in (r"\b47%", r"24\.69", r"21\.85", r"16\.7", r"Nidlegy", r"Philogen"):
        assert re.search(pat, t), pat
    assert not re.search(r"no later delivery evidence was found", t, re.I)
    assert re.search(r"linked in the register", t, re.I)
    assert not re.search(r"59\.9", t) or re.search(r"disposal|denominator", t, re.I)


def test_sun_nidlegy_dates_conflict_is_kept_and_no_approval_claim():
    t = text(cand("sun_pharma", "what-has-management-promised"))
    assert re.search(r"June 2024", t) and re.search(r"June 3, 2025|3 June 2025", t)
    assert not re.search(r"Nidlegy[^.]*\bapproved\b", t, re.I)


@pytest.mark.parametrize("key", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_outlooks_and_observations_are_not_called_hard_commitments(key):
    reg = json.loads((ROOT / "companies" / key / "company_memory/management_commitments/management_commitments.json").read_text())["commitments"]
    bullets = cand(key, "what-has-management-promised")["what_evidence_shows"]
    for c in reg:
        if c["commitment_class"] in ("OUTLOOK_NOT_COMMITMENT", "OBSERVATION", "NOT_TRACKABLE", "VERIFIABLE_UNDATED", "DATED_UNVERIFIABLE"):
            head = c["original_statement"][:40]
            for b in bullets:
                if head in b:
                    assert "— hard commitment" not in b, (key, head)


@pytest.mark.parametrize("key", ["tanla", "ujjivan", "datapatterns"])
def test_named_material_intentions_are_retained_with_their_class(key):
    t = text(cand(key, "what-has-management-promised"))
    assert re.search(r"intention|stated plan|outlook", t, re.I)
    assert len(re.findall(r"“[^”]{20,}”", t)) >= 2, "named statements are quoted, not only counted"


# ── P1: discovery judgment ──
def test_data_patterns_discovery_leads_with_the_amounts_and_does_not_infer_unsustainability():
    a = cand("datapatterns", "are-profits-converting-into-cash")
    t = text(a)
    assert re.search(r"44\.23", t) and re.search(r"8\.09", t) and re.search(r"36\.14", t)
    assert t.index("44.23") < t.find("547") if "547" in t else True
    assert re.search(r"136\.18|receivable", t, re.I)
    assert not re.search(r"unsustainable|cannot sustain", t, re.I) or re.search(r"not (?:proven|established|shown)", t, re.I)


@pytest.mark.parametrize("key", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_discovery_answers_name_the_next_question_and_do_not_claim_self_funded_growth(key):
    t = text(cand(key, "are-profits-converting-into-cash"))
    assert re.search(r"investigate|next question|what would change", t, re.I)
    assert not re.search(r"signals self-funded growth", t)


def test_no_clipped_prose_fragments():
    for key in ("sun_pharma", "tanla", "ujjivan", "datapatterns"):
        for q in ("what-does-company-do", "what-could-go-wrong", "what-has-management-promised", "are-profits-converting-into-cash"):
            t = text(cand(key, q))
            assert not re.search(r"\b(?:v|by s|geographic)\.?\s*$", t, re.M), (key, q)
            assert not re.search(r"\s[a-z]\.\s*$", t, re.M), (key, q)


# ── shared-function and source-identity tests ──
from pipelines import g4_investor_answers as g4  # noqa: E402

KEYS = ["sun_pharma", "tanla", "ujjivan", "datapatterns"]


def test_clean_clip_never_ends_in_a_fragment_or_open_bracket():
    t = "Creates value through R&D, manufacturing and quality investments (including test automation and SDLC integr..."
    out = g4.clean_clip(t)
    assert out.count("(") == out.count(")") and not out.endswith(("...", "…"))
    assert not re.search(r"\b(?:for|the|of|and|to)$", g4.clean_clip("Plan to maintain market leadership and high brand equity in India for the", 60))


def test_fix_brackets_keeps_list_enumerators_and_drops_dangling_brackets():
    assert "(Scope 1 and Scope 2)" in g4.fix_brackets("b) Reduction in emissions (Scope 1 and Scope 2) by 21.85% c) Co-processed")
    assert g4.fix_brackets("emissions (Scope 1 and") == "emissions"


@pytest.mark.parametrize("text,bank,expected", [
    ("Operational and quality system shortcomings while scaling global operations", False, "quality_reg"),
    ("Reliance on multi-carrier revenue-share arrangements which could be affected by carrier negotiations", False, "carrier_terms"),
    ("Third-party service disruption / structural dependency on non-substitutable ecosystem partners", False, "partner"),
    ("Assumption that incremental operational costs are near-zero at scale may not hold", False, "scalability"),
    ("Year-on-year price erosion in the US generics market", False, "pricing"),
    ("Borrower over-indebtedness reducing repayment capacity", True, "credit"),
    ("Heavy reliance on government contracts for revenue", False, "gov_policy"),
])
def test_channel_follows_the_filing_wording_not_a_category_label(text, bank, expected):
    assert g4.classify(text, bank)["id"] == expected


def test_industrial_channels_never_apply_to_a_bank_and_unknown_wording_gets_no_mechanism():
    assert g4.classify("Supply chain disruptions that could interrupt product availability", True) is None
    assert g4.classify("Something the filing does not explain", False) is None


def test_date_conflict_reports_both_dates_without_choosing():
    q = [{"fy": "fy25", "page": 10, "quote": "In June 2024 the agency validated the submission"}, {"fy": "fy25", "page": 35, "quote": "has validated the submission, finalised on June 3, 2025"}]
    msg = g4.date_conflict(q)
    assert "June 2024" in msg and "June 3, 2025" in msg and "not reconciled" in msg
    assert g4.date_conflict(q[:1]) == ""


def test_cash_flow_driver_unit_is_recovered_from_the_registry_and_fails_closed():
    from pathlib import Path
    L = g4.Ledger("datapatterns", Path(ROOT))
    assert abs(L.facts["cfd:receivables@fy26"].num + 136.18) < 0.01
    assert abs(L.facts["cfd:taxes@fy25"].num + 70.55) < 0.01 and L.facts["cfd:taxes@fy26"].page == 134
    S = g4.Ledger("sun_pharma", Path(ROOT))      # statement in ₹ million: converted to crore by matching the operating-cash-flow row
    assert abs(S.facts["cfd:taxes@fy26"].num + 2313.94) < 0.01
    B = g4.Ledger("ujjivan", Path(ROOT))
    assert not [i for i in B.facts if i.startswith("cfd:")]


def test_payout_gap_is_the_difference_of_the_two_reported_amounts():
    from pathlib import Path
    L = g4.Ledger("datapatterns", Path(ROOT))
    assert round(L.facts["dividends_paid@fy26"].num - L.facts["fcf@fy26"].num, 2) == 36.14


def test_sun_tax_payment_movement_is_reported_against_the_operating_cash_flow_change():
    t = text(cand("sun_pharma", "are-profits-converting-into-cash"))
    assert re.search(r"income taxes paid −₹476\.84 → −₹2,314", t) and re.search(r"about 111% of the −₹1,653 crore change", t)


# ── source identity ──
def _norm(x):
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x08\x0b-\x1f•]", " ", x)).strip()


@pytest.mark.parametrize("key", KEYS)
def test_receivable_day_figures_match_the_ratio_files_year_by_year(key):
    t = risk_text(key) + text(cand(key, "are-profits-converting-into-cash"))
    m = re.search(r"Average receivable days[^:]*: ([^.]*(?:\.\d)?(?:, FY\d\d \d+\.\d)*)", t)
    if not m:
        pytest.skip("no series shown for this company")
    for fy, val in re.findall(r"FY(\d\d) (\d+\.\d)", m.group(0)):
        r = json.loads((ROOT / "companies" / key / f"fy{fy}" / "financials" / "financial_ratios.json").read_text())["ratios"]["receivable_days"]["value"]
        assert abs(r - float(val)) < 0.06, (key, fy, r, val)


@pytest.mark.parametrize("key", KEYS)
def test_every_management_progress_quote_is_verbatim_on_its_cited_page(key):
    a = cand(key, "what-has-management-promised")
    for fp, quotes in a.get("g41_progress", {}).items():
        for q in quotes:
            chunks = json.loads((ROOT / "companies" / key / q["fy"] / "extracted" / "clean_chunks.json").read_text())["chunks"]
            body = _norm(q["quote"]).strip("…").strip()
            assert any(c["page"] == q["page"] and body in _norm(c["text"]) for c in chunks), (key, q)


def test_missing_receivable_series_for_a_year_is_not_filled_in():
    t = risk_text("tanla") + text(cand("tanla", "are-profits-converting-into-cash"))
    assert "Average receivable days" not in t or "FY26" not in re.search(r"Average receivable days[^.]*\.", t).group(0)


# ── G4 final correction: deadlines, achievement, restored risks, attribution, boilerplate, Ujjivan comparative ──
import datetime as _dt  # noqa: E402


def test_deadline_dates_follow_the_indian_fiscal_calendar():
    assert g4.deadline_date("by FY 2025-26") == _dt.date(2026, 3, 31)
    assert g4.deadline_date("By 2025") == _dt.date(2025, 12, 31)
    assert g4.deadline_date("H1CY24") == _dt.date(2024, 6, 30)
    assert g4.deadline_date("H1 2024") == _dt.date(2024, 6, 30)
    assert g4.deadline_date("over next couple of years") is None


def test_sun_hazardous_waste_target_is_reported_as_met_with_limits_and_no_59_9():
    t = text(cand("sun_pharma", "what-has-management-promised"))
    assert re.search(r"Management reports the target met: 47% against 30% in FY25 \(p\.103\)", t)
    assert re.search(r"not independently assured", t) and not re.search(r"59\.9", t)
    assert not re.search(r"do not by themselves show it was met", t)
    assert re.search(r"16\.7", t) and re.search(r"is after the assessment date", t)          # the 2030 emissions deadline is still ahead
    assert re.search(r"21\.85", t) and re.search(r"24\.69", t) and re.search(r"Philogen", t)


def test_ujjivan_rac_deadline_has_passed_and_the_outcome_is_unknown_not_missed():
    t = text(cand("ujjivan", "what-has-management-promised"))
    assert re.search(r"deadline \(31 March 2026\) has passed as of 13 October 2026", t)
    assert re.search(r"Delivery outcome unknown: the latest annual report held \(FY25, year to 31 March 2025\) predates the deadline; unknown is not a miss", t)
    assert not re.search(r"not yet reached|ahead of its deadline|is not yet reached", t)
    assert not re.search(r"\bmissed\b[^.]*RAC|RACs?[^.]*\bmissed\b", t.replace("completed, partly completed or missed", ""))


def test_the_assessment_date_is_explicit_and_changes_the_reading(monkeypatch):
    from pathlib import Path
    L = g4.Ledger("ujjivan", Path(ROOT))
    c = next(c for c in L._commitments if c["commitment_class"] == "HARD_COMMITMENT")
    monkeypatch.setattr(g4, "AS_OF", _dt.date(2025, 9, 1))
    assert "is after the assessment date (1 September 2025)" in g4.commitment_block(L, c)[0]
    monkeypatch.setattr(g4, "AS_OF", _dt.date(2026, 10, 13))
    assert "has passed as of 13 October 2026" in g4.commitment_block(L, c)[0]


def test_tanla_critical_third_party_service_risk_is_restored_but_food_prices_are_not():
    a = cand("tanla", "what-could-go-wrong")
    t = text(a)
    assert re.search(r"Third-party service dependency \(FY26, severity critical, restored after source review\)", t)
    assert re.search(r"non-substitutable ecosystem partners", t) and re.search(r"escalation protocols", t)
    assert re.search(r"Carrier commercial terms", t) and re.search(r"scalab", t, re.I) and re.search(r"Cyber", t) and re.search(r"international", t, re.I)
    assert not re.search(r"food|commodity", t, re.I)
    assert "Inflation Commodity Price Risk" not in a["g41_risk_selection"]["restored_after_review"]
    assert re.search(r"realised disruption", t)       # actual disruption remains unestablished


def test_sun_foreign_exchange_exposure_is_restored_with_bounds():
    a = cand("sun_pharma", "what-could-go-wrong")
    t = text(a)
    assert re.search(r"Currency exposure \(FY26, severity medium, restored after source review\)", t)
    assert re.search(r"International revenue share is not the same as net currency exposure", t)
    assert re.search(r"hedging", t) and not re.search(r"worsen|deteriorat", t.split("Currency exposure")[1].split("3.")[0] if "Currency exposure" in t else "")


def _pdf_words(key, fy, page):
    import glob
    import pymupdf
    fs = [f for f in glob.glob(str(Path(__file__).resolve().parents[2] / f"data/Processed/{key}/{fy}/annual_report/*.pdf")) if "afr" not in f]
    if not fs:
        pytest.skip("original PDF not available")
    doc = pymupdf.open(max(fs, key=lambda f: pymupdf.open(f).page_count))
    return set(re.findall(r"[a-z0-9]+", doc[page - 1].get_text().lower()))


@pytest.mark.parametrize("key", KEYS)
def test_every_primary_quote_is_on_its_cited_pdf_page_and_paraphrases_are_never_quoted(key):
    a = cand(key, "what-could-go-wrong")
    t = text(a)
    for s_ in a["g41_risk_selection"]["shown"]:
        fy = s_["fy"] if s_["fy"] in ("fy25", "fy26") else json.loads((ROOT / "companies" / key / "company_memory/risks/risk_registry.json").read_text()) and s_["fy"]
        if s_["attribution"] == "PRIMARY_QUOTE":
            words = re.findall(r"[a-z0-9]+", s_["passage"].lower().replace("…", " "))
            page_words = _pdf_words(key, "fy26" if key != "ujjivan" else "fy25", s_["passage_page"])
            assert sum(w in page_words for w in words) >= 0.95 * len(words), (key, s_["passage_page"], s_["passage"])
            assert f"“{s_['passage']}”" in t
        if s_["paraphrase"]:
            assert f"“{s_['paraphrase']}”" not in t, "a record paraphrase must never appear in quotation marks"
        assert s_["attribution"] in ("PRIMARY_QUOTE", "SOURCE_PARAPHRASE")


def test_tanla_near_zero_cost_claim_is_attributed_to_its_real_page_as_analyst_inference():
    t = text(cand("tanla", "what-could-go-wrong"))
    assert re.search(r"source passage p\.62: “[^”]*near-zero incremental operational cost", t)
    assert re.search(r"Risk record \(paraphrase, p\.185\): Assumption that incremental operational costs are near-zero", t)
    assert "Analyst inference (conditional)" in t


def test_sun_quality_risk_is_a_paraphrase_beside_the_real_passage_not_a_quotation():
    t = text(cand("sun_pharma", "what-could-go-wrong"))
    assert "“Operational and quality system shortcomings" not in t
    assert re.search(r"Risk record \(paraphrase, p\.15\): Operational and quality system shortcomings", t)


@pytest.mark.parametrize("key", KEYS)
def test_management_answers_have_no_shared_boilerplate_and_no_contradictory_status_advice(key):
    t = text(cand(key, "what-has-management-promised"))
    assert not re.search(r"commissioned facility|in-progress or partly delivered|reach a verified completion.*delivered", t)
    if key != "sun_pharma":
        assert not re.search(r"regulatory validation|regulatory step|commercial return", t, re.I)
    if re.search(r"is marked delivered", t):          # G5: the adoption / economic-result caveat is stated once in the explanation, not after every item
        assert "show no adoption, commercial use or economic result" in t
        assert "Adoption, commercial use and economic results are not established" not in t


def test_ujjivan_profit_decline_uses_the_statements_own_comparative_basis():
    for q in ("what-does-company-do", "are-profits-converting-into-cash"):
        t = text(cand("ujjivan", q))
        assert re.search(r"1,281\.49", t) and re.search(r"726\.10", t) and re.search(r"−43\.3%", t) and re.search(r"p\.258", t)
        assert not re.search(r"different or unstated bases|indicative", t)


# ── surgical correction: an opportunity to build an indigenous alternative is not evidence of dependence on foreign technology ──
def test_scarce_domestic_alternatives_do_not_become_foreign_dependence():
    assert g4.classify("Limited availability of domestic alternatives in key technology areas", False) is None
    assert g4.classify("We are developing indigenous solutions in areas where domestic alternatives are limited", False) is None
    assert g4.classify("Strategic dependence on non-indigenous technology for key subsystems", False)["id"] == "import_dependence"


def test_a_risk_whose_wording_supports_no_channel_is_withheld_not_shown_with_a_filler():
    a = cand("datapatterns", "what-could-go-wrong")
    assert all(s["channel"] for s in a["g41_risk_selection"]["shown"])


def test_data_patterns_has_no_foreign_dependence_or_export_control_inference_and_keeps_its_other_risks():
    a = cand("datapatterns", "what-could-go-wrong")
    t = text(a)
    assert not re.search(r"foreign-sourced|non-domestic|export-control|imported|import share|foreign technology", t, re.I)
    chans = {s["channel"] for s in a["g41_risk_selection"]["shown"]}
    assert {"gov_policy", "working_capital", "talent", "tech_obsolescence"} <= chans
    assert not re.search(r"customer concentration|few buyers|major customer", t, re.I) or re.search(r"not (?:established|sized|quantified)", t)
    assert re.search(r"FY23 233\.8", t) and re.search(r"FY26 261\.3", t) and re.search(r"inventory days.*FY26 353\.2", t)
    assert len(chans) >= 4          # no filler is added to keep a fixed count
