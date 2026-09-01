from __future__ import annotations

from typing import Any, Dict, List


FAILURE_LEARNING_DATE = "2026-08-09"
FAILURE_LEARNING_VERSION = "failure_learning.v2"


FAILURE_CLASS_REGISTRY: List[Dict[str, Any]] = [
    {
        "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED",
        "description": "A cleaned item still contains period evidence that the shared chronology resolver cannot interpret safely, typically because source-year anchoring, historical references, forward targets, example clauses, or genuinely conflicting year mentions were collapsed into one undifferentiated period list.",
        "status": "reopened",
        "first_verified": "2026-08-12",
        "last_verified": "2026-08-15",
        "affected_modules": [
            "risks",
            "projects",
            "promises",
            "capacity",
            "capacity_expansions",
            "management_commitments",
            "capital_allocations",
            "initiatives",
        ],
        "affected_company_years": [
            "tanla fy20",
            "tanla fy22",
            "tanla fy23",
            "ujjivan fy21",
            "ujjivan fy23",
            "sun_pharma fy20",
            "sun_pharma fy22",
        ],
        "raw_input_shapes": [
            "source-year anchored disclosure with parenthetical example year",
            "historical year embedded in a current risk narrative",
            "paired fiscal-year disclosure (FY 2021-22)",
            "future-dated plan year (FY25 / FY26)",
            "open-ended ongoing / no specific future date wording",
            "source-year anchored disclosure with incidental comparative year",
            "source-period promise with a historical reference year and a separate forward target/milestone",
            "current-period disclosure with a non-temporal statute, regulation, circular, scheme, or accounting-standard reference year",
            "non-promotable historical regulatory context with multiple historical years and truncated final status",
        ],
        "root_causes": [
            "example-year clauses were being treated like active chronology conflicts",
            "source_year metadata was not guaranteed at the shared validation boundary",
            "incidental comparative years in year-over-year capacity disclosures were still being counted as competing chronology instead of context",
            "temporal roles collapsed source_period, historical_periods, and target_period into one ambiguous year set",
            "years embedded in named legal, regulatory, accounting-standard, or scheme references were treated as company event chronology",
            "the shared cleaner boundary treated every unresolved period validation error as fatal even when materiality explicitly blocked canonical promotion",
        ],
        "root_cause_subtype": "NON_PROMOTABLE_AMBIGUOUS_EVIDENCE_FATAL_BOUNDARY",
        "canonical_fix": [
            "propagate source_year before final validation",
            "strip explicit example clauses from period extraction",
            "prefer source-period anchoring over incidental comparative years when the disclosure clearly expresses a year-over-year comparison",
            "preserve source/report, event, historical-reference, and forward-target roles at the shared period-resolution boundary",
            "filter statute, regulation, accounting-standard, circular, scheme, and other named-reference years before chronology conflict checks",
            "quarantine non-promotable ambiguous period items locally with diagnostics when period ambiguity is the sole validation blocker",
            "keep genuine conflicting chronology invalid",
        ],
        "regression_tests": [
            "risk cleaner accepts source-year anchored example-year clauses",
            "period resolver still rejects true conflicting years",
            "validation diagnostics expose failure_class and period provenance",
            "Ujjivan FY21 capacity comparison keeps 2020 as historical context and resolves to fy21",
            "Ujjivan FY23 promise keeps fy23 as source/event, fy21 as historical reference, and fy24 as target",
            "Ujjivan FY24 capital allocation ignores Income Tax Act, 1961 as chronology while retaining FY23/FY24 statement timing",
            "unrelated future or multi-event historical years remain ambiguous",
            "Sun Pharma FY20 projects_00011 is quarantined with provenance and does not abort cleaning",
            "promotable ambiguous items and required ambiguous facts still hard-fail",
        ],
        "safeguards": [
            "strict ambiguous-year rejection",
            "structured validation diagnostics",
            "ambiguous evidence never enters canonical cleaned output unless resolved",
            "corpus audit report checked into docs/audits",
        ],
    },
    {
        "failure_class": "INITIATIVE_CHRONOLOGY_RESOLUTION_FAILURE",
        "description": "Initiative items mixed source-year anchoring with historical or forward milestone dates in a way that the shared chronology resolver previously treated as a fatal ambiguity.",
        "status": "implemented",
        "first_verified": "2026-08-12",
        "last_verified": "2026-08-12",
        "affected_modules": [
            "initiatives",
        ],
        "affected_company_years": [
            "tanla fy20",
            "tanla fy23",
            "datapatterns fy23",
            "datapatterns fy24",
            "datapatterns fy25",
        ],
        "raw_input_shapes": [
            "completed historical initiative with embedded completion year",
            "future milestone attached to an initiative status string",
            "multi-year initiative narrative with one source FY and one milestone FY",
            "historical initiative with source-year anchor plus legacy date",
        ],
        "root_causes": [
            "source-year anchoring was being double-counted as an explicit year for initiative items",
            "initiative milestone language was not being distinguished from genuine chronology conflict",
        ],
        "canonical_fix": [
            "avoid double-counting source year as explicit initiative chronology evidence",
            "preserve source-year anchoring while allowing clearly marked milestone or completion dates",
            "keep ambiguous multi-year initiative records blocked",
        ],
        "regression_tests": [
            "Tanla FY20 historical completion passes",
            "Tanla FY23 future milestone passes",
            "ambiguous initiative with genuinely conflicting years still fails",
        ],
        "safeguards": [
            "initiative chronology regression corpus",
            "structured diagnostics include failure_class and period provenance",
            "shared period guardrails remain strict for non-initiative modules",
        ],
    }
    ,
    {
        "failure_class": "MULTI_EVENT_HISTORICAL_PERIOD_COLLISION",
        "description": "A single capital-allocation record bundles multiple distinct historical allocation events or plan approvals, and the cleaner must split or preserve them as separate chronology units instead of forcing one canonical period.",
        "status": "implemented",
        "first_verified": "2026-08-12",
        "last_verified": "2026-08-12",
        "affected_modules": [
            "capital_allocations",
        ],
        "affected_company_years": [
            "tanla fy24",
        ],
        "raw_input_shapes": [
            "employee stock compensation plan bundle with multiple approval years",
            "capital-allocation narrative listing several historical events in one action field",
        ],
        "root_causes": [
            "multiple allocation events were bundled into a single canonical row",
            "the cleaner tried to force separate historical event years into one period",
        ],
        "canonical_fix": [
            "split clearly enumerated multi-event capital-allocation rows into separate canonical records",
            "preserve ambiguous multi-event narratives as blocked chronology",
            "keep historical event years as event dates, not source-period dates",
        ],
        "regression_tests": [
            "Tanla FY24 employee stock-compensation bundle splits into separate records",
            "ambiguous multi-year capital-allocation history remains blocked",
            "source-vs-target capital-allocation behavior remains unchanged",
        ],
        "safeguards": [
            "no silent collapse of multiple allocation events",
            "structured split metadata retains lineage",
            "chronology remains strict when the event structure is unclear",
        ],
    }
    ,
    {
        "failure_class": "SOURCE_PERIOD_VS_TARGET_PERIOD_CONFLICT",
        "description": "A forward-looking disclosure mixes the report/source year with the event or target year, including capacity rows that carry explicit current-state and target-state periods, and the resolver must keep the source period separate from the target period instead of treating both as one ambiguous timeline.",
        "status": "implemented",
        "first_verified": "2026-08-12",
        "last_verified": "2026-08-12",
        "affected_modules": [
            "promises",
            "projects",
            "capacity",
            "capacity_expansions",
            "initiatives",
            "management_commitments",
            "capital_allocations",
        ],
        "affected_company_years": [
            "tanla fy23",
            "tanla fy24",
        ],
        "raw_input_shapes": [
            "report-year disclosure that also names a later milestone year",
            "source year mentioned alongside a separate target year in the same narrative",
            "capacity row with explicit current-state and target-state fields plus adjacent years",
        ],
        "root_causes": [
            "the source/report year was being counted as if it were the event/target year",
            "multi-year disclosures were rejected before the source period and target period could be separated",
            "capacity disclosures with structured current/target fields were still collapsing into ambiguity when the year pair was present",
        ],
        "canonical_fix": [
            "pass the event or target year separately from the source period when it is explicitly present",
            "recognize capacity rows with explicit current-state and target-state structure as a distinct chronology subtype",
            "resolve exact source-plus-target pairs as supported chronology instead of ambiguous conflict",
            "keep genuinely multi-year or otherwise conflicting chronology invalid",
        ],
        "regression_tests": [
            "Tanla FY23 capacity row with current-state plus target-state fields resolves",
            "Tanla FY24 promise with source year and target year resolves",
            "historical capacity reference remains historical context",
            "source plus target plus extra year remains ambiguous",
            "validation diagnostics report the new failure class when separation is impossible",
        ],
        "safeguards": [
            "ambiguous chronology still fails",
            "structured diagnostics preserve source_period and target_period provenance",
            "no silent coercion of unsupported year combinations",
        ],
    }
    ,
    {
        "failure_class": "PRIMARY_BALANCE_SHEET_REQUIRED_FIELD_MISSING",
        "description": "A real balance-sheet row is present in extraction output, but readiness still fails because discovery-page gating excludes a semantically valid total-assets row that lives on continuation pages or a mixed financial-note table.",
        "status": "implemented",
        "first_verified": "2026-08-15",
        "last_verified": "2026-08-15",
        "affected_modules": [
            "financial_extraction",
            "primary_balance_sheet_statement",
            "balance_sheet",
        ],
        "affected_company_years": [
            "ujjivan fy21",
            "ujjivan fy22",
            "ujjivan fy23",
        ],
        "raw_input_shapes": [
            "primary balance-sheet row on a continuation page after the discovery anchor",
            "mixed financial-note table with a semantically valid total-assets row",
        ],
        "root_causes": [
            "exact discovery-page filtering excluded support rows that had already been routed into the canonical balance-sheet table",
        ],
        "root_cause_subtype": "MIXED_TABLE_SEMANTIC_ROUTING_COLLISION",
        "canonical_fix": [
            "allow semantically routed balance-sheet support rows to satisfy readiness even when they sit on continuation pages outside the exact discovery-page list",
            "keep row-level semantic mapping authoritative",
            "keep unrelated asset-like lookalikes rejected",
        ],
        "regression_tests": [
            "Ujjivan FY21 real artifact keeps total_assets in readiness",
            "Ujjivan FY22 real artifact keeps total_assets in readiness",
            "Ujjivan FY23 real artifact keeps total_assets in readiness",
            "segment/average/earning/RWA/AUM lookalikes still reject",
        ],
        "safeguards": [
            "no company-specific page hardcoding",
            "no basis weakening",
            "no extraction readiness downgrade",
        ],
    },
    {
        "failure_class": "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION",
        "description": "Ask IntrinsicIQ produced or consumed company-specific intelligence whose semantic fingerprint or artifact identity belonged to another company or reference-company template.",
        "status": "implemented",
        "severity": "PRODUCTION BLOCKER",
        "first_verified": "2026-08-13",
        "last_verified": "2026-08-13",
        "affected_modules": [
            "ask_intrinsiciq",
            "business_journey",
            "products_services",
            "answer_cards",
            "ask_frontend_loaders",
        ],
        "affected_company_years": [
            "tanla",
        ],
        "raw_input_shapes": [
            "enterprise communications / CPaaS language matched by a defence communication-systems template",
            "company-specific public artifact consumed without an explicit requested-company versus artifact-company guard",
            "development fixture fallback containing real Data Patterns facts used as a possible answer source",
        ],
        "root_causes": [
            "deterministic Ask offering and journey classifiers treated generic communications language as defence/aerospace evidence",
            "revenue-flow templates contained defence/aerospace programme wording even when the source company was a software platform",
            "frontend loaders did not hard-reject mismatched company_slug metadata before consuming public artifacts",
        ],
        "canonical_fix": [
            "separate CPaaS/software-platform inference from defence communication-systems inference",
            "remove unsafe factual dev fallback from company-scoped public loaders",
            "validate requested company identity at public artifact load boundaries and expose unavailable/partial state on mismatch",
        ],
        "regression_tests": [
            "Tanla-style enterprise communications fixture does not produce Data Patterns defence wording",
            "Data Patterns-style communication systems fixture remains supported",
            "answer artifact with mismatched company_slug is rejected and becomes unavailable publicly",
            "Data Patterns to Tanla and Tanla to Data Patterns sequential loads remain isolated",
        ],
        "safeguards": [
            "wrong-company data must never be used as fallback",
            "missing company-specific intelligence remains unavailable or partial",
            "diagnostics include requested_company, artifact_company, question, artifact_path, and failure_class where applicable",
        ],
    }
]


