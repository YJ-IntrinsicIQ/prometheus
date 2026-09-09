import json
from pathlib import Path

from core.company_context import CompanyContext
from pipelines.pipeline_context import set_context
from processors.capital_allocation_cleaner import create_cleaner


ROOT = Path(__file__).resolve().parents[2]


def test_capital_allocation_cleaner_resolves_report_year_anchors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy22")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "action": "Capital expenditure",
                "category": "Capex spending",
                "amount": "₹62 crore (31-Mar-22)",
                "purpose": "Support operations and growth (reported capital expenditure for FY22)",
                "source_chunk": "Operating Cash flow Capital expenditure ... 31-Mar-22 31-Mar-21 ...",
                "page": 42,
                "time_reference": "period_specific",
                "year": "2021",
                "actor": "management",
                "value": "Capital expenditure",
            },
        ]
        (context.extracted_dir / "extracted_capital_allocations.json").write_text(
            json.dumps(items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = create_cleaner().run()

        assert len(cleaned) == 1
        assert cleaned[0]["source_year"] == "fy22"
        assert cleaned[0]["action"] == "Capital expenditure"
        output = json.loads((context.extracted_dir / "clean_capital_allocation.json").read_text(encoding="utf-8"))
        assert len(output) == 1
        assert output[0]["source_year"] == "fy22"
    finally:
        set_context(None)


def test_capital_allocation_cleaner_rejects_ambiguous_periods(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy22")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "action": "Capital expenditure",
                "category": "Capex spending",
                "amount": "₹62 crore (31-Mar-22)",
                "purpose": "Support operations and growth (reported capital expenditure for FY19 and FY22)",
                "source_chunk": "Operating Cash flow Capital expenditure ... 31-Mar-22 31-Mar-21 ...",
                "page": 43,
                "time_reference": "period_specific",
                "year": "2021",
                "actor": "management",
                "value": "Capital expenditure",
            },
        ]
        (context.extracted_dir / "extracted_capital_allocations.json").write_text(
            json.dumps(items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Ambiguous periods are quarantined (local rejection) rather than hard-failing.
        # The cleaner must produce 0 cleaned items — the item is rejected, not promoted.
        cleaned = create_cleaner().run()
        assert len(cleaned) == 0, (
            f"Ambiguous capital allocation must be quarantined (0 cleaned items); got {cleaned}"
        )
        output_path = context.extracted_dir / "clean_capital_allocation.json"
        if output_path.exists():
            output = json.loads(output_path.read_text(encoding="utf-8"))
            assert len(output) == 0, (
                f"clean_capital_allocation.json must be empty for ambiguous item; got {output}"
            )
    finally:
        set_context(None)


def test_capital_allocation_cleaner_splits_composite_employee_plan_bundle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy24")
    context.create_directories()
    set_context(context)

    try:
        source = ROOT / "companies" / "tanla" / "fy24" / "extracted" / "extracted_capital_allocations.json"
        items = json.loads(source.read_text(encoding="utf-8"))
        bundle = next(item for item in items if item.get("item_id") == "capital_allocations_00016")
        (context.extracted_dir / "extracted_capital_allocations.json").write_text(
            json.dumps([bundle], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = create_cleaner().run()

        assert len(cleaned) == 3
        assert {item["year"] for item in cleaned} == {"2015", "2018", "2021"}
        assert all(item["source_year"] == "fy24" for item in cleaned)
        assert all(item.get("split_from_item_id") == "capital_allocations_00016" for item in cleaned)
        assert all(item["evidence_quality"]["period_resolution"]["status"] in {"RESOLVED", "HISTORICAL_CONTEXT"} for item in cleaned)
    finally:
        set_context(None)


def test_capital_allocation_cleaner_keeps_ambiguous_multi_year_history_blocked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy24")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "action": "Capital allocation across 2019, 2021, 2023",
                "category": "Equity issuance (employee stock-based compensation)",
                "amount": "",
                "purpose": "Historical reference only",
                "source_chunk": "Capital allocation in 2019, 2021, and 2023 shows varying patterns",
                "page": 9,
                "time_reference": "period_specific",
                "year": "2023",
                "actor": "company",
                "value": "Capital allocation across 2019, 2021, 2023",
                "uncertainty_reason": "multiple years mentioned: 2019, 2021, 2023; conflicting chronology",
            }
        ]
        (context.extracted_dir / "extracted_capital_allocations.json").write_text(
            json.dumps(items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Genuinely ambiguous multi-year capital allocation -> quarantine
        cleaned = create_cleaner().run()
        assert cleaned == []

        rejections = json.loads((context.extracted_dir / "clean_capital_allocation_rejections.json").read_text(encoding="utf-8"))
        assert rejections["rejection_count"] == 1
        rejection = rejections["rejections"][0]
        assert rejection["failure_class"] == "PERIOD_RESOLUTION_UNSUPPORTED"
        assert rejection["diagnostics"]["period_status"] == "AMBIGUOUS"
        assert rejection["diagnostics"]["should_promote"] is False
    finally:
        set_context(None)
