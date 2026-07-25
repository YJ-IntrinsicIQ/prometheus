# Atlas

Single Source of Truth for Prometheus engineering sessions. Read this before development work.

## 1. Project Overview

Prometheus is a Python finance intelligence repository centered on the `knowledge/` package. It ingests company documents, creates company memory and business understanding artifacts, plans discovery questions, retrieves supporting chunks, and produces intelligence outputs.
It also defines a canonical Fundamentals Engine contract under `knowledge/financials` for financial statement normalization before downstream ratios, trends, CIM / PCIM, and investor analysis.

Atlas governs engineering work: architecture first, no duplicate modules, and governance updates when implementation changes architecture or module status.

## 2. Current Phase & Sprint

- Phase: Atlas architecture review.
- Sprint: Architecture Review Round 1.
- Rule: Documentation-only work unless a later sprint explicitly authorizes production code changes.

## 3. Canonical Architecture

Canonical architecture, summarized:

1. Company/year context is created.
2. Raw documents are read and chunked by `scripts/smart_chunker.py`.
3. Company memory is built.
4. Business blueprint is interpreted.
5. Business classification is produced.
6. Discovery questions are planned.
7. `knowledge/retrieval` provides supporting chunks.
8. Discovery runtime executes module extraction.
9. CIM / PCIM intelligence artifacts are written.
10. `multi_year_memory` derives order-independent company-level history from yearly intelligence snapshots.
11. `knowledge/archetypes` provides the curated deterministic registry and pack vocabulary used to normalize multi-year themes, risks, metrics, and capital-allocation signals.
12. The Fundamentals Engine canonical path starts with aggregate year-level `financials`, which orchestrates `financial_discovery` -> `financial_extraction` -> `financial_normalization` -> `financial_validation` -> `financial_reconciliation` -> `financial_ratios` -> `financial_growth` -> `corporate_actions` -> `shareholding_pattern`, then writes `financial_audit_report.json`. The `financial_quality` stage is dual-mode: at year scope it reads yearly financial artifacts and writes `companies/<company>/<year>/financials/financial_quality_summary.json`; at company-memory scope, `financial_memory` orchestrates `financial_trends` -> `financial_quality` -> `financial_attribution`, then deterministically derives the reusable multi-year financial memory set (`financial_year_index.json`, `financial_trends.json`, `financial_quality_evolution.json`, `capital_allocation_financial_timeline.json`, `ownership_evolution.json`, `financial_memory_summary.json`, `financial_quality_summary.json`, `financial_driver_attribution.json`), and finally writes `financial_memory_audit_report.json`. A separate deterministic `financial_pcim_validation` stage now validates year-specific financial PCIM safety against those audited artifacts, and company-level `audit` also writes a `financial_quality_scorecard` before Investor Panel reasoning is treated as financially safe.
13. Committee synthesis now combines the five analyst outputs into a canonical `committee_synthesis.json` through a deterministic skeleton-first architecture. The pipeline owns metadata, analyst coverage, canonical enums, financial warning manifests, and registry-grounded `critical_unknowns`, while the LLM is limited to narrative fill such as executive summary and watch-list prose. The committee brief / QA stages then render and verify that combined story plus financial judgment without reading raw documents directly.
14. Fundamentals acceptance QA now sits above the audited fundamentals path and writes a final company-level readiness judgment under `companies/<company>/audit/` before the fundamentals engine is treated as trusted for investor analysis.

Artifact roles:

- CIM / PCIM: canonical intelligence contract.
- `company_memory`: transient runtime artifact.
- `business_blueprint`: reasoning artifact.
- `business_classification`: classification artifact.
- `knowledge/archetypes`: curated archetype-pack registry activated by Business DNA for deterministic normalization.
- `knowledge/financials`: canonical fundamentals schema, unit-normalization, validation, corporate-action, and ownership-tracking contract.
- Financial monetary normalization: canonical normalized unit is INR crore (`value_crore`), while original reported value/unit must always be preserved.
- Financial schema rule: no LLM-calculated ratios or derived math belongs in the schema layer.
- Corporate-action rule: share-count-sensitive events must be captured as deterministic adjustment metadata, and historical EPS / per-share growth must not be silently restated in this layer.

