import argparse
import json
import os
import sys
import time
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.company_context import CompanyContext  # noqa: E402
from pipelines.pipeline_context import get_context, set_context  # noqa: E402
from knowledge.ai import get_llm  # noqa: E402
from knowledge.ai.input_packs import call_llm_with_input_pack  # noqa: E402
from knowledge.business_understanding import run_business_understanding  # noqa: E402
from knowledge.discovery_runtime import DiscoveryRuntime  # noqa: E402
from knowledge.module_extractor import ModuleExtractor  # noqa: E402
from knowledge.question_engine import QuestionPlanner  # noqa: E402
from knowledge.question_engine import QuestionRegistry  # noqa: E402
from knowledge.retrieval.retriever import HybridRetriever  # noqa: E402
from knowledge.company_memory import CompanyMemoryAggregateBuilder, MultiYearCompanyMemoryBuilder  # noqa: E402
from knowledge.cim_contract import CIMContractBuilder  # noqa: E402
from knowledge.business_identity import ensure_business_identity_contract  # noqa: E402
from intelligence.investor_panel import (  # noqa: E402
    CommitteeBriefRenderer,
    CommitteeBriefQAGate,
    InvestmentCommitteeSynthesizer,
    InvestorBriefBuilder,
    InvestorPanelRunner,
    find_forbidden_recommendation_language,
)
from embeddings.index_builder import ensure_company_year_index, indexed_chunk_count  # noqa: E402
from scripts.pdf_reader import extract_pages  # noqa: E402
from scripts.smart_chunker import chunk_pages  # noqa: E402
from knowledge.question_engine.schema import DiscoveryPlan  # noqa: E402


