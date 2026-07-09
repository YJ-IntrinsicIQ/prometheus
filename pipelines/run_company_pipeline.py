import argparse
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.company_context import CompanyContext  # noqa: E402
from pipelines.pipeline_context import set_context  # noqa: E402
from knowledge.ai import get_llm  # noqa: E402
from knowledge.business_understanding import run_business_understanding  # noqa: E402
from knowledge.discovery_runtime import DiscoveryRuntime  # noqa: E402
from knowledge.module_extractor import ModuleExtractor  # noqa: E402
from knowledge.question_engine import QuestionPlanner  # noqa: E402
from knowledge.question_engine import QuestionRegistry  # noqa: E402
from knowledge.retrieval.retriever import HybridRetriever  # noqa: E402
from knowledge.company_memory import CompanyMemoryAggregateBuilder  # noqa: E402
from knowledge.cim_contract import CIMContractBuilder  # noqa: E402
from intelligence.investor_panel import InvestorPanelRunner  # noqa: E402
from embeddings.index_builder import ensure_company_year_index  # noqa: E402
from scripts.pdf_reader import extract_pages  # noqa: E402
from scripts.smart_chunker import chunk_pages  # noqa: E402
from knowledge.question_engine.schema import DiscoveryPlan  # noqa: E402


def get_discovery_steps():
    from discovery.project_discovery import main as project_discovery_main  # noqa: E402
    from discovery.promise_discovery import main as promise_discovery_main  # noqa: E402
    from discovery.risk_discovery import main as risk_discovery_main  # noqa: E402
    from discovery.capacity_discovery import main as capacity_discovery_main  # noqa: E402
    from discovery.capital_allocation_discovery import main as capital_allocation_discovery_main  # noqa: E402
    from discovery.initiative_discovery import main as initiative_discovery_main  # noqa: E402

    return [
        ("Project Discovery", project_discovery_main),
        ("Promise Discovery", promise_discovery_main),
        ("Risk Discovery", risk_discovery_main),
        ("Capacity Discovery", capacity_discovery_main),
        ("Capital Allocation Discovery", capital_allocation_discovery_main),
        ("Initiative Discovery", initiative_discovery_main),
    ]


def get_extraction_steps():
    from extractors.project_extractor import main as project_extractor_main  # noqa: E402
    from extractors.promise_extractor import main as promise_extractor_main  # noqa: E402
    from extractors.risk_extractor import main as risk_extractor_main  # noqa: E402
    from extractors.capacity_extractor import main as capacity_extractor_main  # noqa: E402
    from extractors.capital_allocation_extractor import main as capital_allocation_extractor_main  # noqa: E402
    from extractors.initiative_extractor import main as initiative_extractor_main  # noqa: E402

    return [
        ("Project Extractor", project_extractor_main),
        ("Promise Extractor", promise_extractor_main),
        ("Risk Extractor", risk_extractor_main),
        ("Capacity Extractor", capacity_extractor_main),
        ("Capital Allocation Extractor", capital_allocation_extractor_main),
        ("Initiative Extractor", initiative_extractor_main),
    ]


def get_cleaning_steps():
    from processors.project_cleaner import main as project_cleaner_main  # noqa: E402
    from processors.promise_cleaner import main as promise_cleaner_main  # noqa: E402
    from processors.risk_cleaner import main as risk_cleaner_main  # noqa: E402
    from processors.capacity_cleaner import main as capacity_cleaner_main  # noqa: E402
    from processors.capital_allocation_cleaner import main as capital_allocation_cleaner_main  # noqa: E402
    from processors.initiative_cleaner import main as initiative_cleaner_main  # noqa: E402

    return [
        ("Project Cleaner", project_cleaner_main),
        ("Promise Cleaner", promise_cleaner_main),
        ("Risk Cleaner", risk_cleaner_main),
        ("Capacity Cleaner", capacity_cleaner_main),
        ("Capital Allocation Cleaner", capital_allocation_cleaner_main),
        ("Initiative Cleaner", initiative_cleaner_main),
    ]


