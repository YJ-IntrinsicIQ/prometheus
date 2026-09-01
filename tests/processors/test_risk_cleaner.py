import json
from pathlib import Path

from core.company_context import CompanyContext
from pipelines.pipeline_context import set_context
from processors.risk_cleaner import create_cleaner
from knowledge.evidence_layer import finalize_cleaned_item, validate_cleaned_item


ROOT = Path(__file__).resolve().parents[2]


def test_risk_cleaner_excludes_quarantined_items_without_failing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy20")
    context.create_directories()
    set_context(context)

    try:
        risks = [
            {
                "risk": "Dynamic and stringent regulatory/compliance environment requiring ongoing changes to platforms and processes",
                "category": "Regulatory risk",
                "severity": "medium",
                "year": "2021",
                "page": 12,
                "actor": "management",
                "value": "Dynamic and stringent regulatory/compliance environment requiring ongoing changes to platforms and processes",
            },
            {
                "risk": "Community development/CSR initiatives failing to be adopted successfully by target communities",
                "category": "CSR risk",
                "severity": "low",
                "year": "2021",
                "page": 13,
                "actor": "company",
                "value": "Community development/CSR initiatives failing to be adopted successfully by target communities",
            },
        ]
        (context.extracted_dir / "extracted_risks.json").write_text(json.dumps(risks, indent=2, ensure_ascii=False), encoding="utf-8")

        cleaned = create_cleaner().run()

        assert len(cleaned) == 1
        assert cleaned[0]["risk"] == risks[0]["risk"]
        output = json.loads((context.extracted_dir / "clean_risks.json").read_text(encoding="utf-8"))
        assert len(output) == 1
        assert output[0]["risk"] == risks[0]["risk"]
    finally:
        set_context(None)