INCIDENT_TAXONOMY: List[Dict[str, Any]] = [
    {
        "category_path": "document_ingestion/text_layer/scanned_pdf_no_extractable_text",
        "label": "Scanned PDF with no extractable text",
        "domain": "document_ingestion",
        "subdomain": "text_layer",
        "code": "scanned_pdf_no_extractable_text",
        "severity": "high",
        "regression_focus": [
            "image-only PDF",
            "valid text-layer PDF",
            "mixed image/text PDF",
            "corrupt PDF",
            "encrypted PDF",
            "OCR-required scanned PDF",
        ],
    },
    {
        "category_path": "financial_pipeline/extraction/insufficient_statement_coverage",
        "label": "Insufficient financial statement extraction",
        "domain": "financial_pipeline",
        "subdomain": "extraction",
        "code": "insufficient_statement_coverage",
        "severity": "high",
        "regression_focus": [
            "sections discovered but rows remain too sparse",
            "P&L incomplete",
            "revenue missing",
            "cash flow absent",
            "normalizer blocked before deep runtime error",
        ],
    },
    {
        "category_path": "financial_pipeline/candidate_resolution/primary_statement_unresolved",
        "label": "Primary statement candidate resolution failure",
        "domain": "financial_pipeline",
        "subdomain": "candidate_resolution",
        "code": "primary_statement_unresolved",
        "severity": "high",
        "regression_focus": [
            "duplicate candidates",
            "many rows but no primary P&L",
            "PAT unavailable",
            "candidate scoring explanation",
        ],
    },
    {
        "category_path": "financial_pipeline/normalization/metric_mapping/tax_metric_reconciliation_failure",
        "label": "Tax normalization breaks PAT bridge",
        "domain": "financial_pipeline",
        "subdomain": "normalization",
        "code": "tax_metric_reconciliation_failure",
        "severity": "critical",
        "regression_focus": [
            "PBT - tax ≈ PAT",
            "source provenance preserved",
            "period alignment",
            "critical field quarantine when the bridge fails",
        ],
    },
    {
        "category_path": "financial_pipeline/normalization/semantic_line_item_collision/note_wrapper_preserved_for_canonical_field",
        "label": "Revenue mapped from unrelated line item",
        "domain": "financial_pipeline",
        "subdomain": "normalization",
        "code": "revenue_wrong_source_section",
        "severity": "critical",
        "regression_focus": [
            "primary P&L preferred for revenue",
            "revenue-intensity / ESG metric denial patterns",
            "statement context required",
            "semantic label alone is insufficient",
        ],
    },
    {
        "category_path": "financial_pipeline/normalization/semantic_line_item_collision/revenue_wrong_source_section",
        "label": "Revenue mapped from unrelated line item",
        "domain": "financial_pipeline",
        "subdomain": "normalization",
        "code": "revenue_wrong_source_section",
        "severity": "critical",
        "regression_focus": [
            "primary P&L preferred for revenue",
            "revenue-intensity / ESG metric denial patterns",
            "statement context required",
            "semantic label alone is insufficient",
        ],
    },
    {
        "category_path": "financial_pipeline/normalization/metric_mapping/pat_wrong_value_or_period",
        "label": "PAT mapped to the wrong value or period",
        "domain": "financial_pipeline",
        "subdomain": "normalization",
        "code": "pat_wrong_value_or_period",
        "severity": "critical",
        "regression_focus": [
            "row plus column validation",
            "period header alignment",
            "PBT / tax / EPS cross-check",
            "generic period labels rejected",
        ],
    },
    {
        "category_path": "financial_pipeline/normalization/balance_sheet_component_mapping/net_worth_wrong_component_mapping",
        "label": "Net worth component mapping failure",
        "domain": "financial_pipeline",
        "subdomain": "normalization",
        "code": "net_worth_wrong_component_mapping",
        "severity": "high",
        "regression_focus": [
            "same period",
            "same basis",
            "same statement scope",
            "total equity / reserves / share capital provenance",
            "row-local unit inference for mixed-unit capital disclosures",
        ],
    },
    {
        "category_path": "financial_pipeline/normalization/semantic_line_item_collision/off_balance_sheet_equity_false_match",
        "label": "Net worth matched from off-balance-sheet equity language",
        "domain": "financial_pipeline",
        "subdomain": "normalization",
        "code": "off_balance_sheet_equity_false_match",
        "severity": "high",
        "regression_focus": [
            "net worth requires real equity or shareholder-fund semantics",
            "tranche / regulatory-capital wording is rejected",
            "off-balance-sheet equity instruments do not map to net worth",
            "statement scope must match the economic meaning",
        ],
    },
    {
        "category_path": "financial_pipeline/scope_resolution/consolidated_standalone_ambiguity",
        "label": "Consolidated versus standalone scope ambiguity",
        "domain": "financial_pipeline",
        "subdomain": "scope_resolution",
        "code": "consolidated_standalone_ambiguity",
        "severity": "high",
        "regression_focus": [
            "explicit basis on critical fields",
            "no silent mixing",
            "preferred-basis policy",
            "ratio gate blocked on incompatible basis",
        ],
    },
    {
        "category_path": "financial_pipeline/orchestration/downstream_blocked_by_upstream_failure",
        "label": "Downstream artifacts blocked by an upstream failure",
        "domain": "financial_pipeline",
        "subdomain": "orchestration",
        "code": "downstream_blocked_by_upstream_failure",
        "severity": "medium",
        "regression_focus": [
            "root failure versus cascade failure",
            "blocked_by_dependency status",
            "not_run versus missing_unexpectedly",
        ],
    },
    {
        "category_path": "ai_provider/structured_output/empty_message_content",
        "label": "Empty structured response from provider",
        "domain": "ai_provider",
        "subdomain": "structured_output",
        "code": "empty_message_content",
        "severity": "high",
        "regression_focus": [
            "empty first response retried once",
            "provider diagnostics preserved",
            "retry exhaustion classified cleanly",
            "batch-level recovery before full abort",
        ],
    },
]


