from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from knowledge.financials.corporate_actions import extract_corporate_actions, write_corporate_actions


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _entry(
    field,
    *,
    value_crore=None,
    value_original="",
    unit_original="crores",
    basis="consolidated",
    artifact="normalized_source.json",
    confidence="high",
):
    return {
        "canonical_field": field,
        "value_crore": value_crore,
        "value_original": value_original,
        "unit_original": unit_original,
        "basis": basis,
        "period": "March 31, 2025",
        "source_line_item": field,
        "source_page": 1,
        "source_artifact": artifact,
        "confidence": confidence,
        "warnings": [],
    }


def _normalized_payload():
    payload = {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "preferred_basis": "consolidated",
        "profit_and_loss": {
            "eps_basic": _entry("eps_basic", value_original="10.00", unit_original="inr"),
            "eps_diluted": _entry("eps_diluted", value_original="9.80", unit_original="inr"),
        },
        "balance_sheet": {
            "equity_share_capital": _entry("equity_share_capital", value_crore=12.0, value_original="12.00"),
        },
        "cash_flow": {},
        "share_data": {
            "face_value": _entry("face_value", value_original="10", unit_original="inr"),
            "shares_outstanding": _entry("shares_outstanding", value_original="12000000", unit_original="shares"),
            "weighted_avg_shares": _entry("weighted_avg_shares", value_original="11800000", unit_original="shares"),
            "diluted_shares": _entry("diluted_shares", value_original="12100000", unit_original="shares"),
            "book_value_per_share": _entry("book_value_per_share", value_original="100.00", unit_original="inr"),
        },
        "corporate_actions": {
            "dividend": {
                "occurred": None,
                "ratio": "",
                "amount": {
                    "value_original": None,
                    "unit_original": "",
                    "value_crore": None,
                    "currency": "INR",
                    "source_year": "",
                    "source_page": None,
                    "source_artifact": "",
                    "confidence": "missing",
                    "notes": [],
                },
                "source_year": "",
                "source_page": None,
                "source_artifact": "",
                "confidence": "missing",
                "notes": [],
            },
            "bonus": {
                "occurred": None,
                "ratio": "",
                "amount": {
                    "value_original": None,
                    "unit_original": "",
                    "value_crore": None,
                    "currency": "INR",
                    "source_year": "",
                    "source_page": None,
                    "source_artifact": "",
                    "confidence": "missing",
                    "notes": [],
                },
                "source_year": "",
                "source_page": None,
                "source_artifact": "",
                "confidence": "missing",
                "notes": [],
            },
            "split": {
                "occurred": None,
                "ratio": "",
                "amount": {
                    "value_original": None,
                    "unit_original": "",
                    "value_crore": None,
                    "currency": "INR",
                    "source_year": "",
                    "source_page": None,
                    "source_artifact": "",
                    "confidence": "missing",
                    "notes": [],
                },
                "source_year": "",
                "source_page": None,
                "source_artifact": "",
                "confidence": "missing",
                "notes": [],
            },
            "buyback": {
                "occurred": None,
                "ratio": "",
                "amount": {
                    "value_original": None,
                    "unit_original": "",
                    "value_crore": None,
                    "currency": "INR",
                    "source_year": "",
                    "source_page": None,
                    "source_artifact": "",
                    "confidence": "missing",
                    "notes": [],
                },
                "source_year": "",
                "source_page": None,
                "source_artifact": "",
                "confidence": "missing",
                "notes": [],
            },
            "rights_issue": {
                "occurred": None,
                "ratio": "",
                "amount": {
                    "value_original": None,
                    "unit_original": "",
                    "value_crore": None,
                    "currency": "INR",
                    "source_year": "",
                    "source_page": None,
                    "source_artifact": "",
                    "confidence": "missing",
                    "notes": [],
                },
                "source_year": "",
                "source_page": None,
                "source_artifact": "",
                "confidence": "missing",
                "notes": [],
            },
            "qip": {
                "occurred": None,
                "ratio": "",
                "amount": {
                    "value_original": None,
                    "unit_original": "",
                    "value_crore": None,
                    "currency": "INR",
                    "source_year": "",
                    "source_page": None,
                    "source_artifact": "",
                    "confidence": "missing",
                    "notes": [],
                },
                "source_year": "",
                "source_page": None,
                "source_artifact": "",
                "confidence": "missing",
                "notes": [],
            },
            "preferential_issue": {
                "occurred": None,
                "ratio": "",
                "amount": {
                    "value_original": None,
                    "unit_original": "",
                    "value_crore": None,
                    "currency": "INR",
                    "source_year": "",
                    "source_page": None,
                    "source_artifact": "",
                    "confidence": "missing",
                    "notes": [],
                },
                "source_year": "",
                "source_page": None,
                "source_artifact": "",
                "confidence": "missing",
                "notes": [],
            },
            "merger": {
                "occurred": None,
                "ratio": "",
                "amount": {
                    "value_original": None,
                    "unit_original": "",
                    "value_crore": None,
                    "currency": "INR",
                    "source_year": "",
                    "source_page": None,
                    "source_artifact": "",
                    "confidence": "missing",
                    "notes": [],
                },
                "source_year": "",
                "source_page": None,
                "source_artifact": "",
                "confidence": "missing",
                "notes": [],
            },
            "demerger": {
                "occurred": None,
                "ratio": "",
                "amount": {
                    "value_original": None,
                    "unit_original": "",
                    "value_crore": None,
                    "currency": "INR",
                    "source_year": "",
                    "source_page": None,
                    "source_artifact": "",
                    "confidence": "missing",
                    "notes": [],
                },
                "source_year": "",
                "source_page": None,
                "source_artifact": "",
                "confidence": "missing",
                "notes": [],
            },
        },
        "shareholding_pattern": {},
        "basis_views": {},
        "unmapped_rows": [],
        "warnings": [],
        "limitations": [],
    }
    return payload


