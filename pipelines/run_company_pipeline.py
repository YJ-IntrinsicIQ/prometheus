import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.company_context import CompanyContext, CompanyMemoryContext  # noqa: E402
from core.context_paths import investor_panel_dir  # noqa: E402
from pipelines.pipeline_context import get_context, set_context  # noqa: E402
from knowledge.ai import get_llm  # noqa: E402
from knowledge.ai.input_packs import call_llm_with_input_pack  # noqa: E402
from knowledge.business_understanding import run_business_understanding  # noqa: E402
from knowledge.company_model import write_company_model  # noqa: E402
from knowledge.management_progression import write_management_progression  # noqa: E402
from intelligence.management_promises.builder import write_management_promise_tracker  # noqa: E402
from intelligence.management_promises.verification_bridge import build_verification_events  # noqa: E402
from intelligence.capital_allocation.builder import write_capital_allocation_outcome_tracker  # noqa: E402
from intelligence.strategy_evolution.builder import write_strategy_evolution_timeline  # noqa: E402
from intelligence.risk_evolution_timeline.builder import write_risk_evolution_timeline  # noqa: E402
from intelligence.management_credibility.builder import write_management_credibility_synthesis  # noqa: E402
from knowledge.discovery_runtime import DiscoveryRuntime  # noqa: E402
from knowledge.module_extractor import ModuleExtractor  # noqa: E402
from knowledge.module_extractor.schema import ModuleExtractionResult  # noqa: E402
from knowledge.question_engine import QuestionPlanner  # noqa: E402
from knowledge.question_engine import QuestionRegistry  # noqa: E402
from knowledge.retrieval.retriever import HybridRetriever  # noqa: E402
from knowledge.company_memory import CompanyMemoryAggregateBuilder, ManagementCommitmentsBuilder, MultiYearCompanyMemoryBuilder  # noqa: E402
from knowledge.company_memory.pcim_multi_year_builder import audit_saved_pcim_manifest  # noqa: E402
from knowledge.company_year_eligibility import (
    build_company_year_eligibility_manifest,
    eligible_company_years,
)
from knowledge.cim_contract import CIMContractBuilder  # noqa: E402
from knowledge.business_identity import ensure_business_identity_contract  # noqa: E402
from knowledge.artifact_audit import run_company_artifact_audit  # noqa: E402
from knowledge.evidence_layer import write_evidence_layer_summary  # noqa: E402
from knowledge.document_intake import build_document_intake_report, read_document_text  # noqa: E402
from intelligence.management_commentary import ManagementCommentaryBuilder  # noqa: E402
from intelligence.capital_allocation_outcomes import CapitalAllocationOutcomesBuilder  # noqa: E402
from intelligence.management_quality import ManagementQualityBuilder  # noqa: E402
from intelligence.investor_panel import (  # noqa: E402
    CommitteeBriefRenderer,
    CommitteeBriefQAGate,
    finalize_analyst_financial_warnings,
    finalize_analyst_validation_status,
    InvestmentCommitteeSynthesizer,
    InvestorBriefBuilder,
    InvestorPanelRunner,
    find_forbidden_recommendation_language,
)
from intelligence.ask_intrinsiciq import generate_ask_intrinsiciq_view  # noqa: E402
from intelligence.projects import ProjectsBuilder  # noqa: E402
from intelligence.capacity import CapacityEvolutionBuilder  # noqa: E402
from intelligence.risks import build_risk_evolution  # noqa: E402
from embeddings.index_builder import ensure_company_year_index, indexed_chunk_count  # noqa: E402
from scripts.pdf_reader import extract_pages  # noqa: E402
from scripts.smart_chunker import chunk_pages  # noqa: E402
from knowledge.question_engine.schema import DiscoveryPlan, QuestionModule  # noqa: E402
from knowledge.discovery_runtime.schema import DiscoveryResult, ExecutionStatistics  # noqa: E402
from knowledge.financials import (  # noqa: E402
    write_financial_memory_artifacts,
    write_financial_audit_report,
    write_financial_basis_resolution,
    write_financial_fact_registry,
    write_investor_financial_modules,
    write_financial_pcim_validation,
    write_financial_quality_scorecard,
    write_financial_driver_attribution,
    write_financial_memory_audit_report,
    write_financial_quality_summary,
    write_financial_reconciliation_report,
    write_financial_trends,
    write_shareholding_pattern,
    write_corporate_actions,
    write_financial_discovery,
    write_financial_extraction,
    write_financial_growth,
    write_normalized_fundamentals,
    write_financial_validation_report,
    write_financial_ratios,
)