def get_intelligence_steps():
    from knowledge.cim_builder import main as cim_builder_main  # noqa: E402
    from synthesis.management_profile_builder import main as management_profile_builder_main  # noqa: E402
    from synthesis.management_summary_generator import main as management_summary_generator_main  # noqa: E402
    from synthesis.theme_builder import main as theme_builder_main  # noqa: E402
    from synthesis.entity_linker import main as entity_linker_main  # noqa: E402
    from synthesis.management_focus_analyzer import main as management_focus_analyzer_main  # noqa: E402
    from synthesis.promise_execution_tracker import main as promise_execution_tracker_main  # noqa: E402
    from synthesis.evidence_graph_builder import main as evidence_graph_builder_main  # noqa: E402
    from synthesis.investor_narrative_generator import main as investor_narrative_generator_main  # noqa: E402

    return [
        ("Company Intelligence Builder", cim_builder_main),
        ("Management Profile Builder", management_profile_builder_main),
        ("Management Summary Generator", management_summary_generator_main),
        ("Theme Builder", theme_builder_main),
        ("Entity Linker", entity_linker_main),
        ("Management Focus Analyzer", management_focus_analyzer_main),
        ("Promise Execution Tracker", promise_execution_tracker_main),
        ("Evidence Graph Builder", evidence_graph_builder_main),
        ("Investor Narrative Generator", investor_narrative_generator_main),
    ]


STAGES = {
    "discovery": ("DISCOVERY", get_discovery_steps),
    "extraction": ("EXTRACTION", get_extraction_steps),
    "cleaning": ("CLEANING", get_cleaning_steps),
    "intelligence": ("INTELLIGENCE", get_intelligence_steps),
}


def run_steps(stage_label, steps):
    if callable(steps):
        steps = steps()

    for step_label, step in steps:
        print(
            f"[{stage_label}] {step_label}"
        )
        step()


def run_business_understanding_stage(context=None):
    if context is not None:
        set_context(context)
    if context is None:
        return run_business_understanding()
    return run_business_understanding(context=context)


