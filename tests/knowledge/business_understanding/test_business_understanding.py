import json
from pathlib import Path

import pytest

from core.company_context import CompanyContext
from pipelines import run_company_pipeline
from pipelines.pipeline_context import set_context
from knowledge.business_understanding import run_business_understanding
from knowledge.business_understanding.pipeline import _load_document_payload
from knowledge.discovery_runtime.schema import DiscoveryResult, ExecutionStatistics
from knowledge.module_extractor.schema import ModuleAnswer, ModuleExtractionResult
from knowledge.question_engine.schema import DiscoveryPlan, Question


def _write_minimal_clean_inputs(context):
    (context.extracted_dir / "clean_projects.json").write_text(
        json.dumps([{"project_name": "Expansion", "source_chunk": "Expansion evidence", "page": 1}]),
        encoding="utf-8",
    )


def test_run_business_understanding_persists_artifacts(tmp_path, monkeypatch):
    context = CompanyContext(company="tips", year="fy24")
    monkeypatch.chdir(tmp_path)
    context.create_directories()
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv(
        "AI_MOCK_RESPONSE",
        json.dumps(
            {
                "metadata": {
                    "company": "tips",
                    "version": "1.0",
                    "confidence": 0.84,
                },
                "business_understanding": {
                    "business_summary": "Operates a music and entertainment catalogue business",
                    "business_model": "Music licensing and digital content monetization",
                    "value_creation": "Creates value from content ownership and distribution",
                    "competitive_position": "Competes through catalogue depth and distribution reach",
                },
                "characteristics": [
                    {"name": "Consumer Brand", "confidence": 0.8},
                ],
                "reasoning": [{"statement": "The memory is interpreted through the configured AI layer."}],
            }
        ),
    )
    set_context(context)

    bundle = run_business_understanding(context=context)

    assert bundle["company_memory"].company_id == "tips"
    assert bundle["business_blueprint"].metadata.company == "tips"
    assert bundle["business_classification"]["report_template"]
    assert bundle["classification_context"]["allowed_dnas"]

    memory_path = context.intelligence_dir / "company_memory.json"
    blueprint_path = context.intelligence_dir / "business_blueprint.json"
    classification_path = context.intelligence_dir / "business_classification.json"

    assert memory_path.exists()
    assert blueprint_path.exists()
    assert classification_path.exists()

    assert json.loads(memory_path.read_text())["company_id"] == "tips"


def test_load_document_payload_prefers_cleaned_artifacts(tmp_path, monkeypatch):
    context = CompanyContext(company="polymatech", year="fy25")
    monkeypatch.chdir(tmp_path)
    context.create_directories()
    set_context(context)

    (context.extracted_dir / "clean_projects.json").write_text(
        json.dumps(
            [
                {
                    "project_name": "Expansion Program",
                    "description": "Adding manufacturing capacity",
                    "status": "In progress",
                    "source_chunk": "The company is expanding capacity through a new manufacturing program.",
                    "page": 12,
                    "distance": 0.4,
                }
            ]
        ),
        encoding="utf-8",
    )
    (context.extracted_dir / "clean_capital_allocation.json").write_text(
        json.dumps(
            [
                {
                    "action": "Capex spending",
                    "category": "Capex",
                    "purpose": "Fund the expansion program",
                    "source_chunk": "Capital is being allocated to new manufacturing equipment.",
                    "page": 18,
                    "distance": 0.1,
                }
            ]
        ),
        encoding="utf-8",
    )

    payload = _load_document_payload(context)

    assert payload["company_id"] == "polymatech"
    assert len(payload["entities"]) == 1
    events = payload["entities"][0]["events"]
    assert [event["event_type"] for event in events] == ["project_1", "capital_allocation_1"]
    assert all(event["event_type"] != "document_loaded" for event in events)
    assert events[0]["evidence"][0]["source"] == "clean_projects.json#1"
    assert "Adding manufacturing capacity" in events[0]["evidence"][0]["content"]


