from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List


ROBUSTNESS_BASELINE_VERSION = "robustness_baseline.v1"
ROBUSTNESS_BASELINE_DATE = "2026-08-17"


ALLOWED_CLASS_STATUSES = {"OPEN", "PARTIALLY_FIXED", "CLASS_FIXED", "UNKNOWN"}
ALLOWED_SEVERITIES = {"HARD_FAIL", "QUARANTINE", "WARNING"}
ALLOWED_EXPECTED_RESULTS = {"PASS", "REJECT", "WARNING"}


ROBUSTNESS_FAILURE_CLASSES: List[Dict[str, Any]] = [
    {
        "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED",
        "status": "PARTIALLY_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "TEMPORAL",
        "reopened": True,
        "known_instances": [
            "tanla fy20 promises",
            "tanla fy22 capital_allocations",
            "tanla fy23 capacity_expansions",
            "ujjivan fy21 capacity_expansions",
            "ujjivan fy23 promises",
            "ujjivan fy24 capital_allocations",
            "polymatech fy24 risks held-out future target negative",
            "sun_pharma fy20 projects_00011 ambiguous historical regulatory context",
        ],
        "closure_gaps": [
            "Sun Pharma FY20 showed that non-promotable ambiguous historical evidence needed local quarantine instead of a stage-level crash",
        ],
    },
    {
        "failure_class": "PRIMARY_PNL_PAT_MISSING",
        "status": "CLASS_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "FINANCIAL_EXTRACTION",
        "reopened": False,
        "known_instances": [
            "tanla fy22 PAT missing before normalization",
            "ujjivan fy22 PAT extraction bridge",
            "sun_pharma fy20 consolidated P&L continuation PAT missing",
            "sun_pharma fy22 consolidated P&L revenue missing (multi-chunk truncation at page 135)",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "PRIMARY_BALANCE_SHEET_REQUIRED_FIELD_MISSING",
        "status": "CLASS_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "FINANCIAL_EXTRACTION",
        "reopened": False,
        "known_instances": [
            "ujjivan fy21 total_assets missing",
            "ujjivan fy22 net_worth missing",
            "ujjivan fy23 total_assets regression",
            "ujjivan fy24 balance-sheet completeness",
            "tanla fy24 total equity and liabilities semantic collision",
            "datapatterns fy24 total equity and liabilities semantic collision",
            "sun_pharma fy20 consolidated balance-sheet continuation total_assets missing",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "WRONG_TAX_ROW_SELECTED",
        "status": "CLASS_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "FINANCIAL_NORMALIZATION",
        "reopened": False,
        "known_instances": [
            "ujjivan fy23 PAT bridge selected the wrong tax-like row",
            "ujjivan fy22 cash_flow Tax adjustment incorrectly mapped to P&L tax",
            "ujjivan balance_sheet Tax Expenses (including deferred tax) incorrectly mapped to P&L tax",
            "tanla fy24 verified correct P&L total tax expense selected",
            "datapatterns fy25 verified correct P&L total tax expense selected (held-out)",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "SEMANTIC_LINE_ITEM_COLLISION",
        "status": "CLASS_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "SEMANTIC_MAPPING",
        "reopened": False,
        "known_instances": [
            "revenue lookalike rows",
            "EPS/share-count lookalikes",
            "off-balance-sheet equity false matches",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "BASIS_MIXED_CONSOLIDATED_STANDALONE",
        "status": "CLASS_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "FINANCIAL_NORMALIZATION",
        "reopened": False,
        "known_instances": [
            "multiple financial artifacts still normalize with unknown basis",
            "tanla fy25 standalone cash-flow evidence promoted into consolidated canonical view",
            "datapatterns fy25 global consolidated hint overwrote standalone field-level basis",
            "ujjivan fy24 global consolidated hint overwrote unresolved field-level basis",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "SOURCE_PERIOD_VS_TARGET_PERIOD_CONFLICT",
        "status": "CLASS_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "TEMPORAL",
        "reopened": False,
        "known_instances": [
            "tanla fy23 capacity source period plus target period",
            "tanla fy24 promise source period plus target period",
            "tanla fy23 risks_00015 source context appears to be FY24/FY25 evidence",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "MULTI_EVENT_HISTORICAL_PERIOD_COLLISION",
        "status": "CLASS_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "TEMPORAL",
        "reopened": False,
        "known_instances": [
            "tanla fy24 capital_allocations_00016",
            "tanla fy24 capacity_expansions multi-phase",
            "tanla fy24 projects multi-phase",
            "ujjivan fy24 promises multi-tranche",
            "polymatech fy24 risks multi-period",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION",
        "status": "CLASS_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "COMPANY_ISOLATION",
        "reopened": False,
        "known_instances": [
            "tanla Ask IntrinsicIQ consumed Data Patterns-style language",
            "frontend loaders accepted mismatched company_slug metadata",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "BUSINESS_RELEVANCE_QUARANTINE",
        "status": "CLASS_FIXED",
        "severity": "QUARANTINE",
        "parent_family": "CLEANING",
        "reopened": False,
        "known_instances": [
            "tanla fy20 risk cleaner quarantined an item at the fatal boundary",
            "non-core CSR/civic items entered investor intelligence",
            "tanla fy20 risks_00015-00021 civic/public-interest items (consumer feedback, stakeholder litigation, labeling regulations, platform dependence) quarantined via four-outcome contract",
            "tanla fy24 risks_00023 ESG-related challenges demoted to secondary evidence",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "OCR_NO_TEXT_LAYER",
        "status": "CLASS_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "FINANCIAL_EXTRACTION",
        "reopened": False,
        "known_instances": [
            "polymatech fy22 image-only PDF",
            "classification is clean and OCR execution is now provisioned (tesseract 5.5.3 + pytesseract 0.3.13)",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "CAPACITY_STATUS_MISSING",
        "status": "CLASS_FIXED",
        "severity": "QUARANTINE",
        "parent_family": "CLEANING",
        "reopened": False,
        "known_instances": [
            "ujjivan fy24 capacity_expansions_00002",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "COMMITTEE_CRITICAL_UNKNOWN_CONTRACT_MISMATCH",
        "status": "CLASS_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "INVESTOR_PANEL",
        "reopened": False,
        "known_instances": [
            "tanla committee_synthesis critical_unknowns item missing unknown",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "COMMITTEE_BRIEF_QA_DUPLICATION",
        "status": "CLASS_FIXED",
        "severity": "WARNING",
        "parent_family": "INVESTOR_PANEL",
        "reopened": False,
        "known_instances": [
            "tanla committee_brief_qa duplication warning",
        ],
        "closure_gaps": [],
    },
    {
        "failure_class": "OPTIONAL_CANONICAL_FIELD_UNSAFE_RENDER",
        "status": "CLASS_FIXED",
        "severity": "HARD_FAIL",
        "parent_family": "COMPANY_ISOLATION",
        "reopened": False,
        "known_instances": [
            "tips how-does-it-make-money prerender undefined replace",
        ],
        "closure_gaps": [],
    },
]


ROBUSTNESS_CORPUS_MANIFEST: List[Dict[str, Any]] = [
    {
        "case_id": "temporal_comparative_tanla_fy20_promises",
        "company": "tanla",
        "year": "fy20",
        "stage": "cleaning",
        "module": "promises",
        "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED",
        "source_artifact": "companies/tanla/fy20/extracted/clean_promises.json",
        "expected_result": "PASS",
        "expected_outcome": "FY20 source context and FY19 comparatives do not make the promise chronology ambiguous",
        "test_reference": "tests/knowledge/test_company_memory_guardrails.py",
        "held_out": False,
    },
    {
        "case_id": "temporal_capital_context_tanla_fy22",
        "company": "tanla",
        "year": "fy22",
        "stage": "cleaning",
        "module": "capital_allocations",
        "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED",
        "source_artifact": "companies/tanla/fy22/extracted/clean_capital_allocation.json",
        "expected_result": "PASS",
        "expected_outcome": "FY21/FY22 comparative capital-allocation tables stay anchored to the FY22 source period",
        "test_reference": "tests/knowledge/test_company_memory_guardrails.py",
        "held_out": False,
    },
    {
        "case_id": "temporal_non_temporal_year_ujjivan_fy24_capital_allocation",
        "company": "ujjivan",
        "year": "fy24",
        "stage": "cleaning",
        "module": "capital_allocations",
        "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED",
        "source_artifact": "companies/ujjivan/fy24/extracted/clean_capital_allocation.json",
        "expected_result": "PASS",
        "expected_outcome": "Income Tax Act, 1961 is not treated as company event chronology",
        "test_reference": "tests/knowledge/test_company_memory_guardrails.py",
        "held_out": False,
    },
    {
        "case_id": "temporal_comparative_ujjivan_fy21_capacity",
        "company": "ujjivan",
        "year": "fy21",
        "stage": "cleaning",
        "module": "capacity_expansions",
        "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED",
        "source_artifact": "companies/ujjivan/fy21/extracted/clean_capacity.json",
        "expected_result": "PASS",
        "expected_outcome": "June 2020 to March 2021 disbursal progression resolves as FY21 source-period evidence",
        "test_reference": "tests/knowledge/test_company_memory_guardrails.py",
        "held_out": False,
    },
    {
        "case_id": "temporal_source_target_ujjivan_fy23_promises",
        "company": "ujjivan",
        "year": "fy23",
        "stage": "cleaning",
        "module": "promises",
        "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED",
        "source_artifact": "companies/ujjivan/fy23/extracted/clean_promises.json",
        "expected_result": "PASS",
        "expected_outcome": "FY21/FY22 historical context and Q1 FY24 target are separated from the FY23 promise source period",
        "test_reference": "tests/knowledge/test_company_memory_guardrails.py",
        "held_out": False,
    },
    {
        "case_id": "held_out_temporal_future_risk_polymatech_fy24",
        "company": "polymatech",
        "year": "fy24",
        "stage": "cleaning",
        "module": "risks",
        "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED",
        "source_artifact": "companies/polymatech/fy24/extracted/clean_risks.json",
        "expected_result": "PASS",
        "expected_outcome": "future 2030 target language does not crash risk cleaning or become unsupported chronology",
        "test_reference": "tests/knowledge/test_company_memory_guardrails.py",
        "held_out": True,
    },
    {
        "case_id": "temporal_non_promotable_ambiguous_project_sun_pharma_fy20",
        "company": "sun_pharma",
        "year": "fy20",
        "stage": "cleaning",
        "module": "projects",
        "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED",
        "source_artifact": "companies/sun_pharma/fy20/extracted/clean_projects_rejections.json",
        "expected_result": "PASS",
        "expected_outcome": "non-promotable ambiguous historical regulatory context is quarantined with diagnostics instead of crashing cleaning",
        "test_reference": "tests/processors/test_project_cleaner.py",
        "held_out": True,
    },
    {
        "case_id": "temporal_source_target_tanla_fy23_capacity",
        "company": "tanla",
        "year": "fy23",
        "stage": "cleaning",
        "module": "capacity_expansions",
        "failure_class": "SOURCE_PERIOD_VS_TARGET_PERIOD_CONFLICT",
        "source_artifact": "companies/tanla/fy23/extracted/clean_capacity.json",
        "expected_result": "PASS",
        "expected_outcome": "source period and target period remain distinct",
        "test_reference": "tests/processors/test_capacity_cleaner.py",
        "held_out": False,
    },
    {
        "case_id": "temporal_source_ownership_tanla_fy23_risk",
        "company": "tanla",
        "year": "fy23",
        "stage": "cleaning",
        "module": "risks",
        "failure_class": "SOURCE_PERIOD_VS_TARGET_PERIOD_CONFLICT",
        "source_artifact": "companies/tanla/fy23/extracted/clean_risks.json",
        "expected_result": "PASS",
        "expected_outcome": "FY24-owned source chunks are excluded from FY23 risk evidence instead of relabeled as FY23",
        "test_reference": "tests/processors/test_risk_cleaner.py",
        "held_out": False,
    },
    {
        "case_id": "held_out_temporal_source_ownership_validator",
        "company": "tanla",
        "year": "fy23",
        "stage": "cleaning",
        "module": "risks",
        "failure_class": "SOURCE_PERIOD_VS_TARGET_PERIOD_CONFLICT",
        "source_artifact": "companies/tanla/fy23/extracted/clean_risks.json",
        "expected_result": "PASS",
        "expected_outcome": "strict validator rejects cross-year source ownership before the cleaner excludes the contaminated item",
        "test_reference": "tests/knowledge/test_document_intake.py",
        "held_out": True,
    },
    {
        "case_id": "temporal_multi_event_tanla_fy24_capital_allocation",
        "company": "tanla",
        "year": "fy24",
        "stage": "cleaning",
        "module": "capital_allocations",
        "failure_class": "MULTI_EVENT_HISTORICAL_PERIOD_COLLISION",
        "source_artifact": "companies/tanla/fy24/extracted/clean_capital_allocation.json",
        "expected_result": "PASS",
        "expected_outcome": "multiple historical allocation events are split or represented without collapsing chronology",
        "test_reference": "tests/processors/test_capital_allocation_cleaner.py",
        "held_out": False,
    },
    {
        "case_id": "cleaning_risk_quarantine_tanla_fy20",
        "company": "tanla",
        "year": "fy20",
        "stage": "cleaning",
        "module": "risks",
        "failure_class": "BUSINESS_RELEVANCE_QUARANTINE",
        "source_artifact": "companies/tanla/fy20/extracted/clean_risks.json",
        "expected_result": "PASS",
        "expected_outcome": "quarantined non-investor risks do not crash the cleaner",
        "test_reference": "tests/processors/test_risk_cleaner.py",
        "held_out": False,
    },
    {
        "case_id": "held_out_cleaning_risk_quarantine_tanla_fy20",
        "company": "tanla",
        "year": "fy20",
        "stage": "cleaning",
        "module": "risks",
        "failure_class": "BUSINESS_RELEVANCE_QUARANTINE",
        "source_artifact": "companies/tanla/fy20/extracted/clean_risks.json",
        "expected_result": "PASS",
        "expected_outcome": "held-out civic/public-interest risk items (consumer feedback, stakeholder litigation, labeling regulations) are quarantined not retained as core",
        "test_reference": "tests/processors/test_risk_cleaner.py",
        "held_out": True,
    },
    {
        "case_id": "held_out_cleaning_risk_demote_tanla_fy24",
        "company": "tanla",
        "year": "fy24",
        "stage": "cleaning",
        "module": "risks",
        "failure_class": "BUSINESS_RELEVANCE_QUARANTINE",
        "source_artifact": "companies/tanla/fy24/extracted/clean_risks.json",
        "expected_result": "PASS",
        "expected_outcome": "held-out ESG-related risk is demoted to secondary evidence, not promoted to canonical core",
        "test_reference": "tests/processors/test_risk_cleaner.py",
        "held_out": True,
    },
    {
        "case_id": "cleaning_capacity_status_ujjivan_fy24",
        "company": "ujjivan",
        "year": "fy24",
        "stage": "cleaning",
        "module": "capacity_expansions",
        "failure_class": "CAPACITY_STATUS_MISSING",
        "source_artifact": "companies/ujjivan/fy24/extracted/clean_capacity.json",
        "expected_result": "PASS",
        "expected_outcome": "semantic operational status is normalized without fabricating in_progress",
        "test_reference": "tests/processors/test_capacity_cleaner.py",
        "held_out": False,
    },
    {
        "case_id": "financial_bs_ujjivan_fy21_total_assets_units",
        "company": "ujjivan",
        "year": "fy21",
        "stage": "financial_normalization",
        "module": "balance_sheet",
        "failure_class": "PRIMARY_BALANCE_SHEET_REQUIRED_FIELD_MISSING",
        "source_artifact": "companies/ujjivan/fy21/financials/normalized_fundamentals.json",
        "expected_result": "PASS",
        "expected_outcome": "large Total Assets values keep their declared thousands unit and survive normalization",
        "test_reference": "tests/financials/test_financial_extractor.py",
        "held_out": False,
    },
    {
        "case_id": "financial_bs_ujjivan_fy22_net_worth_path",
        "company": "ujjivan",
        "year": "fy22",
        "stage": "financial_normalization",
        "module": "balance_sheet",
        "failure_class": "PRIMARY_BALANCE_SHEET_REQUIRED_FIELD_MISSING",
        "source_artifact": "companies/ujjivan/fy22/financials/normalized_fundamentals.json",
        "expected_result": "PASS",
        "expected_outcome": "net worth is completed only from governed equity share capital plus reserves evidence",
        "test_reference": "tests/financials/test_financial_normalizer.py",
        "held_out": False,
    },
    {
        "case_id": "financial_bs_ujjivan_fy24_completeness",
        "company": "ujjivan",
        "year": "fy24",
        "stage": "financial_normalization",
        "module": "balance_sheet",
        "failure_class": "PRIMARY_BALANCE_SHEET_REQUIRED_FIELD_MISSING",
        "source_artifact": "companies/ujjivan/fy24/financials/normalized_fundamentals.json",
        "expected_result": "PASS",
        "expected_outcome": "assets, net worth, and liabilities are usable after face-value correction",
        "test_reference": "tests/financials/test_financial_normalizer.py",
        "held_out": False,
    },
    {
        "case_id": "financial_bs_ujjivan_fy23_regression",
        "company": "ujjivan",
        "year": "fy23",
        "stage": "financial_normalization",
        "module": "balance_sheet",
        "failure_class": "PRIMARY_BALANCE_SHEET_REQUIRED_FIELD_MISSING",
        "source_artifact": "companies/ujjivan/fy23/financials/normalized_fundamentals.json",
        "expected_result": "PASS",
        "expected_outcome": "FY23 assets, derived net worth, and derived liabilities remain available",
        "test_reference": "tests/financials/test_financial_normalizer.py",
        "held_out": False,
    },
    {
        "case_id": "financial_bs_tanla_fy24_equity_liabilities_collision",
        "company": "tanla",
        "year": "fy24",
        "stage": "financial_normalization",
        "module": "balance_sheet",
        "failure_class": "PRIMARY_BALANCE_SHEET_REQUIRED_FIELD_MISSING",
        "source_artifact": "companies/tanla/fy24/financials/normalized_fundamentals.json",
        "expected_result": "PASS",
        "expected_outcome": "Total Equity and Liabilities is rejected as net worth while real equity and derived liabilities survive",
        "test_reference": "tests/financials/test_line_item_mapper.py",
        "held_out": False,
    },
    {
        "case_id": "financial_bs_datapatterns_fy24_equity_liabilities_collision",
        "company": "datapatterns",
        "year": "fy24",
        "stage": "financial_normalization",
        "module": "balance_sheet",
        "failure_class": "PRIMARY_BALANCE_SHEET_REQUIRED_FIELD_MISSING",
        "source_artifact": "companies/datapatterns/fy24/financials/normalized_fundamentals.json",
        "expected_result": "PASS",
        "expected_outcome": "complete primary balance sheet maps assets, liabilities, and equity without promoting the balancing total to net worth",
        "test_reference": "tests/financials/test_line_item_mapper.py",
        "held_out": False,
    },
    {
        "case_id": "held_out_financial_bs_datapatterns_fy25",
        "company": "datapatterns",
        "year": "fy25",
        "stage": "financial_normalization",
        "module": "balance_sheet",
        "failure_class": "PRIMARY_BALANCE_SHEET_REQUIRED_FIELD_MISSING",
        "source_artifact": "companies/datapatterns/fy25/financials/normalized_fundamentals.json",
        "expected_result": "PASS",
        "expected_outcome": "held-out balance-sheet year preserves assets, equity, and liabilities through the same canonical path",
        "test_reference": "tests/robustness/test_robustness_baseline.py",
        "held_out": True,
    },
    {
        "case_id": "held_out_financial_bs_sun_pharma_fy20_total_assets",
        "company": "sun_pharma",
        "year": "fy20",
        "stage": "financial_extraction",
        "module": "balance_sheet",
        "failure_class": "PRIMARY_BALANCE_SHEET_REQUIRED_FIELD_MISSING",
        "source_artifact": "companies/sun_pharma/fy20/financials/raw_financial_tables.json",
        "expected_result": "PASS",
        "expected_outcome": "consolidated primary balance-sheet continuation row maps TOTAL ASSETS with primary provenance",
        "test_reference": "tests/financials/test_financial_extractor.py",
        "held_out": True,
    },
    {
        "case_id": "financial_tax_ujjivan_fy23_pat_bridge",
        "company": "ujjivan",
        "year": "fy23",
        "stage": "financial_validation",
        "module": "profit_and_loss",
        "failure_class": "WRONG_TAX_ROW_SELECTED",
        "source_artifact": "companies/ujjivan/fy23/financials/financial_validation_report.json",
        "expected_result": "WARNING",
        "expected_outcome": "validation is not failed by the prior PAT bridge tax-row collision",
        "test_reference": "tests/financials/test_financial_normalizer.py",
        "held_out": False,
    },
    {
        "case_id": "financial_semantic_collision_tanla_fy24",
        "company": "tanla",
        "year": "fy24",
        "stage": "financial_normalization",
        "module": "semantic_mapping",
        "failure_class": "SEMANTIC_LINE_ITEM_COLLISION",
        "source_artifact": "companies/tanla/fy24/financials/normalized_fundamentals.json",
        "expected_result": "PASS",
        "expected_outcome": "Revenue, PAT, assets, equity, and liabilities are present from canonical rows",
        "test_reference": "tests/financials/test_line_item_mapper.py",
        "held_out": False,
    },
    {
        "case_id": "financial_basis_warning_tanla_fy25",
        "company": "tanla",
        "year": "fy25",
        "stage": "financial_validation",
        "module": "basis",
        "failure_class": "BASIS_MIXED_CONSOLIDATED_STANDALONE",
        "source_artifact": "companies/tanla/fy25/financials/financial_validation_report.json",
        "expected_result": "WARNING",
        "expected_outcome": "basis ambiguity is surfaced without passing as high-confidence truth",
        "test_reference": "tests/financials/test_financial_basis_resolver.py",
        "held_out": False,
    },
    {
        "case_id": "financial_basis_datapatterns_fy25_field_owned",
        "company": "datapatterns",
        "year": "fy25",
        "stage": "financial_basis_resolution",
        "module": "basis",
        "failure_class": "BASIS_MIXED_CONSOLIDATED_STANDALONE",
        "source_artifact": "companies/datapatterns/fy25/financials/financial_basis_resolution.json",
        "expected_result": "PASS",
        "expected_outcome": "held-out field-level standalone basis is preserved instead of overwritten by global consolidated evidence",
        "test_reference": "tests/financials/test_financial_basis_resolver.py",
        "held_out": True,
    },
    {
        "case_id": "financial_basis_ujjivan_fy24_unresolved_not_mixed",
        "company": "ujjivan",
        "year": "fy24",
        "stage": "financial_basis_resolution",
        "module": "basis",
        "failure_class": "BASIS_MIXED_CONSOLIDATED_STANDALONE",
        "source_artifact": "companies/ujjivan/fy24/financials/financial_basis_resolution.json",
        "expected_result": "PASS",
        "expected_outcome": "unknown plus standalone evidence remains unresolved instead of being mislabeled as consolidated or mixed",
        "test_reference": "tests/financials/test_financial_statement_validator.py",
        "held_out": False,
    },
    {
        "case_id": "financial_pat_tanla_fy22",
        "company": "tanla",
        "year": "fy22",
        "stage": "financial_normalization",
        "module": "profit_and_loss",
        "failure_class": "PRIMARY_PNL_PAT_MISSING",
        "source_artifact": "companies/tanla/fy22/financials/normalized_fundamentals.json",
        "expected_result": "PASS",
        "expected_outcome": "PAT survives into normalized fundamentals",
        "test_reference": "tests/financials/test_financial_normalizer.py",
        "held_out": False,
    },
    {
        "case_id": "financial_pat_sun_pharma_fy20_held_out",
        "company": "sun_pharma",
        "year": "fy20",
        "stage": "financial_extraction",
        "module": "profit_and_loss",
        "failure_class": "PRIMARY_PNL_PAT_MISSING",
        "source_artifact": "companies/sun_pharma/fy20/financials/raw_financial_tables.json",
        "expected_result": "PASS",
        "expected_outcome": "consolidated primary P&L continuation row maps owner-attributable profit to PAT",
        "test_reference": "tests/financials/test_financial_extractor.py",
        "held_out": True,
    },
    {
        "case_id": "financial_pnl_sun_pharma_fy22_revenue_truncation",
        "company": "sun_pharma",
        "year": "fy22",
        "stage": "financial_extraction",
        "module": "profit_and_loss",
        "failure_class": "PRIMARY_PNL_PAT_MISSING",
        "source_artifact": "companies/sun_pharma/fy22/financials/raw_financial_tables.json",
        "expected_result": "PASS",
        "expected_outcome": "primary P&L revenue row extracted despite multi-chunk truncation at page 135; continuation-aware assembly stitches fragment starting at '(VI) Exceptional item' with header page",
        "test_reference": "tests/financials/test_financial_extractor.py",
        "held_out": False,
    },
    {
        "case_id": "document_ocr_polymatech_fy22",
        "company": "polymatech",
        "year": "fy22",
        "stage": "document_intake",
        "module": "ocr",
        "failure_class": "OCR_NO_TEXT_LAYER",
        "source_artifact": "companies/polymatech/fy22/extracted/document_intake_report.json",
        "expected_result": "REJECT",
        "expected_outcome": "image-only PDF is blocked as OCR-required instead of treated as extracted text",
        "test_reference": "tests/knowledge/test_document_intake.py",
        "held_out": False,
    },
    {
        "case_id": "company_isolation_tanla_company_model",
        "company": "tanla",
        "year": "",
        "stage": "company_model",
        "module": "company_isolation",
        "failure_class": "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION",
        "source_artifact": "companies/tanla/company_memory/company_model/company_model_validation.json",
        "expected_result": "PASS",
        "expected_outcome": "company-scoped model validation passes for the requested company",
        "test_reference": "tests/knowledge/company_model/test_company_model.py",
        "held_out": False,
    },
    {
        "case_id": "committee_unknowns_tanla",
        "company": "tanla",
        "year": "",
        "stage": "committee_synthesis",
        "module": "investor_panel",
        "failure_class": "COMMITTEE_CRITICAL_UNKNOWN_CONTRACT_MISMATCH",
        "source_artifact": "companies/tanla/company_memory/investor_panel/committee_synthesis.json",
        "expected_result": "PASS",
        "expected_outcome": "critical_unknowns items carry supported unknown text or are excluded",
        "test_reference": "tests/knowledge/investor_panel/test_committee_synthesis.py",
        "held_out": False,
    },
    {
        "case_id": "committee_brief_qa_tanla",
        "company": "tanla",
        "year": "",
        "stage": "committee_brief_qa",
        "module": "investor_panel",
        "failure_class": "COMMITTEE_BRIEF_QA_DUPLICATION",
        "source_artifact": "companies/tanla/company_memory/investor_panel/committee_brief_qa.json",
        "expected_result": "PASS",
        "expected_outcome": "committee brief QA duplication control passes",
        "test_reference": "tests/intelligence/investor_panel/test_committee_brief_qa.py",
        "held_out": False,
    },
    {
        "case_id": "held_out_tips_ask_validation",
        "company": "tips",
        "year": "",
        "stage": "ask_intrinsiciq",
        "module": "frontend_projection",
        "failure_class": "OPTIONAL_CANONICAL_FIELD_UNSAFE_RENDER",
        "source_artifact": "companies/tips/company_memory/ask_intrinsiciq/ask_intrinsiciq_validation_report.json",
        "expected_result": "PASS",
        "expected_outcome": "Tips canonical Ask outputs validate without cross-company fallback",
        "test_reference": "apps/ask-intrinsiciq/src/lib/ask-intrinsiciq/company-discovery.test.ts",
        "held_out": True,
    },
    {
        "case_id": "held_out_datapatterns_company_isolation",
        "company": "datapatterns",
        "year": "",
        "stage": "company_model",
        "module": "company_isolation",
        "failure_class": "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION",
        "source_artifact": "companies/datapatterns/company_memory/company_model/company_model_validation.json",
        "expected_result": "PASS",
        "expected_outcome": "held-out company-scoped model validation passes independently",
        "test_reference": "tests/knowledge/company_model/test_company_model.py",
        "held_out": True,
    },
    {
        "case_id": "held_out_polymatech_management_progression",
        "company": "polymatech",
        "year": "",
        "stage": "management_progression",
        "module": "company_isolation",
        "failure_class": "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION",
        "source_artifact": "companies/polymatech/company_memory/management_progression/management_progression_validation.json",
        "expected_result": "PASS",
        "expected_outcome": "held-out progression artifact validates without borrowing another company",
        "test_reference": "tests/knowledge/management_progression/test_management_progression.py",
        "held_out": True,
    },
    {
        "case_id": "held_out_progression_promise_quarantine_tanla_fy20",
        "company": "tanla",
        "year": "fy20",
        "stage": "cleaning",
        "module": "promises",
        "failure_class": "BUSINESS_RELEVANCE_QUARANTINE",
        "source_artifact": "companies/tanla/fy20/extracted/clean_promises.json",
        "expected_result": "PASS",
        "expected_outcome": "held-out promise stream validates civic/public-interest items are quarantined via four-outcome contract",
        "test_reference": "tests/processors/test_promise_cleaner.py",
        "held_out": True,
    },
    {
        "case_id": "held_out_progression_initiative_demote_tanla_fy24",
        "company": "tanla",
        "year": "fy24",
        "stage": "cleaning",
        "module": "initiatives",
        "failure_class": "BUSINESS_RELEVANCE_QUARANTINE",
        "source_artifact": "companies/tanla/fy24/extracted/clean_initiatives.json",
        "expected_result": "PASS",
        "expected_outcome": "held-out initiative stream validates ESG/generic items are demoted not promoted to canonical",
        "test_reference": "tests/processors/test_initiative_cleaner.py",
        "held_out": True,
    },
]


CODE_QUALITY_HARDENING_TARGETS: List[Dict[str, Any]] = [
    {
        "rank": 1,
        "target": "financial candidate discovery and extraction ranking",
        "reason": "duplicate candidates and mixed-note rows still feed downstream financial truth",
        "modules": ["knowledge/financials/extractor.py", "knowledge/financials/normalizer.py"],
    },
    {
        "rank": 2,
        "target": "semantic line-item mapping",
        "reason": "broad aliases can still collide across revenue, PAT, EPS, tax, equity, and segment rows",
        "modules": ["knowledge/financials/line_item_mapper.py", "knowledge/financials/mapping_registry.py"],
    },
    {
        "rank": 3,
        "target": "basis and period provenance",
        "reason": "normalization can pass with unknown basis while later modules treat results as canonical truth",
        "modules": ["knowledge/financials/basis.py", "knowledge/financials/normalizer.py"],
    },
    {
        "rank": 4,
        "target": "shared temporal role resolver",
        "reason": "source, event, historical, target, and non-temporal year roles affect every cleaner",
        "modules": ["knowledge/company_memory/guardrails.py", "knowledge/evidence_layer.py"],
    },
    {
        "rank": 5,
        "target": "canonical artifact load boundaries",
        "reason": "Ask, company model, progression, and panel consumers need consistent company identity and freshness guards",
        "modules": ["intelligence/ask_intrinsiciq", "knowledge/company_model", "knowledge/management_progression"],
    },
]


def _repo_path(relative_path: str, repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[1]
    return root / relative_path


def status_counts() -> Dict[str, int]:
    counts = {status: 0 for status in ("CLASS_FIXED", "PARTIALLY_FIXED", "OPEN", "UNKNOWN")}
    for entry in ROBUSTNESS_FAILURE_CLASSES:
        counts[str(entry["status"])] += 1
    return counts


def reopened_classes() -> List[str]:
    return [
        str(entry["failure_class"])
        for entry in ROBUSTNESS_FAILURE_CLASSES
        if entry.get("reopened")
    ]


def robustness_metrics() -> Dict[str, Any]:
    classes = {entry["failure_class"] for entry in ROBUSTNESS_FAILURE_CLASSES}
    company_years = {
        " ".join(part for part in (case.get("company", ""), case.get("year", "")) if part).strip()
        for case in ROBUSTNESS_CORPUS_MANIFEST
    }
    stages = {case["stage"] for case in ROBUSTNESS_CORPUS_MANIFEST}
    expected_rejects = [case for case in ROBUSTNESS_CORPUS_MANIFEST if case["expected_result"] == "REJECT"]
    held_out = [case for case in ROBUSTNESS_CORPUS_MANIFEST if case.get("held_out")]
    counts = status_counts()
    class_fixed_percent = round((counts["CLASS_FIXED"] / len(classes)) * 100, 2) if classes else 0.0
    return {
        "baseline_version": ROBUSTNESS_BASELINE_VERSION,
        "baseline_date": ROBUSTNESS_BASELINE_DATE,
        "company_years_tested": len(company_years),
        "stages_tested": len(stages),
        "known_failure_classes": len(classes),
        "known_failure_instances": sum(len(entry.get("known_instances", [])) for entry in ROBUSTNESS_FAILURE_CLASSES),
        "class_fixed_percent": class_fixed_percent,
        "reopened_classes": reopened_classes(),
        "production_hard_fail_recurrence_count": len(reopened_classes()),
        "false_positive_acceptance_regressions": len(expected_rejects),
        "held_out_cases": len(held_out),
        "status_counts": counts,
    }


def validate_robustness_baseline(repo_root: Path | None = None) -> Dict[str, Any]:
    issues: List[str] = []
    seen_classes = set()
    manifest_classes = {case.get("failure_class") for case in ROBUSTNESS_CORPUS_MANIFEST}

    for entry in ROBUSTNESS_FAILURE_CLASSES:
        failure_class = entry.get("failure_class")
        if not failure_class:
            issues.append("failure class entry missing failure_class")
            continue
        if failure_class in seen_classes:
            issues.append(f"duplicate failure class: {failure_class}")
        seen_classes.add(failure_class)
        if entry.get("status") not in ALLOWED_CLASS_STATUSES:
            issues.append(f"{failure_class} has invalid status: {entry.get('status')}")
        if entry.get("severity") not in ALLOWED_SEVERITIES:
            issues.append(f"{failure_class} has invalid severity: {entry.get('severity')}")
        if not entry.get("known_instances"):
            issues.append(f"{failure_class} must include at least one known instance")
        if entry.get("status") == "CLASS_FIXED" and entry.get("closure_gaps"):
            issues.append(f"{failure_class} cannot be CLASS_FIXED while closure gaps remain")
        if failure_class not in manifest_classes:
            issues.append(f"{failure_class} has no corpus manifest case")

    if not any(case.get("held_out") for case in ROBUSTNESS_CORPUS_MANIFEST):
        issues.append("at least one held-out case is required")

    seen_cases = set()
    for case in ROBUSTNESS_CORPUS_MANIFEST:
        case_id = case.get("case_id")
        if not case_id:
            issues.append("manifest case missing case_id")
            continue
        if case_id in seen_cases:
            issues.append(f"duplicate manifest case: {case_id}")
        seen_cases.add(case_id)
        if case.get("failure_class") not in seen_classes:
            issues.append(f"{case_id} references unknown failure class: {case.get('failure_class')}")
        if case.get("expected_result") not in ALLOWED_EXPECTED_RESULTS:
            issues.append(f"{case_id} has invalid expected_result: {case.get('expected_result')}")
        if not case.get("source_artifact"):
            issues.append(f"{case_id} missing source_artifact")
        elif not _repo_path(str(case["source_artifact"]), repo_root).exists():
            issues.append(f"{case_id} source artifact does not exist: {case['source_artifact']}")
        if not case.get("test_reference"):
            issues.append(f"{case_id} missing regression test reference")

    return {
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "metrics": robustness_metrics(),
    }


def cases_by_failure_class(failure_class: str) -> List[Dict[str, Any]]:
    return [
        case
        for case in ROBUSTNESS_CORPUS_MANIFEST
        if case.get("failure_class") == failure_class
    ]


def failure_classes_by_status(status: str) -> List[Dict[str, Any]]:
    return [
        entry
        for entry in ROBUSTNESS_FAILURE_CLASSES
        if entry.get("status") == status
    ]


def artifact_cases(repo_root: Path | None = None) -> Iterable[Dict[str, Any]]:
    for case in ROBUSTNESS_CORPUS_MANIFEST:
        enriched = dict(case)
        enriched["artifact_path"] = _repo_path(str(case["source_artifact"]), repo_root)
        yield enriched


__all__ = [
    "CODE_QUALITY_HARDENING_TARGETS",
    "ROBUSTNESS_BASELINE_DATE",
    "ROBUSTNESS_BASELINE_VERSION",
    "ROBUSTNESS_CORPUS_MANIFEST",
    "ROBUSTNESS_FAILURE_CLASSES",
    "artifact_cases",
    "cases_by_failure_class",
    "failure_classes_by_status",
    "reopened_classes",
    "robustness_metrics",
    "status_counts",
    "validate_robustness_baseline",
]