def _row(line_item_raw: str, value_raw: str, *, table_type: str, unit_hint: str = "inr", page: int = 1, confidence: str = "high"):
    return {
        "statement_type": table_type,
        "table_type": table_type,
        "basis": "consolidated",
        "line_item_raw": line_item_raw,
        "values": [
            {
                "period": "March 31, 2025",
                "value_raw": value_raw,
                "unit_hint": unit_hint,
                "currency_hint": "INR",
                "value_crore": None,
            }
        ],
        "source_artifact": "raw_financial_tables.json",
        "page": page,
        "chunk_id": f"{table_type}-{page}",
        "confidence": confidence,
        "warnings": [],
    }


def _raw_payload(rows_by_table):
    tables = {
        "profit_and_loss": [],
        "balance_sheet": [],
        "cash_flow": [],
        "share_capital": [],
        "reserves": [],
        "borrowings": [],
        "fixed_assets": [],
        "revenue": [],
        "tax": [],
        "eps": [],
        "dividend": [],
        "corporate_actions": [],
        "shareholding_pattern": [],
    }
    tables.update(rows_by_table)
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "source_documents": ["clean_chunks.json"],
        "tables": tables,
        "warnings": [],
        "limitations": [],
    }


def _extract_single(tmp_path: Path, rows_by_table, *, normalized_override=None):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    payload = _normalized_payload()
    if normalized_override:
        payload = normalized_override(payload)
    _write_json(normalized_path, payload)
    _write_json(raw_path, _raw_payload(rows_by_table))
    return extract_corporate_actions(
        company="acme",
        year="fy25",
        normalized_path=normalized_path,
        raw_tables_path=raw_path,
    )


def test_dividend_extraction(tmp_path):
    report = _extract_single(
        tmp_path,
        {"dividend": [_row("Final dividend paid", "35.00", table_type="dividend", unit_hint="crores")]},
    )
    dividend = next(item for item in report.actions if item.action_type in {"dividend", "final_dividend"})
    assert dividend.amount_crore == 35.0
    assert dividend.per_share_amount is None


def test_dividend_per_share_captured_separately(tmp_path):
    report = _extract_single(
        tmp_path,
        {"dividend": [_row("Final dividend per share", "3.50", table_type="dividend")]},
    )
    dividend = next(item for item in report.actions if item.action_type in {"dividend", "final_dividend"})
    assert dividend.per_share_amount == 3.5
    assert dividend.amount_crore is None


def test_bonus_issue_detection(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Bonus issue in the ratio of 1:1", "0", table_type="corporate_actions")]},
    )
    bonus = next(item for item in report.actions if item.action_type == "bonus_issue")
    assert bonus.ratio == "1:1"
    assert bonus.impact_on_eps_comparability == "yes"