def test_load_document_payload_falls_back_to_document_stub_when_no_cleaned_artifacts(tmp_path, monkeypatch):
    context = CompanyContext(company="tips", year="fy24")
    monkeypatch.chdir(tmp_path)
    context.create_directories()
    set_context(context)
    annual_report_dir = tmp_path / "data" / "annual_reports"
    annual_report_dir.mkdir(parents=True, exist_ok=True)
    (annual_report_dir / "tips_fy24.pdf").write_text("placeholder", encoding="utf-8")

    payload = _load_document_payload(context)

    assert payload["company_id"] == "tips"
    assert payload["entities"][0]["events"][0]["event_type"] == "document_loaded"


def test_run_business_intelligence_stage_persists_artifacts(tmp_path, monkeypatch):
    context = CompanyContext(company="tips", year="fy24")
    monkeypatch.chdir(tmp_path)
    context.create_directories()
    set_context(context)
    _write_minimal_clean_inputs(context)
    seen_contexts = []
    seen_runtime_kwargs = {}

    class FakePlanner:
        def build_plan(self, classification):
            return DiscoveryPlan(
                business_dnas=classification.get("business_dnas", []),
                loaded_modules=["capex"],
                questions=[Question(id="q1", module="capex", priority=1, category="capex", question="What is planned?")],
            )

    class FakeRuntime:
        def run(self, plan, business_classification=None):
            return DiscoveryResult(
                business_classification=business_classification or {},
                executed_modules=["capex"],
                module_results=[
                    ModuleExtractionResult(
                        module_id="capex",
                        module_name="Capex",
                        answers=[ModuleAnswer(question_id="q1", question="What is planned?", direct_answer="Not Found", supporting_points=[], primary_evidence=[], secondary_evidence=[], confidence=0.1, status="NOT_FOUND")],
                    )
                ],
                statistics=ExecutionStatistics(modules_executed=1, questions_asked=1, questions_answered=1, questions_not_found=1, average_confidence=0.1, execution_time_seconds=0.01, retrieved_chunks=1, llm_calls=1),
            )

    def fake_business_understanding(context=None):
        seen_contexts.append(context)
        return {
            "business_blueprint": {
                "metadata": {"company": "tips", "version": "1.0", "confidence": 0.8},
                "business_understanding": {
                    "business_summary": "Builds physical products",
                    "business_model": "Manufacturing-led business",
                    "value_creation": "Production assets create value",
                    "competitive_position": "Competes through execution",
                },
                "characteristics": [{"name": "Capital-intensive production", "confidence": 0.8}],
                "candidate_dna_signals": [
                    {
                        "name": "Manufacturing",
                        "confidence": 0.8,
                        "supporting_reason": "Production evidence supports manufacturing.",
                        "evidence_ids": [],
                    }
                ],
                "dnas": [{"name": "Manufacturing", "confidence": 0.8}],
                "dnas_source": "business_classification",
                "reasoning": [{"statement": "Reasoning present."}],
            },
            "business_classification": {
                "business_dnas": ["Manufacturing"],
                "question_modules": ["capital_allocation"],
                "report_template": "manufacturing_v1",
                "rationale": ["Production evidence dominates."],
                "evidence_used": ["Builds physical products"],
                "confidence": 0.8,
                "rejected_dnas": [],
            },
        }

    def fake_runtime(retriever=None, extractor=None, module_definitions=None):
        seen_runtime_kwargs["retriever"] = retriever
        seen_runtime_kwargs["extractor"] = extractor
        return FakeRuntime()

    monkeypatch.setattr(run_company_pipeline, "run_business_understanding", fake_business_understanding)
    monkeypatch.setattr(run_company_pipeline, "QuestionPlanner", lambda: FakePlanner())
    monkeypatch.setattr(run_company_pipeline, "DiscoveryRuntime", fake_runtime)
    monkeypatch.setattr(run_company_pipeline, "_build_runtime_retriever", lambda context: "retriever")
    monkeypatch.setattr(run_company_pipeline, "_build_runtime_extractor", lambda: "extractor")

    run_company_pipeline.run_business_intelligence_stage(context)

    assert seen_contexts == [context]
    assert seen_runtime_kwargs == {"retriever": "retriever", "extractor": "extractor"}
    assert (context.intelligence_dir / "discovery_plan.json").exists()
    assert (context.intelligence_dir / "module_results.json").exists()
    assert (context.intelligence_dir / "discovery_runtime.json").exists()
    payload = json.loads((context.intelligence_dir / "discovery_runtime.json").read_text())
    assert payload["business_classification"]["company"] == "tips"
    assert payload["business_classification"]["year"] == "fy24"