def test_risk_cleaner_rejects_future_dated_near_neighbor_items(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="polymatech", year="fy24")
    context.create_directories()
    set_context(context)

    try:
        bundle = {
            "item_id": "risks_future_unsupported",
            "risk": "Supply chain risk includes a standalone 2030 reference without any stated company action.",
            "category": "supply chain dependence",
            "severity": "medium",
            "year": "2030",
            "actor": "management",
            "value": "Supply chain risk includes a standalone 2030 reference without any stated company action.",
        }
        (context.extracted_dir / "extracted_risks.json").write_text(
            json.dumps([bundle], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        try:
            create_cleaner().run()
        except ValueError as exc:
            message = str(exc)
            assert "invalid or unsupported period resolution" in message
            assert '"failure_class": "PERIOD_RESOLUTION_UNSUPPORTED"' in message
            assert '"company": "polymatech"' in message
            assert '"item_id": "risks_future_unsupported"' in message
        else:
            raise AssertionError("Expected future-dated near-neighbor risk to fail validation")
    finally:
        set_context(None)


def test_risk_cleaner_accepts_current_risk_with_supported_future_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="polymatech", year="fy24")
    context.create_directories()
    set_context(context)

    try:
        source = ROOT / "companies" / "polymatech" / "fy24" / "extracted" / "extracted_risks.json"
        items = json.loads(source.read_text(encoding="utf-8"))
        bundle = next(item for item in items if item.get("item_id") == "risks_00001")
        (context.extracted_dir / "extracted_risks.json").write_text(
            json.dumps([bundle], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = create_cleaner().run()

        assert len(cleaned) == 1
        period = cleaned[0]["evidence_quality"]["period_resolution"]
        assert period["status"] == "RESOLVED"
        assert period["resolved_period"] == "fy24"
        assert period["temporal_roles"]["target_period"] == "fy30"
    finally:
        set_context(None)


def test_risk_cleaner_quarantines_demoted_ambiguous_secondary_item(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="sun_pharma", year="fy20")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "item_id": "risks_00025",
                "risk": "Geographic market concentration exposure across fiscal years 2018, 2019, 2020, 2022",
                "category": "geographic market concentration",
                "severity": "Medium",
                "description": "US market performance spans 2018, 2019, 2020, 2022 with mixed signals and no clear trend.",
                "source_chunk": "US revenue declined in FY18, rose in FY19, declined again in FY20 and FY22. Mixed signals across 2018, 2019, 2020, 2022.",
                "year": "2020",
                "time_reference": "dated",
                "source_year": "fy20",
                "value": "Geographic market concentration exposure",
                "uncertainty_reason": "multiple years mentioned: 2018, 2019, 2020, 2022; conflicting chronology",
                "actor": "company",
                "page": 42,
            }
        ]
        (context.extracted_dir / "extracted_risks.json").write_text(
            json.dumps(items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = create_cleaner().run()

        assert cleaned == []
        rejections = json.loads((context.extracted_dir / "clean_risks_rejections.json").read_text(encoding="utf-8"))
        assert rejections["rejection_count"] == 1
        rejection = rejections["rejections"][0]
        assert rejection["source_item_id"] == "risks_00025"
        assert rejection["failure_class"] == "PERIOD_RESOLUTION_UNSUPPORTED"
        assert rejection["cleaned_period_fields"]["progression_materiality"]["should_promote"] is False
        assert rejection["cleaned_period_fields"]["progression_materiality"]["level"] == "low"
    finally:
        set_context(None)


def test_risk_cleaner_quarantines_low_materiality_ambiguous_non_promotable_item(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="sun_pharma", year="fy20")
    context.create_directories()
    set_context(context)

    try:
        source = ROOT / "companies" / "sun_pharma" / "fy20" / "extracted" / "extracted_risks.json"
        items = json.loads(source.read_text(encoding="utf-8"))
        bundle = next(item for item in items if item.get("item_id") == "risks_00027")
        (context.extracted_dir / "extracted_risks.json").write_text(
            json.dumps([bundle], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = create_cleaner().run()

        assert cleaned == []
        rejections = json.loads((context.extracted_dir / "clean_risks_rejections.json").read_text(encoding="utf-8"))
        rejection = rejections["rejections"][0]
        assert rejection["source_item_id"] == "risks_00027"
        assert rejection["diagnostics"]["period_status"] == "AMBIGUOUS"
        assert rejection["cleaned_period_fields"]["progression_materiality"]["level"] == "low"
        assert rejection["cleaned_period_fields"]["progression_materiality"]["should_promote"] is False
    finally:
        set_context(None)


def test_risk_cleaner_excludes_cross_year_source_period_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy23")
    context.create_directories()
    set_context(context)

    try:
        source = ROOT / "companies" / "tanla" / "fy23" / "extracted" / "extracted_risks.json"
        items = json.loads(source.read_text(encoding="utf-8"))
        contaminated = next(item for item in items if item.get("item_id") == "risks_00015")
        (context.extracted_dir / "extracted_risks.json").write_text(
            json.dumps([contaminated], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        finalized = finalize_cleaned_item(dict(contaminated), module_name="risks", item_index=1)
        validation = validate_cleaned_item(finalized, module_name="risks")
        assert "source period ownership mismatch" in validation["errors"]

        cleaned = create_cleaner().run()

        assert cleaned == []
        output = json.loads((context.extracted_dir / "clean_risks.json").read_text(encoding="utf-8"))
        assert output == []
    finally:
        set_context(None)


def test_risk_cleaner_handles_example_years_inside_current_disclosures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy20")
    context.create_directories()
    set_context(context)

    try:
        risks = [
            {
                "risk": "Dynamic and stringent regulatory/compliance environment (e.g., TCCPR 2018) requiring ongoing changes to platforms and processes",
                "category": "Regulatory risk",
                "severity": "high",
                "page": 12,
                "actor": "management",
                "value": "Dynamic and stringent regulatory/compliance environment (e.g., TCCPR 2018) requiring ongoing changes to platforms and processes",
                "source_chunk": "Management Discussion and Analysis ... TCCPR 2018 ... ongoing changes ...",
            }
        ]
        (context.extracted_dir / "extracted_risks.json").write_text(json.dumps(risks, indent=2, ensure_ascii=False), encoding="utf-8")

        cleaned = create_cleaner().run()

        assert len(cleaned) == 1
        assert cleaned[0]["source_year"] == "fy20"
        assert cleaned[0]["risk"] == risks[0]["risk"]
        output = json.loads((context.extracted_dir / "clean_risks.json").read_text(encoding="utf-8"))
        assert len(output) == 1
        assert output[0]["risk"] == risks[0]["risk"]
    finally:
        set_context(None)
