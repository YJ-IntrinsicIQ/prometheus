import json
from pathlib import Path

from core.company_context import CompanyContext
from pipelines.pipeline_context import set_context
from processors.capacity_cleaner import create_cleaner


ROOT = Path(__file__).resolve().parents[2]


def test_capacity_cleaner_accepts_comparative_years_inside_current_disclosures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="ujjivan", year="fy21")
    context.create_directories()
    set_context(context)

    try:
        source = ROOT / "companies" / "ujjivan" / "fy21" / "extracted" / "extracted_capacity.json"
        items = json.loads(source.read_text(encoding="utf-8"))
        bundle = next(item for item in items if item.get("item_id") == "capacity_expansions_00001")
        (context.extracted_dir / "extracted_capacity.json").write_text(
            json.dumps([bundle], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = create_cleaner().run()

        assert len(cleaned) == 1
        assert cleaned[0]["source_year"] == "fy21"
        assert cleaned[0]["year"] == "2021"
        assert cleaned[0]["capacity_type"] == bundle["capacity_type"]
        assert cleaned[0]["evidence_quality"]["period_resolution"]["status"] == "RESOLVED"
    finally:
        set_context(None)


def test_capacity_cleaner_handles_example_years_inside_current_disclosures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy20")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "capacity_type": "Business volume increase via acquisitions",
                "current_capacity": "Volume of business increased after acquisition of Karix and Gamooga",
                "target_capacity": "Volume of business increased after acquisition of Karix and Gamooga",
                "timeline": "ongoing",
                "location": "",
                "status": "realized (acquisitions led to increased business volume)",
                "source_chunk": "Management Discussion and Analysis ... regulatory environment ... (e.g., TCCPR 2018) ...",
                "page": 20,
                "distance": "",
                "value": "Business volume increase via acquisitions",
                "category": "Capacity expansion",
                "actor": "company",
                "time_reference": "dated",
                "year": "2018",
                "amount": "",
                "currency": "",
                "uncertainty_reason": "",
                "evidence_ids": ["ev_capacity_p20_00001"],
            }
        ]
        (context.extracted_dir / "extracted_capacity.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

        cleaned = create_cleaner().run()

        assert len(cleaned) == 1
        assert cleaned[0]["source_year"] == "fy20"
        assert cleaned[0]["capacity_type"] == items[0]["capacity_type"]
        output = json.loads((context.extracted_dir / "clean_capacity.json").read_text(encoding="utf-8"))
        assert len(output) == 1
        assert output[0]["capacity_type"] == items[0]["capacity_type"]
    finally:
        set_context(None)


def test_non_promotable_ambiguous_historical_capacity_is_quarantined_with_diagnostics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="sun_pharma", year="fy22")
    context.create_directories()
    set_context(context)

    try:
        source = ROOT / "companies" / "sun_pharma" / "fy22" / "extracted" / "extracted_capacity.json"
        items = json.loads(source.read_text(encoding="utf-8"))
        bundle = next(item for item in items if item.get("item_id") == "capacity_expansions_00003")
        (context.extracted_dir / "extracted_capacity.json").write_text(
            json.dumps([bundle], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = create_cleaner().run()

        assert cleaned == []
        output = json.loads((context.extracted_dir / "clean_capacity.json").read_text(encoding="utf-8"))
        assert output == []
        rejections = json.loads((context.extracted_dir / "clean_capacity_rejections.json").read_text(encoding="utf-8"))
        assert rejections["rejection_count"] == 1
        rejection = rejections["rejections"][0]
        assert rejection["source_item_id"] == "capacity_expansions_00003"
        assert rejection["failure_class"] == "PERIOD_RESOLUTION_UNSUPPORTED"
        assert rejection["diagnostics"]["period_status"] == "AMBIGUOUS"
        assert rejection["diagnostics"]["should_promote"] is False
        assert rejection["cleaned_period_fields"]["progression_materiality"]["should_promote"] is False
    finally:
        set_context(None)


def test_generic_non_promotable_ambiguous_capacity_variant_is_quarantined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="acme", year="fy25")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "capacity_type": "Medical rep expansion history",
                "current_capacity": "",
                "target_capacity": "",
                "timeline": "2021 and 2022",
                "location": "India",
                "status": "Expansion happened in 2021 and 2022; final status is truncated before conclusion.",
                "source_chunk": "In 2021 the field force expanded. In 2022 the report referenced continued productivity effects, but the excerpt is truncated.",
                "page": 44,
                "value": "Medical rep expansion history",
                "category": "",
                "actor": "company",
                "time_reference": "dated",
                "year": "2022",
                "amount": "",
                "currency": "",
                "uncertainty_reason": "final status not fully specified in the provided excerpt",
                "evidence_ids": ["ev_capacity_p44_00001"],
            }
        ]
        (context.extracted_dir / "extracted_capacity.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

        cleaned = create_cleaner().run()

        assert cleaned == []
        rejections = json.loads((context.extracted_dir / "clean_capacity_rejections.json").read_text(encoding="utf-8"))
        assert rejections["rejections"][0]["diagnostics"]["company"] == "acme"
        assert rejections["rejections"][0]["diagnostics"]["failure_class"] == "PERIOD_RESOLUTION_UNSUPPORTED"
    finally:
        set_context(None)


def test_capacity_cleaner_derives_status_from_source_text_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="ujjivan", year="fy24")
    context.create_directories()
    set_context(context)

    try:
        source = ROOT / "companies" / "ujjivan" / "fy24" / "extracted" / "extracted_capacity.json"
        items = json.loads(source.read_text(encoding="utf-8"))
        bundle = next(item for item in items if item.get("item_id") == "capacity_expansions_00002")
        (context.extracted_dir / "extracted_capacity.json").write_text(
            json.dumps([bundle], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = create_cleaner().run()

        assert len(cleaned) == 1
        assert cleaned[0]["status"] == "operational"
        assert cleaned[0]["source_year"] == "fy24"
    finally:
        set_context(None)


def test_capacity_cleaner_normalizes_explicit_and_missing_status_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="acme", year="fy25")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "capacity_type": "Digital origination upgrade",
                "current_capacity": "Digital onboarding and account opening system",
                "target_capacity": "",
                "timeline": "",
                "location": "",
                "status": "implemented / operational",
                "source_chunk": "The system is live and running across branches.",
                "page": 10,
                "value": "Digital origination upgrade",
                "category": "",
                "actor": "company",
                "time_reference": "period_specific",
                "year": "2025",
                "amount": "",
                "currency": "",
                "uncertainty_reason": "",
                "evidence_ids": ["ev_capacity_p10_00001"],
            },
                {
                    "capacity_type": "Warehouse expansion",
                    "current_capacity": "Warehouse buildout",
                    "target_capacity": "",
                    "timeline": "",
                    "location": "",
                    "status": "",
                    "source_chunk": "Management discussed a warehouse buildout without giving any status detail.",
                    "page": 11,
                    "value": "Warehouse expansion",
                    "category": "",
                "actor": "company",
                "time_reference": "period_specific",
                "year": "2025",
                "amount": "",
                "currency": "",
                "uncertainty_reason": "",
                "evidence_ids": ["ev_capacity_p11_00001"],
            },
        ]
        (context.extracted_dir / "extracted_capacity.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

        cleaned = create_cleaner().run()

        cleaned_by_type = {item["capacity_type"]: item for item in cleaned}
        assert cleaned_by_type["Digital origination upgrade"]["status"] == "operational"
        assert cleaned_by_type["Warehouse expansion"]["status"] == "unable_to_verify"
        assert cleaned_by_type["Warehouse expansion"]["status"] != "in_progress"
    finally:
        set_context(None)


def test_capacity_cleaner_keeps_planned_and_delayed_distinct(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="acme", year="fy25")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "capacity_type": "Planned line extension",
                "current_capacity": "Line extension",
                "target_capacity": "",
                "timeline": "",
                "location": "",
                "status": "planned",
                "source_chunk": "A planned line extension was described for next year.",
                "page": 12,
                "value": "Planned line extension",
                "category": "",
                "actor": "company",
                "time_reference": "period_specific",
                "year": "2025",
                "amount": "",
                "currency": "",
                "uncertainty_reason": "",
                "evidence_ids": ["ev_capacity_p12_00001"],
            },
            {
                "capacity_type": "Delayed line extension",
                "current_capacity": "Line extension",
                "target_capacity": "",
                "timeline": "",
                "location": "",
                "status": "delayed",
                "source_chunk": "The line extension was delayed due to permitting.",
                "page": 13,
                "value": "Delayed line extension",
                "category": "",
                "actor": "company",
                "time_reference": "period_specific",
                "year": "2025",
                "amount": "",
                "currency": "",
                "uncertainty_reason": "",
                "evidence_ids": ["ev_capacity_p13_00001"],
            },
        ]
        (context.extracted_dir / "extracted_capacity.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

        cleaned = create_cleaner().run()

        cleaned_by_type = {item["capacity_type"]: item for item in cleaned}
        assert cleaned_by_type["Planned line extension"]["status"] == "planned"
        assert cleaned_by_type["Delayed line extension"]["status"] == "delayed"
    finally:
        set_context(None)