INCIDENTS: List[Dict[str, Any]] = [
    {
        "incident_id": "FL-2026-08-07-01",
        "company": "polymatech",
        "year": "fy22",
        "title": "Scanned annual report produced no extractable text",
        "command": "python pipelines/run_company_pipeline.py polymatech fy22 --stage all",
        "category_path": "document_ingestion/text_layer/scanned_pdf_no_extractable_text",
        "root_cause_status": "CONFIRMED",
        "root_cause_hypothesis": "The FY22 annual report is image-only / scanned, so preflight had no machine-readable text layer to work with.",
        "observed_facts": [
            "The pipeline stopped at preflight before discovery, extraction, or downstream company-memory stages could start.",
            "The PDF has pages with visible content but no machine-readable text layer.",
            "The preflight error correctly distinguished the condition from a simple missing-file case.",
        ],
        "durable_safeguards": [
            "Detect image-only PDFs explicitly.",
            "Preserve page count and document metadata in failure diagnostics.",
            "Classify OCR-required input separately from corrupt, encrypted, or unsupported files.",
        ],
        "remediation_status": "implemented",
        "remediation_summary": "Document intake now classifies image-only PDFs and emits an OCR-required block instead of a generic text-missing failure.",
        "regression_requirements": [
            "synthetic image-only PDF",
            "valid text-layer PDF",
            "mixed image/text PDF",
            "corrupt PDF",
            "encrypted PDF",
            "scanned PDF classified as OCR-required",
        ],
        "severity": "high",
    },
    {
        "incident_id": "FL-2026-08-07-02",
        "company": "polymatech",
        "year": "fy23",
        "title": "Financial extraction coverage was too thin for normalization",
        "command": "python pipelines/run_company_pipeline.py polymatech fy23 --stage financials",
        "category_path": "financial_pipeline/extraction/insufficient_statement_coverage",
        "root_cause_status": "HYPOTHESIS",
        "root_cause_hypothesis": "Upstream statement extraction did not capture enough canonical rows for a safe normalization pass, and the missing revenue/cash-flow coverage became fatal at the normalizer gate.",
        "observed_facts": [
            "Discovery found many sections, but extraction still produced too few rows for a complete financial view.",
            "The pipeline warned about incomplete P&L and missing cash flow coverage.",
            "Normalization failed because required revenue was absent.",
        ],
        "durable_safeguards": [
            "Add an extraction-readiness gate before normalization.",
            "Require a minimum statement-coverage score.",
            "Emit a structured failure code for missing revenue coverage.",
        ],
        "remediation_status": "implemented",
        "remediation_summary": "Extraction now writes a readiness report and blocks sparse statements before normalization can fail deeper downstream.",
        "regression_requirements": [
            "sections discovered but rows extracted are sparse",
            "P&L incomplete",
            "revenue missing",
            "cash flow absent",
            "normalizer blocked before deep RuntimeError",
        ],
        "severity": "high",
    },
    {
        "incident_id": "FL-2026-08-07-03",
        "company": "polymatech",
        "year": "fy24",
        "title": "Primary statement candidate resolution failed despite many extracted rows",
        "command": "python pipelines/run_company_pipeline.py polymatech fy24 --stage financials",
        "category_path": "financial_pipeline/candidate_resolution/primary_statement_unresolved",
        "root_cause_status": "HYPOTHESIS",
        "root_cause_hypothesis": "The extractor gathered substantial content but could not reliably choose the canonical primary P&L / balance-sheet candidates, so PAT remained unresolved at normalization time.",
        "observed_facts": [
            "The run found many sections and extracted substantially more rows than FY23.",
            "Extraction still reported duplicate balance-sheet and share-capital candidates.",
            "Normalization failed because required PAT remained unavailable.",
        ],
        "durable_safeguards": [
            "Add candidate scoring transparency.",
            "Record why the winner was selected and why alternatives were rejected.",
            "Gate normalization on the chosen primary statement being explicit and confident.",
        ],
        "remediation_status": "implemented",
        "remediation_summary": "Candidate selection now records matched fields, rejection reasons, and readiness status so missing PAT is visible before normalization runs.",
        "regression_requirements": [
            "duplicate balance-sheet candidates",
            "duplicate share-capital candidates",
            "many rows but no primary P&L",
            "PAT unavailable",
            "candidate-resolution explanation emitted",
        ],
        "severity": "high",
    },
    {
        "incident_id": "FL-2026-08-07-04",
        "company": "tanla",
        "year": "fy25",
        "title": "Tax normalization broke the PAT bridge",
        "command": "python pipelines/run_company_pipeline.py tanla fy25 --stage financials",
        "category_path": "financial_pipeline/normalization/metric_mapping/tax_metric_reconciliation_failure",
        "root_cause_status": "HYPOTHESIS",
        "root_cause_hypothesis": "The normalized tax value appears to have come from the wrong row or period, because the PBT-to-PAT bridge collapsed by a large margin.",
        "observed_facts": [
            "Validation failed on the PAT bridge.",
            "PBT and PAT implied a tax charge around twelve thousand, but the normalized values implied a trivial tax amount.",
            "The audit also exposed missing capex, missing share-count inputs, and incomplete period consistency.",
        ],
        "durable_safeguards": [
            "Reconcile critical metrics before accepting normalization.",
            "Preserve source-line provenance for tax.",
            "Quarantine fields that break the PBT - tax ≈ PAT bridge.",
        ],
        "remediation_status": "implemented",
        "remediation_summary": "Normalization now retries empty structured provider replies and keeps bridge checks explicit so tax / PAT inconsistencies are quarantined instead of silently accepted.",
        "regression_requirements": [
            "correct tax row",
            "wrong tax note row",
            "wrong comparative-period tax",
            "tiny unrelated tax-like number",
            "PAT bridge catches wrong mapping",
        ],
        "severity": "critical",
    },
    {
        "incident_id": "FL-2026-08-07-05",
        "company": "tanla",
        "year": "fy26",
        "title": "Revenue was normalized from a semantically unrelated line item",
        "command": "python pipelines/run_company_pipeline.py tanla fy26 --stage financials",
        "category_path": "financial_pipeline/normalization/semantic_line_item_collision/note_wrapper_preserved_for_canonical_field",
        "root_cause_status": "CONFIRMED",
        "root_cause_hypothesis": "A non-primary note line about energy intensity per revenue was incorrectly matched to the revenue field.",
        "observed_facts": [
            "Reconciliation explicitly rejected revenue because the normalized field used an unrelated source line item.",
            "The source line item came from a financial note, not the primary profit-and-loss statement.",
            "The failure was correctly blocked before downstream ratios could consume the bad field.",
        ],
        "durable_safeguards": [
            "Require allowed source-section types for critical metrics.",
            "Add deny-patterns for revenue-like ESG or intensity metrics.",
            "Keep reconciliation as a hard gate.",
        ],
        "remediation_status": "implemented",
        "remediation_summary": "Revenue mapping now rejects unrelated note-level lookalikes such as intensity, growth, mix, and other non-P&L revenue phrases.",
        "regression_requirements": [
            "Revenue from operations accepted",
            "Total revenue accepted where valid",
            "Revenue growth % rejected as revenue",
            "Energy Intensity per INR Cr Revenue rejected",
            "primary P&L revenue preferred over note-level keyword matches",
        ],
        "severity": "critical",
    },
    {
        "incident_id": "FL-2026-08-14-01",
        "company": "ujjivan",
        "year": "fy21",
        "title": "Revenue and EPS basic retained the note wrapper as their canonical statement type",
        "command": "python pipelines/run_company_pipeline.py ujjivan fy21 --stage financials",
        "category_path": "financial_pipeline/normalization/semantic_line_item_collision/revenue_wrong_source_section",
        "root_cause_status": "CONFIRMED",
        "root_cause_hypothesis": "The extractor preserved note-derived revenue and EPS rows as financial_note statement types, so reconciliation treated the correct note evidence as semantically unrelated even though the underlying line items were valid.",
        "observed_facts": [
            "Revenue was sourced from a legitimate revenue-from-operations note row, but statement_type remained financial_note.",
            "EPS basic was sourced from a legitimate EPS disclosure note row, but statement_type remained financial_note.",
            "Reconciliation rejected both fields as unrelated because the canonical table type was not preserved.",
        ],
        "durable_safeguards": [
            "Promote note-derived rows to their canonical statement_type once the semantic table type is known.",
            "Keep source_section_type for provenance, but do not let the wrapper override the semantic table role.",
            "Preserve reconciliation as a hard semantic gate.",
        ],
        "remediation_status": "implemented",
        "remediation_summary": "Note-derived revenue and EPS rows now keep their note provenance while exposing the correct canonical statement_type for downstream matching.",
        "regression_requirements": [
            "note-derived revenue routes as revenue",
            "note-derived EPS basic routes as eps",
            "primary P&L revenue still preferred when present",
            "retained earnings and other note noise still rejected as revenue/EPS",
        ],
        "severity": "critical",
    },
    {
        "incident_id": "FL-2026-08-07-06",
        "company": "tanla",
        "year": "fy26",
        "title": "PAT mapped to the wrong value or period",
        "command": "python pipelines/run_company_pipeline.py tanla fy26 --stage financials",
        "category_path": "financial_pipeline/normalization/metric_mapping/pat_wrong_value_or_period",
        "root_cause_status": "HYPOTHESIS",
        "root_cause_hypothesis": "The pipeline selected the wrong numeric cell or period column for PAT even though the statement context was correct.",
        "observed_facts": [
            "The PAT bridge compared 0.31 against a much larger expected annual PAT value.",
            "The source provenance showed the field came from the primary P&L, but the mapped value was implausibly small.",
            "This indicates a value/period mapping failure rather than a statement-context failure.",
        ],
        "durable_safeguards": [
            "Validate row and column together.",
            "Check period headers before promoting a value into canonical PAT.",
            "Cross-check PAT against PBT, tax, EPS, and attributable profit where available.",
        ],
        "remediation_status": "implemented",
        "remediation_summary": "Period ranking now refuses placeholder labels so unresolved columns cannot become canonical PAT values.",
        "regression_requirements": [
            "correct current-year PAT column",
            "comparative-year PAT column",
            "note-number mistaken as PAT",
            "small decimal mistaken for crore value",
            "PAT bridge catches incorrect column",
        ],
        "severity": "critical",
    },
    {
        "incident_id": "FL-2026-08-07-07",
        "company": "tanla",
        "year": "fy26",
        "title": "Net worth bridge failed because components did not line up",
        "command": "python pipelines/run_company_pipeline.py tanla fy26 --stage financials",
        "category_path": "financial_pipeline/normalization/balance_sheet_component_mapping/net_worth_wrong_component_mapping",
        "root_cause_status": "HYPOTHESIS",
        "root_cause_hypothesis": "The total-equity, share-capital, or reserves components were pulled from an incompatible basis, period, or statement scope.",
        "observed_facts": [
            "The net worth bridge delta was material.",
            "The failure was detected as a bridge mismatch rather than as a silent drift.",
            "The brief explicitly warned not to assume the root cause until provenance is inspected.",
        ],
        "durable_safeguards": [
            "Require same period, same basis, same statement scope for bridge components.",
            "Preserve component provenance for total equity, share capital, and reserves.",
            "Reject mixed-basis bridge calculations.",
        ],
        "remediation_status": "implemented",
        "remediation_summary": "Bridge components remain provenance-bound so incompatible periods or bases are quarantined instead of merged into a false net-worth result.",
        "regression_requirements": [
            "correct equity bridge",
            "mixed standalone/consolidated inputs",
            "mismatched year inputs",
            "missing reserves",
            "wrong total-equity row",
        ],
        "severity": "high",
    },
    {
        "incident_id": "FL-2026-08-07-08",
        "company": "tanla",
        "year": "fy26",
        "title": "Financial artifacts mixed consolidated and standalone basis",
        "command": "python pipelines/run_company_pipeline.py tanla fy26 --stage financials",
        "category_path": "financial_pipeline/scope_resolution/consolidated_standalone_ambiguity",
        "root_cause_status": "CONFIRMED",
        "root_cause_hypothesis": "Preferred consolidated evidence was missing for many critical fields, so the artifact became a mixed-basis view rather than a coherent canonical view.",
        "observed_facts": [
            "Many critical metrics fell back to unknown basis.",
            "Audit reported a consolidated/standalone basis mismatch across the financial artifacts.",
            "The run showed that plausible individual values can still be unusable as a single canonical view if their bases conflict.",
        ],
        "durable_safeguards": [
            "Require explicit basis on every critical field.",
            "Avoid silent mixing of consolidated, standalone, and unknown bases.",
            "Block ratios when the basis is incompatible.",
        ],
        "remediation_status": "implemented",
        "remediation_summary": "Basis consistency stays explicit in the canonical financial artifacts so mixed standalone/consolidated evidence cannot masquerade as one view.",
        "regression_requirements": [
            "all consolidated",
            "all standalone",
            "mixed standalone/consolidated",
            "unknown critical basis",
            "ratio calculation blocked for incompatible basis",
        ],
        "severity": "high",
    },
    {
        "incident_id": "FL-2026-08-07-09",
        "company": "tanla",
        "year": "fy26",
        "title": "Upstream financial failure cascaded into missing downstream artifacts",
        "command": "python pipelines/run_company_pipeline.py tanla fy26 --stage financials",
        "category_path": "financial_pipeline/orchestration/downstream_blocked_by_upstream_failure",
        "root_cause_status": "CONFIRMED",
        "root_cause_hypothesis": "The missing outputs were a dependency cascade after validation and reconciliation failed, not independent separate failures.",
        "observed_facts": [
            "financial_ratios.json, financial_growth.json, corporate_actions.json, and shareholding_pattern.json were absent after the upstream failure.",
            "The audit should treat those absences as blocked-by-dependency rather than as four separate root causes.",
            "The brief explicitly asked to distinguish root failure from cascade failure.",
        ],
        "durable_safeguards": [
            "Report blocked-by-dependency separately from missing-unexpectedly.",
            "Preserve the causal chain in audit output.",
            "Avoid incident inflation from downstream artifacts that never ran.",
        ],
        "remediation_status": "implemented",
        "remediation_summary": "The orchestrator now distinguishes dependency-blocked downstream artifacts from independent failures so cascades stay visible but not overcounted.",
        "regression_requirements": [
            "upstream fail marks downstream stages blocked",
            "audit distinguishes blocked artifact from unexpectedly missing artifact",
            "causal chain is preserved",
        ],
        "severity": "medium",
    },
    {
        "incident_id": "FL-2026-08-07-10",
        "company": "deepseek",
        "year": "provider",
        "title": "Structured provider response returned empty message content",
        "command": "BaseExtractor -> call_llm_with_input_pack -> DeepSeekProvider.generate -> _parse_response",
        "category_path": "ai_provider/structured_output/empty_message_content",
        "root_cause_status": "CONFIRMED",
        "root_cause_hypothesis": "The provider response reached the client but did not include usable message content in the expected structured field.",
        "observed_facts": [
            "The request completed far enough to produce a response payload.",
            "The expected message content was empty or absent.",
            "The downstream extraction batch failed after the provider error surfaced.",
        ],
        "durable_safeguards": [
            "Retry empty structured content once at provider level.",
            "Preserve provider/model/attempt diagnostics.",
            "Keep batch number, item number, and page in the extraction failure path.",
        ],
        "remediation_status": "implemented",
        "remediation_summary": "Provider adapters now retry empty structured responses once and preserve the original diagnostics when the retry also fails.",
        "regression_requirements": [
            "normal content response",
            "empty content first attempt, valid second attempt",
            "repeated empty content",
            "malformed JSON content",
            "response without choices",
            "response with reasoning field but no final content",
            "retry exhaustion emits classified failure",
        ],
        "severity": "high",
    },
]