def test_run_business_intelligence_stage_uses_saved_classification_before_rerunning_bu(tmp_path, monkeypatch):
    context = CompanyContext(company="tanla", year="fy25")
    monkeypatch.chdir(tmp_path)
    context.create_directories()
    set_context(context)
    _write_minimal_clean_inputs(context)
    (context.intelligence_dir / "business_blueprint.json").write_text(
        json.dumps(
            {
                "metadata": {"company": "tanla", "version": "1.0", "confidence": 0.85},
                "business_understanding": {
                    "business_summary": "Enterprise messaging and compliance platform.",
                    "business_model": "API-first platform with operator and enterprise integrations.",
                    "value_creation": "Creates value through platform scale, trust controls, and partner deployments.",
                    "competitive_position": "Differentiates through throughput, compliance, and platform integrations.",
                },
                "characteristics": [
                    {"name": "API-first platform architecture", "confidence": 0.9},
                    {"name": "Embedded compliance and anti-fraud controls", "confidence": 0.88},
                ],
                "candidate_dna_signals": [
                    {
                        "name": "Enterprise Platform",
                        "confidence": 0.85,
                        "supporting_reason": "Platform architecture supports enterprise platform candidate.",
                        "evidence_ids": [],
                    }
                ],
                "dnas": [
                    {"name": "Compliance Infrastructure", "confidence": 0.85},
                    {"name": "Enterprise Platform", "confidence": 0.85},
                ],
                "dnas_source": "business_classification",
                "reasoning": [{"statement": "Reasoning present."}],
            }
        ),
        encoding="utf-8",
    )
    (context.intelligence_dir / "business_classification.json").write_text(
        json.dumps(
            {
                "business_dnas": ["Compliance Infrastructure", "Enterprise Platform"],
                "question_modules": ["technology", "platform_dependency"],
                "report_template": "software_v1",
                "rationale": ["Platform and compliance evidence dominate."],
                "evidence_used": ["Enterprise messaging and compliance platform."],
                "confidence": 0.84,
                "rejected_dnas": [],
            }
        ),
        encoding="utf-8",
    )

    class FakePlanner:
        def build_plan(self, classification):
            assert classification["question_modules"] == [
                "technology",
                "platform_dependency",
                "platform_economics",
                "compliance_infrastructure",
            ]
            return DiscoveryPlan(
                business_dnas=classification.get("business_dnas", []),
                loaded_modules=list(classification["question_modules"]),
                questions=[
                    Question(
                        id="platform_economics.usage_scale",
                        module="platform_economics",
                        priority=1,
                        category="platform",
                        question="How large is the platform?",
                    )
                ],
            )

    class FakeRuntime:
        def run(self, plan, business_classification=None):
            return DiscoveryResult(
                business_classification=business_classification or {},
                executed_modules=list(plan.loaded_modules),
                module_results=[],
                statistics=ExecutionStatistics(
                    modules_executed=len(plan.loaded_modules),
                    questions_asked=len(plan.questions),
                    questions_answered=0,
                    questions_not_found=0,
                    average_confidence=0.0,
                    execution_time_seconds=0.01,
                    retrieved_chunks=0,
                    llm_calls=0,
                ),
            )

    def fail_business_understanding(context=None):
        raise AssertionError("Business Understanding should not rerun when saved classification exists")

    monkeypatch.setattr(run_company_pipeline, "run_business_understanding", fail_business_understanding)
    monkeypatch.setattr(run_company_pipeline, "QuestionPlanner", lambda: FakePlanner())
    monkeypatch.setattr(run_company_pipeline, "DiscoveryRuntime", lambda retriever=None, extractor=None: FakeRuntime())
    monkeypatch.setattr(run_company_pipeline, "_build_runtime_retriever", lambda context: None)
    monkeypatch.setattr(run_company_pipeline, "_build_runtime_extractor", lambda: None)

    run_company_pipeline.run_business_intelligence_stage(context=context)

    discovery_plan = json.loads((context.intelligence_dir / "discovery_plan.json").read_text())
    classification = json.loads((context.intelligence_dir / "business_classification.json").read_text())

    assert discovery_plan["loaded_modules"] == [
        "technology",
        "platform_dependency",
        "platform_economics",
        "compliance_infrastructure",
    ]
    assert classification["question_modules"] == [
        "technology",
        "platform_dependency",
        "platform_economics",
        "compliance_infrastructure",
    ]