## 4. Canonical Pipelines

- Production pipeline: `pipelines/run_company_pipeline.py`.
- Business-understanding stage: `knowledge/business_understanding/pipeline.py`.
- Multi-year company-memory stage: `multi_year_memory` via `knowledge/company_memory/multi_year.py`.
- Fundamentals Engine stages currently include aggregate year-level `financials`, which runs `financial_discovery`, `financial_extraction`, `financial_normalization`, `financial_validation`, `financial_reconciliation`, `financial_ratios`, `financial_growth`, `corporate_actions`, and `shareholding_pattern`, then writes `companies/<company>/<year>/financials/financial_audit_report.json`; the year-level `financial_quality` stage, which reads yearly financial artifacts and writes `companies/<company>/<year>/financials/financial_quality_summary.json`; the year-level `financial_pcim_validation` stage, which validates `company_memory/pcim_v1.json` against the active year’s deterministic financial artifacts and writes `companies/<company>/<year>/financials/financial_pcim_validation.json`; plus aggregate company-level `financial_memory`, which runs `financial_trends`, `financial_quality`, and `financial_attribution`, derives the multi-year financial memory artifacts, and then writes `companies/<company>/company_memory/financials/financial_memory_audit_report.json`.
- The underlying year-level artifacts remain `companies/<company>/<year>/financials/financial_discovery.json`, `raw_financial_tables.json`, `financial_extraction_rejections.json`, `normalized_fundamentals.json`, `financial_validation_report.json`, `financial_reconciliation_report.json`, `financial_ratios.json`, `financial_growth.json`, `corporate_actions.json`, `corporate_action_rejections.json`, `shareholding_pattern.json`, `shareholding_rejections.json`, and `financial_quality_summary.json`, while the canonical company-level financial memory artifacts are `companies/<company>/company_memory/financials/financial_year_index.json`, `financial_trends.json`, `financial_quality_evolution.json`, `capital_allocation_financial_timeline.json`, `ownership_evolution.json`, `financial_memory_summary.json`, `financial_quality_summary.json`, `financial_driver_attribution.json`, and `financial_memory_audit_report.json`.
- Company-level `cim` now stores full `financial_intelligence`, and company-level `pcim` now stores compact, traceable financial panel inputs plus financial source-manifest status.
- `tools/run_fundamentals_acceptance.py` is the canonical non-LLM acceptance gate for fundamentals readiness. It reads audited yearly and company-level financial artifacts, checks CIM / PCIM / panel financial integration, scores readiness, and writes `fundamentals_acceptance_report.json` plus optional markdown under `companies/<company>/audit/`.
- `financial_pcim_validation` is the canonical deterministic year-level gate for financial PCIM safety. It must verify compact financial section presence, multi-year financial memory carry-forward, no raw-table or `source_chunk` leakage, compactness, source traceability, warning propagation, forbidden-language exclusion, and deterministic value alignment before the investor panel treats financial PCIM as safe.
- `audit` now also writes `companies/<company>/audit/financial_quality_scorecard.json` plus markdown. The scorecard is deterministic, company-level, and must summarize artifact completeness, reconciliation quality, ratio/growth quality, corporate-action quality, shareholding quality, PCIM financial integration, multi-year financial memory quality, and panel financial readiness without generating new financial analysis.
- Investor Panel analysts now consume doctrine-specific compact financial PCIM sections and must interpret precomputed financial metrics rather than calculate new ratios. Saved analyst outputs must carry a structured `financial_assessment` block plus `financial_sections_consumed` / `financial_warnings_carried_forward`, and user-facing briefs may include an optional `financial_lens` when financial evidence materially informs the analyst view.
- Investor Panel evidence routing is now governed by a shared `intelligence/investor_panel/evidence_router.py` contract rather than analyst-specific claim filters. The router owns claim classification, evidence-category matching, financial-metric provenance support, section-name / JSON-filename evidence-id sanitization, routing repair, and final saved-artifact assertion across Graham, Buffett, Fisher, Munger, and Lynch.
- Saved analyst artifacts are now split into clean downstream-safe analysis plus diagnostics sidecar under the canonical company-memory panel path `companies/<company>/company_memory/investor_panel/`. Clean `<analyst>_analysis.json` must remain free of `schema_warnings`, `evidence_grounding_warnings`, `evidence_id_normalization`, `evidence_routing_diagnostics`, prompt/input/debug fields, and other internal pipeline language, while `<analyst>_analysis_diagnostics.json` preserves those repair and validation details for audit/debug use.
- Clean analyst artifact writing is now fail-soft at the string-sanitization boundary and fail-hard at true leakage boundaries. Normal narrative prose that mentions internal artifact language may be rewritten into user-safe wording or moved into diagnostics, but hard-forbidden keys (`schema_warnings`, `evidence_grounding_warnings`, `evidence_id_normalization`, prompt/input/debug fields, `source_chunk` / `raw_text` / `full_text`) plus recommendation/valuation language still block clean artifact save. When final clean validation still fails, the runner must preserve diagnostics and write a `*_analysis_failed_clean_candidate.json` sidecar for inspection.
- `committee_synthesis` now writes a required `financial_committee_view` built from analyst-level financial reasoning only. The canonical shape is `financials_used`, `basis_used`, `financial_consensus`, `financial_strengths`, `financial_concerns`, `financial_disagreements`, `missing_financial_data`, `financial_red_flags`, `financial_interpretation_limits`, and `investor_questions_from_financials`. `committee_brief` renders a `## Financial View` section from that artifact without exposing internal system language or evidence IDs by default.
- `committee_synthesis` is now a deterministic-skeleton stage rather than an LLM-owned strict-JSON stage. `build_committee_synthesis_skeleton(...)` is the canonical boundary: it owns `company`, `analysis_mode`, `generated_at`, `analysts_considered`, `missing_analysts`, `excluded_analysts`, deterministic committee ratings/confidence, `financial_committee_view`, `areas_of_agreement`, `areas_of_disagreement`, `critical_unknowns`, `financial_warning_manifest`, and analyst coverage metadata. The LLM may supply only narrative fields such as `executive_committee_summary`, `synthesis_narrative`, `disagreement_explanation`, and `what_to_watch_next`. If narrative generation fails or is malformed, the clean committee artifact must still be written from the deterministic skeleton with conservative fallback narrative, while failure details go to diagnostics.
- `panel` remains year-aware for readiness checks when invoked as `python pipelines/run_company_pipeline.py <company> <year> --stage panel`, but investor-panel analyst, committee, brief, QA, and `panel_run_summary.json` artifacts live on the canonical company-memory panel path `companies/<company>/company_memory/investor_panel/`. By default, `panel` must reuse the existing clean analyst artifacts from that directory, validate them through the same deterministic path used by `panel_doctor`, and proceed only when those saved analyst artifacts are `pass`/`warning`; analyst regeneration is explicit opt-in via `--regenerate-analysts`. The stage must not regenerate financial artifacts implicitly, must stop when the active year’s `financial_quality_summary.json` is in `fail` status, and must validate all five analysts before blocking committee synthesis.
- `panel_doctor` is the canonical non-LLM analyst-validation audit stage. It must inspect all five saved analyst outputs without fail-fast behavior, classify structural / evidence-id / routing / internal-language / financial-warning issues, read from `companies/<company>/company_memory/investor_panel/`, and write `panel_doctor_report.json` there with `scope = "company_memory"` plus the source PCIM path instead of treating a missing year as an error.
- Experimental pipeline: `run_business_pipeline.py`.
- Merge target: validated work from `run_business_pipeline.py` merges into `pipelines/run_company_pipeline.py`.