PHASE2_SEMANTIC_FAILURES = (
    ("actor_ownership", "external_actor_promoted", "Government or sector targets were promoted as company commitments.", "Actor ownership now overrides misleading source hints.", "government target and company target synthetic pair", "Data Patterns external defence-production target is quarantined"),
    ("statement_typing", "non_commitment_speech_act", "Facts, capabilities, aspirations, and forecasts were treated as commitments.", "A canonical speech-act classifier gates commitment eligibility.", "fact/capability/aspiration/forecast/commitment matrix", "Data Patterns commitments contain only eligible speech acts"),
    ("business_relevance", "non_core_item_promoted", "CSR, classroom, pond, and civic items entered investor intelligence.", "Shared business-relevance guardrails quarantine non-core evidence.", "CSR and core-business contrast fixtures", "No civic or classroom item remains in the seven regenerated streams"),
    ("period_resolution", "historical_period_leakage", "Historical context and malformed fiscal periods became current progression events.", "Period resolution now distinguishes resolved, historical, ambiguous, and invalid chronology.", "FY03/FY13/FY20 and current-period fixtures", "Regenerated streams cover only the active FY22-FY26 window"),
    ("project_boundary", "product_delivery_as_internal_project", "Product deliveries and existing facilities were mislabeled as internal projects.", "Projects require a bounded internal execution action and canonical deduplication.", "radar delivery, existing facility, and bounded installation fixtures", "Data Patterns project registry fell from 29 polluted items to 8 bounded projects"),
    ("capacity_boundary", "abstract_capability_as_capacity", "Training, strategy, and abstract capability language became productive capacity.", "Capacity now requires observable productive-resource or operating evidence.", "training/strategy versus plant/workforce/facility fixtures", "Data Patterns capacity registry contains 3 productive capacity records"),
    ("commentary_progression", "single_observation_as_progression", "Bare facts and one-off observations were labeled as narrative progression.", "Commentary requires management thought; one event is explicitly an observation.", "bare fact, management rationale, and single-event fixtures", "Data Patterns commentary contains 2 coherent themes and labels the single event observation"),
    ("risk_adapter", "material_risk_zero_output", "Material multi-year and working-capital risk evidence produced an empty registry.", "Risk adapters now consume governed multi-year and financial evidence and fail on unexplained zero output.", "material-upstream/zero-output fixture", "Data Patterns risk registry contains 16 canonical risks and passes validation"),
    ("capital_allocation_adapter", "typed_financial_schema_ignored", "The allocation builder ignored typed dividend, issuance, and capex fields and returned zero or blended outcomes.", "Typed adapters preserve allocation family and item-level amounts before ledger fallback.", "dividend/equity/capex mixed-year fixture", "Data Patterns produces separate dividend, QIP, and organic-capex outcomes"),
    ("management_quality_dependency", "downstream_panel_feedback_loop", "Management Quality consumed stale panel/committee conclusions and could amplify them.", "Management Quality now consumes upstream evidence streams only.", "panel evidence rejection fixture", "Regenerated Management Quality evidence contains no investor-panel or committee source"),
    ("semantic_validation", "structural_pass_semantic_failure", "Validators passed structurally valid but investor-irrelevant intelligence.", "Validators now enforce actor, eligibility, materiality, zero-output, and critical-stream rules.", "semantic contract rejection suite", "All seven Data Patterns upstream validators pass after manual semantic audit"),
    ("lineage", "stale_synthesis_after_upstream_regeneration", "A downstream synthesis could predate the evidence it claimed to consume.", "Generated-at lineage is validated and stale dependencies hard-fail Management Quality.", "stale and current timestamp fixtures", "Management Quality manifest reports passing dependency lineage"),
)