def test_build_runtime_retriever_generates_clean_chunks_when_missing(tmp_path, monkeypatch):
    context = CompanyContext(company="tips", year="fy24")
    monkeypatch.chdir(tmp_path)
    context.create_directories()
    annual_report_dir = tmp_path / "data" / "annual_reports"
    annual_report_dir.mkdir(parents=True, exist_ok=True)
    annual_report_path = annual_report_dir / "tips_fy24.pdf"
    annual_report_path.write_text("placeholder", encoding="utf-8")
    seen = {}

    class FakeRetriever:
        def build_company_index(self, company, year):
            seen["company"] = company
            seen["year"] = year

    monkeypatch.setattr(run_company_pipeline, "HybridRetriever", lambda: FakeRetriever())
    monkeypatch.setattr(run_company_pipeline, "extract_pages", lambda path: [{"page": 1, "text": "Long enough paragraph " * 20}])

    def fake_chunk_pages(pages, *, company, year, document_type, output_path):
        seen["pages"] = pages
        seen["chunk_output_path"] = output_path
        output_path.write_text(
            json.dumps(
                {
                    "company": company,
                    "year": year,
                    "document_type": document_type,
                    "chunk_count": 1,
                    "chunks": [
                        {
                            "chunk_id": "CHK-000001",
                            "page": 1,
                            "text": "sample chunk",
                            "metadata": {
                                "page": 1,
                                "company": company,
                                "year": year,
                                "document_type": document_type,
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return [{"page": 1, "text": "sample chunk"}]

    monkeypatch.setattr(run_company_pipeline, "chunk_pages", fake_chunk_pages)

    retriever = run_company_pipeline._build_runtime_retriever(context)

    assert isinstance(retriever, FakeRetriever)
    assert seen["company"] == "tips"
    assert seen["year"] == "fy24"
    assert seen["chunk_output_path"] == context.extracted_dir / "clean_chunks.json"
    assert (context.extracted_dir / "clean_chunks.json").exists()


def test_run_all_reuses_business_understanding_bundle_and_context(monkeypatch):
    context = CompanyContext(company="tips", year="fy24")
    calls = []
    bundle = {
        "business_blueprint": {
            "metadata": {"company": "tips", "version": "1.0", "confidence": 0.8},
            "business_understanding": {
                "business_summary": "Builds physical products",
                "business_model": "Manufacturing-led business",
                "value_creation": "Production assets create value",
                "competitive_position": "Competes through execution",
            },
            "characteristics": [{"name": "Capital-intensive production", "confidence": 0.8}],
            "candidate_dna_signals": [
                {
                    "name": "Manufacturing",
                    "confidence": 0.8,
                    "supporting_reason": "Production evidence supports manufacturing.",
                    "evidence_ids": [],
                }
            ],
            "dnas": [{"name": "Manufacturing", "confidence": 0.8}],
            "dnas_source": "business_classification",
            "reasoning": [{"statement": "Reasoning present."}],
        },
        "business_classification": {
            "business_dnas": ["Manufacturing"],
            "question_modules": ["capital_allocation"],
            "report_template": "manufacturing_v1",
            "rationale": ["Production evidence dominates."],
            "evidence_used": ["Builds physical products"],
            "confidence": 0.8,
            "rejected_dnas": [],
        },
    }

    def fake_business_understanding(context=None):
        calls.append(("business_understanding", context))
        return bundle

    def fake_business_intelligence(context=None, bundle=None):
        calls.append(("business_intelligence", context, bundle))

    monkeypatch.setattr(run_company_pipeline, "set_context", lambda context: None)
    monkeypatch.setattr(run_company_pipeline, "run_business_understanding", fake_business_understanding)
    monkeypatch.setattr(run_company_pipeline, "run_business_intelligence_stage", fake_business_intelligence)
    monkeypatch.setattr(run_company_pipeline, "run_discovery", lambda context=None: calls.append(("discovery", context)))
    monkeypatch.setattr(run_company_pipeline, "run_extraction", lambda context=None: calls.append(("extraction", context)))
    monkeypatch.setattr(run_company_pipeline, "run_cleaning", lambda context=None: calls.append(("cleaning", context)))
    monkeypatch.setattr(run_company_pipeline, "run_intelligence", lambda context=None: calls.append(("intelligence", context)))
    monkeypatch.setattr(
        run_company_pipeline,
        "run_cim_stage",
        lambda company, context=None: calls.append(("cim", company, context)),
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_multi_year_memory_stage",
        lambda company, context=None: calls.append(("multi_year_memory", company, context)),
    )

    run_company_pipeline.run_all(context=context)

    assert calls == [
        ("discovery", context),
        ("extraction", context),
        ("cleaning", context),
        ("business_understanding", context),
        ("business_intelligence", context, bundle),
        ("intelligence", context),
        ("cim", context.company, context),
        ("multi_year_memory", context.company, context),
    ]


def test_main_passes_context_to_run_all(monkeypatch):
    calls = []

    class FakeContext:
        company = "tips"
        year = "fy24"
        raw_dir = Path("/tmp/raw")
        extracted_dir = Path("/tmp/extracted")
        intelligence_dir = Path("/tmp/intelligence")

        def create_directories(self):
            calls.append(("create_directories", self))

    monkeypatch.setattr(run_company_pipeline, "CompanyContext", lambda company, year: FakeContext())
    monkeypatch.setattr(run_company_pipeline, "set_context", lambda context: calls.append(("set_context", context)))
    monkeypatch.setattr(run_company_pipeline, "run_all", lambda context=None: calls.append(("run_all", context)))
    monkeypatch.setattr(run_company_pipeline.sys, "argv", ["run_company_pipeline", "tips", "fy24", "--stage", "all"])

    run_company_pipeline.main()

    context = calls[0][1]
    assert calls[:3] == [
        ("create_directories", context),
        ("set_context", context),
        ("run_all", context),
    ]


def test_main_passes_context_to_run_business_intelligence_stage(monkeypatch):
    calls = []

    class FakeContext:
        company = "tips"
        year = "fy24"
        raw_dir = Path("/tmp/raw")
        extracted_dir = Path("/tmp/extracted")
        intelligence_dir = Path("/tmp/intelligence")

        def create_directories(self):
            calls.append(("create_directories", self))

    monkeypatch.setattr(run_company_pipeline, "CompanyContext", lambda company, year: FakeContext())
    monkeypatch.setattr(run_company_pipeline, "set_context", lambda context: calls.append(("set_context", context)))
    monkeypatch.setattr(
        run_company_pipeline,
        "run_business_intelligence_stage",
        lambda context=None, bundle=None: calls.append(("run_business_intelligence_stage", context, bundle)),
    )
    monkeypatch.setattr(
        run_company_pipeline.sys,
        "argv",
        ["run_company_pipeline", "tips", "fy24", "--stage", "business_intelligence"],
    )

    run_company_pipeline.main()

    context = calls[0][1]
    assert calls[:3] == [
        ("create_directories", context),
        ("set_context", context),
        ("run_business_intelligence_stage", context, None),
    ]


def test_main_runs_company_memory_without_year(monkeypatch):
    calls = []

    monkeypatch.setattr(
        run_company_pipeline,
        "run_company_memory_stage",
        lambda company, context=None: calls.append(("run_company_memory_stage", company, context)),
    )
    monkeypatch.setattr(
        run_company_pipeline.sys,
        "argv",
        ["run_company_pipeline", "tips", "--stage", "company_memory"],
    )

    run_company_pipeline.main()

    assert calls == [("run_company_memory_stage", "tips", None)]


def test_main_runs_cim_without_year(monkeypatch):
    calls = []

    monkeypatch.setattr(
        run_company_pipeline,
        "run_cim_stage",
        lambda company, context=None: calls.append(("run_cim_stage", company, context)),
    )
    monkeypatch.setattr(
        run_company_pipeline.sys,
        "argv",
        ["run_company_pipeline", "tips", "--stage", "cim"],
    )

    run_company_pipeline.main()

    assert calls == [("run_cim_stage", "tips", None)]


def test_main_runs_multi_year_memory_without_year(monkeypatch):
    calls = []

    monkeypatch.setattr(
        run_company_pipeline,
        "run_multi_year_memory_stage",
        lambda company, context=None: calls.append(("run_multi_year_memory_stage", company, context)),
    )
    monkeypatch.setattr(
        run_company_pipeline.sys,
        "argv",
        ["run_company_pipeline", "tips", "--stage", "multi_year_memory"],
    )

    run_company_pipeline.main()

    assert calls == [("run_multi_year_memory_stage", "tips", None)]


def test_run_discovery_ensures_active_company_year_index_before_steps(monkeypatch):
    context = CompanyContext(company="polymatech", year="fy24")
    calls = []

    monkeypatch.setattr(run_company_pipeline, "set_context", lambda current: calls.append(("set_context", current)))
    monkeypatch.setattr(run_company_pipeline, "_run_preflight", lambda current: calls.append(("preflight", current)))
    monkeypatch.setattr(run_company_pipeline, "_ensure_discovery_index", lambda current: (calls.append(("ensure_index", current)), 1)[1])
    monkeypatch.setattr(run_company_pipeline, "run_steps", lambda stage, steps: calls.append(("run_steps", stage, steps)))

    run_company_pipeline.run_discovery(context=context)

    assert calls == [
        ("set_context", context),
        ("preflight", context),
        ("run_steps", "DISCOVERY", run_company_pipeline.get_discovery_steps),
    ]


@pytest.mark.parametrize(
    ("bundle", "message"),
    [
        (None, "did not return a bundle"),
        ({}, "missing business_classification"),
        ({"business_classification": {}}, "invalid business_classification"),
    ],
)
def test_business_understanding_bundle_validation_fails_fast(bundle, message):
    with pytest.raises(ValueError, match=message):
        run_company_pipeline.validate_business_understanding_bundle(bundle)


def test_business_understanding_bundle_validation_returns_classification():
    classification = {
        "business_dnas": ["Manufacturing"],
        "question_modules": ["capital_allocation"],
        "report_template": "manufacturing_v1",
        "rationale": ["Production evidence dominates."],
        "evidence_used": ["Builds physical products"],
        "confidence": 0.8,
        "rejected_dnas": [],
    }
    blueprint = {
        "metadata": {"company": "tips", "version": "1.0", "confidence": 0.8},
        "business_understanding": {
            "business_summary": "Builds physical products",
            "business_model": "Manufacturing-led business",
            "value_creation": "Production assets create value",
            "competitive_position": "Competes through execution",
        },
        "characteristics": [{"name": "Capital-intensive production", "confidence": 0.8}],
        "candidate_dna_signals": [
            {
                "name": "Manufacturing",
                "confidence": 0.8,
                "supporting_reason": "Production evidence supports manufacturing.",
                "evidence_ids": [],
            }
        ],
        "dnas": [{"name": "Manufacturing", "confidence": 0.8}],
        "dnas_source": "business_classification",
        "reasoning": [{"statement": "Reasoning present."}],
    }

    assert run_company_pipeline.validate_business_understanding_bundle(
        {"business_blueprint": blueprint, "business_classification": classification}
    ) is classification


def test_apply_bi_test_caps_limits_modules_and_questions(monkeypatch):
    plan = DiscoveryPlan(
        business_dnas=["Manufacturing"],
        loaded_modules=["capital_allocation", "technology"],
        questions=[
            Question(id="q1", module="capital_allocation", priority=1, category="capital", question="Q1"),
            Question(id="q2", module="capital_allocation", priority=2, category="capital", question="Q2"),
            Question(id="q3", module="technology", priority=1, category="technology", question="Q3"),
        ],
    )
    monkeypatch.setenv("BI_MAX_MODULES", "1")
    monkeypatch.setenv("BI_MAX_QUESTIONS", "1")

    capped = run_company_pipeline._apply_bi_test_caps(plan)

    assert capped.loaded_modules == ["capital_allocation"]
    assert [question.id for question in capped.questions] == ["q1"]


@pytest.mark.parametrize("name", ["BI_MAX_MODULES", "BI_MAX_QUESTIONS"])
@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_apply_bi_test_caps_rejects_invalid_env(monkeypatch, name, value):
    plan = DiscoveryPlan(
        business_dnas=["Manufacturing"],
        loaded_modules=["capital_allocation"],
        questions=[Question(id="q1", module="capital_allocation", priority=1, category="capital", question="Q1")],
    )
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        run_company_pipeline._apply_bi_test_caps(plan)