## 5. Canonical Modules

| Module | Status |
| --- | --- |
| `knowledge.ai` | Testing |
| `knowledge.company_memory` | Integrated |
| `knowledge.business_blueprint` | Integrated |
| `knowledge.business_interpreter` | Integrated |
| `knowledge.business_classifier` | Integrated |
| `knowledge.question_engine` | Integrated |
| `knowledge.retrieval` | Production |
| `knowledge.module_extractor` | Integrated |
| `knowledge.discovery_runtime` | Integrated |
| `knowledge.business_understanding` | Integrated |
| `knowledge.archetypes` | Integrated |
| `knowledge.financials` | Integrated |
| `knowledge.cim*` / PCIM helpers | Production |
| `scripts.smart_chunker` | Production |
| `scripts/chunker.py` | Deprecated |
| `run_business_pipeline.py` | Development |
| `scripts/embed.py` | Development |
| `scripts/chunk_and_embed.py` | Development |
| `scripts/rag.py` | Development |

`scripts/embed.py`, `scripts/chunk_and_embed.py`, and `scripts/rag.py` are experimental/manual tools only.

## 6. Current Focus

Merge validated experimental pipeline behavior into `pipelines/run_company_pipeline.py` without creating duplicate production paths.

## 7. Current Priorities

1. Plan the merge from `run_business_pipeline.py` into `pipelines/run_company_pipeline.py`.
2. Keep `scripts/smart_chunker.py` as the canonical chunker and avoid extending `scripts/chunker.py`.
3. Treat CIM / PCIM as the canonical intelligence contract.
4. Keep retrieval work inside `knowledge/retrieval`.
5. Add versioning for all AI prompts and AI output schemas before breaking changes.
6. Keep financial normalization canonical in `knowledge/financials` before normalized fundamentals and ratio/trend work expands.