for index, (subdomain, code, root_cause, fix, regression, live_verification) in enumerate(PHASE2_SEMANTIC_FAILURES, start=11):
    category_path = f"investor_intelligence/{subdomain}/{code}"
    INCIDENT_TAXONOMY.append({
        "category_path": category_path,
        "label": root_cause,
        "domain": "investor_intelligence",
        "subdomain": subdomain,
        "code": code,
        "severity": "high",
        "regression_focus": [regression],
    })
    INCIDENTS.append({
        "incident_id": f"FL-2026-08-09-{index:02d}",
        "company": "datapatterns",
        "year": "fy22-fy26",
        "title": root_cause,
        "command": "targeted upstream regeneration and semantic audit",
        "category_path": category_path,
        "root_cause_status": "CONFIRMED",
        "root_cause_hypothesis": root_cause,
        "observed_facts": [root_cause, live_verification],
        "durable_safeguards": [fix],
        "remediation_status": "implemented_and_verified",
        "remediation_summary": fix,
        "regression_requirements": [regression],
        "real_company_verification": live_verification,
        "severity": "high",
    })


CORE_LESSONS: List[str] = [
    "Pipeline stage success is not the same as data correctness.",
    "Critical financial metrics require context, not keywords.",
    "A strong-looking extraction can still be wrong if the statement candidate is wrong.",
    "Bridge checks are not optional; they are the guardrail that keeps semantic mistakes from turning into canonical truth.",
    "Cascades should be reported as dependency blocks, not inflated into extra root incidents.",
    "Provider success does not guarantee usable structured output.",
    "Structural validation is insufficient when semantic eligibility is wrong.",
    "Synthesis lineage must move forward only after its upstream evidence is current and valid.",
]