def _resolve_annual_report_path(context):
    candidates = [
        Path("data/annual_reports") / f"{context.company}_{context.year}.pdf",
        Path("data/annual_reports") / f"{context.company}_{context.year}.txt",
    ]

    normalized_year = str(context.year).lower()
    if normalized_year.startswith("fy") and len(normalized_year) > 2:
        year_suffix = normalized_year[-2:]
        candidates.extend(
            [
                Path("data/annual_reports") / f"{context.company}_fy{year_suffix}.pdf",
                Path("data/annual_reports") / f"{context.company}_fy{year_suffix}.txt",
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def _ensure_clean_chunks(context):
    chunk_path = context.extracted_dir / "clean_chunks.json"
    if chunk_path.exists():
        return chunk_path

    annual_report_path = _resolve_annual_report_path(context)
    if not annual_report_path.exists():
        raise FileNotFoundError(f"Annual report not found: {annual_report_path}")
    if annual_report_path.suffix.lower() != ".pdf":
        raise FileNotFoundError(
            f"Cannot generate clean chunks from non-PDF annual report: {annual_report_path}"
        )

    pages = extract_pages(annual_report_path)
    chunk_pages(
        pages,
        company=context.company,
        year=context.year,
        document_type="annual_report",
        output_path=chunk_path,
    )
    return chunk_path


def _build_runtime_retriever(context):
    if context is None:
        return None

    _ensure_clean_chunks(context)
    retriever = HybridRetriever()
    retriever.build_company_index(
        company=context.company,
        year=context.year,
    )
    return retriever


def _build_runtime_extractor():
    llm = get_llm()

    def ai_adapter(prompt: str) -> str:
        response = llm.generate(
            prompt=prompt,
            response_schema={"type": "object"},
        )
        return response.text

    return ModuleExtractor(llm_client=ai_adapter)


def _ensure_discovery_index(context):
    annual_report_path = _resolve_annual_report_path(context)
    if not annual_report_path.exists():
        raise FileNotFoundError(f"Annual report not found: {annual_report_path}")

    indexed_count = ensure_company_year_index(
        pdf_path=annual_report_path,
        company=context.company,
        year=context.year,
        document_type="annual_report",
    )

    print(
        f"[DISCOVERY] Active company/year index ready: "
        f"{context.company} {context.year} ({indexed_count} chunks)"
    )


def validate_business_understanding_bundle(bundle):
    if not isinstance(bundle, dict):
        raise ValueError("Business Understanding stage did not return a bundle")

    if "business_classification" not in bundle:
        raise ValueError("Business Understanding bundle is missing business_classification")

    business_classification = bundle["business_classification"]
    if not isinstance(business_classification, dict) or not business_classification:
        raise ValueError("Business Understanding bundle contains an invalid business_classification")

    return business_classification


def _load_saved_business_intelligence_bundle(context):
    if context is None:
        return None

    classification_path = context.intelligence_dir / "business_classification.json"
    if not classification_path.exists():
        return None

    try:
        business_classification = json.loads(classification_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(business_classification, dict) or not business_classification:
        return None

    canonicalized = _canonicalize_business_classification(business_classification)
    if canonicalized != business_classification:
        classification_path.write_text(
            json.dumps(canonicalized, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return {"business_classification": canonicalized}


def _canonicalize_business_classification(business_classification):
    classification = dict(business_classification or {})
    registry = QuestionRegistry()
    modules = registry.modules_for_classification(classification)
    classification["question_modules"] = [module.module_id for module in modules]
    return classification


def _resolve_positive_int_env(name):
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return None

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer when set") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than 0 when set")

    return value


def _apply_bi_test_caps(plan):
    max_modules = _resolve_positive_int_env("BI_MAX_MODULES")
    max_questions = _resolve_positive_int_env("BI_MAX_QUESTIONS")

    loaded_modules = list(plan.loaded_modules)
    questions = list(plan.questions)

    if max_modules is not None and len(loaded_modules) > max_modules:
        print(
            f"[BUSINESS INTELLIGENCE] BI_MAX_MODULES active: "
            f"loaded modules={len(loaded_modules)}, capped to {max_modules}"
        )
        loaded_modules = loaded_modules[:max_modules]
        allowed_modules = set(loaded_modules)
        questions = [question for question in questions if question.module in allowed_modules]

    if max_questions is not None and len(questions) > max_questions:
        print(
            f"[BUSINESS INTELLIGENCE] BI_MAX_QUESTIONS active: "
            f"planned questions={len(questions)}, capped to {max_questions}"
        )
        questions = questions[:max_questions]
        allowed_modules = {question.module for question in questions}
        loaded_modules = [module_id for module_id in loaded_modules if module_id in allowed_modules]

    if loaded_modules == list(plan.loaded_modules) and questions == list(plan.questions):
        return plan

    return DiscoveryPlan(
        business_dnas=list(plan.business_dnas),
        loaded_modules=loaded_modules,
        questions=questions,
    )


def run_business_intelligence_stage(context=None, bundle=None):
    if context is not None:
        set_context(context)

    if bundle is None:
        bundle = _load_saved_business_intelligence_bundle(context)
    if bundle is None:
        bundle = run_business_understanding_stage(context=context)

    business_classification = _canonicalize_business_classification(
        validate_business_understanding_bundle(bundle)
    )
    planner = QuestionPlanner()
    plan = planner.build_plan(business_classification)
    plan = _apply_bi_test_caps(plan)

    intelligence_dir = getattr(context, "intelligence_dir", None)
    if intelligence_dir is None:
        from core.context_paths import intelligence_path  # noqa: E402
        intelligence_dir = Path(str(intelligence_path("", context_dir="intelligence_dir")))

    intelligence_dir.mkdir(parents=True, exist_ok=True)

    def _write_json(filename, payload):
        path = intelligence_dir / filename
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    _write_json("discovery_plan.json", plan.to_dict())

    runtime = DiscoveryRuntime(
        retriever=_build_runtime_retriever(context),
        extractor=_build_runtime_extractor(),
    )
    runtime_classification = {
        **business_classification,
    }
    if context is not None:
        runtime_classification = {
            "company": context.company,
            "year": context.year,
            **runtime_classification,
        }
    result = runtime.run(plan, business_classification=runtime_classification)

    _write_json("module_results.json", {"module_results": [item.to_dict() for item in result.module_results]})
    _write_json("discovery_runtime.json", result.to_dict())

    print("[BUSINESS INTELLIGENCE]")
    print(f"Business DNAs: {', '.join(business_classification.get('business_dnas', [])) or 'None'}")
    print(f"Modules Loaded: {len(plan.loaded_modules)}")
    print(f"Questions Asked: {result.statistics.questions_asked}")
    print(f"Questions Answered: {result.statistics.questions_answered}")
    print(f"Questions Not Found: {result.statistics.questions_not_found}")
    print(f"LLM Calls: {result.statistics.llm_calls}")
    print(f"Retrieved Chunks: {result.statistics.retrieved_chunks}")
    print(f"Execution Time: {result.statistics.execution_time_seconds:.3f}s")

    return result


def run_discovery(context=None):
    if context is not None:
        set_context(context)
        _ensure_discovery_index(context)
    run_steps(
        *STAGES["discovery"]
    )


def run_extraction(context=None):
    if context is not None:
        set_context(context)
    run_steps(
        *STAGES["extraction"]
    )


def run_cleaning(context=None):
    if context is not None:
        set_context(context)
    run_steps(
        *STAGES["cleaning"]
    )


def run_intelligence(context=None):
    if context is not None:
        set_context(context)
    run_steps(
        *STAGES["intelligence"]
    )


def run_company_memory_stage(company, context=None):
    if context is not None:
        set_context(context)
    builder = CompanyMemoryAggregateBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory"
    print("[COMPANY MEMORY]")
    print(f"Company: {company}")
    print(f"Output Dir: {output_dir}")
    print(f"Artifacts Written: {len(written_paths)}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_cim_stage(company, context=None):
    if context is not None:
        set_context(context)
    builder = CIMContractBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory"
    print("[CIM / PCIM]")
    print(f"Company: {company}")
    print(f"Output Dir: {output_dir}")
    print(f"Artifacts Written: {len(written_paths)}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_investor_panel_stage(company, analyst=None, context=None):
    if context is not None:
        set_context(context)
    runner = InvestorPanelRunner(company=company)
    written_paths = runner.run(analyst=analyst)
    output_dir = Path("companies") / company / "company_memory" / "investor_panel"
    print("[INVESTOR PANEL]")
    print(f"Company: {company}")
    print(f"Analyst: {analyst or 'all'}")
    print(f"Output Dir: {output_dir}")
    print(f"Artifacts Written: {len(written_paths)}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_all(context=None):
    if context is not None:
        set_context(context)

    bundle = run_business_understanding_stage(context=context)
    run_business_intelligence_stage(context=context, bundle=bundle)
    run_discovery(context=context)
    run_extraction(context=context)
    run_cleaning(context=context)
    run_intelligence(context=context)


def build_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "company"
    )

    parser.add_argument(
        "year",
        nargs="?",
    )

    parser.add_argument(
        "--stage",
        choices=[
            "all",
            "business_understanding",
            "business_intelligence",
            "company_memory",
            "cim",
            "pcim",
            "investor_panel",
            "discovery",
            "extraction",
            "cleaning",
            "intelligence",
        ],
        default="all",
    )
    parser.add_argument(
        "--analyst",
        choices=["graham", "fisher", "buffett", "munger", "lynch"],
        default=None,
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.stage not in {"company_memory", "cim", "pcim", "investor_panel"} and not args.year:
        parser.error("year is required unless --stage company_memory, --stage cim, --stage pcim, or --stage investor_panel is used")

    context = None
    if args.year:
        context = CompanyContext(
            company=args.company,
            year=args.year,
        )
        context.create_directories()
        set_context(context)

    if args.stage == "all":
        run_all(context=context)
    elif args.stage == "business_understanding":
        run_business_understanding_stage(context=context)
    elif args.stage == "business_intelligence":
        run_business_intelligence_stage(context=context)
    elif args.stage == "company_memory":
        run_company_memory_stage(company=args.company, context=context)
    elif args.stage in {"cim", "pcim"}:
        run_cim_stage(company=args.company, context=context)
    elif args.stage == "investor_panel":
        run_investor_panel_stage(company=args.company, analyst=args.analyst, context=context)
    elif args.stage == "discovery":
        run_discovery(context=context)
    elif args.stage == "extraction":
        run_extraction(context=context)
    elif args.stage == "cleaning":
        run_cleaning(context=context)
    elif args.stage == "intelligence":
        run_intelligence(context=context)

    if context is not None:
        print(
            f"Raw: {context.raw_dir}"
        )

        print(
            f"Extracted: {context.extracted_dir}"
        )

        print(
            f"Intelligence: {context.intelligence_dir}"
        )


if __name__ == "__main__":
    main()