def test_split_detection(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Stock split from Rs 10 to Rs 5", "0", table_type="corporate_actions")]},
    )
    split = next(item for item in report.actions if item.action_type == "stock_split")
    assert split.face_value_before == 10.0
    assert split.face_value_after == 5.0


def test_qip_dilution_detection(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("QIP issue proceeds", "250.00", table_type="corporate_actions", unit_hint="crores")]},
    )
    qip = next(item for item in report.actions if item.action_type == "qip")
    assert qip.impact_on_share_count == "unknown"
    assert qip.impact_on_eps_comparability == "unknown"
    assert qip.amount_raised_crore == 250.0
    assert qip.action_subtype == "qip_issue"
    assert "possible dilution, share count not captured" in qip.warnings


def test_qip_share_count_not_treated_as_amount_crore(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Issue of shares through QIP", "4097319", table_type="corporate_actions", unit_hint="shares")]},
    )
    qip = next(item for item in report.actions if item.action_type == "qip")
    assert qip.amount_crore is None
    assert qip.amount_raised_crore is None
    assert qip.shares_issued == 4097319.0
    assert qip.shares_after == 4097319.0
    assert qip.value_type_used == "share_count"


def test_qip_proceeds_utilization_maps_to_amount_utilised_not_amount_raised(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Utilisation of QIP proceeds", "120.00", table_type="corporate_actions", unit_hint="crores")]},
    )
    qip = next(item for item in report.actions if item.action_type == "qip")
    assert qip.action_subtype == "qip_proceeds_utilization"
    assert qip.amount_utilised_crore == 120.0
    assert qip.amount_raised_crore is None
    assert qip.impact_on_share_count == "none"
    assert qip.impact_on_eps_comparability == "no"


def test_absurd_qip_amount_is_nullified_with_warning(tmp_path):
    def _override(payload):
        payload["profit_and_loss"]["revenue"] = _entry("revenue", value_crore=100.0, value_original="100.00")
        payload["balance_sheet"]["net_worth"] = _entry("net_worth", value_crore=80.0, value_original="80.00")
        payload["balance_sheet"]["total_assets"] = _entry("total_assets", value_crore=200.0, value_original="200.00")
        return payload

    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("QIP issue proceeds", "5000.00", table_type="corporate_actions", unit_hint="crores")]},
        normalized_override=_override,
    )
    assert not any(item.action_type == "qip" for item in report.actions)
    assert any("suspicious relative to financial scale" in reason for reason in report.rejection_reasons)


def test_dividend_paid_from_cash_flow_remains_amount_crore(tmp_path):
    report = _extract_single(
        tmp_path,
        {"cash_flow": [_row("Dividend paid", "35.00", table_type="cash_flow", unit_hint="crores")]},
    )
    dividend = next(item for item in report.actions if item.action_type in {"dividend", "final_dividend", "interim_dividend"})
    assert dividend.amount_crore == 35.0
    assert dividend.per_share_amount is None


def test_buyback_detection(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Buyback of equity shares", "20.00", table_type="corporate_actions", unit_hint="crores")]},
    )
    buyback = next(item for item in report.actions if item.action_type == "buyback")
    assert buyback.impact_on_share_count == "decrease"


def test_face_value_change_warning(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Face value changed from Rs 10 to Rs 5", "0", table_type="corporate_actions")]},
    )
    assert "face value changed" in report.per_share_comparability_warnings


def test_weighted_average_shares_capture(tmp_path):
    report = _extract_single(
        tmp_path,
        {"eps": [_row("Weighted average shares", "11800000", table_type="eps", unit_hint="shares")]},
    )
    assert report.share_count_summary.weighted_avg_shares == 11800000.0


def test_diluted_shares_capture(tmp_path):
    report = _extract_single(
        tmp_path,
        {"eps": [_row("Diluted shares", "12100000", table_type="eps", unit_hint="shares")]},
    )
    diluted = next(item for item in report.actions if item.action_type == "diluted_shares")
    assert diluted.shares_after == 12100000.0


def test_eps_comparability_warning_when_share_count_missing(tmp_path):
    def _override(payload):
        payload["share_data"]["weighted_avg_shares"]["value_original"] = ""
        payload["share_data"]["diluted_shares"]["value_original"] = ""
        return payload

    report = _extract_single(
        tmp_path,
        {"eps": [_row("Earnings per share", "10.00", table_type="eps")]},
        normalized_override=_override,
    )
    assert "EPS exists but weighted average shares are missing" in report.per_share_comparability_warnings
    assert "diluted shares missing" in report.per_share_comparability_warnings