SUPPORTED_RAW_DOC_SUFFIXES = {".pdf", ".txt", ".md"}
INDEXABLE_RAW_DOC_SUFFIXES = {".pdf"}
DISCOVERY_OUTPUT_FILES = [
    "project_discovery_results.json",
    "promise_discovery_results.json",
    "risk_discovery_results.json",
    "capacity_discovery_results.json",
    "capital_allocation_discovery_results.json",
    "initiative_discovery_results.json",
    "commentary_discovery_results.json",
]
EXTRACTION_OUTPUT_FILES = [
    "extracted_projects.json",
    "extracted_promises.json",
    "extracted_risks.json",
    "extracted_capacity.json",
    "extracted_capital_allocation.json",
    "extracted_initiatives.json",
    "extracted_commentary.json",
]
CLEANING_OUTPUT_FILES = [
    "clean_projects.json",
    "clean_promises.json",
    "clean_risks.json",
    "clean_capacity.json",
    "clean_capital_allocation.json",
    "clean_initiatives.json",
    "clean_commentary.json",
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
MANAGEMENT_COMMITMENTS_OUTPUT_FILES = [
    "management_commitments.json",
    "commitment_timeline.json",
    "commitment_validation.json",
    "management_commitments_manifest.json",
]
MANAGEMENT_COMMENTARY_OUTPUT_FILES = [
    "commentary_themes.json",
    "commentary_timelines.json",
    "commentary_assessments.json",
    "commentary_validation.json",
    "commentary_manifest.json",
]
PROJECTS_OUTPUT_FILES = [
    "projects_registry.json",
    "project_timelines.json",
    "project_assessments.json",
    "projects_validation.json",
    "projects_manifest.json",
]
CAPACITY_EVOLUTION_OUTPUT_FILES = [
    "capacity_registry.json",
    "capacity_timelines.json",
    "capacity_assessments.json",
    "capacity_validation.json",
    "capacity_manifest.json",
]
RISK_EVOLUTION_OUTPUT_FILES = [
    "risk_registry.json",
    "risk_timelines.json",
    "risk_assessments.json",
    "risk_validation.json",
    "risk_manifest.json",
]
FINANCIAL_DISCOVERY_OUTPUT_FILES = [
    "financial_discovery.json",
]
FINANCIAL_EXTRACTION_OUTPUT_FILES = [
    "raw_financial_tables.json",
]
FINANCIAL_NORMALIZATION_OUTPUT_FILES = [
    "normalized_fundamentals.json",
]
FINANCIAL_VALIDATION_OUTPUT_FILES = [
    "financial_validation_report.json",
]
FINANCIAL_RECONCILIATION_OUTPUT_FILES = [
    "financial_reconciliation_report.json",
]
FINANCIAL_BASIS_RESOLUTION_OUTPUT_FILES = [
    "financial_basis_resolution.json",
]
FINANCIAL_TRUTH_REGISTRY_OUTPUT_FILES = [
    "financial_fact_registry.json",
    "financial_truth_reconciliation_report.json",
    "financial_artifact_quarantine_report.json",
]
FINANCIAL_RATIO_OUTPUT_FILES = [
    "financial_ratios.json",
]
FINANCIAL_GROWTH_OUTPUT_FILES = [
    "financial_growth.json",
]
FINANCIAL_CORPORATE_ACTION_OUTPUT_FILES = [
    "corporate_actions.json",
    "corporate_action_rejections.json",
]
FINANCIAL_SHAREHOLDING_OUTPUT_FILES = [
    "shareholding_pattern.json",
    "shareholding_rejections.json",
]
FINANCIAL_AUDIT_OUTPUT_FILES = [
    "financial_audit_report.json",
]
FINANCIAL_TRENDS_OUTPUT_FILES = [
    "financial_trends.json",
]
FINANCIAL_QUALITY_OUTPUT_FILES = [
    "financial_quality_summary.json",
]
FINANCIAL_ATTRIBUTION_OUTPUT_FILES = [
    "financial_driver_attribution.json",
]
FINANCIAL_MEMORY_AUDIT_OUTPUT_FILES = [
    "financial_memory_audit_report.json",
]
FINANCIAL_PCIM_VALIDATION_OUTPUT_FILES = [
    "financial_pcim_validation.json",
]
FINANCIAL_MEMORY_OUTPUT_FILES = [
    "financial_year_index.json",
    "financial_memory_manifest.json",
    "financial_truth_pack.json",
    "financial_trends.json",
    "financial_quality_summary.json",
    "financial_quality_evolution.json",
    "capital_allocation_financial_timeline.json",
    "ownership_evolution.json",
    "financial_driver_attribution.json",
    "financial_memory_summary.json",
    "financial_memory_audit_report.json",
]
INVESTOR_FINANCIAL_MODULE_OUTPUT_FILES = [
    "owner_earnings_bridge.json",
    "capital_allocation_roi_ledger.json",
    "working_capital_quality_drilldown.json",
    "order_revenue_cash_conversion_tracker.json",
    "per_share_compounding_analysis.json",
    "investor_financial_modules_manifest.json",
]
CAPITAL_ALLOCATION_OUTCOMES_OUTPUT_FILES = [
    "capital_allocation_outcomes.json",
    "capital_allocation_timelines.json",
    "capital_allocation_assessments.json",
    "capital_allocation_validation.json",
    "capital_allocation_manifest.json",
]
MANAGEMENT_QUALITY_OUTPUT_FILES = [
    "management_quality_summary.json",
    "management_quality_dimensions.json",
    "management_quality_evidence.json",
    "management_quality_validation.json",
    "management_quality_manifest.json",
]
ASK_INTRINSICIQ_OUTPUT_FILES = [
    "company_research_view.json",
    "business_journey.json",
    "products_services.json",
    "answer_cards.json",
    "financial_visual_summaries.json",
    "uncertainty_map.json",
    "ask_intrinsiciq_manifest.json",
    "ask_intrinsiciq_validation_report.json",
]
COMPANY_MODEL_OUTPUT_FILES = [
    "company_model.json",
    "company_model_validation.json",
    "company_model_manifest.json",
]
MANAGEMENT_PROGRESSION_OUTPUT_FILES = [
    "management_progression.json",
    "management_progression_validation.json",
    "management_progression_manifest.json",
]
ALL_STAGE_SEQUENCE = [
    "preflight",
    "discovery",
    "extraction",
    "cleaning",
    "business_understanding",
    "business_intelligence",
    "intelligence",
    "multi_year_memory",
    "cim",
    "pcim",
]
COMPANY_YEAR_STAGE_SEQUENCE = [
    "preflight",
    "discovery",
    "extraction",
    "cleaning",
    "business_understanding",
    "business_intelligence",
    "intelligence",
    "financials",
    "financial_quality",
    "financial_basis_resolution",
    "financial_truth_registry",
    "financial_pcim_validation",
]
COMPANY_MEMORY_STAGE_SEQUENCE = [
    "company_memory",
    "multi_year_memory",
    "financial_trends",
    "financial_attribution",
    "financial_memory",
    "investor_financials",
    "cim",
    "pcim",
    "company_model",
    "management_progression",
    "management_commitments",
    "management_commentary",
    "capital_allocation_outcomes",
    "projects",
    "capacity_evolution",
    "risk_evolution",
    "management_quality",
    "audit",
    "panel",
    "panel_doctor",
    "investor_briefs",
    "ask_intrinsiciq",
]
PIPELINE_SCOPE_CLASSIFICATION = {
    "meta_only": ("all", "production", "company_year"),
    "company_year": {
        "sequence": COMPANY_YEAR_STAGE_SEQUENCE,
        "subsumed": (
            "financial_discovery",
            "financial_extraction",
            "financial_normalization",
            "financial_validation",
            "financial_reconciliation",
            "financial_ratios",
            "financial_growth",
            "corporate_actions",
            "shareholding_pattern",
        ),
        "rationale": "The year meta-stage owns the full year-scoped financial umbrella; leaf financial stages are executed inside financials.",
    },
    "company_memory": {
        "sequence": COMPANY_MEMORY_STAGE_SEQUENCE,
        "subsumed": (
            "investor_panel",
            "committee_synthesis",
            "committee_brief",
            "committee_brief_qa",
        ),
        "rationale": "The company-memory meta-stage owns the investor-panel umbrella; the committee leaf stages execute inside panel.",
    },
}
PRODUCTION_STAGE_SEQUENCE = [
    "preflight",
    "discovery",
    "extraction",
    "cleaning",
    "business_understanding",
    "business_intelligence",
    "intelligence",
    "financials",
    "multi_year_memory",
    "financial_memory",
    "investor_financials",
    "cim",
    "pcim",
    "financial_pcim_validation",
    "audit",
    "panel",
    "ask_intrinsiciq",
]
STAGE_SEQUENCE_PROFILES = {
    "all": ALL_STAGE_SEQUENCE,
    "company_year": COMPANY_YEAR_STAGE_SEQUENCE,
    "company_memory": COMPANY_MEMORY_STAGE_SEQUENCE,
    "production": PRODUCTION_STAGE_SEQUENCE,
}
# Stage scope sets are derived from STAGE_CATALOG after it is defined.
STAGE_CATALOG = {
    "all": {
        "description": "Runs the canonical year-level pipeline in dependency order.",
        "requires": ["company", "year", "raw annual report", "non-empty chunks"],
        "outputs": ["run_summary.json", "year intelligence artifacts", "cim_v1.json", "pcim_v1.json"],
        "llm_calls": True,
        "scope": "company/year",
        "year_required": True,
    },
    "company_year": {
        "description": "Runs the full company/year pipeline, including the canonical financial bundle and year-level truth outputs.",
        "requires": ["company", "year", "raw annual report", "non-empty chunks"],
        "outputs": [
            "run_summary.json",
            "year intelligence artifacts",
            "companies/<company>/<year>/financials/*",
        ],
        "llm_calls": True,
        "scope": "company/year",
        "year_required": True,
    },
    "production": {
        "description": "Runs the full customer-facing Ask IntrinsicIQ production pipeline in dependency order.",
        "requires": ["company", "year", "raw annual report", "auditable downstream company-memory outputs"],
        "outputs": [
            "run_summary.json",
            "year intelligence artifacts",
            "company_memory financials and investor panel artifacts",
            "company_memory ask_intrinsiciq/*",
        ],
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
    "financial_discovery": {
        "description": "Scans annual-report chunks to locate likely financial statement and note sections.",
        "requires": ["raw annual report or clean chunks"],
        "outputs": ["companies/<company>/<year>/financials/financial_discovery.json"],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "financial_extraction": {
        "description": "Extracts raw financial table rows from discovered financial statement and note sections.",
        "requires": ["financial_discovery.json", "clean_chunks.json"],
        "outputs": ["companies/<company>/<year>/financials/raw_financial_tables.json"],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "financial_normalization": {
        "description": "Maps raw financial rows into canonical normalized fundamentals with traceable field-level lineage.",
        "requires": ["raw_financial_tables.json"],
        "outputs": ["companies/<company>/<year>/financials/normalized_fundamentals.json"],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "financial_validation": {
        "description": "Validates normalized fundamentals for readiness before downstream ratio calculation.",
        "requires": ["normalized_fundamentals.json"],
        "outputs": ["companies/<company>/<year>/financials/financial_validation_report.json"],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "financial_reconciliation": {
        "description": "Checks normalized fundamentals for source relevance and value-type integrity before ratios and growth are calculated.",
        "requires": ["normalized_fundamentals.json", "financial_validation_report.json"],
        "outputs": ["companies/<company>/<year>/financials/financial_reconciliation_report.json"],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "financial_basis_resolution": {
        "description": "Resolves standalone versus consolidated basis from deterministic document and table evidence, then safely enriches yearly financial artifacts.",
        "requires": [
            "normalized_fundamentals.json",
            "financial_discovery.json / raw_financial_tables.json / clean_chunks.json if available",
        ],
        "outputs": ["companies/<company>/<year>/financials/financial_basis_resolution.json"],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "financial_truth_registry": {
        "description": "Builds a year-level financial fact registry and truth-reconciliation report from deterministic financial artifacts.",
        "requires": [
            "normalized_fundamentals.json",
            "financial_ratios.json / financial_growth.json / financial_quality_summary.json if available",
        ],
        "outputs": [
            "companies/<company>/<year>/financials/financial_fact_registry.json",
            "companies/<company>/<year>/financials/financial_truth_reconciliation_report.json",
        ],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "financial_ratios": {
        "description": "Calculates deterministic financial ratios from reconciled normalized fundamentals.",
        "requires": ["normalized_fundamentals.json", "financial_reconciliation_report.json"],
        "outputs": ["companies/<company>/<year>/financials/financial_ratios.json"],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "financial_growth": {
        "description": "Calculates deterministic growth and margin-change metrics from reconciled normalized fundamentals and available ratio history.",
        "requires": ["normalized_fundamentals.json", "financial_reconciliation_report.json"],
        "outputs": ["companies/<company>/<year>/financials/financial_growth.json"],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "corporate_actions": {
        "description": "Captures corporate actions and share-count comparability events from normalized fundamentals and raw financial tables.",
        "requires": ["normalized_fundamentals.json", "raw_financial_tables.json if available"],
        "outputs": [
            "companies/<company>/<year>/financials/corporate_actions.json",
            "companies/<company>/<year>/financials/corporate_action_rejections.json",
        ],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "shareholding_pattern": {
        "description": "Captures ownership categories and ownership-change signals from normalized fundamentals and raw shareholding rows.",
        "requires": ["normalized_fundamentals.json", "raw_financial_tables.json if available"],
        "outputs": [
            "companies/<company>/<year>/financials/shareholding_pattern.json",
            "companies/<company>/<year>/financials/shareholding_rejections.json",
        ],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "financials": {
        "description": "Runs the canonical end-to-end year-level fundamentals pipeline and writes a year-level financial audit report.",
        "requires": [
            "raw annual report or clean chunks",
            "financial discovery/extraction/normalization inputs",
        ],
        "outputs": [
            "companies/<company>/<year>/financials/financial_discovery.json",
            "companies/<company>/<year>/financials/raw_financial_tables.json",
            "companies/<company>/<year>/financials/normalized_fundamentals.json",
            "companies/<company>/<year>/financials/financial_validation_report.json",
            "companies/<company>/<year>/financials/financial_reconciliation_report.json",
            "companies/<company>/<year>/financials/financial_ratios.json",
            "companies/<company>/<year>/financials/financial_growth.json",
            "companies/<company>/<year>/financials/corporate_actions.json",
            "companies/<company>/<year>/financials/corporate_action_rejections.json",
            "companies/<company>/<year>/financials/shareholding_pattern.json",
            "companies/<company>/<year>/financials/shareholding_rejections.json",
            "companies/<company>/<year>/financials/financial_audit_report.json",
        ],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "financial_trends": {
        "description": "Builds a company-level multi-year financial trend view from yearly financial artifacts.",
        "requires": ["at least one year with normalized fundamentals", "financial ratios/growth/corporate actions/shareholding if available"],
        "outputs": ["companies/<company>/company_memory/financials/financial_trends.json"],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "financial_quality": {
        "description": "Builds a deterministic financial quality summary from yearly financial artifacts, or refreshes the company-memory diagnostic layer when run without a year.",
        "requires": [
            "<year>/financials/* core artifacts for year mode",
            "company_memory/financials/financial_trends.json for company-memory mode",
        ],
        "outputs": [
            "companies/<company>/<year>/financials/financial_quality_summary.json",
            "companies/<company>/company_memory/financials/financial_quality_summary.json",
        ],
        "llm_calls": False,
        "scope": "company or company/year",
        "year_required": False,
    },
    "financial_attribution": {
        "description": "Builds a deterministic financial driver-attribution layer that links major financial movements to possible business events or management actions.",
        "requires": [
            "company_memory/financials/financial_trends.json",
            "company_memory/financials/financial_quality_summary.json",
            "company_memory/multi_year/* if available",
        ],
        "outputs": ["companies/<company>/company_memory/financials/financial_driver_attribution.json"],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "financial_memory": {
        "description": "Runs the canonical company-level multi-year financial memory pipeline and writes a financial memory audit report.",
        "requires": [
            "at least one year with financial fundamentals artifacts",
            "company_memory/financials/financial_trends.json inputs if already present",
        ],
        "outputs": [f"companies/<company>/company_memory/financials/{name}" for name in FINANCIAL_MEMORY_OUTPUT_FILES],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "investor_financials": {
        "description": "Builds investor-facing deterministic financial modules from reconciled company-memory financial truth.",
        "requires": [
            "company_memory/financials/financial_truth_pack.json or year-level truth-registry artifacts",
            "at least one usable year in the financial truth loader",
        ],
        "outputs": [f"companies/<company>/company_memory/financials/investor_financial_modules/{name}" for name in INVESTOR_FINANCIAL_MODULE_OUTPUT_FILES],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "ask_intrinsiciq": {
        "description": "Builds the canonical Ask IntrinsicIQ backend output layer and writes a minimal UI-ready company research view skeleton.",
        "requires": [
            "existing company-memory sources if available",
            "no year context",
        ],
        "outputs": [f"companies/<company>/company_memory/ask_intrinsiciq/{name}" for name in ASK_INTRINSICIQ_OUTPUT_FILES],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "company_model": {
        "description": "Builds canonical Company Model v1 artifacts for business model, offerings, customers, revenue engines, economic drivers, dependencies, and current business state.",
        "requires": [
            "governed business-understanding evidence where available",
            "company_memory/pcim_v1.json or yearly business_blueprint/business_classification artifacts",
            "no Ask/UI presentation artifacts",
        ],
        "outputs": [f"companies/<company>/company_memory/company_model/{name}" for name in COMPANY_MODEL_OUTPUT_FILES],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "management_progression": {
        "description": "Builds canonical Management Progression v1 artifacts for management statements, actions, milestones, outcomes, unresolved proof points, and investor implications.",
        "requires": [
            "company_memory/company_model/company_model.json if available",
            "dedicated progression streams where available",
            "legacy multi_year progression artifacts only as temporary adapters",
            "no Ask/UI/Panel/Committee outputs",
        ],
        "outputs": [f"companies/<company>/company_memory/management_progression/{name}" for name in MANAGEMENT_PROGRESSION_OUTPUT_FILES],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "financial_pcim_validation": {
        "description": "Validates that year-level financial PCIM sections stay compact, traceable, warning-aware, and aligned with deterministic financial artifacts.",
        "requires": [
            "company_memory/pcim_v1.json",
            "<company>/<year>/financials/* deterministic artifacts",
        ],
        "outputs": ["companies/<company>/<year>/financials/financial_pcim_validation.json"],
        "llm_calls": False,
        "scope": "company/year",
        "year_required": True,
    },
    "company_memory": {
        "description": "Runs the company-memory and downstream investor-intelligence orchestration anchored to existing yearly intelligence snapshots.",
        "requires": ["at least one valid yearly intelligence snapshot", "company context only; eligible yearly snapshots are discovered internally"],
        "outputs": ["companies/<company>/company_memory/*"],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "management_commitments": {
        "description": "Builds canonical management commitments memory with progression, validation, and manifest outputs.",
        "requires": [
            "at least one valid yearly intelligence snapshot",
            "companies/<company>/<year>/intelligence/company_intelligence.json",
            "companies/<company>/<year>/intelligence/management_summary.json",
        ],
        "outputs": [f"companies/<company>/company_memory/management_commitments/{name}" for name in MANAGEMENT_COMMITMENTS_OUTPUT_FILES],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "management_commentary": {
        "description": "Builds canonical management commentary evolution intelligence with progression, validation, and manifest outputs.",
        "requires": [
            "at least one valid yearly intelligence snapshot",
            "companies/<company>/<year>/intelligence/company_intelligence.json",
            "companies/<company>/<year>/intelligence/management_summary.json",
        ],
        "outputs": [f"companies/<company>/company_memory/management_commentary/{name}" for name in MANAGEMENT_COMMENTARY_OUTPUT_FILES],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "capital_allocation_outcomes": {
        "description": "Builds canonical capital allocation outcomes intelligence from the existing capital-allocation ledger, financial timeline, and linked company-memory evidence.",
        "requires": [
            "companies/<company>/company_memory/financials/investor_financial_modules/capital_allocation_roi_ledger.json",
            "companies/<company>/company_memory/financials/capital_allocation_financial_timeline.json",
            "linked company-memory evidence if available",
        ],
        "outputs": [f"companies/<company>/company_memory/capital_allocation_outcomes/{name}" for name in CAPITAL_ALLOCATION_OUTCOMES_OUTPUT_FILES],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "management_quality": {
        "description": "Builds canonical management-quality synthesis from longitudinal company-memory evidence across commitments, projects, capacity, risks, commentary, capital allocation, and per-share economics.",
        "requires": [
            "companies/<company>/company_memory/management_commitments/management_commitments.json",
            "companies/<company>/company_memory/projects/projects_registry.json",
            "companies/<company>/company_memory/capacity/capacity_registry.json",
            "companies/<company>/company_memory/management_commentary/commentary_themes.json",
            "companies/<company>/company_memory/financials/investor_financial_modules/owner_earnings_bridge.json if available",
            "companies/<company>/company_memory/financials/investor_financial_modules/per_share_compounding_analysis.json if available",
        ],
        "outputs": [f"companies/<company>/company_memory/management_quality/{name}" for name in MANAGEMENT_QUALITY_OUTPUT_FILES],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "projects": {
        "description": "Builds canonical projects intelligence with progression, execution assessment, and manifest outputs.",
        "requires": [
            "companies/<company>/<year>/extracted/clean_projects.json",
            "companies/<company>/<year>/extracted/clean_capacity.json",
            "company_memory/management_commitments/management_commitments.json if available",
        ],
        "outputs": [f"companies/<company>/company_memory/projects/{name}" for name in PROJECTS_OUTPUT_FILES],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "capacity_evolution": {
        "description": "Builds canonical capacity-evolution intelligence from existing company-memory evidence and progression outputs.",
        "requires": [
            "companies/<company>/<year>/extracted/clean_capacity.json",
            "company_memory/projects/projects_registry.json if available",
            "company_memory/management_commitments/management_commitments.json if available",
        ],
        "outputs": [f"companies/<company>/company_memory/capacity/{name}" for name in CAPACITY_EVOLUTION_OUTPUT_FILES],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "risk_evolution": {
        "description": "Builds canonical risk-evolution intelligence from existing company-memory evidence and progression outputs.",
        "requires": [
            "companies/<company>/<year>/intelligence/company_intelligence.json",
            "companies/<company>/<year>/intelligence/management_summary.json",
            "companies/<company>/<year>/financials/financial_audit_report.json if available",
        ],
        "outputs": [f"companies/<company>/company_memory/risks/{name}" for name in RISK_EVOLUTION_OUTPUT_FILES],
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
    "audit": {
        "description": "Audits existing year-level and company-level artifacts and writes the financial quality scorecard.",
        "requires": ["existing company artifacts to inspect"],
        "outputs": [
            "companies/<company>/audit/company_artifact_audit.json",
            "companies/<company>/audit/company_artifact_audit.md",
            "companies/<company>/audit/financial_quality_scorecard.json",
            "companies/<company>/audit/financial_quality_scorecard.md",
        ],
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
    "panel_doctor": {
        "description": "Validates all analyst outputs and writes one consolidated panel doctor report.",
        "requires": ["investor_panel analyst outputs"],
        "outputs": ["panel_doctor_report.json"],
        "llm_calls": False,
        "scope": "company",
        "year_required": False,
    },
    "panel": {
        "description": "Runs the full investor panel, committee synthesis, brief render, and brief QA chain, with optional year-scoped financial readiness checks.",
        "requires": ["company_memory/pcim_v1.json", "year-level financial artifacts when a year context is provided"],
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


def _derive_stage_scope_sets(stage_catalog):
    year_required = {
        stage_name
        for stage_name, metadata in stage_catalog.items()
        if metadata.get("year_required")
    }
    company_level = {
        stage_name
        for stage_name, metadata in stage_catalog.items()
        if metadata.get("scope") == "company" and not metadata.get("year_required")
    }
    return year_required, company_level


YEAR_REQUIRED_STAGES, COMPANY_LEVEL_STAGES = _derive_stage_scope_sets(STAGE_CATALOG)


def get_discovery_steps():
    from discovery.project_discovery import main as project_discovery_main  # noqa: E402
    from discovery.promise_discovery import main as promise_discovery_main  # noqa: E402
    from discovery.risk_discovery import main as risk_discovery_main  # noqa: E402
    from discovery.capacity_discovery import main as capacity_discovery_main  # noqa: E402
    from discovery.capital_allocation_discovery import main as capital_allocation_discovery_main  # noqa: E402
    from discovery.initiative_discovery import main as initiative_discovery_main  # noqa: E402
    from discovery.commentary_discovery import main as commentary_discovery_main  # noqa: E402

    return [
        ("Project Discovery", project_discovery_main),
        ("Promise Discovery", promise_discovery_main),
        ("Risk Discovery", risk_discovery_main),
        ("Capacity Discovery", capacity_discovery_main),
        ("Capital Allocation Discovery", capital_allocation_discovery_main),
        ("Initiative Discovery", initiative_discovery_main),
        ("Commentary Discovery", commentary_discovery_main),
    ]


def get_extraction_steps():
    from extractors.project_extractor import main as project_extractor_main  # noqa: E402
    from extractors.promise_extractor import main as promise_extractor_main  # noqa: E402
    from extractors.risk_extractor import main as risk_extractor_main  # noqa: E402
    from extractors.capacity_extractor import main as capacity_extractor_main  # noqa: E402
    from extractors.capital_allocation_extractor import main as capital_allocation_extractor_main  # noqa: E402
    from extractors.initiative_extractor import main as initiative_extractor_main  # noqa: E402
    from extractors.commentary_extractor import main as commentary_extractor_main  # noqa: E402

    return [
        ("Project Extractor", project_extractor_main),
        ("Promise Extractor", promise_extractor_main),
        ("Risk Extractor", risk_extractor_main),
        ("Capacity Extractor", capacity_extractor_main),
        ("Capital Allocation Extractor", capital_allocation_extractor_main),
        ("Initiative Extractor", initiative_extractor_main),
        ("Commentary Extractor", commentary_extractor_main),
    ]


def get_cleaning_steps():
    from processors.project_cleaner import main as project_cleaner_main  # noqa: E402
    from processors.promise_cleaner import main as promise_cleaner_main  # noqa: E402
    from processors.risk_cleaner import main as risk_cleaner_main  # noqa: E402
    from processors.capacity_cleaner import main as capacity_cleaner_main  # noqa: E402
    from processors.capital_allocation_cleaner import main as capital_allocation_cleaner_main  # noqa: E402
    from processors.initiative_cleaner import main as initiative_cleaner_main  # noqa: E402
    from processors.commentary_cleaner import main as commentary_cleaner_main  # noqa: E402

    return [
        ("Project Cleaner", project_cleaner_main),
        ("Promise Cleaner", promise_cleaner_main),
        ("Risk Cleaner", risk_cleaner_main),
        ("Capacity Cleaner", capacity_cleaner_main),
        ("Capital Allocation Cleaner", capital_allocation_cleaner_main),
        ("Initiative Cleaner", initiative_cleaner_main),
        ("Commentary Cleaner", commentary_cleaner_main),
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

    from core.inbox_paths import PROCESSED, INBOX
    _fy = str(context.year).lower()
    _processed_annual = PROCESSED / context.company / _fy / "annual_report"
    canonical_candidates = []
    if _processed_annual.exists():
        for path in sorted(_processed_annual.iterdir()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_RAW_DOC_SUFFIXES:
                if path.name not in seen:
                    seen.add(path.name)
                    canonical_candidates.append(path)
    for _inbox_path in sorted(INBOX.glob(f"{context.company}_{_fy}*.pdf")):
        if _inbox_path.name not in seen:
            seen.add(_inbox_path.name)
            canonical_candidates.append(_inbox_path)
    candidates.extend(canonical_candidates)

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
    return read_document_text(path, allow_ocr=True)


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
    return eligible_company_years(company=company, company_root=company_root)


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


def _build_company_memory_context(company):
    eligible_years = tuple(_valid_years_for_company(company))
    if not eligible_years:
        raise RuntimeError(
            f"company_memory requires at least one valid yearly intelligence snapshot for {company}"
        )
    context = CompanyMemoryContext(company=company, eligible_years=eligible_years)
    context.year_eligibility_manifest = build_company_year_eligibility_manifest(
        company=company,
        company_root=Path("companies") / company,
    )
    context.create_directories()
    return context


def _ensure_sequence_context(company_slug, profile_name, context):
    if context is not None:
        return context
    if profile_name == "company_memory":
        return _build_company_memory_context(company_slug)
    raise RuntimeError(f"{profile_name} requires a company/year context")


def _run_preflight(context):
    context = _ensure_context("preflight", context)
    context.create_directories()

    raw_docs = _iter_raw_document_candidates(context)
    if not raw_docs:
        raise RuntimeError(
            f"No raw documents found for {context.company} {context.year}. "
            f"Place the annual report PDF in: {context.raw_dir}"
        )

    intake_report = build_document_intake_report(raw_docs, allow_ocr=True)
    intake_report_path = context.extracted_dir / "document_intake_report.json"
    intake_report_path.write_text(
        json.dumps(intake_report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    extractable_docs = []
    for path in raw_docs:
        text = _read_text_from_document(path)
        if text:
            extractable_docs.append(path)

    if not extractable_docs:
        classified = [record for record in intake_report.get("documents", []) if str(record.get("classification", "")).strip()]
        required_ocr = [record for record in classified if record.get("ocr_required")]
        if required_ocr and not intake_report.get("ocr_available"):
            raise RuntimeError(
                "OCR_REQUIRED: image-only or substantially image-only PDFs were detected, "
                "but no OCR infrastructure is available. "
                f"See {intake_report_path} for document classification details."
            )

        blocked_classes = sorted(
            {
                str(record.get("classification", "UNSUPPORTED_PDF"))
                for record in classified
                if not record.get("has_extractable_text")
            }
        )
        if blocked_classes:
            raise RuntimeError(
                "DOCUMENT_INTAKE_BLOCKED: "
                f"{', '.join(blocked_classes)}. See {intake_report_path} for details."
            )

        raise RuntimeError(
            "Raw documents found, but no extractable text was produced. "
            f"See {intake_report_path} for document intake details."
        )

    pdf_docs = [path for path in extractable_docs if path.suffix.lower() in INDEXABLE_RAW_DOC_SUFFIXES]
    if not pdf_docs:
        raise RuntimeError(
            f"Discovery requires at least one PDF annual report for {context.company} {context.year}. "
            f"Checked: {context.raw_dir}, data/Processed/{context.company}/{context.year}/annual_report, data/Inbox"
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


def _prepare_business_intelligence_runtime_plan(plan):
    loaded_modules = [
        module_id
        for module_id in getattr(plan, "loaded_modules", [])
        if isinstance(module_id, str) and module_id.strip()
    ]
    if len(loaded_modules) <= 1:
        return plan, None, loaded_modules

    questions = list(getattr(plan, "questions", []))
    synthetic_module = QuestionModule(
        module_id="business_intelligence",
        module_name="Business Intelligence",
        description="Merged business intelligence question batch",
        questions=questions,
    )
    runtime_plan = DiscoveryPlan(
        business_dnas=list(getattr(plan, "business_dnas", [])),
        loaded_modules=[synthetic_module.module_id],
        questions=questions,
    )
    return runtime_plan, [synthetic_module], loaded_modules


def _split_business_intelligence_results(result, original_modules, module_lookup):
    if len(original_modules) <= 1:
        return result

    question_to_module = {}
    for module in module_lookup.values():
        for question in getattr(module, "questions", []):
            question_to_module[question.id] = module.module_id

    answers_by_module = {module_id: [] for module_id in original_modules}
    for module_result in getattr(result, "module_results", []):
        for answer in getattr(module_result, "answers", []):
            module_id = question_to_module.get(answer.question_id)
            if module_id in answers_by_module:
                answers_by_module[module_id].append(answer)

    split_results = []
    for module_id in original_modules:
        module = module_lookup.get(module_id)
        module_name = module.module_name if module is not None else module_id
        split_results.append(
            ModuleExtractionResult(
                module_id=module_id,
                module_name=module_name,
                answers=answers_by_module.get(module_id, []),
            )
        )

    statistics = ExecutionStatistics(
        modules_executed=len(original_modules),
        questions_asked=result.statistics.questions_asked,
        questions_answered=result.statistics.questions_answered,
        questions_not_found=result.statistics.questions_not_found,
        average_confidence=result.statistics.average_confidence,
        execution_time_seconds=result.statistics.execution_time_seconds,
        retrieved_chunks=result.statistics.retrieved_chunks,
        llm_calls=result.statistics.llm_calls,
    )
    return DiscoveryResult(
        business_classification=result.business_classification,
        executed_modules=list(original_modules),
        module_results=split_results,
        statistics=statistics,
    )


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

    runtime_plan, runtime_module_definitions, original_loaded_modules = _prepare_business_intelligence_runtime_plan(plan)
    runtime = DiscoveryRuntime(
        retriever=_build_runtime_retriever(context),
        extractor=_build_runtime_extractor(),
        module_definitions=runtime_module_definitions,
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
    result = runtime.run(runtime_plan, business_classification=runtime_classification)
    if len(original_loaded_modules) > 1:
        registry = QuestionRegistry()
        module_lookup = {}
        for module_id in original_loaded_modules:
            try:
                module_lookup[module_id] = registry.get_module(module_id)
            except Exception:
                continue
        result = _split_business_intelligence_results(result, original_loaded_modules, module_lookup)

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
    write_evidence_layer_summary(context)
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


def run_financial_discovery(context=None):
    context = _ensure_context("financial_discovery", context)
    set_context(context)

    chunk_path = context.extracted_dir / "clean_chunks.json"
    if not chunk_path.exists():
        raw_docs = _iter_raw_document_candidates(context)
        if not raw_docs:
            raise RuntimeError(
                f"financial_discovery requires raw or extracted sources for {context.company} {context.year}"
            )
        chunk_path = _ensure_clean_chunks(context)

    if not chunk_path.exists():
        raise RuntimeError(
            f"financial_discovery could not find or generate clean chunks for {context.company} {context.year}"
        )

    output_path = context.financials_dir / "financial_discovery.json"
    result = write_financial_discovery(
        company=context.company,
        year=context.year,
        chunk_path=chunk_path,
        output_path=output_path,
    )
    print("[FINANCIAL DISCOVERY]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(
        "Sections Found: "
        f"{sum(len(items) for items in result.sections.values())}"
    )
    for warning in result.warnings:
        print(f"Warning: {warning}")
    return output_path


def run_financial_extraction(context=None):
    context = _ensure_context("financial_extraction", context)
    set_context(context)

    discovery_path = context.financials_dir / "financial_discovery.json"
    if not discovery_path.exists():
        raise RuntimeError(
            f"financial_extraction requires financial_discovery.json for {context.company} {context.year}"
        )

    chunk_path = context.extracted_dir / "clean_chunks.json"
    if not chunk_path.exists():
        raw_docs = _iter_raw_document_candidates(context)
        if not raw_docs:
            raise RuntimeError(
                f"financial_extraction requires raw or extracted sources for {context.company} {context.year}"
            )
        chunk_path = _ensure_clean_chunks(context)

    if not chunk_path.exists():
        raise RuntimeError(
            f"financial_extraction could not find or generate clean chunks for {context.company} {context.year}"
        )

    output_path = context.financials_dir / "raw_financial_tables.json"
    result = write_financial_extraction(
        company=context.company,
        year=context.year,
        chunk_path=chunk_path,
        discovery_path=discovery_path,
        output_path=output_path,
    )
    print("[FINANCIAL EXTRACTION]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(
        "Rows Extracted: "
        f"{sum(len(items) for items in result.tables.values())}"
    )
    for warning in result.warnings:
        print(f"Warning: {warning}")
    return output_path


def run_financial_normalization(context=None):
    context = _ensure_context("financial_normalization", context)
    set_context(context)

    raw_tables_path = context.financials_dir / "raw_financial_tables.json"
    if not raw_tables_path.exists():
        raise RuntimeError(
            f"financial_normalization requires raw_financial_tables.json for {context.company} {context.year}"
        )

    output_path = context.financials_dir / "normalized_fundamentals.json"
    payload = write_normalized_fundamentals(
        company=context.company,
        year=context.year,
        raw_tables_path=raw_tables_path,
        output_path=output_path,
    )
    print("[FINANCIAL NORMALIZATION]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(f"Preferred Basis: {payload.get('preferred_basis', 'unknown')}")
    print(f"Unmapped Rows: {len(payload.get('unmapped_rows', []))}")
    for warning in payload.get("warnings", []):
        print(f"Warning: {warning}")
    return output_path


def run_financial_validation(context=None):
    context = _ensure_context("financial_validation", context)
    set_context(context)

    normalized_path = context.financials_dir / "normalized_fundamentals.json"
    if not normalized_path.exists():
        raise RuntimeError(
            f"financial_validation requires normalized_fundamentals.json for {context.company} {context.year}"
        )

    output_path = context.financials_dir / "financial_validation_report.json"
    report = write_financial_validation_report(
        company=context.company,
        year=context.year,
        normalized_path=normalized_path,
        output_path=output_path,
    )
    print("[FINANCIAL VALIDATION]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(f"Status: {report.status}")
    print(f"Basis Checked: {report.basis_checked}")
    print(f"Hard Failures: {len(report.hard_failures)}")
    print(f"Warnings: {len(report.warnings)}")
    return output_path


def run_financial_reconciliation(context=None):
    context = _ensure_context("financial_reconciliation", context)
    set_context(context)

    normalized_path = context.financials_dir / "normalized_fundamentals.json"
    validation_path = context.financials_dir / "financial_validation_report.json"
    if not normalized_path.exists():
        raise RuntimeError(
            f"financial_reconciliation requires normalized_fundamentals.json for {context.company} {context.year}"
        )
    if not validation_path.exists():
        raise RuntimeError(
            f"financial_reconciliation requires financial_validation_report.json for {context.company} {context.year}"
        )

    output_path = context.financials_dir / "financial_reconciliation_report.json"
    report = write_financial_reconciliation_report(
        company=context.company,
        year=context.year,
        normalized_path=normalized_path,
        output_path=output_path,
    )
    print("[FINANCIAL RECONCILIATION]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(f"Status: {report.status}")
    print(f"Hard Failures: {len(report.hard_failures)}")
    print(f"Warnings: {len(report.warnings)}")
    return output_path


def run_financial_basis_resolution(context=None):
    context = _ensure_context("financial_basis_resolution", context)
    set_context(context)

    normalized_path = context.financials_dir / "normalized_fundamentals.json"
    if not normalized_path.exists():
        raise RuntimeError(
            f"financial_basis_resolution requires normalized_fundamentals.json for {context.company} {context.year}"
        )

    output_path = context.financials_dir / "financial_basis_resolution.json"
    report = write_financial_basis_resolution(
        company=context.company,
        year=context.year,
        financial_root=context.financials_dir,
        output_path=output_path,
    )
    print("[FINANCIAL BASIS RESOLUTION]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(f"Resolved Basis: {report.resolved_basis}")
    print(f"Confidence: {report.confidence}")
    print(f"Field Resolutions: {len(report.field_resolutions)}")
    print(f"Warnings: {len(report.warnings)}")
    return output_path


def run_financial_truth_registry(context=None):
    context = _ensure_context("financial_truth_registry", context)
    set_context(context)

    normalized_path = context.financials_dir / "normalized_fundamentals.json"
    if not normalized_path.exists():
        raise RuntimeError(
            f"financial_truth_registry requires normalized_fundamentals.json for {context.company} {context.year}"
        )

    registry_output_path = context.financials_dir / "financial_fact_registry.json"
    reconciliation_output_path = context.financials_dir / "financial_truth_reconciliation_report.json"
    quarantine_output_path = context.financials_dir / "financial_artifact_quarantine_report.json"
    registry, report, quarantine_report = write_financial_fact_registry(
        company=context.company,
        year=context.year,
        financial_root=context.financials_dir,
        registry_output_path=registry_output_path,
        reconciliation_output_path=reconciliation_output_path,
        quarantine_output_path=quarantine_output_path,
    )
    print("[FINANCIAL TRUTH REGISTRY]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Registry Output: {registry_output_path}")
    print(f"Reconciliation Output: {reconciliation_output_path}")
    print(f"Quarantine Output: {quarantine_output_path}")
    print(
        f"Facts: {len(registry.available_facts) + len(registry.derived_facts) + len(registry.partial_facts) + len(registry.unreliable_facts) + len(registry.invalid_facts)}"
    )
    print(f"Truth Status: {registry.downstream_readiness.get('financial_truth_status', 'unknown')}")
    print(f"Contradictions: {len(report.contradictions_found)}")
    print(f"Quarantined Facts: {len(quarantine_report.quarantined_facts)}")
    return {
        "financial_fact_registry.json": registry_output_path,
        "financial_truth_reconciliation_report.json": reconciliation_output_path,
        "financial_artifact_quarantine_report.json": quarantine_output_path,
    }


def run_financial_ratios(context=None):
    context = _ensure_context("financial_ratios", context)
    set_context(context)

    normalized_path = context.financials_dir / "normalized_fundamentals.json"
    reconciliation_path = context.financials_dir / "financial_reconciliation_report.json"
    if not normalized_path.exists():
        raise RuntimeError(
            f"financial_ratios requires normalized_fundamentals.json for {context.company} {context.year}"
        )
    if not reconciliation_path.exists():
        raise RuntimeError(
            f"financial_ratios requires financial_reconciliation_report.json for {context.company} {context.year}"
        )

    output_path = context.financials_dir / "financial_ratios.json"
    report = write_financial_ratios(
        company=context.company,
        year=context.year,
        normalized_path=normalized_path,
        reconciliation_path=reconciliation_path,
        output_path=output_path,
    )
    print("[FINANCIAL RATIOS]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(f"Status: {report.status}")
    print(f"Basis Used: {report.basis_used}")
    print(f"Warnings: {len(report.warnings)}")
    return output_path


def run_financial_growth(context=None):
    context = _ensure_context("financial_growth", context)
    set_context(context)

    normalized_path = context.financials_dir / "normalized_fundamentals.json"
    reconciliation_path = context.financials_dir / "financial_reconciliation_report.json"
    ratios_path = context.financials_dir / "financial_ratios.json"
    if not normalized_path.exists():
        raise RuntimeError(
            f"financial_growth requires normalized_fundamentals.json for {context.company} {context.year}"
        )
    if not reconciliation_path.exists():
        raise RuntimeError(
            f"financial_growth requires financial_reconciliation_report.json for {context.company} {context.year}"
        )

    output_path = context.financials_dir / "financial_growth.json"
    report = write_financial_growth(
        company=context.company,
        year=context.year,
        normalized_path=normalized_path,
        reconciliation_path=reconciliation_path,
        ratios_path=ratios_path if ratios_path.exists() else None,
        output_path=output_path,
    )
    print("[FINANCIAL GROWTH]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(f"Status: {report.status}")
    print(f"Basis Used: {report.basis_used}")
    print(f"Warnings: {len(report.warnings)}")
    return output_path


def run_corporate_actions(context=None):
    context = _ensure_context("corporate_actions", context)
    set_context(context)

    normalized_path = context.financials_dir / "normalized_fundamentals.json"
    raw_tables_path = context.financials_dir / "raw_financial_tables.json"
    if not normalized_path.exists():
        raise RuntimeError(
            f"corporate_actions requires normalized_fundamentals.json for {context.company} {context.year}"
        )

    output_path = context.financials_dir / "corporate_actions.json"
    report = write_corporate_actions(
        company=context.company,
        year=context.year,
        normalized_path=normalized_path,
        raw_tables_path=raw_tables_path if raw_tables_path.exists() else None,
        output_path=output_path,
    )
    print("[CORPORATE ACTIONS]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(f"Status: {report.status}")
    print(f"Actions: {len(report.actions)}")
    print(f"Warnings: {len(report.warnings)}")
    return output_path


def run_shareholding_pattern(context=None):
    context = _ensure_context("shareholding_pattern", context)
    set_context(context)

    normalized_path = context.financials_dir / "normalized_fundamentals.json"
    raw_tables_path = context.financials_dir / "raw_financial_tables.json"
    if not normalized_path.exists():
        raise RuntimeError(
            f"shareholding_pattern requires normalized_fundamentals.json for {context.company} {context.year}"
        )

    output_path = context.financials_dir / "shareholding_pattern.json"
    report = write_shareholding_pattern(
        company=context.company,
        year=context.year,
        raw_tables_path=raw_tables_path,
        normalized_path=normalized_path,
        output_path=output_path,
    )
    print("[SHAREHOLDING PATTERN]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(f"Status: {report.status}")
    print(f"Rows: {len(report.items)}")
    print(f"Warnings: {len(report.warnings)}")
    return output_path


def run_financials_stage(context=None):
    context = _ensure_context("financials", context)
    set_context(context)

    output_path = context.financials_dir / "financial_audit_report.json"
    stage_error = None

    try:
        run_financial_discovery(context=context)
        run_financial_extraction(context=context)
        run_financial_normalization(context=context)
        run_financial_validation(context=context)
        run_financial_reconciliation(context=context)
        run_financial_ratios(context=context)
        run_financial_growth(context=context)
        run_corporate_actions(context=context)
        run_shareholding_pattern(context=context)
    except Exception as exc:
        stage_error = exc

    report = write_financial_audit_report(
        company=context.company,
        year=context.year,
        financials_dir=context.financials_dir,
        output_path=output_path,
    )
    print("[FINANCIALS]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(f"Status: {report.status}")
    print(f"Warnings: {len(report.warnings)}")
    print(f"Hard Failures: {len(report.hard_failures)}")

    if stage_error is not None:
        raise stage_error
    if str(report.status).lower() == "fail":
        details = "; ".join(str(item) for item in report.hard_failures[:3])
        raise RuntimeError(
            f"financials audit failed for {context.company} {context.year}"
            + (f": {details}" if details else "")
        )

    return {"financial_audit_report.json": output_path}


def run_financial_trends_stage(company, context=None):
    if context is not None:
        set_context(context)
    company_root = Path("companies") / company
    output_path = company_root / "company_memory" / "financials" / "financial_trends.json"
    report = write_financial_trends(
        company=company,
        company_root=company_root,
        output_path=output_path,
    )
    print("[FINANCIAL TRENDS]")
    print(f"Company: {company}")
    print(f"Output: {output_path}")
    print(f"Years Covered: {', '.join(report.years_covered)}")
    print(f"Basis: {report.basis}")
    print(f"Warnings: {len(report.warnings)}")
    return {"financial_trends.json": output_path}


def run_financial_quality_stage(company, context=None):
    if context is not None:
        set_context(context)
        output_path = context.financials_dir / "financial_quality_summary.json"
        report = write_financial_quality_summary(
            company=company,
            year=context.year,
            financial_root=context.financials_dir,
            output_path=output_path,
        )
        print("[FINANCIAL QUALITY]")
        print(f"Company: {company}")
        print(f"Year: {context.year}")
        print(f"Output: {output_path}")
        print(f"Status: {report.status}")
        print(f"Basis Used: {report.basis_used}")
        print(f"Warnings: {len(report.warnings)}")
        return {"financial_quality_summary.json": output_path}

    company_root = Path("companies") / company
    trends_path = company_root / "company_memory" / "financials" / "financial_trends.json"
    output_path = company_root / "company_memory" / "financials" / "financial_quality_summary.json"
    report = write_financial_quality_summary(
        company=company,
        trends_path=trends_path,
        output_path=output_path,
    )
    print("[FINANCIAL QUALITY]")
    print(f"Company: {company}")
    print(f"Output: {output_path}")
    print(f"Overall Financial Quality: {report.overall_financial_quality}")
    print(f"Warnings: {len(report.warnings)}")
    return {"financial_quality_summary.json": output_path}


def run_financial_attribution_stage(company, context=None):
    if context is not None:
        set_context(context)
    company_root = Path("companies") / company
    output_path = company_root / "company_memory" / "financials" / "financial_driver_attribution.json"
    report = write_financial_driver_attribution(
        company=company,
        company_root=company_root,
        output_path=output_path,
    )
    print("[FINANCIAL ATTRIBUTION]")
    print(f"Company: {company}")
    print(f"Output: {output_path}")
    print(f"Attributions: {len(report.attributions)}")
    print(f"Warnings: {len(report.warnings)}")
    return {"financial_driver_attribution.json": output_path}


def _refresh_year_level_financial_quality(company):
    company_root = Path("companies") / company
    written = {}
    for year_dir in sorted(
        (
            child
            for child in company_root.iterdir()
            if child.is_dir() and child.name.lower().startswith("fy")
        ),
        key=lambda child: child.name.lower(),
    ) if company_root.exists() else []:
        financial_root = year_dir / "financials"
        if not (financial_root / "normalized_fundamentals.json").exists():
            continue
        output_path = financial_root / "financial_quality_summary.json"
        write_financial_quality_summary(
            company=company,
            year=year_dir.name,
            financial_root=financial_root,
            output_path=output_path,
        )
        written[f"{year_dir.name}/financial_quality_summary.json"] = output_path
    return written


def run_financial_memory_stage(company, context=None):
    if context is not None:
        set_context(context)
    paths = {}
    paths.update(run_financial_trends_stage(company=company, context=context))
    paths.update(_refresh_year_level_financial_quality(company))
    paths.update(run_financial_quality_stage(company=company, context=None))
    paths.update(run_financial_attribution_stage(company=company, context=context))

    company_root = Path("companies") / company
    financial_memory_dir = company_root / "company_memory" / "financials"
    paths.update(
        write_financial_memory_artifacts(
            company=company,
            company_root=company_root,
            output_dir=financial_memory_dir,
        )
    )
    output_path = company_root / "company_memory" / "financials" / "financial_memory_audit_report.json"
    report = write_financial_memory_audit_report(
        company=company,
        company_root=company_root,
        output_path=output_path,
    )
    print("[FINANCIAL MEMORY]")
    print(f"Company: {company}")
    print(f"Output: {output_path}")
    print(f"Status: {report.status}")
    print(f"Warnings: {len(report.warnings)}")
    print(f"Hard Failures: {len(report.hard_failures)}")
    paths["financial_memory_audit_report.json"] = output_path
    return paths


def run_investor_financials_stage(company, context=None):
    if context is not None:
        set_context(context)
    company_root = Path("companies") / company
    output_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    paths = write_investor_financial_modules(
        company=company,
        company_root=company_root,
        output_dir=output_dir,
    )
    manifest_path = output_dir / "investor_financial_modules_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print("[INVESTOR FINANCIALS]")
    print(f"Company: {company}")
    print(f"Output: {output_dir}")
    print(f"Modules: {', '.join(manifest.get('modules_run', []))}")
    print(f"Warnings: {len(manifest.get('warnings', []))}")
    print(f"Limitations: {len(manifest.get('limitations', []))}")
    return paths


def run_financial_pcim_validation_stage(context=None):
    context = _ensure_context("financial_pcim_validation", context)
    set_context(context)

    payload, output_path = write_financial_pcim_validation(
        company=context.company,
        year=context.year,
        companies_root=Path("companies"),
    )
    print("[FINANCIAL PCIM VALIDATION]")
    print(f"Company: {context.company}")
    print(f"Year: {context.year}")
    print(f"Output: {output_path}")
    print(f"Status: {payload.get('status', 'unknown')}")
    print(f"Warnings: {len(payload.get('warnings', []))}")
    print(f"Hard Failures: {len(payload.get('hard_failures', []))}")
    return {"financial_pcim_validation.json": output_path}


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


def run_management_commitments_stage(company, context=None):
    if context is not None:
        set_context(context)
    valid_years, warnings = _require_company_level_intelligence(company, "management_commitments")
    builder = ManagementCommitmentsBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory" / "management_commitments"
    commitments_path = output_dir / "management_commitments.json"
    validation_path = output_dir / "commitment_validation.json"
    commitments = _load_json_file(commitments_path) if commitments_path.exists() else {}
    validation = _load_json_file(validation_path) if validation_path.exists() else {}
    print("[MANAGEMENT COMMITMENTS]")
    print(f"Company: {company}")
    print(f"Valid Years: {', '.join(valid_years)}")
    print(f"Output Dir: {output_dir}")
    print(f"Commitments: {commitments.get('commitment_count', 0)}")
    print(f"Validation: {validation.get('status', 'unknown')}")
    print(f"Artifacts Written: {len(written_paths)}")
    for warning in warnings:
        print(f"Warning: {warning}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_management_commentary_stage(company, context=None):
    if context is not None:
        set_context(context)
    valid_years, warnings = _require_company_level_intelligence(company, "management_commentary")
    builder = ManagementCommentaryBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory" / "management_commentary"
    themes_path = output_dir / "commentary_themes.json"
    validation_path = output_dir / "commentary_validation.json"
    themes = _load_json_file(themes_path) if themes_path.exists() else {}
    validation = _load_json_file(validation_path) if validation_path.exists() else {}
    print("[MANAGEMENT COMMENTARY]")
    print(f"Company: {company}")
    print(f"Valid Years: {', '.join(valid_years)}")
    print(f"Output Dir: {output_dir}")
    print(f"Themes: {themes.get('commentary_count', 0)}")
    print(f"Validation: {validation.get('status', 'unknown')}")
    print(f"Artifacts Written: {len(written_paths)}")
    for warning in warnings:
        print(f"Warning: {warning}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_capital_allocation_outcomes_stage(company, context=None):
    if context is not None:
        set_context(context)
    valid_years, warnings = _require_company_level_intelligence(company, "capital_allocation_outcomes")
    builder = CapitalAllocationOutcomesBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory" / "capital_allocation_outcomes"
    outcomes_path = output_dir / "capital_allocation_outcomes.json"
    timelines_path = output_dir / "capital_allocation_timelines.json"
    assessments_path = output_dir / "capital_allocation_assessments.json"
    validation_path = output_dir / "capital_allocation_validation.json"
    outcomes = _load_json_file(outcomes_path) if outcomes_path.exists() else {}
    timelines = _load_json_file(timelines_path) if timelines_path.exists() else {}
    assessments = _load_json_file(assessments_path) if assessments_path.exists() else {}
    validation = _load_json_file(validation_path) if validation_path.exists() else {}
    # Derive Gold artifacts immediately after capital allocation outcomes are written
    try:
        gold_path = write_capital_allocation_outcome_tracker(company)
        written_paths[str(gold_path.relative_to(Path(".")))] = gold_path
    except Exception:
        pass  # Gold layer is best-effort; never block the capital allocation stage
    try:
        gold_path = write_strategy_evolution_timeline(company, companies_root=Path("companies"))
        written_paths[str(gold_path.relative_to(Path(".")))] = gold_path
    except Exception:
        pass  # Gold layer is best-effort; never block the pipeline stage
    print("[CAPITAL ALLOCATION OUTCOMES]")
    print(f"Company: {company}")
    print(f"Valid Years: {', '.join(valid_years)}")
    print(f"Output Dir: {output_dir}")
    print(f"Allocations: {outcomes.get('allocation_count', 0)}")
    print(f"Timelines: {timelines.get('timeline_count', 0)}")
    print(f"Assessments: {assessments.get('assessment_count', 0)}")
    print(f"Validation: {validation.get('status', 'unknown')}")
    print(f"Artifacts Written: {len(written_paths)}")
    for warning in warnings:
        print(f"Warning: {warning}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_management_quality_stage(company, context=None):
    if context is not None:
        set_context(context)
    valid_years, warnings = _require_company_level_intelligence(company, "management_quality")
    builder = ManagementQualityBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory" / "management_quality"
    summary_path = output_dir / "management_quality_summary.json"
    dimensions_path = output_dir / "management_quality_dimensions.json"
    validation_path = output_dir / "management_quality_validation.json"
    summary = _load_json_file(summary_path) if summary_path.exists() else {}
    dimensions = _load_json_file(dimensions_path) if dimensions_path.exists() else {}
    validation = _load_json_file(validation_path) if validation_path.exists() else {}
    print("[MANAGEMENT QUALITY]")
    print(f"Company: {company}")
    print(f"Valid Years: {', '.join(valid_years)}")
    print(f"Output Dir: {output_dir}")
    print(f"Overall View: {summary.get('overall_view', 'unknown')}")
    print(f"Overall Direction: {summary.get('overall_direction', 'unknown')}")
    print(f"Dimensions: {len(dimensions.get('dimensions', []))}")
    print(f"Validation: {validation.get('status', 'unknown')}")
    print(f"Artifacts Written: {len(written_paths)}")
    for warning in warnings:
        print(f"Warning: {warning}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_projects_stage(company, context=None):
    if context is not None:
        set_context(context)
    valid_years, warnings = _require_company_level_intelligence(company, "projects")
    builder = ProjectsBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory" / "projects"
    registry_path = output_dir / "projects_registry.json"
    assessments_path = output_dir / "project_assessments.json"
    validation_path = output_dir / "projects_validation.json"
    registry = _load_json_file(registry_path) if registry_path.exists() else {}
    assessments = _load_json_file(assessments_path) if assessments_path.exists() else {}
    validation = _load_json_file(validation_path) if validation_path.exists() else {}
    status_counts = defaultdict(int)
    for project in registry.get("projects", []):
        status_counts[str(project.get("current_status") or "unable_to_verify")] += 1
    economic_observable = sum(
        1
        for assessment in assessments.get("assessments", [])
        if assessment.get("economic_impact_status") in {"early_evidence", "partially_observed", "clearly_observed", "negative_outcome"}
    )
    print("[PROJECTS INTELLIGENCE]")
    print(f"Company: {company}")
    print(f"Valid Years: {', '.join(valid_years)}")
    print(f"Output Dir: {output_dir}")
    print(f"Projects detected: {registry.get('project_count', 0)}")
    print(f"Active: {status_counts.get('announced', 0) + status_counts.get('planning', 0) + status_counts.get('funded', 0) + status_counts.get('under_execution', 0)}")
    print(f"Commissioned: {status_counts.get('commissioned', 0) + status_counts.get('operational', 0)}")
    print(f"Delayed: {status_counts.get('delayed', 0)}")
    print(f"Unable to verify: {status_counts.get('unable_to_verify', 0)}")
    print(f"Economic impact observable: {economic_observable}")
    print(f"Validation: {validation.get('status', 'unknown').upper()}")
    print(f"Artifacts Written: {len(written_paths)}")
    for warning in warnings:
        print(f"Warning: {warning}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_capacity_evolution_stage(company, context=None):
    if context is not None:
        set_context(context)
    valid_years, warnings = _require_company_level_intelligence(company, "capacity_evolution")
    builder = CapacityEvolutionBuilder(company=company)
    written_paths = builder.build()
    output_dir = Path("companies") / company / "company_memory" / "capacity"
    registry_path = output_dir / "capacity_registry.json"
    assessments_path = output_dir / "capacity_assessments.json"
    validation_path = output_dir / "capacity_validation.json"
    registry = _load_json_file(registry_path) if registry_path.exists() else {}
    assessments = _load_json_file(assessments_path) if assessments_path.exists() else {}
    validation = _load_json_file(validation_path) if validation_path.exists() else {}
    status_counts = defaultdict(int)
    for capacity in registry.get("capacity_items", []):
        status_counts[str(capacity.get("current_status") or "unable_to_verify")] += 1
    utilization_counts = defaultdict(int)
    for assessment in assessments.get("assessments", []):
        utilization_counts[str(assessment.get("utilization_status") or "unclear")] += 1
    economic_observable = sum(
        1
        for assessment in assessments.get("assessments", [])
        if assessment.get("economic_impact_status") in {"early_evidence", "partially_observed", "clearly_observed", "negative_outcome"}
    )
    print("[CAPACITY EVOLUTION]")
    print(f"Company: {company}")
    print(f"Valid Years: {', '.join(valid_years)}")
    print(f"Output Dir: {output_dir}")
    print(f"Capacity items detected: {registry.get('capacity_count', 0)}")
    print(f"Operational: {status_counts.get('operational', 0) + status_counts.get('commissioned', 0)}")
    print(f"Ramping: {status_counts.get('ramping', 0)}")
    print(f"Utilized: {status_counts.get('partially_utilized', 0) + status_counts.get('materially_utilized', 0)}")
    print(f"Underutilized: {status_counts.get('underutilized', 0)}")
    print(f"Unable to verify: {status_counts.get('unable_to_verify', 0)}")
    print(f"Economic impact observable: {economic_observable}")
    print(f"Validation: {validation.get('status', 'unknown').upper()}")
    print(f"Artifacts Written: {len(written_paths)}")
    for warning in warnings:
        print(f"Warning: {warning}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_risk_evolution_stage(company, context=None):
    if context is not None:
        set_context(context)
    valid_years, warnings = _require_company_level_intelligence(company, "risk_evolution")
    company_root = Path("companies") / company
    written_paths = build_risk_evolution(company, companies_root=Path("companies"))
    try:
        gold_path = write_risk_evolution_timeline(company, companies_root=Path("companies"))
        if isinstance(written_paths, dict):
            written_paths[str(gold_path.relative_to(Path(".")))] = gold_path
    except Exception:
        pass  # Gold layer is best-effort; never block the base risk stage
    output_dir = company_root / "company_memory" / "risks"
    registry_path = output_dir / "risk_registry.json"
    assessments_path = output_dir / "risk_assessments.json"
    validation_path = output_dir / "risk_validation.json"
    registry = _load_json_file(registry_path) if registry_path.exists() else {}
    assessments = _load_json_file(assessments_path) if assessments_path.exists() else {}
    validation = _load_json_file(validation_path) if validation_path.exists() else {}
    status_counts = defaultdict(int)
    for risk in registry.get("risks", []):
        status_counts[str(risk.get("current_status") or "unable_to_verify")] += 1
    materiality_counts = defaultdict(int)
    for risk in registry.get("risks", []):
        materiality = risk.get("materiality", {})
        level = str(materiality.get("level", "unclear"))
        materiality_counts[level] += 1
    print("[RISK EVOLUTION INTELLIGENCE]")
    print(f"Company: {company}")
    print(f"Valid Years: {', '.join(valid_years)}")
    print(f"Output Dir: {output_dir}")
    print(f"Risks detected: {registry.get('risk_count', 0)}")
    print(f"Emerging: {status_counts.get('emerging', 0)}")
    print(f"Persistent: {status_counts.get('persistent', 0)}")
    print(f"Increasing: {status_counts.get('increasing', 0)}")
    print(f"Reducing: {status_counts.get('reducing', 0)}")
    print(f"Mitigated: {status_counts.get('mitigated', 0)}")
    print(f"Resolved: {status_counts.get('resolved', 0)}")
    print(f"Unable to verify: {status_counts.get('unable_to_verify', 0)}")
    print(f"High materiality: {materiality_counts.get('high', 0)}")
    print(f"Medium materiality: {materiality_counts.get('medium', 0)}")
    print(f"Low materiality: {materiality_counts.get('low', 0)}")
    print(f"Validation: {validation.get('status', 'unknown').upper()}")
    print(f"Artifacts Written: {len(written_paths) if isinstance(written_paths, dict) else 0}")
    for warning in warnings:
        print(f"Warning: {warning}")
    if isinstance(written_paths, dict):
        for filename in sorted(written_paths.values()):
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


def run_ask_intrinsiciq_stage(company, context=None, force=False):
    if context is not None:
        set_context(context)
    result = generate_ask_intrinsiciq_view(company, force=force)
    output_dir = Path("companies") / company / "company_memory" / "ask_intrinsiciq"
    manifest = result.get("manifest") or {}
    validation_report = result.get("validation_report") or {}
    business_journey = result.get("business_journey") or {}
    products_services = result.get("products_services") or {}
    financial_visual_summaries = result.get("financial_visual_summaries") or {}
    uncertainty_map = result.get("uncertainty_map") or {}
    answer_cards = result.get("answer_cards") or {}
    answer_coverage = answer_cards.get("coverage_summary") or {}
    visual_coverage = financial_visual_summaries.get("coverage_summary") or {}
    print("[ASK INTRINSICIQ]")
    print(f"Company: {company}")
    print(f"Output Dir: {output_dir}")
    print(f"Generation Status: {manifest.get('generation_status', 'unknown')}")
    print(f"Validation Status: {validation_report.get('status', 'unknown')}")
    print(f"Journey Coverage: {business_journey.get('coverage_status', 'unknown')}")
    print(f"Journey Stages: {len(business_journey.get('stages', []))}")
    print(f"Products Coverage: {products_services.get('coverage_status', 'unknown')}")
    print(f"Product Groups: {len(products_services.get('groups', []))}")
    print(f"Product Items: {sum(len(group.get('items', [])) for group in products_services.get('groups', []))}")
    print(f"Uncertainty Coverage: {uncertainty_map.get('coverage_status', 'unknown')}")
    print(f"Mapped Uncertainties: {len(uncertainty_map.get('items', []))}")
    print("Financial visuals:")
    print(f"- available: {visual_coverage.get('available', 0)}")
    print(f"- partial: {visual_coverage.get('partial', 0)}")
    print(f"- unavailable: {visual_coverage.get('unavailable', 0)}")
    print("Ask IntrinsicIQ answers:")
    print(f"- supported: {answer_coverage.get('supported', 0)}")
    print(f"- partially supported: {answer_coverage.get('partially_supported', 0)}")
    print(f"- not supported: {answer_coverage.get('not_supported', 0)}")
    print(f"- unavailable: {answer_coverage.get('unavailable', 0)}")
    print(f"Sources Found: {len(manifest.get('source_files_found', []))}")
    print(f"Sources Missing: {len(manifest.get('source_files_missing', []))}")
    print("Artifacts Written: 8")
    print("- business_journey.json")
    print("- products_services.json")
    print("- answer_cards.json")
    print("- financial_visual_summaries.json")
    print("- uncertainty_map.json")
    print("- company_research_view.json")
    print("- ask_intrinsiciq_manifest.json")
    print("- ask_intrinsiciq_validation_report.json")
    return {
        "business_journey.json": output_dir / "business_journey.json",
        "products_services.json": output_dir / "products_services.json",
        "answer_cards.json": output_dir / "answer_cards.json",
        "financial_visual_summaries.json": output_dir / "financial_visual_summaries.json",
        "uncertainty_map.json": output_dir / "uncertainty_map.json",
        "company_research_view.json": output_dir / "company_research_view.json",
        "ask_intrinsiciq_manifest.json": output_dir / "ask_intrinsiciq_manifest.json",
        "ask_intrinsiciq_validation_report.json": output_dir / "ask_intrinsiciq_validation_report.json",
    }


def run_company_model_stage(company, context=None):
    if context is not None:
        set_context(context)
    written_paths = write_company_model(company)
    output_dir = Path("companies") / company / "company_memory" / "company_model"
    validation_path = output_dir / "company_model_validation.json"
    validation = _load_json_file(validation_path)
    model_path = output_dir / "company_model.json"
    model = _load_json_file(model_path)
    current_business_model = model.get("current_business_model") or {}
    print("[COMPANY MODEL]")
    print(f"Company: {company}")
    print(f"Output Dir: {output_dir}")
    print(f"Coverage: {model.get('coverage_status') or 'unknown'}")
    print(f"Business Model Type: {current_business_model.get('business_model_type') or 'unknown'}")
    print(f"Validation Status: {validation.get('status') or 'unknown'}")
    print(f"Artifacts Written: {len(written_paths)}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_management_progression_stage(company, context=None):
    if context is not None:
        set_context(context)
    # Canonical order: MC identity/ontology -> deterministic verification
    # evidence -> MP lifecycle -> derived Gold/credibility.
    build_verification_events(company, Path("companies"))
    written_paths = write_management_progression(company)
    output_dir = Path("companies") / company / "company_memory" / "management_progression"
    validation = _load_json_file(output_dir / "management_progression_validation.json")
    payload = _load_json_file(output_dir / "management_progression.json")
    # Derive Gold artifact immediately after progression is written
    try:
        gold_path = write_management_promise_tracker(company)
        written_paths[str(gold_path.relative_to(Path(".")))] = gold_path
    except Exception:
        pass  # Gold layer is best-effort; never block the progression stage
    try:
        gold_path = write_management_credibility_synthesis(company, companies_root=Path("companies"))
        written_paths[str(gold_path.relative_to(Path(".")))] = gold_path
    except Exception:
        pass  # Gold layer is best-effort; never block the progression stage
    print("[MANAGEMENT PROGRESSION]")
    print(f"Company: {company}")
    print(f"Output Dir: {output_dir}")
    print(f"Coverage: {payload.get('coverage_status') or 'unknown'}")
    print(f"Progression Items: {len(payload.get('progression_items') or [])}")
    print(f"Validation Status: {validation.get('status') or 'unknown'}")
    print(f"Artifacts Written: {len(written_paths)}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def run_audit_stage(company, context=None, fix_safe=False):
    if context is not None:
        set_context(context)
    written_paths = run_company_artifact_audit(company, fix_safe=fix_safe)
    written_paths.update(
        write_financial_quality_scorecard(
            company=company,
            companies_root=Path("companies"),
        )
    )
    try:
        gold_path = write_risk_evolution_timeline(company, companies_root=Path("companies"))
        written_paths[str(gold_path.relative_to(Path(".")))] = gold_path
    except Exception:
        pass  # Gold layer is best-effort; never block audit
    try:
        gold_path = write_management_credibility_synthesis(company, companies_root=Path("companies"))
        written_paths[str(gold_path.relative_to(Path(".")))] = gold_path
    except Exception:
        pass  # Gold layer is best-effort; never block audit
    output_dir = Path("companies") / company / "audit"
    print("[ARTIFACT AUDIT]")
    print(f"Company: {company}")
    print(f"Output Dir: {output_dir}")
    print(f"Artifacts Written: {len(written_paths)}")
    for filename in sorted(written_paths):
        print(f"- {filename}")
    return written_paths


def _load_audit_payload(company):
    audit_path = Path("companies") / company / "audit" / "company_artifact_audit.json"
    if not audit_path.exists():
        raise RuntimeError(f"audit stage did not write expected artifact: {audit_path}")
    try:
        return json.loads(audit_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"audit artifact is not valid JSON: {audit_path}") from exc


def _ensure_audit_allows_customer_output(company):
    payload = _load_audit_payload(company)
    status = str(payload.get("status") or "").lower()
    if status == "fail":
        critical_failures = payload.get("critical_failures") or []
        details = f" Critical failures: {'; '.join(str(item) for item in critical_failures)}" if critical_failures else ""
        raise RuntimeError(
            "audit reported blocking readiness failures; customer-facing Ask IntrinsicIQ output is blocked."
            f"{details}"
        )
    return payload


def run_investor_panel_stage(company, analyst=None, context=None):
    if context is not None:
        set_context(context)
    pcim_path = Path("companies") / company / "company_memory" / "pcim_v1.json"
    if not pcim_path.exists():
        raise RuntimeError(f"investor_panel requires PCIM: {pcim_path}")
    pcim_payload = json.loads(pcim_path.read_text(encoding="utf-8"))
    freshness = _assess_pcim_freshness(company, pcim_payload)
    manifest_status = freshness.get("status")
    if manifest_status == "fail":
        raise RuntimeError(
            "investor_panel requires a usable PCIM source manifest; "
            f"current status is fail for {pcim_path}"
        )
    if manifest_status == "warning":
        print("[INVESTOR PANEL] Warning: PCIM source manifest status is warning.")
        for warning in freshness.get("warnings", []):
            print(f"Warning: {warning}")
    try:
        runner = InvestorPanelRunner(
            company=company,
            output_dir=_panel_output_dir(company, context=context),
        )
    except TypeError:
        runner = InvestorPanelRunner(company=company)
    written_paths = runner.run(analyst=analyst)
    output_dir = _panel_output_dir(company, context=context)
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
    output_dir = _panel_output_dir(company, context=context) / "briefs"
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
    panel_dir = _panel_output_dir(company, context=context)
    analyst_paths = [panel_dir / f"{analyst}_analysis.json" for analyst in ("graham", "buffett", "fisher", "munger", "lynch")]
    if not any(path.exists() for path in analyst_paths):
        raise RuntimeError(f"committee_synthesis requires analyst outputs in {panel_dir}")
    synthesizer = InvestmentCommitteeSynthesizer(company=company)
    written_path = synthesizer.run(cleanup_only=cleanup_only)
    output_dir = panel_dir
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
    synthesis_path = _panel_output_dir(company, context=context) / "committee_synthesis.json"
    if not synthesis_path.exists():
        raise RuntimeError(f"committee_brief requires committee_synthesis.json: {synthesis_path}")
    builder = CommitteeBriefRenderer(company=company)
    written_paths = builder.build(include_evidence_ids=include_evidence_ids)
    qa_builder = CommitteeBriefQAGate(company=company)
    written_paths.update(qa_builder.build(include_evidence_ids=include_evidence_ids))
    output_dir = _panel_output_dir(company, context=context)
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
    panel_dir = _panel_output_dir(company, context=context)
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


def _panel_output_dir(company, context=None):
    return investor_panel_dir(company, prefer_company_memory=True)


def _panel_summary_dir(company, context=None):
    return _panel_output_dir(company, context=context)


def _panel_summary_path(company, context=None):
    return _panel_summary_dir(company, context=context) / "panel_run_summary.json"


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


PANEL_REQUIRED_FINANCIAL_ARTIFACTS = (
    "normalized_fundamentals.json",
    "financial_validation_report.json",
    "financial_reconciliation_report.json",
    "financial_ratios.json",
    "financial_growth.json",
    "financial_quality_summary.json",
    "corporate_actions.json",
    "shareholding_pattern.json",
)


def _dedupe_preserve(items):
    seen = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _contains_source_chunk(value):
    if isinstance(value, dict):
        if "source_chunk" in value:
            return True
        return any(_contains_source_chunk(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_source_chunk(item) for item in value)
    if isinstance(value, str):
        return "source_chunk" in value
    return False


def _contains_raw_financial_table_reference(value):
    if isinstance(value, dict):
        return any(_contains_raw_financial_table_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_raw_financial_table_reference(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return "raw_financial_tables.json" in lowered or "raw financial table" in lowered
    return False


def _parse_financial_context_messages(payload):
    messages = []
    if isinstance(payload, dict):
        for field in ("warnings", "limitations", "missing_data", "missing_fields", "hard_failures"):
            value = payload.get(field)
            if isinstance(value, list):
                messages.extend(str(item).strip() for item in value if str(item).strip())
    return messages


def _classify_financial_message(message):
    lowered = message.lower()
    if "basis" in lowered and "unknown" in lowered:
        return "warning", message
    if "capex" in lowered and "missing" in lowered:
        return "warning", message
    if ("free cash flow" in lowered or "fcf" in lowered) and "missing" in lowered:
        return "warning", message
    if "share count" in lowered and "missing" in lowered:
        return "warning", message
    if "share-count" in lowered and "missing" in lowered:
        return "warning", message
    if "payables" in lowered and "missing" in lowered:
        return "warning", message
    if "shareholding" in lowered and "missing" in lowered:
        return "warning", message
    return "limitation", message


def _assess_panel_financial_context(context):
    checked = []
    missing = []
    optional_missing = []
    warnings = []
    limitations = []
    hard_failures = []
    payloads = {}

    if context is None:
        companies_root = Path("companies")
        company_dirs = [path for path in companies_root.iterdir() if path.is_dir()] if companies_root.exists() else []
        if len(company_dirs) != 1:
            return {
                "available": False,
                "status": "missing",
                "artifacts_checked": checked,
                "missing_artifacts": missing,
                "warnings": ["Year context was not provided; year-level financial readiness was not assessed."],
                "limitations": ["Panel is running without an active year-specific financial prerequisite check."],
                "hard_failures": [],
            }
        company_root = company_dirs[0]
        company_memory_financial_dir = company_root / "company_memory" / "financials"
        panel_dir = company_root / "company_memory" / "investor_panel"
        company_truth_pack_path = company_memory_financial_dir / "financial_truth_pack.json"
        checked.extend(
            [
                str(company_truth_pack_path),
                str(company_memory_financial_dir / "financial_quality_summary.json"),
                str(company_root / "company_memory" / "pcim_v1.json"),
                str(panel_dir / "committee_synthesis.json"),
            ]
        )
        truth_pack = _load_json_file(company_truth_pack_path) if company_truth_pack_path.exists() else {}
        quality = _load_json_file(company_memory_financial_dir / "financial_quality_summary.json") if (company_memory_financial_dir / "financial_quality_summary.json").exists() else {}
        pcim = _load_json_file(company_root / "company_memory" / "pcim_v1.json") if (company_root / "company_memory" / "pcim_v1.json").exists() else {}
        committee = _load_json_file(panel_dir / "committee_synthesis.json") if (panel_dir / "committee_synthesis.json").exists() else {}
        analyst_financial_usage_detected = False
        if panel_dir.exists():
            for analyst_path in panel_dir.glob("*_analysis.json"):
                checked.append(str(analyst_path))
                try:
                    analyst_payload = _load_json_file(analyst_path)
                except Exception:
                    continue
                financial_assessment = analyst_payload.get("financial_assessment") or {}
                if financial_assessment.get("financials_used") or analyst_payload.get("financial_metrics_used"):
                    analyst_financial_usage_detected = True
        truth_detected = bool(
            truth_pack.get("usable_current_metrics")
            or truth_pack.get("usable_derived_metrics")
            or truth_pack.get("partial_metrics")
            or (committee.get("committee_financial_truth") or {}).get("truth_detected")
            or analyst_financial_usage_detected
            or pcim.get("financial_truth_inputs")
        )
        status = "missing"
        if truth_detected:
            truth_status = str(truth_pack.get("financial_panel_status") or "").strip().lower()
            if truth_status == "pass":
                status = "pass"
            elif truth_status in {"warning", "partial"} or quality:
                status = "warning"
            else:
                status = "warning"
        return {
            "available": truth_detected,
            "status": status,
            "artifacts_checked": checked,
            "missing_artifacts": missing,
            "warnings": [] if truth_detected else ["No company-memory financial truth source was detected."],
            "limitations": [] if truth_detected else ["Panel is running without an active year-specific financial prerequisite check."],
            "hard_failures": [],
        }

    company_root = Path("companies") / context.company
    company_memory_financial_dir = company_root / "company_memory" / "financials"

    for filename in PANEL_REQUIRED_FINANCIAL_ARTIFACTS:
        path = context.financials_dir / filename
        checked.append(str(path))
        if not path.exists():
            missing.append(str(path))
            continue
        try:
            payloads[filename] = _load_json_file(path)
        except Exception as exc:
            hard_failures.append(f"Malformed financial artifact {filename}: {exc}")

    company_memory_candidates = [
        company_memory_financial_dir / "financial_truth_pack.json",
        company_memory_financial_dir / "financial_memory_manifest.json",
        company_memory_financial_dir / "financial_trends.json",
        company_memory_financial_dir / "financial_quality_summary.json",
        company_memory_financial_dir / "investor_financial_modules" / "investor_financial_modules_manifest.json",
    ]
    company_memory_payloads = {}
    for path in company_memory_candidates:
        checked.append(str(path))
        if not path.exists():
            optional_missing.append(str(path))
            continue
        try:
            company_memory_payloads[path.name] = _load_json_file(path)
        except Exception as exc:
            hard_failures.append(f"Malformed financial artifact {path.name}: {exc}")

    year_truth_candidates = []
    for child in company_root.iterdir() if company_root.exists() else []:
        if not child.is_dir() or not child.name.lower().startswith("fy"):
            continue
        fin_dir = child / "financials"
        for filename in (
            "financial_fact_registry.json",
            "financial_truth_reconciliation_report.json",
            "financial_basis_resolution.json",
            "financial_artifact_quarantine_report.json",
        ):
            year_truth_candidates.append(fin_dir / filename)
    for path in year_truth_candidates:
        checked.append(str(path))
        if not path.exists():
            optional_missing.append(str(path))

    quality = payloads.get("financial_quality_summary.json")
    quality_status = str((quality or {}).get("status") or "").strip().lower()
    if quality is None and "financial_quality_summary.json" not in missing:
        quality_status = "fail"

    for filename, payload in payloads.items():
        for message in _parse_financial_context_messages(payload):
            target, text = _classify_financial_message(message)
            if target == "warning":
                warnings.append(text)
            else:
                limitations.append(text)

    company_truth_pack = company_memory_payloads.get("financial_truth_pack.json") or {}
    company_memory_quality = company_memory_payloads.get("financial_quality_summary.json") or {}
    truth_pack_hydrated = any(
        bool(company_truth_pack.get(field))
        for field in (
            "usable_current_metrics",
            "usable_derived_metrics",
            "derived_not_explicitly_reported",
            "precision_limits",
            "investor_relevant_questions",
        )
    )
    truth_pack_status = str(company_truth_pack.get("financial_panel_status") or "").strip().lower()
    pcim_path = company_root / "company_memory" / "pcim_v1.json"
    checked.append(str(pcim_path))
    pcim_payload = _load_json_file(pcim_path) if pcim_path.exists() else {}
    pcim_truth_present = any(
        key in pcim_payload
        for key in (
            "financial_truth_inputs",
            "analyst_financial_truth_pack",
            "financial_quality_inputs",
        )
    )
    panel_dir = investor_panel_dir(context.company)
    analyst_financial_usage_detected = False
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        analysis_path = panel_dir / f"{analyst}_analysis.json"
        checked.append(str(analysis_path))
        if not analysis_path.exists():
            continue
        try:
            analyst_payload = _load_json_file(analysis_path)
        except Exception as exc:
            warnings.append(f"Could not parse analyst artifact for financial-context assessment: {analysis_path} ({exc})")
            continue
        financial_assessment = analyst_payload.get("financial_assessment") or {}
        if bool(financial_assessment.get("financials_used")) or bool(analyst_payload.get("financial_sections_consumed")):
            analyst_financial_usage_detected = True
    truth_pack_present = bool(company_truth_pack) and (truth_pack_hydrated or truth_pack_status in {"pass", "warning", "partial", "invalid"})

    if missing:
        warnings.extend(f"Missing financial artifact: {path}" for path in missing)
    if optional_missing:
        warnings.extend(f"Optional financial truth artifact missing: {path}" for path in optional_missing)

    if quality_status == "fail":
        hard_failures.append(
            "financial_quality_summary.json status is fail; investor panel must not reason on failed financial inputs"
        )
    elif quality_status == "warning":
        warnings.append("financial_quality_summary.json status is warning")
    elif not quality_status:
        warnings.append("financial_quality_summary.json is missing or has no usable status")

    available = bool(
        truth_pack_present
        or pcim_truth_present
        or analyst_financial_usage_detected
        or quality_status in {"pass", "warning"}
        or str((company_memory_quality or {}).get("status") or "").strip().lower() in {"pass", "warning"}
    )
    if truth_pack_status == "invalid":
        warnings.append("financial_truth_pack.json is present but hydration status is invalid")
    if analyst_financial_usage_detected and not (truth_pack_present or pcim_truth_present):
        warnings.append("Analyst artifacts consumed financial sections but company-level financial truth hydration was not fully present.")
    if not available and payloads:
        available = True

    status = "pass"
    if hard_failures:
        status = "fail"
    elif missing and available:
        status = "partial"
    elif missing and not available:
        status = "missing"
    elif warnings or limitations:
        status = "warning"

    return {
        "available": available,
        "status": status,
        "artifacts_checked": checked,
        "missing_artifacts": missing + optional_missing,
        "warnings": _dedupe_preserve(warnings),
        "limitations": _dedupe_preserve(limitations),
        "hard_failures": _dedupe_preserve(hard_failures),
    }


def _validate_analyst_output(company, analyst, context=None):
    panel_dir = _panel_output_dir(company, context=context)
    path = panel_dir / f"{analyst}_analysis.json"
    payload = _load_json_file(path)
    diagnostics_path = panel_dir / f"{analyst}_analysis_diagnostics.json"
    diagnostics = _load_json_file(diagnostics_path) if diagnostics_path.exists() else {}
    failed_clean_candidate_path = panel_dir / f"{analyst}_analysis_failed_clean_candidate.json"

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
        "financial_assessment",
        "financial_sections_consumed",
        "financial_warnings_carried_forward",
    ):
        if field not in payload:
            failures.append(f"{analyst}: missing {field}")
    for forbidden_field in (
        "schema_warnings",
        "evidence_grounding_warnings",
        "evidence_id_normalization",
        "evidence_routing_diagnostics",
    ):
        if forbidden_field in payload:
            failures.append(f"{analyst}: clean analysis still contains internal field {forbidden_field}")

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

    def _diagnostic_block(name):
        nested = diagnostics.get("finalization_diagnostics") or {}
        if isinstance(nested, dict):
            nested_value = nested.get(name)
            if nested_value:
                return nested_value
        value = diagnostics.get(name)
        if value:
            return value
        return {}

    def resolve_final_analyst_status(analyst_artifact, analyst_diagnostics):
        def _status_block(name):
            nested = analyst_diagnostics.get("finalization_diagnostics") or {}
            if isinstance(nested, dict):
                nested_value = nested.get(name)
                if nested_value:
                    return nested_value
            value = analyst_diagnostics.get(name)
            if value:
                return value
            return {}

        finalization_summary = _status_block("finalization_summary") or {}
        post_finalization_status = _status_block("post_finalization_status") or {}
        pre_finalization_status = _status_block("pre_finalization_status") or {}

        resolved_evidence_grounding_status = str(
            post_finalization_status.get("evidence_grounding_status")
            or analyst_artifact.get("evidence_grounding_status")
            or analyst_artifact.get("status")
            or "fail"
        ).strip().lower()
        resolved_validation_status = str(
            post_finalization_status.get("validation_status")
            or analyst_artifact.get("validation_status")
            or resolved_evidence_grounding_status
            or "fail"
        ).strip().lower()
        resolved_status = str(
            post_finalization_status.get("status")
            or analyst_artifact.get("status")
            or resolved_validation_status
            or resolved_evidence_grounding_status
            or "fail"
        ).strip().lower()

        if isinstance(finalization_summary, dict) and "hard_failures" in finalization_summary:
            hard_failures = list(finalization_summary.get("hard_failures") or [])
        else:
            hard_failures = list(analyst_artifact.get("hard_failures", []) or [])
        active_unresolved_claims = list(finalization_summary.get("active_unresolved_claims", []) or [])

        if hard_failures or active_unresolved_claims:
            resolved_status = "fail"
            resolved_validation_status = "fail"
            resolved_evidence_grounding_status = "fail"

        if resolved_status not in {"pass", "warning", "fail"}:
            resolved_status = "fail"
        if resolved_validation_status not in {"pass", "warning", "fail"}:
            resolved_validation_status = resolved_status
        if resolved_evidence_grounding_status not in {"pass", "warning", "fail"}:
            resolved_evidence_grounding_status = resolved_status

        return {
            "status": resolved_status,
            "validation_status": resolved_validation_status,
            "evidence_grounding_status": resolved_evidence_grounding_status,
            "hard_failures": hard_failures,
            "active_unresolved_claims": active_unresolved_claims,
            "finalization_summary": finalization_summary,
            "post_finalization_status": post_finalization_status,
            "pre_finalization_status": pre_finalization_status,
        }

    truth_pack = payload.get("analyst_financial_truth_pack") or {}
    finalized_payload = finalize_analyst_financial_warnings(payload, truth_pack, diagnostics)
    finalized_payload = finalize_analyst_validation_status(finalized_payload, diagnostics)

    resolved = resolve_final_analyst_status(finalized_payload, diagnostics)
    finalization_summary = resolved["finalization_summary"]
    post_finalization_status = resolved["post_finalization_status"]
    status = resolved["evidence_grounding_status"]
    warning_count = len((finalization_summary.get("warnings", []) or [])) + len(diagnostics.get("evidence_grounding_warnings", []) or [])
    analyst_status = resolved["status"]

    final_hard_failures = list(resolved["hard_failures"] or [])
    final_active_unresolved = list(resolved["active_unresolved_claims"] or [])

    for item in final_hard_failures:
        failures.append(f"{analyst}: {item}")
    if final_active_unresolved:
        failures.append(f"{analyst}: unresolved factual claims remain after evidence routing repair")
    for item in finalized_payload.get("warnings", []) or []:
        warnings.append(f"{analyst}: {item}")

    if not final_hard_failures and not final_active_unresolved and analyst_status in {"pass", "warning"}:
        failures = [
            item for item in failures
            if "unresolved factual claims remain after evidence routing repair" not in item
        ]

    return {
        "status": analyst_status,
        "evidence_grounding_status": status,
        "warning_count": warning_count,
        "output": str(path),
        "failed_clean_candidate_path": str(failed_clean_candidate_path),
        "failed_clean_candidate_exists": failed_clean_candidate_path.exists(),
        "payload": finalized_payload,
        "diagnostics": diagnostics,
        "warnings": warnings,
        "failures": failures,
        "pre_finalization_status": resolved["pre_finalization_status"],
        "post_finalization_status": post_finalization_status,
        "finalization_summary": finalization_summary,
        "resolved_final_status": resolved["status"],
        "resolved_final_validation_status": resolved["validation_status"],
        "resolved_final_evidence_grounding_status": resolved["evidence_grounding_status"],
        "diagnostics_used": bool(diagnostics),
    }


def validate_existing_panel_artifacts(company, panel_dir, *, context=None):
    analyst_results = {}
    statuses = []
    failures = []
    warnings = []

    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        analysis_path = panel_dir / f"{analyst}_analysis.json"
        diagnostics_path = panel_dir / f"{analyst}_analysis_diagnostics.json"
        if not analysis_path.exists():
            result = {
                "status": "fail",
                "analyst": analyst,
                "output": str(analysis_path),
                "diagnostics_path": str(diagnostics_path),
                "analysis_exists": False,
                "diagnostics_exists": diagnostics_path.exists(),
                "warnings": [],
                "failures": [f"{analyst}: missing clean analysis artifact"],
                "payload": {},
                "diagnostics": _load_json_file(diagnostics_path) if diagnostics_path.exists() else {},
                "evidence_grounding_status": "fail",
                "warning_count": 0,
                "failed_clean_candidate_path": str(panel_dir / f"{analyst}_analysis_failed_clean_candidate.json"),
                "failed_clean_candidate_exists": (panel_dir / f"{analyst}_analysis_failed_clean_candidate.json").exists(),
            }
        else:
            result = _validate_analyst_output(company, analyst, context=context)
            result["analyst"] = analyst
            result["diagnostics_path"] = str(diagnostics_path)
            result["analysis_exists"] = True
            result["diagnostics_exists"] = diagnostics_path.exists()
        analyst_results[analyst] = result
        statuses.append(result["status"])
        failures.extend(list(result.get("failures") or []))
        warnings.extend(list(result.get("warnings") or []))

    overall_status = "pass"
    for status in statuses:
        overall_status = _merge_status(overall_status, status)

    return {
        "status": overall_status,
        "analysts": analyst_results,
        "failures": _dedupe_preserve(failures),
        "warnings": _dedupe_preserve(warnings),
    }


def run_panel_doctor_stage(company, context=None):
    if context is not None:
        set_context(context)
    panel_dir = _panel_output_dir(company, context=context)
    panel_dir.mkdir(parents=True, exist_ok=True)
    source_pcim = Path("companies") / company / "company_memory" / "pcim_v1.json"
    report = {
        "company": company,
        "scope": "company_memory",
        "source_pcim": str(source_pcim),
        "panel_dir": str(panel_dir),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "analysts": [],
    }
    validation = validate_existing_panel_artifacts(company, panel_dir, context=context)
    overall_status = validation["status"]
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        analysis_path = panel_dir / f"{analyst}_analysis.json"
        diagnostics_path = panel_dir / f"{analyst}_analysis_diagnostics.json"
        result = validation["analysts"][analyst]
        analysis_exists = result["analysis_exists"]
        diagnostics_exists = result["diagnostics_exists"]
        failed_clean_candidate_path = panel_dir / f"{analyst}_analysis_failed_clean_candidate.json"
        failed_clean_candidate_exists = failed_clean_candidate_path.exists()
        if not analysis_exists:
            report["analysts"].append(
                {
                    "analyst": analyst,
                    "status": "fail",
                    "analysis_path": str(analysis_path),
                    "diagnostics_path": str(diagnostics_path),
                    "analysis_exists": analysis_exists,
                    "diagnostics_exists": diagnostics_exists,
                    "failed_clean_candidate_exists": failed_clean_candidate_exists,
                    "clean_status": "missing",
                    "structural_errors": ["missing_clean_analysis"],
                    "evidence_routing_errors": [],
                    "evidence_id_errors": [],
                    "internal_term_errors": [],
                    "financial_warning_errors": [],
                    "valuation_language_errors": [],
                    "recommendation_language_errors": [],
                    "remaining_forbidden_keys": [],
                    "remaining_forbidden_strings": [],
                    "suggested_fix_category": "missing_output",
                }
            )
            continue
        diagnostics = result.get("diagnostics") or {}
        failures = list(result.get("failures") or [])
        warnings = list(result.get("warnings") or [])
        routing_errors = [
            item for item in (diagnostics.get("evidence_grounding_warnings") or [])
            if isinstance(item, dict) and "routing" in str(item.get("issue") or "").lower()
        ]
        evidence_id_errors = [
            item for item in (diagnostics.get("evidence_id_normalization", {}).get("removed_invalid_ids") or [])
        ]
        internal_term_errors = [item for item in failures if "internal field" in item or "source_chunk" in item]
        financial_warning_errors = [item for item in failures if "financial warning" in item]
        valuation_errors = [item for item in failures if "valuation" in item.lower()]
        recommendation_errors = [item for item in failures if "recommendation" in item.lower() or "buy/sell/hold" in item.lower()]
        clean_writer_status = str(diagnostics.get("clean_writer_status") or ("pass" if analysis_exists else "missing"))
        remaining_forbidden_keys = list(diagnostics.get("remaining_forbidden_keys", []) or [])
        remaining_forbidden_strings = list(diagnostics.get("remaining_forbidden_strings", []) or [])
        status = result["status"]
        report["analysts"].append(
            {
                "analyst": analyst,
                "status": status,
                "analysis_path": str(analysis_path),
                "diagnostics_path": str(diagnostics_path),
                "analysis_exists": analysis_exists,
                "diagnostics_exists": diagnostics_exists,
                "failed_clean_candidate_exists": result.get("failed_clean_candidate_exists", False),
                "clean_status": clean_writer_status,
                "structural_errors": failures,
                "evidence_routing_errors": routing_errors,
                "evidence_id_errors": evidence_id_errors,
                "internal_term_errors": internal_term_errors,
                "financial_warning_errors": financial_warning_errors,
                "valuation_language_errors": valuation_errors,
                "recommendation_language_errors": recommendation_errors,
                "remaining_forbidden_keys": remaining_forbidden_keys,
                "remaining_forbidden_strings": remaining_forbidden_strings,
                "suggested_fix_category": (
                    "clean_writer"
                    if clean_writer_status == "fail"
                    else "forbidden_payload_hygiene"
                    if remaining_forbidden_keys or remaining_forbidden_strings
                    else "evidence_routing"
                    if routing_errors
                    else "evidence_hygiene"
                    if evidence_id_errors
                    else "validation"
                    if failures
                    else "none"
                ),
                "warnings": warnings,
            }
        )
    report["status"] = overall_status
    output_path = panel_dir / "panel_doctor_report.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[PANEL DOCTOR]")
    print(f"Company: {company}")
    print(f"Output: {output_path}")
    print(f"Status: {overall_status.upper()}")
    return {"panel_doctor_report.json": output_path}


def _write_panel_run_summary(company, payload, *, context=None):
    path = _panel_summary_path(company, context=context)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def canonicalize_panel_run_summary(summary):
    analysts = summary.get("analysts") or {}
    stages = summary.setdefault("stages", {})
    analysts_stage = stages.get("analysts") or {}
    financial_context = summary.get("financial_context") or {}

    canonical_analyst_failures = []
    canonical_stage_warnings = []
    canonical_statuses = []
    analyst_outputs = []
    any_financial_usage = False

    unresolved_claim_message = "unresolved factual claims remain after evidence routing repair"

    for analyst, data in analysts.items():
        if not isinstance(data, dict):
            continue
        warnings = _dedupe_preserve(list(data.get("warnings", []) or []))
        post_finalization_status = data.get("post_finalization_status") or {}
        finalization_summary = data.get("finalization_summary") or {}
        hard_failures = _dedupe_preserve(list(finalization_summary.get("hard_failures", []) or []))
        active_unresolved_claims = list(finalization_summary.get("active_unresolved_claims", []) or [])

        post_status_present = isinstance(post_finalization_status, dict) and bool(
            post_finalization_status.get("status")
            or post_finalization_status.get("validation_status")
            or post_finalization_status.get("evidence_grounding_status")
        )

        resolved_status = str(
            post_finalization_status.get("status")
            or data.get("status")
            or "fail"
        ).strip().lower()
        resolved_validation_status = str(
            post_finalization_status.get("validation_status")
            or data.get("validation_status")
            or resolved_status
            or "fail"
        ).strip().lower()
        resolved_evidence_grounding_status = str(
            post_finalization_status.get("evidence_grounding_status")
            or data.get("evidence_grounding_status")
            or resolved_status
            or "fail"
        ).strip().lower()

        if resolved_status not in {"pass", "warning", "fail"}:
            resolved_status = "fail"
        if resolved_validation_status not in {"pass", "warning", "fail"}:
            resolved_validation_status = resolved_status
        if resolved_evidence_grounding_status not in {"pass", "warning", "fail"}:
            resolved_evidence_grounding_status = resolved_status

        canonical_hard_failures = []
        if post_status_present:
            if resolved_status == "fail":
                if hard_failures or active_unresolved_claims:
                    canonical_hard_failures.extend(hard_failures)
                    if active_unresolved_claims and unresolved_claim_message not in canonical_hard_failures:
                        canonical_hard_failures.append(unresolved_claim_message)
                else:
                    resolved_status = "warning"
                    if resolved_validation_status == "fail":
                        resolved_validation_status = "warning"
                    if resolved_evidence_grounding_status == "fail":
                        resolved_evidence_grounding_status = "warning"
            else:
                canonical_hard_failures = []
        else:
            canonical_hard_failures = _dedupe_preserve(list(data.get("hard_failures", []) or []))

        if resolved_status in {"pass", "warning"}:
            canonical_hard_failures = []
        if resolved_validation_status == "fail" and resolved_status in {"pass", "warning"}:
            resolved_validation_status = resolved_status
        if resolved_evidence_grounding_status == "fail" and resolved_status in {"pass", "warning"}:
            resolved_evidence_grounding_status = resolved_status

        data["status"] = resolved_status
        data["validation_status"] = resolved_validation_status
        data["evidence_grounding_status"] = resolved_evidence_grounding_status
        data["hard_failures"] = canonical_hard_failures
        data["warnings"] = warnings

        canonical_statuses.append(resolved_status)
        canonical_stage_warnings.extend(warnings)
        if resolved_status == "fail":
            canonical_analyst_failures.extend(f"{analyst}: {item}" for item in canonical_hard_failures)
        analyst_outputs.append(f"{analyst}:{resolved_status}")
        if bool(data.get("financials_used")):
            any_financial_usage = True

    analysts_stage_status = "pass"
    for status in canonical_statuses:
        analysts_stage_status = _merge_status(analysts_stage_status, status)
    if not canonical_statuses and analysts_stage.get("status"):
        analysts_stage_status = str(analysts_stage.get("status") or "pass").lower()

    stages["analysts"] = {
        "status": analysts_stage_status,
        "output": "; ".join(analyst_outputs),
        "warnings": _dedupe_preserve(canonical_stage_warnings),
        "hard_failures": _dedupe_preserve(canonical_analyst_failures),
        "failures": _dedupe_preserve(canonical_analyst_failures),
    }

    company = summary.get("company")
    year = summary.get("year")
    panel_dir = investor_panel_dir(company) if company else Path()
    company_root = Path("companies") / company if company else Path()
    pcim_path = company_root / "company_memory" / "pcim_v1.json"
    truth_pack_path = company_root / "company_memory" / "financials" / "financial_truth_pack.json"

    artifacts_checked = _dedupe_preserve(list(financial_context.get("artifacts_checked", []) or []))
    missing_artifacts = _dedupe_preserve(list(financial_context.get("missing_artifacts", []) or []))
    financial_warnings = _dedupe_preserve(list(financial_context.get("warnings", []) or []))
    financial_limitations = _dedupe_preserve(list(financial_context.get("limitations", []) or []))

    if any_financial_usage:
        for analyst, data in analysts.items():
            output_path = data.get("output_path") or str(panel_dir / f"{analyst}_analysis.json")
            if output_path:
                artifacts_checked.append(str(output_path))
        if company:
            artifacts_checked.append(str(pcim_path))
            artifacts_checked.append(str(truth_pack_path))
            if not truth_pack_path.exists() and str(truth_pack_path) not in missing_artifacts:
                missing_artifacts.append(str(truth_pack_path))
        financial_context["available"] = True
        if year is None:
            if str(financial_context.get("status") or "").strip().lower() in {"", "missing"}:
                financial_context["status"] = "warning"
            elif str(financial_context.get("status") or "").strip().lower() == "fail":
                financial_context["status"] = "warning"
            inference_warning = "Financial context was inferred from analyst financial usage; year-specific readiness was not assessed."
            if inference_warning not in financial_warnings:
                financial_warnings.append(inference_warning)
        elif str(financial_context.get("status") or "").strip().lower() == "missing":
            financial_context["status"] = "warning"

    if financial_context.get("available") and str(financial_context.get("status") or "").strip().lower() == "missing":
        financial_context["status"] = "warning"

    financial_context["artifacts_checked"] = _dedupe_preserve(artifacts_checked)
    financial_context["missing_artifacts"] = _dedupe_preserve(missing_artifacts)
    financial_context["warnings"] = _dedupe_preserve(financial_warnings)
    financial_context["limitations"] = _dedupe_preserve(financial_limitations)
    summary["financial_context"] = financial_context

    top_warnings = _dedupe_preserve(list(financial_context.get("warnings", []) or []))
    top_failures = []
    overall_status = "pass"
    financial_status = str(financial_context.get("status") or "pass").strip().lower()
    if financial_status == "fail":
        overall_status = "fail"
    elif financial_status in {"warning", "partial", "missing"}:
        overall_status = "warning"

    for stage_name, stage in stages.items():
        if not isinstance(stage, dict) or not stage:
            continue
        stage_status = str(stage.get("status") or "pass").strip().lower()
        stage_warnings = _dedupe_preserve(list(stage.get("warnings", []) or []))
        stage_failures = _dedupe_preserve(list(stage.get("hard_failures", []) or stage.get("failures", []) or []))
        stage["warnings"] = stage_warnings
        stage["hard_failures"] = stage_failures
        stage["failures"] = stage_failures
        top_warnings.extend(stage_warnings)
        top_failures.extend(stage_failures)
        overall_status = _merge_status(overall_status, stage_status)

    summary["warnings"] = _dedupe_preserve(top_warnings)
    summary["hard_failures"] = _dedupe_preserve(top_failures)
    summary["failures"] = _dedupe_preserve(top_failures)
    summary["status"] = "fail" if summary["hard_failures"] else overall_status

    return summary


def _assess_pcim_freshness(company, pcim_payload):
    company_root = Path("companies") / company
    result = audit_saved_pcim_manifest(
        company_root,
        pcim_payload.get("pcim_source_manifest") or {},
        saved_multi_year_inputs=pcim_payload.get("multi_year_inputs") or {},
        expected_years=pcim_payload.get("available_years") or [],
    )
    pcim_path = company_root / "company_memory" / "pcim_v1.json"
    financial_sources = [
        company_root / "company_memory" / "financials" / "financial_truth_pack.json",
        company_root / "company_memory" / "financials" / "investor_financial_modules" / "investor_financial_modules_manifest.json",
    ]
    newer_sources = [
        path
        for path in financial_sources
        if path.exists() and pcim_path.exists() and path.stat().st_mtime > pcim_path.stat().st_mtime
    ]
    if newer_sources:
        result = dict(result)
        result["status"] = "fail"
        result["failures"] = _dedupe_preserve(
            list(result.get("failures", []) or [])
            + [
                "PCIM is stale relative to governed financial outputs; rebuild CIM/PCIM before running the investor panel."
            ]
        )
        result["stale_financial_sources"] = [str(path) for path in newer_sources]
    return result


def run_panel_stage(company, context=None, include_evidence_ids=False, regenerate_analysts=False):
    if context is not None:
        set_context(context)

    panel_dir = _panel_output_dir(company, context=context)
    panel_dir.mkdir(parents=True, exist_ok=True)
    pcim_path = Path("companies") / company / "company_memory" / "pcim_v1.json"

    summary = {
        "company": company,
        "year": context.year if context is not None else None,
        "run_mode": "panel_v2_financial_aware",
        "analyst_source_mode": "regenerated" if regenerate_analysts else "loaded_existing",
        "status": "pass",
        "financial_context": {
            "available": False,
            "status": "missing",
            "artifacts_checked": [],
            "missing_artifacts": [],
            "warnings": [],
            "limitations": [],
        },
        "stages": {
            "cim": {},
            "pcim": {},
            "analysts": {},
            "committee_synthesis": {},
            "committee_brief": {},
            "committee_brief_qa": {},
        },
        "analysts": {},
        "committee": {
            "synthesis_path": None,
            "brief_path": None,
            "qa_path": None,
            "financial_committee_view_present": False,
            "qa_status": "fail",
            "warnings": [],
            "hard_failures": [],
        },
        "outputs": {},
        "warnings": [],
        "hard_failures": [],
        "failures": [],
        "generated_at": None,
    }

    def record_stage(stage, status, output="", warnings=None, failures=None):
        warnings = list(warnings or [])
        failures = list(failures or [])
        previous = summary["stages"].get(stage) or {}
        merged_status = _merge_status(str(previous.get("status") or "pass"), status)
        merged_warnings = _dedupe_preserve(list(previous.get("warnings", []) or []) + warnings)
        merged_failures = _dedupe_preserve(list(previous.get("hard_failures", []) or []) + failures)
        summary["stages"][stage] = {
            "status": merged_status,
            "output": output,
            "warnings": merged_warnings,
            "hard_failures": merged_failures,
            "failures": merged_failures,
        }
        for item in warnings:
            if item not in summary["warnings"]:
                summary["warnings"].append(item)
        for item in failures:
            if item not in summary["hard_failures"]:
                summary["hard_failures"].append(item)
            if item not in summary["failures"]:
                summary["failures"].append(item)
        summary["status"] = _merge_status(summary["status"], status)

    def finalize_and_raise(message):
        canonicalize_panel_run_summary(summary)
        summary["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        summary["outputs"]["panel_run_summary"] = str(_panel_summary_path(company, context=context))
        summary_path = _write_panel_run_summary(company, summary, context=context)
        print(f"Panel Run — {company}")
        for stage_name, stage in summary["stages"].items():
            if not stage:
                continue
            print(f"{stage_name}: {str(stage.get('status', 'fail')).upper()}")
        print(f"Overall: {summary['status'].upper()}")
        print(f"Summary: {summary_path}")
        raise RuntimeError(message)

    financial_context = _assess_panel_financial_context(context)
    summary["financial_context"] = {
        key: value for key, value in financial_context.items() if key != "hard_failures"
    }
    for warning in summary["financial_context"]["warnings"]:
        if warning not in summary["warnings"]:
            summary["warnings"].append(warning)
    if financial_context["hard_failures"]:
        for failure in financial_context["hard_failures"]:
            if failure not in summary["hard_failures"]:
                summary["hard_failures"].append(failure)
        summary["status"] = _merge_status(summary["status"], "fail")
        finalize_and_raise(financial_context["hard_failures"][0])
    if summary["financial_context"]["status"] in {"warning", "partial", "missing"}:
        summary["status"] = _merge_status(summary["status"], "warning")

    if context is not None:
        try:
            cim_paths = run_cim_stage(company=company, context=context)
        except Exception as exc:
            record_stage(
                "cim",
                "fail",
                failures=[f"cim: stage execution failed: {exc}"],
            )
            finalize_and_raise("Panel stopped: CIM generation failed")
        record_stage(
            "cim",
            "pass",
            output=str(cim_paths.get("cim_v1.json", "")),
        )
        summary["outputs"].update({key: str(value) for key, value in cim_paths.items()})

    pcim_failures = []
    pcim_warnings = []
    if not pcim_path.exists():
        pcim_failures.append(f"PCIM missing: {pcim_path}")
        record_stage("pcim", "fail", output=str(pcim_path), failures=pcim_failures)
        finalize_and_raise(pcim_failures[0])
    pcim_payload = _load_json_file(pcim_path)
    if _contains_source_chunk(pcim_payload):
        pcim_failures.append(f"PCIM contains source_chunk: {pcim_path}")
    if _contains_raw_financial_table_reference(pcim_payload):
        pcim_failures.append(f"PCIM contains raw financial table content: {pcim_path}")
    freshness = _assess_pcim_freshness(company, pcim_payload)
    manifest_status = freshness.get("status")
    if manifest_status == "fail":
        generic_pcim_failure = f"PCIM source manifest unusable: {pcim_path}"
        detailed_pcim_failures = list(freshness.get("failures", []))
        pcim_failures.append(generic_pcim_failure)
        pcim_failures.extend(detailed_pcim_failures)
        record_stage("pcim", "fail", output=str(pcim_path), failures=pcim_failures)
        if detailed_pcim_failures and detailed_pcim_failures[0] != "Saved PCIM source manifest status is fail.":
            finalize_and_raise(detailed_pcim_failures[0])
        finalize_and_raise(generic_pcim_failure)
    if manifest_status == "warning":
        pcim_warnings.extend(freshness.get("warnings", []))
    pcim_status = "fail" if pcim_failures else ("warning" if pcim_warnings else "pass")
    record_stage("pcim", pcim_status, output=str(pcim_path), warnings=pcim_warnings, failures=pcim_failures)
    if pcim_failures:
        finalize_and_raise(pcim_failures[0])
    if pcim_warnings:
        summary["status"] = _merge_status(summary["status"], "warning")
    summary["outputs"]["pcim_v1.json"] = str(pcim_path)
    if manifest_status == "warning":
        pass
    else:
        pass

    analyst_order = ["graham", "buffett", "fisher", "munger", "lynch"]
    analyst_failures = []
    if regenerate_analysts:
        for analyst in analyst_order:
            try:
                run_investor_panel_stage(company=company, analyst=analyst, context=context)
            except Exception as exc:
                summary["analysts"][analyst] = {
                    "status": "fail",
                    "output_path": None,
                    "financials_used": False,
                    "financial_sections_consumed": [],
                    "evidence_grounding_status": "fail",
                    "validation_status": "fail",
                    "warnings": [],
                    "hard_failures": [f"{analyst}: stage execution failed: {exc}"],
                }
                record_stage(
                    "analysts",
                    "fail",
                    warnings=[],
                    failures=[f"{analyst}: stage execution failed: {exc}"],
                )
                analyst_failures.append(f"{analyst}: stage execution failed: {exc}")
                continue
            result = _validate_analyst_output(company, analyst, context=context)
            payload = result["payload"]
            financial_assessment = payload.get("financial_assessment") or {}
            summary["analysts"][analyst] = {
                "status": result.get("resolved_final_status", result.get("status", "fail")),
                "output_path": result["output"],
                "financials_used": bool(financial_assessment.get("financials_used")),
                "financial_sections_consumed": list(payload.get("financial_sections_consumed", []) or []),
                "evidence_grounding_status": result.get(
                    "resolved_final_evidence_grounding_status",
                    result.get("evidence_grounding_status", "fail"),
                ),
                "validation_status": result.get(
                    "resolved_final_validation_status",
                    result.get("validation_status", result.get("status", "fail")),
                ),
                "raw_artifact_status": str(payload.get("status") or ""),
                "pre_finalization_status": result.get("pre_finalization_status", {}),
                "post_finalization_status": result.get("post_finalization_status", {}),
                "finalization_summary": result.get("finalization_summary", {}),
                "diagnostics_used": bool(result.get("diagnostics_used")),
                "warnings": result["warnings"],
                "hard_failures": result["failures"],
            }
            summary["outputs"][f"{analyst}_analysis.json"] = result["output"]
            record_stage(
                "analysts",
                result["status"],
                output="; ".join(
                    f"{name}:{data['status']}"
                    for name, data in summary["analysts"].items()
                ),
                warnings=result["warnings"],
                failures=result["failures"],
            )
            if result["status"] == "fail":
                analyst_failures.extend(result["failures"])
    else:
        validation = validate_existing_panel_artifacts(company, panel_dir, context=context)
        for analyst in analyst_order:
            result = validation["analysts"][analyst]
            payload = result.get("payload") or {}
            financial_assessment = payload.get("financial_assessment") or {}
            summary["analysts"][analyst] = {
                "status": result["status"],
                "output_path": result.get("output"),
                "financials_used": bool(financial_assessment.get("financials_used")),
                "financial_sections_consumed": list(payload.get("financial_sections_consumed", []) or []),
                "evidence_grounding_status": result.get("resolved_final_evidence_grounding_status", result.get("evidence_grounding_status", "fail")),
                "validation_status": result.get("resolved_final_validation_status", result["status"]),
                "raw_artifact_status": str(payload.get("status") or ""),
                "pre_finalization_status": result.get("pre_finalization_status", {}),
                "post_finalization_status": result.get("post_finalization_status", {}),
                "finalization_summary": result.get("finalization_summary", {}),
                "diagnostics_used": bool(result.get("diagnostics_used")),
                "warnings": list(result.get("warnings") or []),
                "hard_failures": list(result.get("failures") or []),
            }
            if result.get("output"):
                summary["outputs"][f"{analyst}_analysis.json"] = result["output"]
            if result["status"] == "fail":
                analyst_failures.extend(list(result.get("failures") or []))
        record_stage(
            "analysts",
            validation["status"],
            output="; ".join(
                f"{name}:{data['status']}"
                for name, data in summary["analysts"].items()
            ),
            warnings=validation["warnings"],
            failures=validation["failures"],
        )

    canonicalize_panel_run_summary(summary)

    if summary["stages"].get("analysts", {}).get("status") == "fail":
        finalize_and_raise("Panel stopped: analyst validation failed. See panel_run_summary.json for all failures.")

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
    for item in synthesis_payload.get("areas_of_disagreement", []) or []:
        if not isinstance(item, dict):
            synthesis_failures.append("committee_synthesis: areas_of_disagreement contains non-object item")
            continue
        if item.get("disagreement_type") not in {
            "true_disagreement",
            "different_emphasis",
            "risk_weighting_difference",
        }:
            synthesis_failures.append("committee_synthesis: disagreement_type missing")
            break
    if list(normalization.get("unresolved_ids", []) or []):
        synthesis_failures.append("committee_synthesis: unresolved_ids remain after cleanup")
    synthesis_status = "fail" if synthesis_failures else "pass"
    summary["committee"]["synthesis_path"] = str(synthesis_path)
    summary["committee"]["financial_committee_view_present"] = isinstance(
        synthesis_payload.get("financial_committee_view"), dict
    )
    summary["outputs"]["committee_synthesis.json"] = str(synthesis_path)
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
    summary["committee"]["brief_path"] = str(brief_path)
    summary["outputs"]["committee_brief.md"] = str(brief_path)
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
    summary["committee"]["qa_path"] = str(qa_path)
    summary["committee"]["qa_status"] = qa_status
    summary["committee"]["warnings"] = list(qa_payload.get("warnings", []) or [])
    summary["committee"]["hard_failures"] = list(qa_payload.get("failures", []) or [])
    summary["outputs"]["committee_brief_qa.json"] = str(qa_path)
    record_stage(
        "committee_brief_qa",
        qa_status,
        output=str(qa_path),
        warnings=list(qa_payload.get("warnings", []) or []),
        failures=list(qa_payload.get("failures", []) or []),
    )
    if qa_status == "warning":
        summary["status"] = _merge_status(summary["status"], "warning")
    if qa_status == "fail":
        finalize_and_raise("Panel stopped: committee brief QA failed")

    canonicalize_panel_run_summary(summary)
    summary["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary["outputs"]["panel_run_summary"] = str(_panel_summary_path(company, context=context))
    summary_path = _write_panel_run_summary(company, summary, context=context)
    summary["outputs"]["panel_run_summary"] = str(summary_path)

    print(f"Panel Run — {company}")
    if context is not None:
        print(f"Year: {context.year}")
    print(f"Financial context: {summary['financial_context']['status'].upper()}")
    print(f"PCIM: {summary['stages']['pcim'].get('status', 'fail').upper()}")
    for analyst in analyst_order:
        print(f"{analyst.title()}: {summary['analysts'][analyst]['status'].upper()}")
    print(f"Committee synthesis: {summary['stages']['committee_synthesis'].get('status', 'fail').upper()}")
    print(f"Committee brief: {summary['stages']['committee_brief'].get('status', 'fail').upper()}")
    print(f"Committee brief QA: {summary['committee']['qa_status'].upper()}")
    print(f"Overall: {summary['status'].upper()}")
    print("Outputs:")
    print("- committee_synthesis.json")
    print("- committee_brief.md")
    print("- committee_brief_qa.json")
    print("- panel_run_summary.json")

    canonicalize_panel_run_summary(summary)
    _write_panel_run_summary(company, summary, context=context)
    return {"panel_run_summary.json": summary_path, **summary["outputs"]}


def run_all(context=None):
    return run_stage_sequence(context.company if context is not None else None, ALL_STAGE_SEQUENCE, context=context, profile_name="all")


def _build_stage_output_map(context):
    return {
        "preflight": lambda: [str(context.extracted_dir / "clean_chunks.json")],
        "discovery": lambda: [str(context.raw_dir / filename) for filename in DISCOVERY_OUTPUT_FILES],
        "financial_discovery": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_DISCOVERY_OUTPUT_FILES],
        "financial_extraction": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_EXTRACTION_OUTPUT_FILES],
        "financial_normalization": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_NORMALIZATION_OUTPUT_FILES],
        "financial_validation": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_VALIDATION_OUTPUT_FILES],
        "financial_reconciliation": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_RECONCILIATION_OUTPUT_FILES],
        "financial_basis_resolution": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_BASIS_RESOLUTION_OUTPUT_FILES],
        "financial_truth_registry": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_TRUTH_REGISTRY_OUTPUT_FILES],
        "financial_ratios": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_RATIO_OUTPUT_FILES],
        "financial_growth": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_GROWTH_OUTPUT_FILES],
        "financial_quality": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_QUALITY_OUTPUT_FILES],
        "corporate_actions": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_CORPORATE_ACTION_OUTPUT_FILES],
        "shareholding_pattern": lambda: [str(context.financials_dir / filename) for filename in FINANCIAL_SHAREHOLDING_OUTPUT_FILES],
        "financials": lambda: [str(context.financials_dir / "financial_audit_report.json")],
        "financial_pcim_validation": lambda: [str(context.financials_dir / "financial_pcim_validation.json")],
        "extraction": lambda: [str(context.extracted_dir / filename) for filename in EXTRACTION_OUTPUT_FILES],
        "cleaning": lambda: [str(context.extracted_dir / filename) for filename in CLEANING_OUTPUT_FILES],
        "business_understanding": lambda: [str(context.intelligence_dir / filename) for filename in BUSINESS_UNDERSTANDING_OUTPUT_FILES],
        "business_intelligence": lambda: [str(context.intelligence_dir / filename) for filename in BUSINESS_INTELLIGENCE_OUTPUT_FILES],
        "intelligence": lambda: [str(context.intelligence_dir / filename) for filename in INTELLIGENCE_OUTPUT_FILES],
        "cim": lambda: [
            str(Path("companies") / context.company / "company_memory" / "cim_v1.json"),
            str(Path("companies") / context.company / "company_memory" / "pcim_v1.json"),
        ],
        "management_commitments": lambda: [
            str(Path("companies") / context.company / "company_memory" / "management_commitments" / filename)
            for filename in MANAGEMENT_COMMITMENTS_OUTPUT_FILES
        ],
        "management_commentary": lambda: [
            str(Path("companies") / context.company / "company_memory" / "management_commentary" / filename)
            for filename in MANAGEMENT_COMMENTARY_OUTPUT_FILES
        ],
        "capital_allocation_outcomes": lambda: [
            str(Path("companies") / context.company / "company_memory" / "capital_allocation_outcomes" / filename)
            for filename in CAPITAL_ALLOCATION_OUTCOMES_OUTPUT_FILES
        ],
        "management_quality": lambda: [
            str(Path("companies") / context.company / "company_memory" / "management_quality" / filename)
            for filename in MANAGEMENT_QUALITY_OUTPUT_FILES
        ],
        "projects": lambda: [
            str(Path("companies") / context.company / "company_memory" / "projects" / filename)
            for filename in PROJECTS_OUTPUT_FILES
        ],
        "capacity_evolution": lambda: [
            str(Path("companies") / context.company / "company_memory" / "capacity" / filename)
            for filename in CAPACITY_EVOLUTION_OUTPUT_FILES
        ],
        "risk_evolution": lambda: [
            str(Path("companies") / context.company / "company_memory" / "risks" / filename)
            for filename in RISK_EVOLUTION_OUTPUT_FILES
        ],
        "pcim": lambda: [str(Path("companies") / context.company / "company_memory" / "pcim_v1.json")],
        "multi_year_memory": lambda: [str(Path("companies") / context.company / "company_memory" / "multi_year" / "multi_year_index.json")],
        "financial_memory": lambda: [
            str(Path("companies") / context.company / "company_memory" / "financials" / filename)
            for filename in FINANCIAL_MEMORY_OUTPUT_FILES
        ],
        "financial_trends": lambda: [
            str(Path("companies") / context.company / "company_memory" / "financials" / filename)
            for filename in FINANCIAL_TRENDS_OUTPUT_FILES
        ],
        "financial_attribution": lambda: [
            str(Path("companies") / context.company / "company_memory" / "financials" / filename)
            for filename in FINANCIAL_ATTRIBUTION_OUTPUT_FILES
        ],
        "investor_financials": lambda: [
            str(Path("companies") / context.company / "company_memory" / "financials" / "investor_financial_modules" / filename)
            for filename in INVESTOR_FINANCIAL_MODULE_OUTPUT_FILES
        ],
        "investor_briefs": lambda: [
            str(Path("companies") / context.company / "company_memory" / "investor_panel" / "briefs")
        ],
        "audit": lambda: [
            str(Path("companies") / context.company / "audit" / "company_artifact_audit.json"),
            str(Path("companies") / context.company / "audit" / "company_artifact_audit.md"),
            str(Path("companies") / context.company / "audit" / "financial_quality_scorecard.json"),
            str(Path("companies") / context.company / "audit" / "financial_quality_scorecard.md"),
        ],
        "panel": lambda: [str(Path("companies") / context.company / "company_memory" / "investor_panel" / "panel_run_summary.json")],
        "panel_doctor": lambda: [str(Path("companies") / context.company / "company_memory" / "panel_doctor_report.json")],
        "ask_intrinsiciq": lambda: [
            str(Path("companies") / context.company / "company_memory" / "ask_intrinsiciq" / filename)
            for filename in ASK_INTRINSICIQ_OUTPUT_FILES
        ],
        "company_model": lambda: [
            str(Path("companies") / context.company / "company_memory" / "company_model" / filename)
            for filename in COMPANY_MODEL_OUTPUT_FILES
        ],
        "company_memory": lambda: [str(Path("companies") / context.company / "company_memory" / "company_memory.json")],
        "management_progression": lambda: [
            str(Path("companies") / context.company / "company_memory" / "management_progression" / filename)
            for filename in MANAGEMENT_PROGRESSION_OUTPUT_FILES
        ],
    }


def _build_run_summary(context, profile_name):
    return {
        "company": context.company,
        "year": context.year,
        "run_mode": f"{profile_name}_v2",
        "stage_profile": profile_name,
        "status": "pass",
        "stages": [],
        "completed_stages": [],
        "skipped_stages": [],
        "failed_stage": None,
        "llm_calls_estimated": 0,
        "warnings": [],
        "failures": [],
        "total_runtime_seconds": 0.0,
        "generated_at": None,
    }


def _finalize_run_summary(summary, context, started_at, skipped_stages):
    summary["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary["total_runtime_seconds"] = round(time.time() - started_at, 3)
    summary["completed_stages"] = [stage["stage"] for stage in summary["stages"] if stage["status"] in {"pass", "warning"}]
    summary["skipped_stages"] = list(skipped_stages)
    summary_path = context.year_root / "run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary_path


def _print_stage_sequence_summary(profile_name, summary):
    completed = summary.get("completed_stages", [])
    skipped = summary.get("skipped_stages", [])
    failed_stage = summary.get("failed_stage")
    if profile_name == "production" and summary.get("status") != "fail":
        completed_set = set(completed)

        def _status_for_group(required_stages):
            return "complete" if all(stage in completed_set for stage in required_stages) else "incomplete"

        print("Production pipeline complete")
        print()
        print(f"Core intelligence: {_status_for_group(ALL_STAGE_SEQUENCE)}")
        print(f"Financial intelligence: {_status_for_group(['financials', 'financial_memory', 'investor_financials', 'financial_pcim_validation'])}")
        print(f"Audit/readiness: {_status_for_group(['audit'])}")
        print(f"Investor panel: {_status_for_group(['panel'])}")
        print(f"Ask IntrinsicIQ: {_status_for_group(['ask_intrinsiciq'])}")
    else:
        print(f"{profile_name.capitalize()} pipeline {'complete' if summary.get('status') != 'fail' else 'stopped'}")
    print()
    print(f"Completed stages: {', '.join(completed) if completed else 'None'}")
    print(f"Failed stage: {failed_stage or 'None'}")
    print(f"Skipped stages: {', '.join(skipped) if skipped else 'None'}")
    print(f"Total runtime: {summary.get('total_runtime_seconds', 0.0):.3f}s")


def _record_stage(summary, stage_name, status, outputs=None, warnings=None, failures=None):
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
    if status == "fail":
        summary["failed_stage"] = stage_name
    summary["status"] = _merge_status(summary["status"], status)


def _reusable_year_financial_outputs(context):
    """Return reusable only for a complete, non-failing artifact set for this year."""
    required = (
        "normalized_fundamentals.json",
        "financial_validation_report.json",
        "financial_reconciliation_report.json",
        "financial_ratios.json",
        "financial_growth.json",
        "corporate_actions.json",
        "shareholding_pattern.json",
        "financial_audit_report.json",
    )
    payloads = {}
    for filename in required:
        path = context.financials_dir / filename
        if not path.exists():
            return False, []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False, []
        if not isinstance(payload, dict):
            return False, []
        payloads[filename] = payload

    for filename, payload in payloads.items():
        if str(payload.get("company", "")) != context.company or str(payload.get("year", "")) != context.year:
            return False, []

    for filename in ("financial_validation_report.json", "financial_reconciliation_report.json"):
        if str(payloads[filename].get("status", "")).lower() == "fail":
            return False, []
        if payloads[filename].get("hard_failures"):
            return False, []

    audit = payloads["financial_audit_report.json"]
    if str(audit.get("status", "")).lower() not in {"pass", "warning"} or audit.get("hard_failures"):
        return False, []

    return True, [
        f"Reused existing validated financial outputs for {context.year}; no cross-period values were substituted."
    ]


def _run_stage_by_name(stage_name, context, *, stage_outputs, options, state):
    company = context.company
    if stage_name == "preflight":
        _run_preflight(context)
        return {"status": "pass", "outputs": stage_outputs["preflight"]()}
    if stage_name == "discovery":
        run_discovery(context=context)
        return {"status": "pass", "outputs": stage_outputs["discovery"]()}
    if stage_name == "extraction":
        run_extraction(context=context)
        return {"status": "pass", "outputs": stage_outputs["extraction"]()}
    if stage_name == "cleaning":
        run_cleaning(context=context)
        return {"status": "pass", "outputs": stage_outputs["cleaning"]()}
    if stage_name == "business_understanding":
        bundle = run_business_understanding_stage(context=context)
        validate_business_understanding_bundle(bundle)
        if sum(_artifact_counts(context.intelligence_dir, BUSINESS_UNDERSTANDING_OUTPUT_FILES).values()) <= 0:
            raise RuntimeError("business_understanding produced no usable artifacts")
        state["business_understanding_bundle"] = bundle
        return {"status": "pass", "outputs": stage_outputs["business_understanding"]()}
    if stage_name == "business_intelligence":
        bundle = state.get("business_understanding_bundle")
        if bundle is None:
            bundle = _load_saved_business_intelligence_bundle(context)
        run_business_intelligence_stage(context=context, bundle=bundle)
        if sum(_artifact_counts(context.intelligence_dir, BUSINESS_INTELLIGENCE_OUTPUT_FILES).values()) <= 0:
            raise RuntimeError("business_intelligence produced no usable artifacts")
        return {"status": "pass", "outputs": stage_outputs["business_intelligence"]()}
    if stage_name == "intelligence":
        run_intelligence(context=context)
        return {"status": "pass", "outputs": stage_outputs["intelligence"]()}
    if stage_name == "multi_year_memory":
        _, warnings = _require_company_level_intelligence(company, "multi_year_memory")
        run_multi_year_memory_stage(company=company, context=context)
        return {
            "status": "warning" if warnings else "pass",
            "outputs": stage_outputs["multi_year_memory"](),
            "warnings": warnings,
        }
    if stage_name == "management_commitments":
        _, warnings = _require_company_level_intelligence(company, "management_commitments")
        run_management_commitments_stage(company=company, context=context)
        return {
            "status": "warning" if warnings else "pass",
            "outputs": stage_outputs["management_commitments"](),
            "warnings": warnings,
        }
    if stage_name == "management_commentary":
        _, warnings = _require_company_level_intelligence(company, "management_commentary")
        run_management_commentary_stage(company=company, context=context)
        return {
            "status": "warning" if warnings else "pass",
            "outputs": stage_outputs["management_commentary"](),
            "warnings": warnings,
        }
    if stage_name == "capital_allocation_outcomes":
        _, warnings = _require_company_level_intelligence(company, "capital_allocation_outcomes")
        run_capital_allocation_outcomes_stage(company=company, context=context)
        return {
            "status": "warning" if warnings else "pass",
            "outputs": stage_outputs["capital_allocation_outcomes"](),
            "warnings": warnings,
        }
    if stage_name == "management_quality":
        _, warnings = _require_company_level_intelligence(company, "management_quality")
        run_management_quality_stage(company=company, context=context)
        return {
            "status": "warning" if warnings else "pass",
            "outputs": stage_outputs["management_quality"](),
            "warnings": warnings,
        }
    if stage_name == "projects":
        _, warnings = _require_company_level_intelligence(company, "projects")
        run_projects_stage(company=company, context=context)
        return {
            "status": "warning" if warnings else "pass",
            "outputs": stage_outputs["projects"](),
            "warnings": warnings,
        }
    if stage_name == "capacity_evolution":
        _, warnings = _require_company_level_intelligence(company, "capacity_evolution")
        run_capacity_evolution_stage(company=company, context=context)
        return {
            "status": "warning" if warnings else "pass",
            "outputs": stage_outputs["capacity_evolution"](),
            "warnings": warnings,
        }
    if stage_name == "risk_evolution":
        _, warnings = _require_company_level_intelligence(company, "risk_evolution")
        run_risk_evolution_stage(company=company, context=context)
        return {
            "status": "warning" if warnings else "pass",
            "outputs": stage_outputs["risk_evolution"](),
            "warnings": warnings,
        }
    if stage_name in {"cim", "pcim"}:
        if not state.get("cim_pcim_built"):
            _, warnings = _require_company_level_intelligence(company, "cim/pcim")
            run_cim_stage(company=company, context=context)
            state["cim_pcim_built"] = True
            state["cim_pcim_warnings"] = warnings
        outputs_key = "cim" if stage_name == "cim" else "pcim"
        return {
            "status": "pass",
            "outputs": stage_outputs[outputs_key](),
            "warnings": state.get("cim_pcim_warnings", []) if stage_name == "cim" else [],
        }
    if stage_name == "financials":
        if options.get("_profile_name") == "production" and not options.get("force", False):
            reusable, reuse_warnings = _reusable_year_financial_outputs(context)
            if reusable:
                return {
                    "status": "warning" if reuse_warnings else "pass",
                    "outputs": stage_outputs["financials"](),
                    "warnings": reuse_warnings,
                }
        run_financials_stage(context=context)
        return {"status": "pass", "outputs": stage_outputs["financials"]()}
    if stage_name == "financial_quality":
        run_financial_quality_stage(company=company, context=context)
        return {"status": "pass", "outputs": stage_outputs["financial_quality"]()}
    if stage_name == "financial_basis_resolution":
        run_financial_basis_resolution(context=context)
        return {"status": "pass", "outputs": stage_outputs["financial_basis_resolution"]()}
    if stage_name == "financial_truth_registry":
        run_financial_truth_registry(context=context)
        return {"status": "pass", "outputs": stage_outputs["financial_truth_registry"]()}
    if stage_name == "financial_memory":
        run_financial_memory_stage(company=company, context=context)
        return {"status": "pass", "outputs": stage_outputs["financial_memory"]()}
    if stage_name == "financial_trends":
        run_financial_trends_stage(company=company, context=context)
        return {"status": "pass", "outputs": stage_outputs["financial_trends"]()}
    if stage_name == "financial_attribution":
        run_financial_attribution_stage(company=company, context=context)
        return {"status": "pass", "outputs": stage_outputs["financial_attribution"]()}
    if stage_name == "investor_financials":
        run_investor_financials_stage(company=company, context=context)
        return {"status": "pass", "outputs": stage_outputs["investor_financials"]()}
    if stage_name == "financial_pcim_validation":
        run_financial_pcim_validation_stage(context=context)
        return {"status": "pass", "outputs": stage_outputs["financial_pcim_validation"]()}
    if stage_name == "company_memory":
        written_paths = run_company_memory_stage(company=company, context=context)
        outputs = [str(path) for path in written_paths.values()] if isinstance(written_paths, dict) else [str(path) for path in written_paths]
        return {"status": "pass", "outputs": sorted(outputs)}
    if stage_name == "investor_briefs":
        run_investor_briefs_stage(company=company, context=context)
        return {"status": "pass", "outputs": stage_outputs["investor_briefs"]()}
    if stage_name == "audit":
        run_audit_stage(company=company, context=context, fix_safe=options.get("fix_safe", False))
        payload = _load_audit_payload(company)
        status = str(payload.get("status") or "pass").lower()
        normalized_status = "warning" if status == "warning" else "pass" if status == "pass" else "fail"
        warnings = [str(item) for item in (payload.get("warnings") or [])]
        failures = [str(item) for item in (payload.get("critical_failures") or [])] if normalized_status == "fail" else []
        return {
            "status": normalized_status,
            "outputs": stage_outputs["audit"](),
            "warnings": warnings,
            "failures": failures,
        }
    if stage_name == "panel":
        run_panel_stage(
            company=company,
            context=context,
            include_evidence_ids=options.get("include_evidence_ids", False),
            regenerate_analysts=options.get("regenerate_analysts", False),
        )
        return {"status": "pass", "outputs": stage_outputs["panel"]()}
    if stage_name == "panel_doctor":
        run_panel_doctor_stage(company=company, context=context)
        return {"status": "pass", "outputs": stage_outputs["panel_doctor"]()}
    if stage_name == "ask_intrinsiciq":
        _ensure_audit_allows_customer_output(company)
        run_ask_intrinsiciq_stage(company=company, context=context, force=options.get("force", False))
        return {"status": "pass", "outputs": stage_outputs["ask_intrinsiciq"]()}
    if stage_name == "company_model":
        run_company_model_stage(company=company, context=context)
        return {"status": "pass", "outputs": stage_outputs["company_model"]()}
    if stage_name == "management_progression":
        run_management_progression_stage(company=company, context=context)
        return {"status": "pass", "outputs": stage_outputs["management_progression"]()}
    raise RuntimeError(f"Unsupported sequence stage: {stage_name}")


def run_stage_sequence(company_slug, stages, options=None, context=None, profile_name="custom"):
    context = _ensure_sequence_context(company_slug, profile_name, context)
    set_context(context)
    options = dict(options or {})
    options["_profile_name"] = profile_name
    summary = _build_run_summary(context, profile_name)
    stage_outputs = _build_stage_output_map(context)
    stage_list = list(stages)
    started_at = time.time()
    state = {}
    skipped_stages = []

    try:
        for index, stage_name in enumerate(stage_list):
            result = _run_stage_by_name(stage_name, context, stage_outputs=stage_outputs, options=options, state=state)
            _record_stage(
                summary,
                stage_name,
                result.get("status", "pass"),
                outputs=result.get("outputs"),
                warnings=result.get("warnings"),
                failures=result.get("failures"),
            )
            if result.get("status") == "fail":
                skipped_stages.extend(stage_list[index + 1 :])
                break
    except Exception as exc:
        current_stage = stage_list[len(summary["stages"])] if len(summary["stages"]) < len(stage_list) else profile_name
        _record_stage(summary, current_stage, "fail", failures=[str(exc)])
        skipped_stages.extend(stage_list[len(summary["stages"]) :])
        _finalize_run_summary(summary, context, started_at, skipped_stages)
        _print_stage_sequence_summary(profile_name, summary)
        raise

    _finalize_run_summary(summary, context, started_at, skipped_stages)
    _print_stage_sequence_summary(profile_name, summary)
    return summary


def print_stage_catalog():
    for stage_name in [
        "all",
        "production",
        "company_year",
        "discovery",
        "financial_discovery",
        "financial_extraction",
        "financial_normalization",
        "financial_validation",
        "financial_reconciliation",
        "financial_basis_resolution",
        "financial_truth_registry",
        "financial_ratios",
        "financial_growth",
        "corporate_actions",
        "shareholding_pattern",
        "financial_pcim_validation",
        "financials",
        "financial_trends",
        "financial_quality",
        "financial_attribution",
        "financial_memory",
        "investor_financials",
        "ask_intrinsiciq",
        "company_model",
        "management_progression",
        "extraction",
        "cleaning",
        "business_understanding",
        "business_intelligence",
        "intelligence",
        "company_memory",
        "management_commitments",
        "management_commentary",
        "capital_allocation_outcomes",
        "management_quality",
        "projects",
        "capacity_evolution",
        "risk_evolution",
        "cim",
        "pcim",
        "audit",
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
            "production",
            "company_year",
            "business_understanding",
            "business_intelligence",
            "financial_discovery",
            "financial_extraction",
            "financial_normalization",
            "financial_validation",
            "financial_reconciliation",
            "financial_basis_resolution",
            "financial_truth_registry",
            "financial_ratios",
            "financial_growth",
            "corporate_actions",
            "shareholding_pattern",
            "financials",
            "financial_trends",
            "financial_quality",
            "financial_attribution",
            "financial_memory",
            "investor_financials",
            "ask_intrinsiciq",
            "company_model",
            "management_progression",
            "financial_pcim_validation",
            "company_memory",
            "management_commitments",
            "management_commentary",
            "capital_allocation_outcomes",
            "management_quality",
            "projects",
            "capacity_evolution",
            "risk_evolution",
            "multi_year_memory",
            "cim",
            "pcim",
            "audit",
            "investor_panel",
            "investor_briefs",
            "committee_synthesis",
            "committee_brief",
            "committee_brief_qa",
            "panel",
            "panel_doctor",
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
        "--fix-safe",
        action="store_true",
        help="For audit, apply only deterministic safe repairs before writing the audit output.",
    )
    parser.add_argument(
        "--include-evidence-ids",
        action="store_true",
        help="For committee_brief, append a compact Evidence References section.",
    )
    parser.add_argument(
        "--regenerate-analysts",
        action="store_true",
        help="For panel, rerun analyst generation instead of reusing validated saved analyst artifacts.",
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
    if args.stage in COMPANY_LEVEL_STAGES and args.year and args.stage not in {"panel", "panel_doctor"}:
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
    elif args.stage == "production":
        run_stage_sequence(
            args.company,
            PRODUCTION_STAGE_SEQUENCE,
            context=context,
            profile_name="production",
            options={
                "fix_safe": args.fix_safe,
                "include_evidence_ids": args.include_evidence_ids,
                "regenerate_analysts": args.regenerate_analysts,
            },
        )
    elif args.stage == "company_year":
        run_stage_sequence(
            args.company,
            COMPANY_YEAR_STAGE_SEQUENCE,
            context=context,
            profile_name="company_year",
            options={
                "fix_safe": args.fix_safe,
                "include_evidence_ids": args.include_evidence_ids,
                "regenerate_analysts": args.regenerate_analysts,
            },
        )
    elif args.stage == "company_memory":
        run_stage_sequence(
            args.company,
            COMPANY_MEMORY_STAGE_SEQUENCE,
            context=context,
            profile_name="company_memory",
            options={
                "fix_safe": args.fix_safe,
                "include_evidence_ids": args.include_evidence_ids,
                "regenerate_analysts": args.regenerate_analysts,
            },
        )
    elif args.stage == "business_understanding":
        run_business_understanding_stage(context=context)
    elif args.stage == "business_intelligence":
        run_business_intelligence_stage(context=context)
    elif args.stage == "financial_discovery":
        run_financial_discovery(context=context)
    elif args.stage == "financial_extraction":
        run_financial_extraction(context=context)
    elif args.stage == "financial_normalization":
        run_financial_normalization(context=context)
    elif args.stage == "financial_validation":
        run_financial_validation(context=context)
    elif args.stage == "financial_reconciliation":
        run_financial_reconciliation(context=context)
    elif args.stage == "financial_basis_resolution":
        run_financial_basis_resolution(context=context)
    elif args.stage == "financial_truth_registry":
        run_financial_truth_registry(context=context)
    elif args.stage == "financial_ratios":
        run_financial_ratios(context=context)
    elif args.stage == "financial_growth":
        run_financial_growth(context=context)
    elif args.stage == "corporate_actions":
        run_corporate_actions(context=context)
    elif args.stage == "shareholding_pattern":
        run_shareholding_pattern(context=context)
    elif args.stage == "financials":
        run_financials_stage(context=context)
    elif args.stage == "financial_trends":
        run_financial_trends_stage(company=args.company, context=context)
    elif args.stage == "financial_quality":
        run_financial_quality_stage(company=args.company, context=context)
    elif args.stage == "financial_attribution":
        run_financial_attribution_stage(company=args.company, context=context)
    elif args.stage == "financial_memory":
        run_financial_memory_stage(company=args.company, context=context)
    elif args.stage == "investor_financials":
        run_investor_financials_stage(company=args.company, context=context)
    elif args.stage == "ask_intrinsiciq":
        run_ask_intrinsiciq_stage(company=args.company, context=context)
    elif args.stage == "company_model":
        run_company_model_stage(company=args.company, context=context)
    elif args.stage == "management_progression":
        run_management_progression_stage(company=args.company, context=context)
    elif args.stage == "financial_pcim_validation":
        run_financial_pcim_validation_stage(context=context)
    elif args.stage == "management_commitments":
        run_management_commitments_stage(company=args.company, context=context)
    elif args.stage == "management_commentary":
        run_management_commentary_stage(company=args.company, context=context)
    elif args.stage == "capital_allocation_outcomes":
        run_capital_allocation_outcomes_stage(company=args.company, context=context)
    elif args.stage == "management_quality":
        run_management_quality_stage(company=args.company, context=context)
    elif args.stage == "projects":
        run_projects_stage(company=args.company, context=context)
    elif args.stage == "capacity_evolution":
        run_capacity_evolution_stage(company=args.company, context=context)
    elif args.stage == "multi_year_memory":
        run_multi_year_memory_stage(company=args.company, context=context)
    elif args.stage in {"cim", "pcim"}:
        run_cim_stage(company=args.company, context=context)
    elif args.stage == "audit":
        run_audit_stage(company=args.company, context=context, fix_safe=args.fix_safe)
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
    elif args.stage == "panel_doctor":
        run_panel_doctor_stage(company=args.company, context=context)
    elif args.stage == "panel":
        run_panel_stage(
            company=args.company,
            context=context,
            include_evidence_ids=args.include_evidence_ids,
            regenerate_analysts=args.regenerate_analysts,
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