## 8. Known Architectural Debt

- `run_business_pipeline.py` contains validated behavior that is not yet merged into `pipelines/run_company_pipeline.py`.
- `scripts/chunker.py` remains present but deprecated.
- Experimental embedding/RAG scripts remain as manual tools.
- Prompt and AI output schema versioning still needs implementation.
- Breaking-change version bump rules are approved but not yet enforced in code.
- Financial statement discovery, raw financial extraction, normalized fundamentals, financial validation, financial ratios, corporate actions, financial growth, shareholding-pattern tracking, company-level financial trends, company-level financial quality, and company-level financial attribution are now wired into the canonical pipeline as standalone stages, but broader interpretive financial layers are still not wired into `--stage all`.
- The new aggregate `financials` stage now writes an audit report even when deterministic downstream gates stop the run, but real-company financial runs still surface legitimate upstream quality warnings around basis clarity, capex capture, and unmapped rows that need extraction/normalization improvement rather than orchestration relaxation.
- Fundamentals acceptance QA is now available, but real companies with partial year coverage or failed yearly validation still score as untrusted for investor use. Current `datapatterns` acceptance fails because `fy22` and `fy23` have no financial artifact chain yet and `fy24` still fails yearly financial validation before ratios are available.
- Financial PCIM validation and the financial quality scorecard are now available, but real-company usefulness still depends on upstream year-level financial quality. Missing capex/FCF/share-count/payables/shareholding may remain warning-level, while misleading PCIM content, hidden hard failures, raw leakage, or invented values must still fail deterministically.
- Investor-panel financial integration is now wired into the canonical analyst path, but real-company analyst prompts can still exceed budget after compaction when large non-financial PCIM sections and new financial sections are combined. Analyst validation is intentionally strict: it must block invented financial claims, unsupported ratio/valuation language, and silent omission of major missing-data limits from the supplied financial PCIM context.
- Existing saved `committee_synthesis.json` artifacts created before the financial committee contract bump must be regenerated before the new committee brief renderer can accept them.