def test_write_corporate_actions(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    output_path = tmp_path / "corporate_actions.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(raw_path, _raw_payload({"dividend": [_row("Final dividend per share", "3.50", table_type="dividend")]}))

    report = write_corporate_actions(
        company="acme",
        year="fy25",
        normalized_path=normalized_path,
        raw_tables_path=raw_path,
        output_path=output_path,
    )
    assert output_path.exists()
    written = json.loads(output_path.read_text())
    assert written["company"] == report.company
    rejection_path = output_path.with_name("corporate_action_rejections.json")
    assert rejection_path.exists()
    assert json.loads(rejection_path.read_text(encoding="utf-8")) == []


def test_corporate_action_rejections_record_rejected_candidates(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    raw_path = tmp_path / "raw_financial_tables.json"
    output_path = tmp_path / "corporate_actions.json"
    payload = _normalized_payload()
    payload["profit_and_loss"]["revenue"] = _entry("revenue", value_crore=100.0, value_original="100.00")
    payload["balance_sheet"]["net_worth"] = _entry("net_worth", value_crore=80.0, value_original="80.00")
    payload["balance_sheet"]["total_assets"] = _entry("total_assets", value_crore=200.0, value_original="200.00")
    _write_json(normalized_path, payload)
    _write_json(
        raw_path,
        _raw_payload({"corporate_actions": [_row("QIP issue proceeds", "5000.00", table_type="corporate_actions", unit_hint="crores")]}),
    )

    write_corporate_actions(
        company="acme",
        year="fy25",
        normalized_path=normalized_path,
        raw_tables_path=raw_path,
        output_path=output_path,
    )

    rejection_payload = json.loads(output_path.with_name("corporate_action_rejections.json").read_text(encoding="utf-8"))
    assert rejection_payload
    assert rejection_payload[0]["attempted_action_type"] == "qip"
    assert rejection_payload[0]["raw_value"] == "5000.00"
    assert rejection_payload[0]["detected_value_type"] == "monetary"
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert not any(item["action_type"] == "qip" for item in written["actions"])


def test_rejected_qip_candidate_does_not_appear_as_active_action(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("QIP issue proceeds", "5000.00", table_type="corporate_actions", unit_hint="crores")]},
        normalized_override=lambda payload: {
            **payload,
            "profit_and_loss": {**payload["profit_and_loss"], "revenue": _entry("revenue", value_crore=100.0, value_original="100.00")},
            "balance_sheet": {
                **payload["balance_sheet"],
                "net_worth": _entry("net_worth", value_crore=80.0, value_original="80.00"),
                "total_assets": _entry("total_assets", value_crore=200.0, value_original="200.00"),
            },
        },
    )
    assert not any(item.action_type == "qip" for item in report.actions)


def test_qip_issue_without_share_count_uses_unknown_impact(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("QIP issue proceeds", "250.00", table_type="corporate_actions", unit_hint="crores")]},
    )
    qip = next(item for item in report.actions if item.action_type == "qip")
    assert qip.impact_on_share_count == "unknown"
    assert "possible dilution, share count not captured" in qip.warnings


def test_qip_proceeds_utilization_does_not_create_dilution_warning(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Utilisation of QIP proceeds", "120.00", table_type="corporate_actions", unit_hint="crores")]},
    )
    assert not any("qip may affect per-share comparability" == warning for warning in report.per_share_comparability_warnings)


def test_no_company_specific_behavior():
    text = Path("knowledge/financials/corporate_actions.py").read_text(encoding="utf-8").lower()
    assert "datapatterns" not in text
    assert "polymatech" not in text
    assert "tanla" not in text
    assert "tips" not in text


def test_authorized_share_capital_not_treated_as_issued_share_increase(tmp_path):
    report = _extract_single(
        tmp_path,
        {"share_capital": [_row("Authorised share capital", "50000000", table_type="share_capital", unit_hint="shares")]},
    )
    assert report.actions == []
    assert any("authorized share-capital" in reason.lower() for reason in report.rejection_reasons)


def test_face_value_not_mapped_from_fair_value_gain(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Fair value gain on financial assets", "10.00", table_type="corporate_actions", unit_hint="crores")]},
    )
    assert report.actions == []


