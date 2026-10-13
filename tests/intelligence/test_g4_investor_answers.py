"""M63/G4 tests: the candidate generator's omission/absence detector, derivation audit and the generated candidates.
Candidate checks read /private/tmp/claude-501/g4/out (skipped when absent); nothing here touches companies/ or the approval registry."""
import json
import os
import re
from pathlib import Path

import pytest

from pipelines import g4_investor_answers as g4

OUT = Path(os.environ.get("G41_OUT", "/private/tmp/claude-501/g5/out"))
CANDS = sorted(OUT.glob("*.candidate.json")) if OUT.exists() else []
pytestmark_cands = pytest.mark.skipif(not CANDS, reason="G4 candidates not generated")


def load(p):
    return json.loads(p.read_text())["answer"]


def text_of(p):
    return g4.answer_text(load(p))


def test_money_keeps_sign_and_scale():
    assert g4.money(-12.5) == "−₹12.5 crore"
    assert g4.money(1234.4) == "₹1,234 crore"


def test_derivable_explains_ratio_and_rejects_unrelated():
    assert g4.derivable(30.0, [30.0 * 10, 100.0 * 10, 7.0]) is not None  # a share of two recorded figures
    assert g4.derivable(41.37, [100.0, 7.0, 3.0]) is None


@pytestmark_cands
def test_candidate_has_no_confident_absence_on_gap_and_no_omitted_available_class():
    res = json.loads((OUT / "g4_results.json").read_text())["answers"]
    assert len(res) == 16
    for r in res:
        new = r["new"]["score"]
        assert not new["absence_claims_on_gaps"], (r["company"], r["question_id"], new["absence_claims_on_gaps"])
        # supporting financial lines (balance sheet, cash conversion) yield to source-grounded risks inside the 600-word cap in G4-final
        assert not [x for x in new["omitted"] if x not in ("r_cash", "r_balance")], (r["company"], r["question_id"], new["omitted"])


@pytest.mark.parametrize("p", [p for p in CANDS if p.stem.startswith("ujjivan")], ids=lambda p: p.stem)
def test_bank_candidates_use_no_industrial_free_cash_flow_or_working_capital(p):
    metrics = " ".join(str(f.get("metric", "")) for f in load(p).get("deterministic_precision_facts", [])).lower()
    assert not re.search(r"free cash flow|working capital", metrics), "industrial cash fact on a bank"


@pytest.mark.parametrize("p", [p for p in CANDS if "datapatterns__what-does" in p.stem], ids=lambda p: p.stem)
def test_unextracted_order_book_is_labelled_not_asserted_absent(p):
    t = text_of(p)
    assert re.search(r"order book.*(do not carry|not sized)", t, re.I)
    assert not re.search(r"no order book|does not (?:have|disclose) an order book", t, re.I)


@pytest.mark.parametrize("p", [p for p in CANDS if "management-promised" in p.stem], ids=lambda p: p.stem)
def test_management_answer_does_not_promote_outlook_or_observation(p):
    t = text_of(p).lower()
    assert not re.search(r"management (?:has )?promised that (?:the )?(?:industry|market)", t)


@pytest.mark.parametrize("p", [p for p in CANDS if p.stem.startswith("sun_pharma__what-has")], ids=lambda p: p.stem)
def test_signed_transaction_is_not_described_as_completed(p):
    t = text_of(p)
    if "Organon" in t:
        assert re.search(r"signed|agreement", t, re.I) and not re.search(r"completed the (?:acquisition|purchase) of Organon", t, re.I)


def test_scoring_flags_absence_claim_on_extracted_gap(monkeypatch):
    L = type("L", (), {})()
    monkeypatch.setattr(g4, "CLASSES", [g4.Cls("x", "A", "mix", lambda L: [], "any", "f", lambda L: True, None, ("segment",), None)])
    monkeypatch.setattr(g4, "class_status", lambda L, c: {"status": g4.NOT_EXTRACTED, "facts": [], "why": ""})
    r = g4.score_answer(L, "A", {"simple_answer": "The records do not show segment revenue."})
    assert r["absence_claims_on_gaps"] == ["x"]  # NOT_EXTRACTED: any absence wording is an unsupported claim
    r = g4.score_answer(L, "A", {"simple_answer": "Segment figures exist in the filing but are not carried here."})
    assert r["absence_claims_on_gaps"] == []