def validate_failure_class_registry() -> Dict[str, Any]:
    issues: List[str] = []
    seen_failure_classes = set()
    required_fields = {
        "failure_class",
        "description",
        "status",
        "first_verified",
        "last_verified",
        "affected_modules",
        "raw_input_shapes",
        "root_causes",
        "canonical_fix",
        "regression_tests",
        "safeguards",
    }

    for entry in FAILURE_CLASS_REGISTRY:
        failure_class = entry.get("failure_class")
        if not failure_class:
            issues.append("missing failure_class identifier")
            continue
        if failure_class in seen_failure_classes:
            issues.append(f"duplicate failure_class entry: {failure_class}")
        seen_failure_classes.add(failure_class)
        missing = sorted(field for field in required_fields if field not in entry or not entry.get(field))
        if missing:
            issues.append(f"{failure_class} is missing required fields: {', '.join(missing)}")
        if not isinstance(entry.get("affected_modules"), list) or not entry.get("affected_modules"):
            issues.append(f"{failure_class} must list affected modules")
        if not isinstance(entry.get("raw_input_shapes"), list) or not entry.get("raw_input_shapes"):
            issues.append(f"{failure_class} must list raw input shapes")
        if not isinstance(entry.get("regression_tests"), list) or not entry.get("regression_tests"):
            issues.append(f"{failure_class} must list regression tests")

    return {
        "status": "pass" if not issues else "fail",
        "failure_class_count": len(FAILURE_CLASS_REGISTRY),
        "issues": issues,
    }