def test_bonus_false_positive_rejected(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Bonus provision reserve", "10.00", table_type="corporate_actions", unit_hint="crores")]},
    )
    assert report.actions == []
    assert any("bonus_issue" in reason or "bonus issue" in reason.lower() for reason in report.rejection_reasons)


def test_rights_issue_false_positive_rejected(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Rights of lease assets", "10.00", table_type="corporate_actions", unit_hint="crores")]},
    )
    assert report.actions == []


def test_preferential_issue_false_positive_rejected(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Preferential tax adjustment", "10.00", table_type="corporate_actions", unit_hint="crores")]},
    )
    assert report.actions == []


def test_rejects_dividend_income_reference(tmp_path):
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Dividend income from subsidiary", "10.00", table_type="corporate_actions", unit_hint="crores")]},
    )
    assert report.actions == []
    assert any("Rejected dividend reference" in reason for reason in report.rejection_reasons)


# ---------------------------------------------------------------------------
# Face-value regression tests
# Requirement: a plain disclosure of the current face value must NOT become a
# corporate action. Only explicit from→to transition evidence qualifies.
# ---------------------------------------------------------------------------

def test_static_face_value_disclosure_is_not_a_corporate_action(tmp_path):
    """'Face value per share ₹1' is a metadata disclosure, not a change event."""
    report = _extract_single(
        tmp_path,
        {"eps": [_row("Face value per share (in ₹)", "1", table_type="eps", unit_hint="inr")]},
    )
    fv_actions = [a for a in report.actions if a.action_type == "face_value_change"]
    assert fv_actions == [], (
        f"Static face-value disclosure should not create a face_value_change action; got {fv_actions}"
    )


def test_same_face_value_repeated_across_table_not_a_change(tmp_path):
    """Two rows with the same face value amount must not be interpreted as a change."""
    report = _extract_single(
        tmp_path,
        {"eps": [
            _row("Face value per share", "2", table_type="eps", unit_hint="inr", page=1),
            _row("Face value per equity share", "2", table_type="eps", unit_hint="inr", page=2),
        ]},
    )
    fv_actions = [a for a in report.actions if a.action_type == "face_value_change"]
    assert fv_actions == []


def test_explicit_face_value_change_emits_action(tmp_path):
    """An explicit 'Face value changed from Rs 10 to Rs 2' row must produce an action."""
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Face value changed from Rs 10 to Rs 2", "0", table_type="corporate_actions")]},
    )
    fv_actions = [a for a in report.actions if a.action_type == "face_value_change"]
    assert len(fv_actions) == 1, f"Expected 1 face_value_change action, got {fv_actions}"
    assert fv_actions[0].face_value_before == 10.0
    assert fv_actions[0].face_value_after == 2.0


def test_stock_split_wording_emits_action_not_face_value_change(tmp_path):
    """'Sub-division of equity shares from Rs 10 to Rs 1' should produce a stock_split action."""
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Sub-division of equity shares from Rs 10 to Rs 1", "0", table_type="corporate_actions")]},
    )
    action_types = {a.action_type for a in report.actions}
    assert "stock_split" in action_types, f"Expected stock_split in actions; got {action_types}"
    assert "face_value_change" not in action_types


def test_ambiguous_face_value_text_rejected_not_fabricated(tmp_path):
    """'Face value' in isolation without transition language must be rejected, not fabricated."""
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Face value (in Rs)", "5", table_type="corporate_actions", unit_hint="inr")]},
    )
    fv_actions = [a for a in report.actions if a.action_type == "face_value_change"]
    assert fv_actions == [], (
        "Ambiguous face-value row should not fabricate a face_value_change action"
    )


def test_genuine_face_value_change_produces_eps_comparability_warning(tmp_path):
    """A confirmed face_value_change must still carry per_share_comparability_warnings."""
    report = _extract_single(
        tmp_path,
        {"corporate_actions": [_row("Face value changed from Rs 10 to Rs 5", "0", table_type="corporate_actions")]},
    )
    assert "face value changed" in report.per_share_comparability_warnings, (
        "Genuine face_value_change must produce per-share comparability warning"
    )


def test_no_hardcoding_for_face_value_fix():
    """The corporate_actions module must not contain company-specific hardcoding."""
    text = Path("knowledge/financials/corporate_actions.py").read_text(encoding="utf-8").lower()
    assert "sun pharma" not in text
    assert "sunpharma" not in text
    assert "sun_pharma" not in text