SUPPORTED_RAW_DOC_SUFFIXES = {".pdf", ".txt", ".md"}
INDEXABLE_RAW_DOC_SUFFIXES = {".pdf"}
DISCOVERY_OUTPUT_FILES = [
    "project_discovery_results.json",
    "promise_discovery_results.json",
    "risk_discovery_results.json",
    "capacity_discovery_results.json",
    "capital_allocation_discovery_results.json",
    "initiative_discovery_results.json",
]
EXTRACTION_OUTPUT_FILES = [
    "extracted_projects.json",
    "extracted_promises.json",
    "extracted_risks.json",
    "extracted_capacity.json",
    "extracted_capital_allocation.json",
    "extracted_initiatives.json",
]
CLEANING_OUTPUT_FILES = [
    "clean_projects.json",
    "clean_promises.json",
    "clean_risks.json",
    "clean_capacity.json",
    "clean_capital_allocation.json",
    "clean_initiatives.json",
]
BUSINESS_UNDERSTANDING_OUTPUT_FILES = [
    "business_blueprint.json",
    "business_classification.json",
]
BUSINESS_INTELLIGENCE_OUTPUT_FILES = [
    "discovery_plan.json",
    "module_results.json",
    "discovery_runtime.json",
]
INTELLIGENCE_OUTPUT_FILES = [
    "company_intelligence.json",
    "management_summary.json",
]
ALL_STAGE_SEQUENCE = [
    "preflight",
    "discovery",
    "extraction",
    "cleaning",
    "business_understanding",
    "business_intelligence",
    "intelligence",
    "cim",
    "pcim",
    "multi_year_memory",
]
YEAR_REQUIRED_STAGES = {
    "all",
    "business_understanding",
    "business_intelligence",
    "discovery",
    "extraction",
    "cleaning",
    "intelligence",
}
COMPANY_LEVEL_STAGES = {
    "company_memory",
    "multi_year_memory",
    "cim",
    "pcim",
    "investor_panel",
    "investor_briefs",
    "committee_synthesis",
    "committee_brief",
    "committee_brief_qa",
    "panel",
}
STAGE_CATALOG = {
    "all": {
        "description": "Runs the canonical year-level pipeline in dependency order.",
        "requires": ["company", "year", "raw annual report", "non-empty chunks"],
        "outputs": ["run_summary.json", "year intelligence artifacts", "cim_v1.json", "pcim_v1.json"],
        "llm_calls": True,
        "scope": "company/year",
        "year_required": True,
    },
    "preflight": {
        "description": "Validates raw documents, extractable text, chunks, and index readiness.",
        "requires": ["company", "year", "raw annual report PDF", "extractable text"],
        "outputs": ["clean_chunks.json", "active company/year index"],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "business_understanding": {
        "description": "Builds business blueprint and business classification from cleaned artifacts.",
        "requires": ["cleaned extracted artifacts"],
        "outputs": BUSINESS_UNDERSTANDING_OUTPUT_FILES,
        "llm_calls": True,
        "scope": "company/year",
        "year_required": True,
    },
    "business_intelligence": {
        "description": "Plans archetype-native questions, retrieves evidence, and writes runtime outputs.",
        "requires": ["business_understanding outputs", "clean chunks / retrieval index"],
        "outputs": BUSINESS_INTELLIGENCE_OUTPUT_FILES,
        "llm_calls": True,
        "scope": "company/year",
        "year_required": True,
    },
    "company_memory": {
        "description": "Builds company-level aggregate memory from yearly intelligence snapshots.",
        "requires": ["at least one valid yearly intelligence snapshot"],
        "outputs": ["companies/<company>/company_memory/*"],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "multi_year_memory": {
        "description": "Builds deterministic cross-year company-memory artifacts.",
        "requires": ["at least one valid yearly intelligence snapshot"],
        "outputs": ["companies/<company>/company_memory/multi_year/*"],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "cim": {
        "description": "Builds company-level CIM and PCIM from yearly intelligence snapshots.",
        "requires": ["at least one valid yearly intelligence snapshot"],
        "outputs": ["cim_v1.json", "pcim_v1.json"],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "pcim": {
        "description": "Alias for CIM/PCIM build; writes pcim_v1.json alongside cim_v1.json.",
        "requires": ["at least one valid yearly intelligence snapshot"],
        "outputs": ["pcim_v1.json"],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "investor_panel": {
        "description": "Runs one analyst or all analysts from PCIM.",
        "requires": ["company_memory/pcim_v1.json"],
        "outputs": ["companies/<company>/company_memory/investor_panel/*_analysis.json"],
        "llm_calls": True,
        "scope": "company",
        "year_required": False,
    },
    "investor_briefs": {
        "description": "Renders user-facing analyst briefs from saved analyst JSON files.",
        "requires": ["investor_panel analyst outputs"],
        "outputs": ["companies/<company>/company_memory/investor_panel/briefs/*"],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "committee_synthesis": {
        "description": "Builds committee_synthesis.json from analyst outputs.",
        "requires": ["investor_panel analyst outputs"],
        "outputs": ["committee_synthesis.json"],
        "llm_calls": True,
        "scope": "company",
        "year_required": False,
    },
    "committee_brief": {
        "description": "Renders committee brief markdown from committee_synthesis.json.",
        "requires": ["committee_synthesis.json"],
        "outputs": ["committee_brief.md", "committee_brief_qa.json"],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "committee_brief_qa": {
        "description": "Runs deterministic QA gate on committee brief output.",
        "requires": ["committee_synthesis.json", "committee_brief.md"],
        "outputs": ["committee_brief_qa.json"],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "panel": {
        "description": "Runs the full investor panel, committee synthesis, brief render, and brief QA chain.",
        "requires": ["company_memory/pcim_v1.json"],
        "outputs": [
            "companies/<company>/company_memory/investor_panel/*_analysis.json",
            "committee_synthesis.json",
            "committee_brief.md",
            "committee_brief_qa.json",
            "panel_run_summary.json",
        ],
        "llm_calls": True,
        "scope": "company",
        "year_required": False,
    },
    "discovery": {
        "description": "Builds company/year retrieval index and writes discovery candidate files.",
        "requires": ["raw annual report PDF", "extractable text", "non-empty chunks"],
        "outputs": DISCOVERY_OUTPUT_FILES,
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "extraction": {
        "description": "Runs LLM extractors over discovery candidates.",
        "requires": ["non-empty discovery outputs"],
        "outputs": EXTRACTION_OUTPUT_FILES,
        "llm_calls": True,
        "scope": "company/year",
        "year_required": True,
    },
    "cleaning": {
        "description": "Cleans extracted records into canonical cleaned artifacts.",
        "requires": ["non-empty extraction outputs"],
        "outputs": CLEANING_OUTPUT_FILES,
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "intelligence": {
        "description": "Builds company intelligence and management summary artifacts from cleaned and business outputs.",
        "requires": ["cleaned artifacts", "business_understanding outputs", "business_intelligence outputs"],
        "outputs": INTELLIGENCE_OUTPUT_FILES,
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
}


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
        _require_nonempty_stage_inputs(
            "business_understanding",
            context.extracted_dir,
            CLEANING_OUTPUT_FILES,
            "cleaned",
        )
    if context is None:
        return run_business_understanding()
    return run_business_understanding(context=context)


def _iter_raw_document_candidates(context):
    seen = set()
    candidates = []

    if context is not None and context.raw_dir.exists():
        for path in sorted(context.raw_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_RAW_DOC_SUFFIXES:
                continue
            if path.name in seen:
                continue
            seen.add(path.name)
            candidates.append(path)

    legacy_candidates = [
        Path("data/annual_reports") / f"{context.company}_{context.year}.pdf",
        Path("data/annual_reports") / f"{context.company}_{context.year}.txt",
        Path("data/annual_reports") / f"{context.company}_{context.year}.md",
    ]

    normalized_year = str(context.year).lower()
    if normalized_year.startswith("fy") and len(normalized_year) > 2:
        year_suffix = normalized_year[-2:]
        legacy_candidates.extend(
            [
                Path("data/annual_reports") / f"{context.company}_fy{year_suffix}.pdf",
                Path("data/annual_reports") / f"{context.company}_fy{year_suffix}.txt",
                Path("data/annual_reports") / f"{context.company}_fy{year_suffix}.md",
            ]
        )

    for candidate in legacy_candidates:
        if candidate.exists() and candidate.name not in seen:
            seen.add(candidate.name)
            candidates.append(candidate)

    return candidates


def _resolve_annual_report_path(context):
    candidates = _iter_raw_document_candidates(context)
    pdf_candidates = [candidate for candidate in candidates if candidate.suffix.lower() == ".pdf"]
    if pdf_candidates:
        return pdf_candidates[0]
    if candidates:
        return candidates[0]
    return context.raw_dir / f"{context.company}_{context.year}.pdf"


def _read_text_from_document(path):
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        pages = extract_pages(path)
        return "\n".join((page.get("text") or "") for page in pages).strip()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8").strip()
    return ""


def _load_json_payload(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _payload_signal_count(payload):
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return sum(1 for value in payload.values() if value not in (None, "", [], {}))
    return 0


def _count_json_items(path):
    payload = _load_json_payload(path)
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        if "module_results" in payload and isinstance(payload["module_results"], list):
            return len(payload["module_results"])
        return _payload_signal_count(payload)
    return 0


def _artifact_counts(directory, filenames):
    counts = {}
    for filename in filenames:
        counts[filename] = _count_json_items(directory / filename)
    return counts


def _require_nonempty_stage_inputs(stage_name, directory, filenames, noun):
    counts = _artifact_counts(directory, filenames)
    missing = [filename for filename, count in counts.items() if count == 0]
    total = sum(counts.values())
    if total <= 0:
        raise RuntimeError(
            f"{stage_name} requires non-empty {noun} inputs, but none were found in {directory}"
        )
    return counts, missing


def _ensure_context(stage_name, context):
    if context is None:
        raise RuntimeError(f"{stage_name} requires a company/year context")
    return context


def _valid_years_for_company(company):
    company_root = Path("companies") / company
    valid_years = []
    for year_dir in sorted(company_root.iterdir()) if company_root.exists() else []:
        if not year_dir.is_dir() or not year_dir.name.lower().startswith("fy"):
            continue
        intelligence_dir = year_dir / "intelligence"
        company_intelligence = _load_json_payload(intelligence_dir / "company_intelligence.json")
        business_classification = _load_json_payload(intelligence_dir / "business_classification.json")
        if isinstance(company_intelligence, dict) and company_intelligence and isinstance(business_classification, dict) and business_classification:
            valid_years.append(year_dir.name)
    return valid_years


def _require_company_level_intelligence(company, stage_name):
    valid_years = _valid_years_for_company(company)
    if not valid_years:
        raise RuntimeError(
            f"{stage_name} requires at least one valid yearly intelligence snapshot for {company}"
        )
    warnings = []
    if len(valid_years) == 1:
        warnings.append(
            f"{stage_name}: only one valid year is available for {company}; multi-year conclusions remain limited"
        )
    return valid_years, warnings


def _run_preflight(context):
    context = _ensure_context("preflight", context)
    context.create_directories()

    raw_docs = _iter_raw_document_candidates(context)
    if not raw_docs:
        raise RuntimeError(
            f"No raw documents found for {context.company} {context.year}. "
            f"Place the annual report PDF in: {context.raw_dir}"
        )

    extractable_docs = []
    for path in raw_docs:
        text = _read_text_from_document(path)
        if text:
            extractable_docs.append(path)

    if not extractable_docs:
        raise RuntimeError(
            "Raw documents found, but no extractable text was produced. "
            "The PDF may be scanned/image-only or unsupported."
        )

    pdf_docs = [path for path in extractable_docs if path.suffix.lower() in INDEXABLE_RAW_DOC_SUFFIXES]
    if not pdf_docs:
        raise RuntimeError(
            f"Discovery requires at least one PDF annual report for {context.company} {context.year}. "
            f"Checked: {context.raw_dir} and data/annual_reports"
        )

    chunk_path = _ensure_clean_chunks(context)
    chunk_count = _count_json_items(chunk_path)
    if chunk_count <= 0:
        raise RuntimeError(
            f"Raw documents found for {context.company} {context.year}, but chunk generation produced 0 chunks."
        )

    indexed_count = _ensure_discovery_index(context)
    if indexed_count <= 0:
        raise RuntimeError(
            f"Index building produced 0 chunks for {context.company} {context.year}; discovery cannot continue."
        )

    return {
        "raw_documents": [str(path) for path in raw_docs],
        "extractable_documents": [str(path) for path in extractable_docs],
        "chunk_output": str(chunk_path),
        "chunk_count": chunk_count,
        "indexed_chunk_count": indexed_count,
    }


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
    context = get_context()

    def ai_adapter(prompt: str, *, llm_input_pack=None) -> str:
        response = call_llm_with_input_pack(
            llm=llm,
            prompt=prompt,
            input_pack=llm_input_pack,
            manifest_path=(
                context.intelligence_dir / "business_intelligence_llm_call_manifest.json"
                if context is not None
                else None
            ),
            require_source_artifacts=True,
            response_schema={"type": "object"},
        )
        return response.text

    return ModuleExtractor(
        llm_client=ai_adapter,
        manifest_path=(
            context.intelligence_dir / "business_intelligence_llm_call_manifest.json"
            if context is not None
            else None
        ),
    )


def _ensure_discovery_index(context):
    annual_report_path = _resolve_annual_report_path(context)
    if not annual_report_path.exists():
        raise FileNotFoundError(f"Annual report not found: {annual_report_path}")
    if annual_report_path.suffix.lower() not in INDEXABLE_RAW_DOC_SUFFIXES:
        raise RuntimeError(
            f"Discovery indexing requires a PDF annual report, but found: {annual_report_path.name}"
        )

    chunk_path = _ensure_clean_chunks(context)
    chunk_count = _count_json_items(chunk_path)
    if chunk_count <= 0:
        raise RuntimeError(
            f"Chunk generation produced 0 chunks for {context.company} {context.year}; discovery cannot continue."
        )

    indexed_count = ensure_company_year_index(
        pdf_path=annual_report_path,
        company=context.company,
        year=context.year,
        document_type="annual_report",
    )

    if indexed_count <= 0:
        indexed_count = indexed_chunk_count(
            company=context.company,
            year=context.year,
            document_type="annual_report",
        )
    if indexed_count <= 0:
        raise RuntimeError(
            f"Index building produced 0 chunks for {context.company} {context.year}; discovery cannot continue."
        )

    print(
        f"[DISCOVERY] Active company/year index ready: "
        f"{context.company} {context.year} ({indexed_count} chunks)"
    )
    return indexed_count


def validate_business_understanding_bundle(bundle):
    if not isinstance(bundle, dict):
        raise ValueError("Business Understanding stage did not return a bundle")

    business_blueprint = bundle.get("business_blueprint")
    if "business_classification" not in bundle:
        raise ValueError("Business Understanding bundle is missing business_classification")

    business_classification = bundle["business_classification"]
    if not isinstance(business_classification, dict) or not business_classification:
        raise ValueError("Business Understanding bundle contains an invalid business_classification")

    ensure_business_identity_contract(
        business_blueprint,
        business_classification,
        require_classification=True,
    )

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

    blueprint = None
    blueprint_path = context.intelligence_dir / "business_blueprint.json"
    if blueprint_path.exists():
        try:
            blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            blueprint = None

    ensure_business_identity_contract(
        blueprint,
        business_classification,
        require_classification=True,
    )

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
        _require_nonempty_stage_inputs(
            "business_intelligence",
            context.extracted_dir,
            CLEANING_OUTPUT_FILES,
            "cleaned",
        )

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
    context = _ensure_context("discovery", context)
    set_context(context)
    _run_preflight(context)
    run_steps(
        *STAGES["discovery"]
    )
    counts = _artifact_counts(context.raw_dir, DISCOVERY_OUTPUT_FILES)
    total = sum(counts.values())
    if total <= 0:
        raise RuntimeError(
            f"Discovery produced zero candidates for {context.company} {context.year}; failing before extraction."
        )
    return counts


def run_extraction(context=None):
    context = _ensure_context("extraction", context)
    set_context(context)
    _require_nonempty_stage_inputs(
        "extraction",
        context.raw_dir,
        DISCOVERY_OUTPUT_FILES,
        "discovery",
    )
    run_steps(
        *STAGES["extraction"]
    )
    counts = _artifact_counts(context.extracted_dir, EXTRACTION_OUTPUT_FILES)
    if sum(counts.values()) <= 0:
        raise RuntimeError(
            f"Extraction produced zero records for {context.company} {context.year}; failing before cleaning."
        )
    return counts


def run_cleaning(context=None):
    context = _ensure_context("cleaning", context)
    set_context(context)
    _require_nonempty_stage_inputs(
        "cleaning",
        context.extracted_dir,
        EXTRACTION_OUTPUT_FILES,
        "extraction",
    )
    run_steps(
        *STAGES["cleaning"]
    )
    counts = _artifact_counts(context.extracted_dir, CLEANING_OUTPUT_FILES)
    if sum(counts.values()) <= 0:
        raise RuntimeError(
            f"Cleaning produced zero usable records for {context.company} {context.year}; failing before downstream intelligence."
        )
    return counts


def run_intelligence(context=None):
    context = _ensure_context("intelligence", context)
    set_context(context)
    _require_nonempty_stage_inputs(
        "intelligence",
        context.extracted_dir,
        CLEANING_OUTPUT_FILES,
        "cleaned",
    )
    _require_nonempty_stage_inputs(
        "intelligence",
        context.intelligence_dir,
        BUSINESS_UNDERSTANDING_OUTPUT_FILES,
        "business_understanding",
    )
    _require_nonempty_stage_inputs(
        "intelligence",
        context.intelligence_dir,
        BUSINESS_INTELLIGENCE_OUTPUT_FILES,
        "business_intelligence",
    )
    run_steps(
        *STAGES["intelligence"]
    )
    counts = _artifact_counts(context.intelligence_dir, INTELLIGENCE_OUTPUT_FILES)
    if sum(counts.values()) <= 0:
        raise RuntimeError(
            f"Intelligence produced no usable artifacts for {context.company} {context.year}."
        )
    return counts


def run_company_memory_stage(company, context=None):
    if context is not None:
        set_context(context)
    valid_years, warnings = _require_company_level_intelligence(company, "company_memory")
    builder = CompanyMemoryAggregateBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory"
    print("[COMPANY MEMORY]")
    print(f"Company: {company}")
    print(f"Valid Years: {', '.join(valid_years)}")
    print(f"Output Dir: {output_dir}")
    print(f"Artifacts Written: {len(written_paths)}")
    for warning in warnings:
        print(f"Warning: {warning}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_cim_stage(company, context=None):
    if context is not None:
        set_context(context)
    valid_years, warnings = _require_company_level_intelligence(company, "cim/pcim")
    builder = CIMContractBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory"
    print("[CIM / PCIM]")
    print(f"Company: {company}")
    print(f"Valid Years: {', '.join(valid_years)}")
    print(f"Output Dir: {output_dir}")
    print(f"Artifacts Written: {len(written_paths)}")
    for warning in warnings:
        print(f"Warning: {warning}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_multi_year_memory_stage(company, context=None):
    if context is not None:
        set_context(context)
    valid_years, warnings = _require_company_level_intelligence(company, "multi_year_memory")
    builder = MultiYearCompanyMemoryBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory" / "multi_year"
    print("[MULTI-YEAR MEMORY]")
    print(f"Company: {company}")
    print(f"Valid Years: {', '.join(valid_years)}")
    print(f"Output Dir: {output_dir}")
    print(f"Artifacts Written: {len(written_paths)}")
    for warning in warnings:
        print(f"Warning: {warning}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_investor_panel_stage(company, analyst=None, context=None):
    if context is not None:
        set_context(context)
    pcim_path = Path("companies") / company / "company_memory" / "pcim_v1.json"
    if not pcim_path.exists():
        raise RuntimeError(f"investor_panel requires PCIM: {pcim_path}")
    pcim_payload = json.loads(pcim_path.read_text(encoding="utf-8"))
    source_manifest = pcim_payload.get("pcim_source_manifest") or {}
    manifest_status = source_manifest.get("status")
    if manifest_status == "fail":
        raise RuntimeError(
            "investor_panel requires a usable PCIM source manifest; "
            f"current status is fail for {pcim_path}"
        )
    if manifest_status == "warning":
        print("[INVESTOR PANEL] Warning: PCIM source manifest status is warning.")
        for warning in source_manifest.get("stale_source_warnings", []):
            print(f"Warning: {warning}")
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


def run_investor_briefs_stage(company, context=None):
    if context is not None:
        set_context(context)
    builder = InvestorBriefBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory" / "investor_panel" / "briefs"
    print("[INVESTOR BRIEFS]")
    print(f"Company: {company}")
    print(f"Output Dir: {output_dir}")
    print(f"Artifacts Written: {len(written_paths)}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_committee_synthesis_stage(company, context=None, cleanup_only=False):
    if context is not None:
        set_context(context)
    panel_dir = Path("companies") / company / "company_memory" / "investor_panel"
    analyst_paths = [panel_dir / f"{analyst}_analysis.json" for analyst in ("graham", "buffett", "fisher", "munger", "lynch")]
    if not any(path.exists() for path in analyst_paths):
        raise RuntimeError(f"committee_synthesis requires analyst outputs in {panel_dir}")
    synthesizer = InvestmentCommitteeSynthesizer(company=company)
    written_path = synthesizer.run(cleanup_only=cleanup_only)
    output_dir = Path("companies") / company / "company_memory" / "investor_panel"
    print("[COMMITTEE SYNTHESIS]")
    print(f"Company: {company}")
    print(f"Mode: {'cleanup-only' if cleanup_only else 'generate+cleanup'}")
    print(f"Output Dir: {output_dir}")
    print("Artifacts Written: 1")
    print(f"- {written_path.name}")
    return {"committee_synthesis.json": written_path}


def run_committee_brief_stage(company, context=None, include_evidence_ids=False):
    if context is not None:
        set_context(context)
    synthesis_path = Path("companies") / company / "company_memory" / "investor_panel" / "committee_synthesis.json"
    if not synthesis_path.exists():
        raise RuntimeError(f"committee_brief requires committee_synthesis.json: {synthesis_path}")
    builder = CommitteeBriefRenderer(company=company)
    written_paths = builder.build(include_evidence_ids=include_evidence_ids)
    qa_builder = CommitteeBriefQAGate(company=company)
    written_paths.update(qa_builder.build(include_evidence_ids=include_evidence_ids))
    output_dir = Path("companies") / company / "company_memory" / "investor_panel"
    print("[COMMITTEE BRIEF]")
    print(f"Company: {company}")
    print(f"Include Evidence IDs: {'yes' if include_evidence_ids else 'no'}")
    print(f"Output Dir: {output_dir}")
    print(f"Artifacts Written: {len(written_paths)}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_committee_brief_qa_stage(company, context=None, include_evidence_ids=False):
    if context is not None:
        set_context(context)
    panel_dir = Path("companies") / company / "company_memory" / "investor_panel"
    synthesis_path = panel_dir / "committee_synthesis.json"
    brief_path = panel_dir / "committee_brief.md"
    if not synthesis_path.exists() or not brief_path.exists():
        raise RuntimeError(
            f"committee_brief_qa requires committee_synthesis.json and committee_brief.md in {panel_dir}"
        )
    builder = CommitteeBriefQAGate(company=company)
    written_paths = builder.build(include_evidence_ids=include_evidence_ids)
    output_dir = Path("companies") / company / "company_memory" / "investor_panel"
    print("[COMMITTEE BRIEF QA]")
    print(f"Company: {company}")
    print(f"Include Evidence IDs: {'yes' if include_evidence_ids else 'no'}")
    print(f"Output Dir: {output_dir}")
    print(f"Artifacts Written: {len(written_paths)}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def _panel_output_dir(company):
    return Path("companies") / company / "company_memory" / "investor_panel"


def _panel_summary_path(company):
    return _panel_output_dir(company) / "panel_run_summary.json"


def _load_json_file(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Required file missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON: {path}") from exc


def _status_rank(status):
    return {"pass": 0, "warning": 1, "fail": 2}.get(status, 2)


def _merge_status(current, new_status):
    return new_status if _status_rank(new_status) > _status_rank(current) else current


def _validate_analyst_output(company, analyst):
    panel_dir = _panel_output_dir(company)
    path = panel_dir / f"{analyst}_analysis.json"
    payload = _load_json_file(path)

    failures = []
    warnings = []

    if payload.get("doctrine_id") != analyst:
        failures.append(f"{analyst}: doctrine_id mismatch")
    for field in (
        "evidence_grounding_status",
        "historical_context_used",
        "years_considered",
        "supporting_pcim_sections",
        "user_facing_brief",
        "evidence_id_normalization",
    ):
        if field not in payload:
            failures.append(f"{analyst}: missing {field}")

    payload_text = json.dumps(payload, ensure_ascii=False)
    if "source_chunk" in payload_text:
        failures.append(f"{analyst}: source_chunk detected in saved output")
    forbidden_matches = find_forbidden_recommendation_language(payload_text)
    if forbidden_matches:
        matched_texts = ", ".join(
            sorted({str(item["matched_text"]) for item in forbidden_matches})
        )
        failures.append(
            f"{analyst}: forbidden recommendation language detected ({matched_texts})"
        )

    status = str(payload.get("evidence_grounding_status") or "").strip().lower()
    if status == "fail":
        failures.append(f"{analyst}: evidence_grounding_status=fail")

    normalization = payload.get("evidence_id_normalization") or {}
    unresolved_ids = list(normalization.get("unresolved_ids", []) or [])
    if unresolved_ids and status == "pass":
        failures.append(f"{analyst}: unresolved_ids present while status=pass")
    elif unresolved_ids:
        warnings.append(f"{analyst}: unresolved_ids present ({len(unresolved_ids)})")

    warning_count = len(payload.get("evidence_grounding_warnings", []) or [])
    analyst_status = "pass"
    if failures:
        analyst_status = "fail"
    elif status == "warning" or warning_count > 0:
        analyst_status = "warning"

    return {
        "status": analyst_status,
        "evidence_grounding_status": status,
        "warning_count": warning_count,
        "output": str(path),
        "warnings": warnings,
        "failures": failures,
    }


def _write_panel_run_summary(company, payload):
    path = _panel_summary_path(company)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def run_panel_stage(company, context=None, include_evidence_ids=False):
    if context is not None:
        set_context(context)

    panel_dir = _panel_output_dir(company)
    panel_dir.mkdir(parents=True, exist_ok=True)
    pcim_path = Path("companies") / company / "company_memory" / "pcim_v1.json"

    summary = {
        "company": company,
        "run_mode": "panel_v1",
        "status": "pass",
        "stages": [],
        "analysts": {},
        "committee": {
            "synthesis_status": "fail",
            "brief_status": "fail",
            "brief_qa_status": "fail",
        },
        "outputs": {},
        "warnings": [],
        "failures": [],
        "generated_at": None,
    }

    def record_stage(stage, status, output="", warnings=None, failures=None):
        warnings = list(warnings or [])
        failures = list(failures or [])
        summary["stages"].append(
            {
                "stage": stage,
                "status": status,
                "output": output,
                "warnings": warnings,
                "failures": failures,
            }
        )
        for item in warnings:
            if item not in summary["warnings"]:
                summary["warnings"].append(item)
        for item in failures:
            if item not in summary["failures"]:
                summary["failures"].append(item)
        summary["status"] = _merge_status(summary["status"], status)

    def finalize_and_raise(message):
        summary["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        summary_path = _write_panel_run_summary(company, summary)
        print(f"Panel Run — {company}")
        for stage in summary["stages"]:
            print(f"{stage['stage']}: {stage['status'].upper()}")
        print(f"Overall: {summary['status'].upper()}")
        print(f"Summary: {summary_path}")
        raise RuntimeError(message)

    pcim_failures = []
    pcim_warnings = []
    if not pcim_path.exists():
        pcim_failures.append(f"PCIM missing: {pcim_path}")
        record_stage("pcim_check", "fail", output=str(pcim_path), failures=pcim_failures)
        finalize_and_raise(pcim_failures[0])
    pcim_payload = _load_json_file(pcim_path)
    source_manifest = pcim_payload.get("pcim_source_manifest") or {}
    manifest_status = source_manifest.get("status")
    if manifest_status == "fail":
        pcim_failures.append(f"PCIM source manifest unusable: {pcim_path}")
        record_stage("pcim_check", "fail", output=str(pcim_path), failures=pcim_failures)
        finalize_and_raise(pcim_failures[0])
    if manifest_status == "warning":
        pcim_warnings.extend(source_manifest.get("stale_source_warnings", []))
        record_stage("pcim_check", "warning", output=str(pcim_path), warnings=pcim_warnings)
    else:
        record_stage("pcim_check", "pass", output=str(pcim_path))

    analyst_order = ["graham", "buffett", "fisher", "munger", "lynch"]
    for analyst in analyst_order:
        try:
            run_investor_panel_stage(company=company, analyst=analyst, context=context)
        except Exception as exc:
            record_stage(
                analyst,
                "fail",
                warnings=[],
                failures=[f"{analyst}: stage execution failed: {exc}"],
            )
            finalize_and_raise(f"Panel stopped: {analyst} analyst execution failed")
        result = _validate_analyst_output(company, analyst)
        summary["analysts"][analyst] = {
            "status": result["status"],
            "evidence_grounding_status": result["evidence_grounding_status"],
            "warning_count": result["warning_count"],
            "output": result["output"],
        }
        summary["outputs"][analyst] = result["output"]
        record_stage(
            analyst,
            result["status"],
            output=result["output"],
            warnings=result["warnings"],
            failures=result["failures"],
        )
        if result["status"] == "fail":
            finalize_and_raise(f"Panel stopped: {analyst} analyst validation failed")

    try:
        synthesis_paths = run_committee_synthesis_stage(company=company, context=context, cleanup_only=False)
    except Exception as exc:
        record_stage(
            "committee_synthesis",
            "fail",
            failures=[f"committee_synthesis: stage execution failed: {exc}"],
        )
        finalize_and_raise("Panel stopped: committee synthesis execution failed")
    synthesis_path = synthesis_paths["committee_synthesis.json"]
    synthesis_payload = _load_json_file(synthesis_path)
    synthesis_failures = []
    if "source_chunk" in json.dumps(synthesis_payload, ensure_ascii=False):
        synthesis_failures.append("committee_synthesis: source_chunk detected")
    normalization = synthesis_payload.get("evidence_id_normalization") or {}
    if "disagreement_type" not in json.dumps(synthesis_payload, ensure_ascii=False):
        synthesis_failures.append("committee_synthesis: disagreement_type missing")
    if list(normalization.get("unresolved_ids", []) or []):
        synthesis_failures.append("committee_synthesis: unresolved_ids remain after cleanup")
    synthesis_status = "fail" if synthesis_failures else "pass"
    summary["committee"]["synthesis_status"] = synthesis_status
    summary["outputs"]["committee_synthesis"] = str(synthesis_path)
    record_stage(
        "committee_synthesis",
        synthesis_status,
        output=str(synthesis_path),
        failures=synthesis_failures,
    )
    if synthesis_status == "fail":
        finalize_and_raise("Panel stopped: committee synthesis validation failed")

    try:
        brief_paths = run_committee_brief_stage(
            company=company,
            context=context,
            include_evidence_ids=include_evidence_ids,
        )
    except Exception as exc:
        record_stage(
            "committee_brief",
            "fail",
            failures=[f"committee_brief: stage execution failed: {exc}"],
        )
        finalize_and_raise("Panel stopped: committee brief execution failed")
    brief_path = brief_paths["committee_brief.md"]
    summary["committee"]["brief_status"] = "pass"
    summary["outputs"]["committee_brief"] = str(brief_path)
    record_stage("committee_brief", "pass", output=str(brief_path))

    try:
        qa_paths = run_committee_brief_qa_stage(
            company=company,
            context=context,
            include_evidence_ids=include_evidence_ids,
        )
    except Exception as exc:
        record_stage(
            "committee_brief_qa",
            "fail",
            failures=[f"committee_brief_qa: stage execution failed: {exc}"],
        )
        finalize_and_raise("Panel stopped: committee brief QA execution failed")
    qa_path = qa_paths["committee_brief_qa.json"]
    qa_payload = _load_json_file(qa_path)
    qa_status = str(qa_payload.get("status") or "fail").lower()
    summary["committee"]["brief_qa_status"] = qa_status
    summary["outputs"]["committee_brief_qa"] = str(qa_path)
    record_stage(
        "committee_brief_qa",
        qa_status,
        output=str(qa_path),
        warnings=list(qa_payload.get("warnings", []) or []),
        failures=list(qa_payload.get("failures", []) or []),
    )
    if qa_status != "pass":
        finalize_and_raise("Panel stopped: committee brief QA failed")

    summary["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary_path = _write_panel_run_summary(company, summary)
    summary["outputs"]["panel_run_summary"] = str(summary_path)

    print(f"Panel Run — {company}")
    print(f"PCIM: PASS")
    for analyst in analyst_order:
        print(f"{analyst.title()}: {summary['analysts'][analyst]['status'].upper()}")
    print(f"Committee synthesis: {summary['committee']['synthesis_status'].upper()}")
    print(f"Committee brief: {summary['committee']['brief_status'].upper()}")
    print(f"Committee brief QA: {summary['committee']['brief_qa_status'].upper()}")
    print(f"Overall: {summary['status'].upper()}")
    print("Outputs:")
    print("- committee_synthesis.json")
    print("- committee_brief.md")
    print("- committee_brief_qa.json")
    print("- panel_run_summary.json")

    _write_panel_run_summary(company, summary)
    return {"panel_run_summary.json": summary_path, **summary["outputs"]}


def run_all(context=None):
    context = _ensure_context("all", context)
    set_context(context)

    summary = {
        "company": context.company,
        "year": context.year,
        "run_mode": "all_v2",
        "status": "pass",
        "stages": [],
        "llm_calls_estimated": 0,
        "warnings": [],
        "failures": [],
        "generated_at": None,
    }

    def record_stage(stage_name, status, outputs=None, warnings=None, failures=None):
        outputs = list(outputs or [])
        warnings = list(warnings or [])
        failures = list(failures or [])
        summary["stages"].append(
            {
                "stage": stage_name,
                "status": status,
                "inputs_checked": list(STAGE_CATALOG.get(stage_name, {}).get("requires", [])),
                "outputs": outputs,
                "warnings": warnings,
                "failures": failures,
            }
        )
        if STAGE_CATALOG.get(stage_name, {}).get("llm_calls"):
            summary["llm_calls_estimated"] += 1
        for warning in warnings:
            if warning not in summary["warnings"]:
                summary["warnings"].append(warning)
        for failure in failures:
            if failure not in summary["failures"]:
                summary["failures"].append(failure)
        summary["status"] = _merge_status(summary["status"], status)

    def finalize_summary():
        summary["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        summary_path = context.year_root / "run_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary_path

    stage_outputs = {
        "preflight": lambda: [str(context.extracted_dir / "clean_chunks.json")],
        "discovery": lambda: [str(context.raw_dir / filename) for filename in DISCOVERY_OUTPUT_FILES],
        "extraction": lambda: [str(context.extracted_dir / filename) for filename in EXTRACTION_OUTPUT_FILES],
        "cleaning": lambda: [str(context.extracted_dir / filename) for filename in CLEANING_OUTPUT_FILES],
        "business_understanding": lambda: [str(context.intelligence_dir / filename) for filename in BUSINESS_UNDERSTANDING_OUTPUT_FILES],
        "business_intelligence": lambda: [str(context.intelligence_dir / filename) for filename in BUSINESS_INTELLIGENCE_OUTPUT_FILES],
        "intelligence": lambda: [str(context.intelligence_dir / filename) for filename in INTELLIGENCE_OUTPUT_FILES],
        "cim": lambda: [
            str(Path("companies") / context.company / "company_memory" / "cim_v1.json"),
            str(Path("companies") / context.company / "company_memory" / "pcim_v1.json"),
        ],
        "pcim": lambda: [str(Path("companies") / context.company / "company_memory" / "pcim_v1.json")],
        "multi_year_memory": lambda: [str(Path("companies") / context.company / "company_memory" / "multi_year" / "multi_year_index.json")],
    }

    try:
        _run_preflight(context)
        record_stage("preflight", "pass", outputs=stage_outputs["preflight"]())

        run_discovery(context=context)
        record_stage("discovery", "pass", outputs=stage_outputs["discovery"]())

        run_extraction(context=context)
        record_stage("extraction", "pass", outputs=stage_outputs["extraction"]())

        run_cleaning(context=context)
        record_stage("cleaning", "pass", outputs=stage_outputs["cleaning"]())

        bundle = run_business_understanding_stage(context=context)
        validate_business_understanding_bundle(bundle)
        if sum(_artifact_counts(context.intelligence_dir, BUSINESS_UNDERSTANDING_OUTPUT_FILES).values()) <= 0:
            raise RuntimeError("business_understanding produced no usable artifacts")
        record_stage("business_understanding", "pass", outputs=stage_outputs["business_understanding"]())

        run_business_intelligence_stage(context=context, bundle=bundle)
        if sum(_artifact_counts(context.intelligence_dir, BUSINESS_INTELLIGENCE_OUTPUT_FILES).values()) <= 0:
            raise RuntimeError("business_intelligence produced no usable artifacts")
        record_stage("business_intelligence", "pass", outputs=stage_outputs["business_intelligence"]())

        run_intelligence(context=context)
        record_stage("intelligence", "pass", outputs=stage_outputs["intelligence"]())

        _, cim_warnings = _require_company_level_intelligence(context.company, "cim/pcim")
        run_cim_stage(company=context.company, context=context)
        record_stage("cim", "pass", outputs=stage_outputs["cim"](), warnings=cim_warnings)
        record_stage("pcim", "pass", outputs=stage_outputs["pcim"]())

        _, multi_year_warnings = _require_company_level_intelligence(context.company, "multi_year_memory")
        run_multi_year_memory_stage(company=context.company, context=context)
        multi_year_status = "warning" if multi_year_warnings else "pass"
        record_stage(
            "multi_year_memory",
            multi_year_status,
            outputs=stage_outputs["multi_year_memory"](),
            warnings=multi_year_warnings,
        )
    except Exception as exc:
        current_stage = ALL_STAGE_SEQUENCE[len(summary["stages"])] if len(summary["stages"]) < len(ALL_STAGE_SEQUENCE) else "all"
        record_stage(current_stage, "fail", failures=[str(exc)])
        finalize_summary()
        raise

    finalize_summary()


def print_stage_catalog():
    for stage_name in [
        "all",
        "discovery",
        "extraction",
        "cleaning",
        "business_understanding",
        "business_intelligence",
        "intelligence",
        "company_memory",
        "cim",
        "pcim",
        "multi_year_memory",
        "investor_panel",
        "investor_briefs",
        "committee_synthesis",
        "committee_brief",
        "committee_brief_qa",
        "panel",
    ]:
        metadata = STAGE_CATALOG[stage_name]
        print(stage_name)
        print(f"  Description: {metadata['description']}")
        print(f"  Requires: {', '.join(metadata['requires'])}")
        print(f"  Writes: {', '.join(metadata['outputs'])}")
        print(f"  LLM calls: {'yes' if metadata['llm_calls'] else 'no'}")
        print(f"  Scope: {metadata['scope']}")
        print(f"  Year required: {'yes' if metadata['year_required'] else 'no'}")


def build_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "company",
        nargs="?",
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
            "multi_year_memory",
            "cim",
            "pcim",
            "investor_panel",
            "investor_briefs",
            "committee_synthesis",
            "committee_brief",
            "committee_brief_qa",
            "panel",
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
    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="For committee_synthesis, clean and canonicalize the existing artifact without an LLM call.",
    )
    parser.add_argument(
        "--include-evidence-ids",
        action="store_true",
        help="For committee_brief, append a compact Evidence References section.",
    )
    parser.add_argument(
        "--list-stages",
        action="store_true",
        help="Print stage descriptions, dependencies, outputs, and LLM usage.",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.list_stages:
        print_stage_catalog()
        return

    if not args.company:
        parser.error("company is required unless --list-stages is used")

    if args.stage in YEAR_REQUIRED_STAGES and not args.year:
        parser.error(f"year is required for --stage {args.stage}")
    if args.stage in COMPANY_LEVEL_STAGES and args.year:
        parser.error(f"--stage {args.stage} is company-level and does not accept a year argument")

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
    elif args.stage == "multi_year_memory":
        run_multi_year_memory_stage(company=args.company, context=context)
    elif args.stage in {"cim", "pcim"}:
        run_cim_stage(company=args.company, context=context)
    elif args.stage == "investor_panel":
        run_investor_panel_stage(company=args.company, analyst=args.analyst, context=context)
    elif args.stage == "investor_briefs":
        run_investor_briefs_stage(company=args.company, context=context)
    elif args.stage == "committee_synthesis":
        run_committee_synthesis_stage(company=args.company, context=context, cleanup_only=args.cleanup_only)
    elif args.stage == "committee_brief":
        run_committee_brief_stage(
            company=args.company,
            context=context,
            include_evidence_ids=args.include_evidence_ids,
        )
    elif args.stage == "committee_brief_qa":
        run_committee_brief_qa_stage(
            company=args.company,
            context=context,
            include_evidence_ids=args.include_evidence_ids,
        )
    elif args.stage == "panel":
        run_panel_stage(
            company=args.company,
            context=context,
            include_evidence_ids=args.include_evidence_ids,
        )
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