## 9. Active Decisions

- `pipelines/run_company_pipeline.py` is the canonical production pipeline.
- `run_business_pipeline.py` is experimental; validated behavior should merge into the canonical pipeline.
- `scripts/smart_chunker.py` is the canonical chunker; `scripts/chunker.py` is deprecated.
- `knowledge/retrieval` is canonical retrieval; embedding/RAG scripts are experimental/manual tools only.
- CIM / PCIM is the canonical intelligence contract.
- AI prompts and AI output schemas require versioning; breaking changes require version bumps.
- `knowledge/financials` is the canonical fundamentals schema subsystem, and its yearly plus company-level artifacts now feed CIM / PCIM directly.
- Financial monetary values must preserve original reported value/unit and normalize to `value_crore` in INR.
- Financial schema / validator layers must not contain LLM-calculated ratios or downstream analytical math.
- `financial_discovery` is the canonical non-LLM stage for locating likely financial statement and note sections before any financial number extraction.
- `financial_discovery` items must carry explicit basis metadata (`basis`, `basis_confidence`) whenever standalone / consolidated evidence is detectable so downstream stages do not need to re-guess basis from raw text alone.
- `financial_discovery` must classify primary statements, explicit notes, accounting-policy text, auditor-report text, management-discussion financial summaries, and irrelevant financial narrative separately so downstream extraction can favor precision over broad recall.
- `financial_extraction` is the canonical non-LLM stage for capturing raw financial table rows with preserved labels, raw values, basis hints, typed values (`value_type`, `raw_number`), and `value_crore` normalization only where the row is genuinely monetary.
- `financial_extraction` must also emit `financial_extraction_rejections.json` so rejected table candidates remain auditable instead of disappearing silently.
- `financial_normalization` is the canonical non-LLM stage for mapping raw financial rows into field-level normalized fundamentals, preserving source lineage, basis, original reported values, and unmapped rows.
- `normalized_fundamentals.json` is the canonical preferred-basis surface for downstream math. It must expose `preferred_basis`, `basis_options_available`, `selected_basis_reason`, `basis_confidence`, and `basis_manifest`, must preserve non-preferred evidence under `basis_views`, and must not silently promote standalone values into a consolidated preferred view or vice versa.
- `financial_normalization` must prefer primary statements over note summaries or management-discussion financial summaries when multiple candidate rows compete for the same canonical field.
- `cash_flow.capex` is a guarded normalized field: it should only be populated from clear investing cash-flow capex evidence or equally explicit capex/additions evidence, must preserve cash-flow sign semantics, and should carry `capex_abs_crore` plus `sign_convention` metadata so downstream FCF remains deterministic. Missing capex is acceptable as a warning; incorrect capex sourcing is not.
- `financial_validation` is the canonical non-LLM readiness gate that checks normalized fundamentals for required fields, consistency, unit/source integrity, and suspicious sign conventions before ratios are allowed downstream.
- `financial_reconciliation` is the canonical non-LLM gate between `financial_validation` and downstream financial math. It verifies that normalized fundamentals still point to relevant source lines, preserve the correct value type for EPS/share-count fields, and do not rely on unrelated or disallowed source sections before ratios or growth proceed.
- `cash_flow.fcf` should normally be derived from CFO plus capex provenance rather than loosely extracted from noisy text. Missing FCF because capex is genuinely unavailable is a warning path; populated FCF from an unrelated heading, balance row, or non-capex source is a hard failure.
- `financial_ratios` is the canonical non-LLM ratio-calculation stage that reads reconciled normalized fundamentals, preserves formula plus input provenance, emits null-plus-warning for missing inputs, and refuses to calculate on top of failed reconciliation for critical inputs.
- `financial_ratios` and `financial_growth` must carry explicit basis context (`basis_used`, `basis_confidence`, `basis_warnings`) so downstream consumers can distinguish a clean consolidated/standalone run from an explicitly unknown or warning-level basis state.
- `financial_quality` is the canonical non-LLM diagnostic stage with two deterministic modes. Year mode reads `normalized_fundamentals.json`, `financial_reconciliation_report.json`, `financial_validation_report.json`, `financial_ratios.json`, `financial_growth.json`, `corporate_actions.json`, and optional `shareholding_pattern.json`, then writes a year-level `financial_quality_summary.json` with section-level assessments, evidence metrics, warnings, limitations, red flags, missing-data notes, and investor questions. Company-memory mode reads `financial_trends.json`, converts multi-year growth, margin, return, cash-conversion, leverage, working-capital, ownership, and corporate-action signals into investor-readable positives, red flags, missing-data notes, and warning-aware quality sections, and writes the company-memory `financial_quality_summary.json` without valuation or recommendation language.
- `financial_attribution` is the canonical non-LLM company-level attribution stage that reads `financial_trends.json`, `financial_quality_summary.json`, and available multi-year company-memory artifacts, then links major financial movements to possible business events or management actions without overclaiming causation, and writes `financial_driver_attribution.json`.
- `corporate_actions` is the canonical non-LLM metadata stage for dividends, split/bonus/dilution events, face-value changes, and share-count comparability warnings, using normalized fundamentals plus raw financial table evidence without silently restating historical per-share values.
- `corporate_actions` must stay conservative: dividend cash outflow and dividend-per-share are separate signals, share counts must never be stored as `amount_crore`, QIP/rights/preferential issue rows must distinguish issue events from proceeds-utilization rows where the source makes that distinction visible, and rejected or nullified action-like candidates must remain auditable in `corporate_action_rejections.json` instead of being silently accepted or dropped.
- `financial_growth` is the canonical non-LLM growth-calculation stage that reads reconciled normalized fundamentals plus available ratio history, computes YoY and multi-year growth where evidence exists, records null-plus-warning when history is missing or unusable, and may derive margin changes directly from normalized fundamentals when ratio history is unavailable.
- `shareholding_pattern` is the canonical non-LLM ownership-tracking stage that reads normalized fundamentals plus available raw shareholding rows, records ownership categories and change signals only from explicit shareholding evidence, emits warning-only artifacts when real reports do not yet yield usable ownership rows, and preserves rejected ownership candidates in `shareholding_rejections.json` for auditability.
- `financial_trends` is the canonical non-LLM company-level aggregation stage that reads yearly financial artifacts, preserves year-level provenance plus comparability warnings, and builds the reusable multi-year financial trend view before downstream CIM / PCIM interpretation.
- `financials` is the canonical aggregate year-level fundamentals stage. It must run the deterministic yearly fundamentals stages in order, must still emit `financial_audit_report.json` when a downstream readiness gate fails, and must not bypass validation in order to produce ratios or growth.
- `financial_memory` is the canonical aggregate company-level fundamentals stage. It must run `financial_trends`, `financial_quality`, and `financial_attribution` in order, then derive `financial_year_index`, `financial_quality_evolution`, `capital_allocation_financial_timeline`, `ownership_evolution`, and `financial_memory_summary` before emitting `financial_memory_audit_report.json` for downstream CIM / PCIM consumption.
- `financial_pcim_validation` is the canonical year-level deterministic safety gate for financial PCIM. It must validate existing PCIM output against audited year-level financial artifacts, must not call LLMs, must not calculate new ratios, and must fail on raw leakage, invented financial values, hidden hard failures, or forbidden valuation/recommendation language.
- `run_fundamentals_acceptance.py` is the canonical final QA gate for fundamentals readiness. It must stay deterministic, must not call LLMs, must treat missing revenue/PAT, failed financial validation, missing normalized INR-crore values, missing core traceability, or missing PCIM financial manifest as hard failures, and must keep `ready_for_valuation` false at this stage even when `ready_for_panel` becomes true.
- `cim` is the canonical storage layer for full financial intelligence artifacts, including yearly fundamentals, yearly ratios/growth/corporate-actions/shareholding, and company-level financial trends, quality summary, and driver attribution.
- `cim.financials` is the canonical compact financial judgment view for downstream consumers. It must expose named sections for `core_fundamentals`, `profitability`, `growth`, `return_on_capital`, `cash_conversion`, `balance_sheet`, `working_capital`, `per_share`, `corporate_actions`, `shareholding`, `financial_quality_summary`, plus `basis_used`, `basis_confidence`, `warnings`, `limitations`, and `source_manifest`.
- `pcim` is the canonical compact panel-facing projection layer for financial evidence. It must preserve source-year and source-artifact traceability, exclude `source_chunk`, and carry `pcim_source_manifest` financial status (`financial_artifacts_used`, `financial_years_covered`, `financial_status`, `financial_warnings`).
- The canonical compact financial PCIM sections are `financial_fundamentals_inputs`, `financial_trend_inputs`, `financial_growth_inputs`, `profitability_inputs`, `cash_conversion_inputs`, `return_on_capital_inputs`, `balance_sheet_strength_inputs`, `working_capital_inputs`, `per_share_inputs`, `corporate_action_inputs`, `ownership_inputs`, `financial_quality_inputs`, `financial_driver_inputs`, and `multi_year_financial_inputs`. These sections must stay compact, deterministic, raw-table-free, and panel-safe.
- `multi_year_financial_inputs` is the canonical panel-facing summary of company-level financial memory. It must be derived only from audited year-level financial artifacts and company-level financial memory files, must stay compact, must exclude raw tables and `source_chunk`, and should be the preferred multi-year financial context surface for downstream investor-panel reasoning when present.
- `financial_quality_scorecard` is the canonical deterministic company-level financial readiness scorecard. It must aggregate year-level financial PCIM validation, audited yearly financial artifacts, multi-year financial memory, and panel-readiness signals into dimension scores and recommended next fixes, but it must not perform new financial interpretation or valuation.
- `financial_source_manifest` and `financial_panel_ready` are required top-level PCIM financial contract fields whenever financial PCIM sections are present. `financial_panel_ready` may be true only when usable financial quality evidence exists and manifest status is `pass` or `warning`.
- Financial numbers enter downstream CIM / PCIM and investor workflows only through audited financial memory: normalized INR-crore values, preserved original values/units, source traceability, and no-LLM-math checks are required contract points.
- Investor-panel doctrine mappings are the canonical control for which compact financial PCIM sections each analyst can see. Analysts may interpret only precomputed metrics already present in PCIM, must surface missing-data and comparability limits explicitly, and must not calculate new ratios in the LLM layer.
- Investor-panel financial metric validation must use a deterministic selected-metric registry derived from the exact compact financial PCIM sections shown to the analyst. `financial_metrics_used` should prefer structured `{metric_id, metric, period, used_for}` objects, while string fallbacks may be canonicalized only through approved metric aliases tied to selected PCIM evidence.
- Investor-panel analyst output now carries `schema_warnings` as a canonical validation artifact. Harmless list-shape drift in fields such as `reasoning_limits`, `financial_missing_data`, `financial_interpretation_limits`, `financial_warnings_carried_forward`, `financial_red_flags`, and nested `financial_assessment` list fields may be normalized deterministically into `list[str]`, but only with explicit `schema_warnings`; raw payload leakage (`source_chunk`, `raw_text`, `full_text`), forbidden recommendation/valuation language, unsupported financial claims, and missing required sections must still fail hard.
- Investor-panel analyst `evidence_ids` must contain only canonical evidence IDs present in the PCIM evidence lookup. PCIM section-name aliases such as `risk_inputs`, `financial_quality_inputs`, `governance_and_incentive_inputs`, and other compact-section labels are not evidence IDs; they must be removed from every nested analyst evidence list before save, recorded under `evidence_id_normalization.removed_invalid_ids`, and leave the saved analyst output at `warning` rather than `fail` when the cleanup is hygiene-only. Unknown evidence IDs are likewise removed from active evidence lists but retained in diagnostics; a final recursive assertion must prevent invalid evidence IDs from being written.
- Munger analyst outputs carry internal `munger_evidence_routing_diagnostics` so deterministic pre-validation routing repairs remain auditable. Governance/incentive claims may not cite market-risk / FX / interest-rate evidence unless the claim is explicitly about risk oversight or risk governance; misrouted governance claims must be rerouted to governance/ownership/capital-allocation/corporate-action/uncertainty evidence when such evidence is available to Munger, or converted into limitation / open-uncertainty language before final grounding validation. These diagnostics are internal and must not appear in user-facing briefs.
- Financial warning carry-forward is a canonical investor-panel validation contract. Major financial warnings from selected PCIM context must be preserved semantically in analyst output via `financial_missing_data`, `financial_interpretation_limits`, or `financial_warnings_carried_forward`, with precise wording preferred over generic placeholders. The system must build deterministic required warning groups from selected financial PCIM context, auto-carry any omitted major warning before final validation, record that repair in `schema_warnings`, and still fail hard if the analyst contradicts the required warning (for example by claiming FCF, owner earnings, or FCF-backed dividend quality when FCF/capex is missing). In particular, share-count warnings must distinguish `share count missing` from `weighted average shares missing` / `diluted shares missing`, and generic missing-data claims must not be emitted when a more specific supported limitation is available.
- Investor-panel prompt compaction is now a hard serialized-section-budget contract, not only a best-effort global prompt shrink. After recursive compaction, each included PCIM section must still obey deterministic post-compaction char caps (`multi_year_inputs` 4000; `financial_quality_inputs`, `capital_allocation_inputs`, `management_quality_inputs`, `moat_inputs`, `governance_and_incentive_inputs` 3000; `business_understanding` and `business_economics_inputs` 2500; other sections 2500). `multi_year_inputs` must preserve `years_covered`, `limitations`, compact evidence traceability, and no `source_chunk`, while section-over-budget fallbacks must collapse to limitation objects rather than silently leaking oversized payloads into analyst prompts.
- Committee synthesis may interpret only analyst-level financial outputs already produced by the investor panel. It must not calculate new ratios, must not introduce unsupported financial claims, and must keep user-facing committee brief text free of internal architecture terms such as PCIM / CIM / schema / validator language. Committee financial synthesis must derive from analyst `financial_assessment`, `financial_sections_consumed`, `financial_warnings_carried_forward`, and other saved analyst financial fields rather than raw PCIM or raw financial artifacts.
- Committee synthesis `critical_unknowns` use a canonical grounded shape: `unknown`, `raised_by`, `why_it_matters`, `source_uncertainty_ids`, and `evidence_limit`. Every critical unknown must trace to the analyst uncertainty registry; missing `raised_by` or `source_uncertainty_ids` may be deterministically inferred only from that registry, and ungrounded unknowns must fail validation.
- Committee synthesis clean artifacts must remain downstream-safe. User-facing `committee_synthesis.json` may not expose internal normalization/debug markers such as `grounding_status`, prompt/input-pack fields, schema-repair metadata, or other internal pipeline terms. Those belong only in `committee_synthesis_diagnostics.json`.
- The panel-stage financial readiness gate is orchestration-only: it may inspect the presence and status of yearly financial artifacts, surface missing or warning-level finance context into the panel summary, and rely on CIM / PCIM rebuilds to carry those limitations forward, but it must not silently rerun financial discovery/extraction/normalization/ratios/growth stages.

## 10. Next Milestone

Regenerate stale committee synthesis artifacts against the new financial committee contract, then continue tightening investor-panel prompt compaction for real company PCIMs while keeping doctrine-declared financial coverage and the no-new-ratio rule intact.