def validate_failure_learning_registry() -> Dict[str, Any]:
    incident_codes = [item["category_path"] for item in INCIDENT_TAXONOMY]
    incident_paths = [item["category_path"] for item in INCIDENTS]
    issues: List[str] = []
    if len(set(incident_codes)) != len(incident_codes):
        issues.append("duplicate incident taxonomy codes detected")
    if len(set(incident_paths)) != len(incident_paths):
        issues.append("duplicate incident category paths detected")
    allowed_codes = set(incident_codes)
    for incident in INCIDENTS:
        if incident["category_path"] not in allowed_codes:
            issues.append(f"undocumented category path: {incident['category_path']}")
        if incident.get("root_cause_status") not in {"CONFIRMED", "HYPOTHESIS"}:
            issues.append(f"invalid root-cause status for {incident['incident_id']}")
        if not incident.get("observed_facts"):
            issues.append(f"missing observed facts for {incident['incident_id']}")
        if not incident.get("durable_safeguards"):
            issues.append(f"missing durable safeguards for {incident['incident_id']}")
        if not incident.get("regression_requirements"):
            issues.append(f"missing regression requirements for {incident['incident_id']}")
    return {
        "version": FAILURE_LEARNING_VERSION,
        "date": FAILURE_LEARNING_DATE,
        "incident_count": len(INCIDENTS),
        "taxonomy_count": len(INCIDENT_TAXONOMY),
        "failure_class_count": len(FAILURE_CLASS_REGISTRY),
        "issues": issues,
        "status": "pass" if not issues else "fail",
    }


__all__ = [
    "CORE_LESSONS",
    "FAILURE_LEARNING_DATE",
    "FAILURE_LEARNING_VERSION",
    "FAILURE_CLASS_REGISTRY",
    "INCIDENTS",
    "INCIDENT_TAXONOMY",
    "validate_failure_class_registry",
    "validate_failure_learning_registry",
]
