"""The fact registry is the only authority on which extracted figures may be used: a figure it rejects leaves normalized_fundamentals.json before ratios, growth, trends,
CIM / PCIM or the truth pack can read it, and stays visible only as a quarantined fact with its reasons."""
import json
from pathlib import Path

from knowledge.financials.fact_registry import build_financial_fact_registry
from knowledge.financials.ratio_calculator import write_financial_ratios
from knowledge.financials.registry_authority import excluded_metrics, settle_financial_authority
from tests.financials.test_financial_fact_registry import _normalized_entry, _normalized_payload, _reconciliation_payload, _write_json


def _year(tmp_path, *, debt_label):
    root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    normalized = _normalized_payload()
    normalized["balance_sheet"]["total_debt"] = {**_normalized_entry("total_debt", value_crore=30.0, value_original="30"), "source_line_item": debt_label}
    normalized["balance_sheet"]["net_worth"] = _normalized_entry("net_worth", value_crore=100.0, value_original="100")
    normalized["profit_and_loss"]["revenue"] = {**_normalized_entry("revenue", value_crore=200.0, value_original="200"), "statement_type": "profit_and_loss", "source_line_item": "Revenue from operations"}
    normalized["profit_and_loss"]["pat"] = {**_normalized_entry("pat", value_crore=20.0, value_original="20"), "statement_type": "profit_and_loss", "source_line_item": "Profit for the year"}
    normalized["balance_sheet"]["total_assets"] = _normalized_entry("total_assets", value_crore=300.0, value_original="300")
    _write_json(root / "normalized_fundamentals.json", normalized)
    _write_json(root / "financial_reconciliation_report.json", _reconciliation_payload())
    return root


def test_a_rejected_figure_leaves_the_normalized_file_and_stays_a_quarantined_fact(tmp_path):
    root = _year(tmp_path, debt_label="Current liabilities (i) Borrowings")        # one section's borrowings, offered as total debt
    out = settle_financial_authority(company="acme", year="fy25", financial_root=root, output_root=tmp_path / "companies")
    assert "total_debt" in out and excluded_metrics(root) == ["total_debt"]
    normalized = json.loads((root / "normalized_fundamentals.json").read_text())
    assert normalized["balance_sheet"]["total_debt"]["value_crore"] is None
    assert normalized["registry_exclusions"]["total_debt"]["entry"]["value_crore"] == 30.0     # kept only as evidence of what was rejected
    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=root)
    fact = next(f for f in registry.invalid_facts if f.metric_id == "total_debt")
    assert fact.usable_downstream is False and fact.availability_status == "invalid" and "borrowings" in " ".join(fact.warnings).lower()
    assert not any(f.metric_id == "total_debt" for f in [*registry.available_facts, *registry.derived_facts, *registry.partial_facts])


def test_ratios_computed_after_settlement_cannot_use_the_rejected_figure(tmp_path, monkeypatch):
    from knowledge.financials.ratio_calculator import calculate_financial_ratios
    monkeypatch.setattr("knowledge.financials.ratio_calculator.reconciliation_blocks_stage", lambda *a, **k: [])      # the synthetic year is not a full statement set
    root = _year(tmp_path, debt_label="Current liabilities (i) Borrowings")
    _write_json(root / "financial_reconciliation_report.json", _reconciliation_payload())
    args = dict(company="acme", year="fy25", normalized_path=root / "normalized_fundamentals.json", reconciliation_path=root / "financial_reconciliation_report.json")
    before = calculate_financial_ratios(**args).to_dict()["ratios"]
    # Authority is enforced when the ratio is COMPUTED: the rejected figure is unusable even though the settlement stage has not run, and the report says it was withheld
    assert before["debt_to_equity"]["value"] is None and before["net_debt"]["value"] is None
    assert any("withheld by the financial fact registry" in w for w in calculate_financial_ratios(**args).warnings)
    settle_financial_authority(company="acme", year="fy25", financial_root=root, output_root=tmp_path / "companies")
    after = calculate_financial_ratios(**args).to_dict()["ratios"]
    assert after["debt_to_equity"]["value"] is None and after["net_debt"]["value"] is None


def test_a_supported_figure_is_untouched_and_settlement_is_idempotent(tmp_path):
    root = _year(tmp_path, debt_label="Total borrowings")
    assert settle_financial_authority(company="acme", year="fy25", financial_root=root, output_root=tmp_path / "companies") == {}
    first = (root / "normalized_fundamentals.json").read_text()
    settle_financial_authority(company="acme", year="fy25", financial_root=root, output_root=tmp_path / "companies")
    assert json.loads((root / "normalized_fundamentals.json").read_text())["balance_sheet"]["total_debt"]["value_crore"] == 30.0
    root2 = _year(tmp_path / "b", debt_label="Current liabilities (i) Borrowings")
    settle_financial_authority(company="acme", year="fy25", financial_root=root2, output_root=tmp_path / "b" / "companies")
    snapshot = (root2 / "normalized_fundamentals.json").read_text()
    settle_financial_authority(company="acme", year="fy25", financial_root=root2, output_root=tmp_path / "b" / "companies")
    assert (root2 / "normalized_fundamentals.json").read_text() == snapshot


def test_settlement_refuses_the_served_tree_without_authorization():
    import pytest
    from core.context_paths import WriteBoundaryError
    served = Path(__file__).resolve().parents[2] / "companies"
    with pytest.raises(WriteBoundaryError):
        settle_financial_authority(company="sun_pharma", year="fy21", financial_root=served / "sun_pharma" / "fy21" / "financials", output_root=served)


def test_a_rejected_metric_is_withheld_in_every_basis_view_of_the_normalized_file(tmp_path):
    root = _year(tmp_path, debt_label="Current liabilities (i) Borrowings")
    normalized = json.loads((root / "normalized_fundamentals.json").read_text())
    other_label = {**normalized["balance_sheet"]["total_debt"], "source_line_item": "Borrowings (note)", "source_page": 99}
    normalized["basis_views"] = {"consolidated": {"balance_sheet": {"total_debt": normalized["balance_sheet"]["total_debt"]}}, "unknown": {"balance_sheet": {"total_debt": other_label}}}
    _write_json(root / "normalized_fundamentals.json", normalized)
    settle_financial_authority(company="acme", year="fy25", financial_root=root, output_root=tmp_path / "companies")
    views = json.loads((root / "normalized_fundamentals.json").read_text())["basis_views"]
    assert all(v["balance_sheet"]["total_debt"].get("value_crore") is None for v in views.values())
