import json

from core.company_context import CompanyContext
from pipelines.pipeline_context import set_context
from processors.capacity_cleaner import create_cleaner


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
