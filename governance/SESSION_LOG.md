# Session Log

Chronological engineering history only.

## 2026-07-03

- Date: 2026-07-03
- Sprint: Atlas Phase 1
- What was completed: Created the initial governance inventory and expanded Atlas governance framework.
- Important decisions: No production architecture decisions were made.
- Backlog items created: `ENG-001` through `ENG-005`.
- Next session goal: Simplify governance into a smaller single-source-of-truth system.

## 2026-07-03

- Date: 2026-07-03
- Sprint: Atlas Simplification Pass
- What was completed: Archived fragmented governance documents, renamed engineering backlog to `BACKLOG.md`, created `ATLAS.md`, and simplified `SESSION_LOG.md`.
- Important decisions: `ATLAS.md` is now the single source of truth before development sessions; `SESSION_LOG.md` is historical; `BACKLOG.md` is future work only.
- Backlog items created: None.
- Next session goal: Run architecture review for canonical pipeline ownership and module lifecycle assignments.

## 2026-07-03

- Date: 2026-07-03
- Sprint: Architecture Review Round 1
- What was completed: Applied approved Architecture Review Board decisions for `ENG-001` through `ENG-005` to `ATLAS.md` and marked the backlog items completed.
- Important decisions: `pipelines/run_company_pipeline.py` is the canonical production pipeline; `run_business_pipeline.py` is experimental with validated behavior merging into the canonical pipeline; `scripts/smart_chunker.py` is canonical and `scripts/chunker.py` is deprecated; `knowledge/retrieval` is canonical while embedding/RAG scripts remain experimental/manual tools; CIM / PCIM is the canonical intelligence contract; AI prompts and AI output schemas require versioning and breaking changes require version bumps.
- Backlog items created: None.
- Next session goal: Prepare the implementation plan for merging validated behavior from `run_business_pipeline.py` into `pipelines/run_company_pipeline.py`.

## 2026-07-03

- Date: 2026-07-03
- Sprint: Canonical Pipeline Hardening
- What was completed: Hardened `pipelines/run_company_pipeline.py` to pass the active `CompanyContext` through canonical stage calls, reuse the business-understanding bundle in `run_all()`, and fail fast when the business-understanding bundle or `business_classification` is missing or invalid.
- Important decisions: No new architecture decisions were made; implementation followed existing Atlas decisions.
- Backlog items created: `ENG-006`.
- Next session goal: Align focused pipeline tests with explicit context flow and continue planning the merge from `run_business_pipeline.py` into `pipelines/run_company_pipeline.py`.

## 2026-07-03

- Date: 2026-07-03
- Sprint: ENG-006 Pipeline Test Alignment
- What was completed: Updated focused pipeline/business-understanding tests to use explicit `CompanyContext` propagation, assert Business Understanding executes once in `run_all()`, assert the returned bundle is reused downstream, and cover fail-fast bundle validation.
- Important decisions: No new architecture decisions were made; tests were aligned to existing Atlas decisions.
- Backlog items created: None.
- Next session goal: Continue planning the merge from `run_business_pipeline.py` into `pipelines/run_company_pipeline.py`.

## 2026-07-03

- Date: 2026-07-03
- Sprint: Business Interpreter Contract Fix
- What was completed: Aligned the Business Interpreter prompt with the Business Blueprint validator by using the existing blueprint version constant and the canonical `characteristics` field; added focused test coverage for the prompt/validator contract.
- Important decisions: No new architecture decisions were made; the fix reused the existing `DEFAULT_BLUEPRINT_VERSION`.
- Backlog items created: `ENG-007`.
- Next session goal: Decide default mock behavior for canonical pipeline smoke runs.

## 2026-07-04

- Date: 2026-07-04
- Sprint: ENG-007 Mock Provider Determinism
- What was completed: Added a deterministic default Business Blueprint fixture for the mock AI provider when `AI_MOCK_RESPONSE` is not configured, and updated focused tests to prove the default fixture, explicit override behavior, and unchanged Groq behavior.
- Important decisions: No new architecture decisions were made; the mock provider now returns a valid canonical Business Blueprint fixture by default.
- Backlog items created: None.
- Next session goal: Continue normal development with deterministic local smoke runs.

## 2026-07-04

- Date: 2026-07-04
- Sprint: Groq Model Migration
- What was completed: Migrated all remaining production and manual Groq call sites off `llama-3.3-70b-versatile` to `openai/gpt-oss-120b`, using the existing Groq model-selection environment variables where present.
- Important decisions: No architecture changes were made; model selection was centralized through the existing Groq environment-variable pattern.
- Backlog items created: None.
- Next session goal: Continue normal development with the new Groq model default in place.

## 2026-07-04

- Date: 2026-07-04
- Sprint: Extractor Batching Hardening
- What was completed: Hardened the shared `core/base_extractor.py` path to split oversized discovery chunk payloads into smaller batches, merge batch outputs back into the same final extracted file schema, add batch-level logging, and raise clearer batch-context errors; added focused batching tests.
- Important decisions: No architecture changes were made; batching was implemented in the shared `BaseExtractor` path so all existing extractor entrypoints benefit automatically.
- Backlog items created: None.
- Next session goal: Re-run the full extractor stage in an environment with the `groq` package available and confirm the capital allocation path completes on full discovery output.

## 2026-07-04

- Date: 2026-07-04
- Sprint: Business Understanding Ingestion Fix
- What was completed: Replaced the canonical business-understanding stage's placeholder `document_loaded` primary ingestion path with real ingestion from cleaned extracted artifacts under the active company/year context, built stable company-memory events/evidence from those artifacts, preserved the annual-report stub only as fallback, and added focused tests for real-artifact ingestion and fallback behavior.
- Important decisions: No architecture changes were made; the canonical `company_memory -> business_blueprint -> business_classification` flow was preserved and the cleaned-artifact path now rebuilds transient `company_memory` fresh to avoid carrying stale placeholder events across reruns.
- Backlog items created: None.
- Next session goal: Verify business-understanding quality with a real AI provider and continue the canonical pipeline merge with substantive company-memory inputs in place.

## 2026-07-04

- Date: 2026-07-04
- Sprint: Real End-to-End Verification
- What was completed: Installed the missing runtime dependencies needed for real Groq and discovery execution, switched the canonical run off the default mock path by restoring `.env` loading, compacted the Business Interpreter's company-memory prompt view to fit Groq token limits, verified a real Groq-backed `business_understanding` run for `polymatech fy25`, and exercised discovery/extraction far enough to confirm the `chromadb` path and extractor batching are live.
- Important decisions: No architecture changes were made; prompt compaction was implemented at the Business Interpreter input layer so persisted `company_memory` remains substantive while the model receives a smaller factual view. Real verification showed meaningful business-understanding output, but classifier registry mappings do not yet translate the richer characteristic vocabulary into Business DNAs.
- Backlog items created: `ENG-008`.
- Next session goal: Align classifier mappings to real Business Understanding characteristics and continue full canonical pipeline verification once Groq rate limits clear.

## 2026-07-04

- Date: 2026-07-04
- Sprint: ENG-008 Taxonomy Alignment
- What was completed: Expanded the canonical business-classifier registry to recognize the real characteristic vocabulary now emitted by Groq-backed Business Understanding, verified the Polymatech blueprint classifies to `Manufacturing`, `Semiconductor`, and `Export`, and confirmed the Question Planner now loads the canonical `capital_allocation` and `technology` modules.
- Important decisions: No architecture changes were made; taxonomy alignment was implemented by extending the existing classifier mappings rather than changing classifier structure or prompt behavior. Full pipeline verification confirmed Business Intelligence no longer shows `Business DNAs: None` or `Modules Loaded: 0`, and uncovered a separate retrieval-wiring follow-up for the canonical Business Intelligence stage.
- Backlog items created: `ENG-009`.
- Next session goal: Wire the canonical Business Intelligence stage to retrieval evidence and continue full pipeline verification after Groq daily token limits reset.

## 2026-07-04

- Date: 2026-07-04
- Sprint: ENG-009 Retrieval Wiring
- What was completed: Wired the canonical Business Intelligence stage in `pipelines/run_company_pipeline.py` to build and pass a real retriever plus module extractor into `DiscoveryRuntime`, ensured canonical retrieval artifacts are generated when `clean_chunks.json` is missing, restored the retrieval embedder's cached local sentence-transformer loading path, and added focused tests for runtime wiring and embedder cache behavior.
- Important decisions: No architecture changes were made; the fix reused the existing canonical `knowledge.retrieval` and `knowledge.discovery_runtime` path rather than introducing a new runtime abstraction. Practical verification against `polymatech fy25` confirmed the planner/runtime path now retrieves non-zero evidence (`99` chunks across `capital_allocation` and `technology`) and passes it into module execution. A full live Groq rerun remains externally constrained by current API rate limiting.
- Backlog items created: None.
- Next session goal: Re-run the full canonical Business Intelligence stage once Groq rate limits clear and verify fresh persisted `module_results.json` and `discovery_runtime.json` from the real extractor path.

## 2026-07-04

- Date: 2026-07-04
- Sprint: Temporary Extraction Input Cap
- What was completed: Added an optional `EXTRACTOR_MAX_ITEMS` environment-variable cap in the shared `core/base_extractor.py` path so local verification runs can process only the first N discovery items without editing discovery JSON files, kept default behavior unchanged when unset, added focused tests for capped and invalid values, and verified the cap against the real `polymatech fy25` capital allocation discovery input (`66` items capped to `10`).
- Important decisions: No architecture changes were made; the cap was implemented as a small testing aid in the existing shared extractor path so every extractor using `BaseExtractor` inherits it automatically. Live Groq-backed extraction verification still remains externally constrained by provider/network limits rather than the cap mechanism itself.
- Backlog items created: None.
- Next session goal: Re-run capped or full extraction once Groq token limits reset and confirm end-to-end extractor outputs under the canonical pipeline path.

## 2026-07-04

- Date: 2026-07-04
- Sprint: Business Interpreter Required Summary Contract
- What was completed: Tightened the Business Interpreter prompt contract so `business_understanding.business_summary` is explicitly required, clarified the full required JSON structure with a final response checklist, switched the embedded Company Memory view to valid JSON for clearer model guidance, added focused prompt-contract tests, and verified a real Groq-backed `polymatech fy25` business-understanding run now completes and writes `business_blueprint.json`.
- Important decisions: No architecture changes were made; the fix was applied at the prompt/response-contract layer rather than weakening validation or adding parser fallbacks. Real verification confirmed the missing-field failure is resolved, though the resulting summary content can still be semantically weak when the supplied memory is weak.
- Backlog items created: None.
- Next session goal: Improve business-understanding output quality further only if needed, without relaxing the current validator contract.

## 2026-07-04

- Date: 2026-07-04
- Sprint: Env-Driven OpenAI Provider Support
- What was completed: Added an `OpenAIProvider` in `knowledge.ai`, updated the provider factory to select between `groq`, `openai`, and `mock` from `AI_PROVIDER`, added focused AI-layer tests for provider selection and env-driven model lookup, and verified the canonical `business_understanding` path still runs through Groq when `AI_PROVIDER=groq` and `GROQ_MODEL=openai/gpt-oss-120b` are set in the environment.
- Important decisions: No architecture changes were made; provider/model switching remains centralized in the existing AI provider layer so business modules continue calling `get_llm()` unchanged. The OpenAI path is now code-complete and test-covered, but live OpenAI verification could not be completed in this workspace because `OPENAI_API_KEY` and `OPENAI_MODEL` are not currently configured.
- Backlog items created: None.
- Next session goal: Add the required OpenAI environment variables locally and verify the canonical `business_understanding` path end to end on `AI_PROVIDER=openai`.

## 2026-07-04

- Date: 2026-07-04
- Sprint: Rule-Based Business Classifier Normalization
- What was completed: Hardened the canonical business-classifier registry so characteristic matching no longer depends on exact full-string equality, added deterministic normalization plus contains and keyword-group matching, added focused regression tests for exact matches, substring variants, and the real `polymatech fy25` blueprint phrases, and verified that the existing `polymatech` blueprint now classifies to populated Business DNAs and question modules with a non-empty discovery plan.
- Important decisions: No architecture changes were made; the fix stayed inside `knowledge.business_classifier` and used transparent rule-based matching rather than embeddings, vector search, or pipeline-side fallbacks. Matching remains explainable: normalized exact match first, phrase contains next, then controlled keyword groups.
- Backlog items created: None.
- Next session goal: Re-run the full canonical `business_understanding -> discovery_plan` path when practical and continue tightening business-understanding quality without changing classifier architecture.

## 2026-07-05

- Date: 2026-07-05
- Sprint: Groq JSON Reliability Hardening
- What was completed: Hardened the Business Interpreter JSON contract for Groq-backed runs by tightening the prompt’s machine-readable formatting rules, explicitly requiring numeric JSON confidence values and nested object structure, adding a Groq provider system instruction that only applies to structured JSON generation, and adding focused regression tests. A real `polymatech fy25` Groq-backed `business_understanding` run now completes successfully and writes `business_blueprint.json` with numeric confidence fields.
- Important decisions: No architecture changes were made; the fix stayed in the existing prompt and Groq provider layers rather than adding parser-side fallbacks or weakening validation. The output contract is unchanged, but the JSON-generation instructions are stricter and more machine-oriented for reliability.
- Backlog items created: None.
- Next session goal: Continue improving business-understanding quality and evidence richness without loosening the current JSON/validator contract.

## 2026-07-05

- Date: 2026-07-05
- Sprint: Business Intelligence CLI Stage
- What was completed: Added a minimal `business_intelligence` CLI stage to `pipelines/run_company_pipeline.py`, wired it to the existing canonical `run_business_intelligence_stage(context=...)` path, and added a focused dispatch test to confirm the new stage reuses the active `CompanyContext` without changing existing stage behavior.
- Important decisions: No architecture changes were made; the new CLI option is only a thin dispatch layer over the existing canonical Business Intelligence stage. Real end-to-end verification reached the Business Intelligence runtime successfully, but the full artifact refresh was externally blocked by a Groq rate limit during module extraction rather than by CLI wiring.
- Backlog items created: None.
- Next session goal: Re-run the new `business_intelligence` stage once provider limits clear and confirm refreshed `discovery_plan.json`, `module_results.json`, and `discovery_runtime.json` from the canonical path.

## 2026-07-05

- Date: 2026-07-05
- Sprint: Temporary Business Intelligence Test Caps
- What was completed: Added optional env-driven Business Intelligence test caps for loaded modules, planned questions, and retrieved chunks per question in the canonical BI path; added focused tests for plan capping and per-question chunk capping; and verified that a capped `business_intelligence` run logs the active limits and reduces planning/retrieval fanout as intended.
- Important decisions: No architecture changes were made; the caps were implemented as temporary testing aids in the canonical pipeline/runtime path and remain fully disabled when unset. Real capped verification showed improved control over BI fanout, but end-to-end artifact refresh can still be dominated by downstream provider latency in module extraction.
- Backlog items created: None.
- Next session goal: Re-run capped Business Intelligence with the active provider once latency/timeout pressure is lower and confirm refreshed BI artifacts from the canonical path.

## 2026-07-05

- Date: 2026-07-05
- Sprint: Business Interpreter Specificity Improvement
- What was completed: Tightened the Business Interpreter prompt to explicitly prefer concrete, company-specific, economically relevant characteristics and to discourage vague labels like `Sustainability`, `Innovation`, `Social Responsibility`, and `Human Resources` unless tied to a specific operating attribute. Added focused prompt tests and verified a real `polymatech fy25` business-understanding run now emits sharper characteristics such as export-led expansion, advanced manufacturing automation, R&D collaboration, and capital-intensive manufacturing buildout, with improved DNA/module coverage downstream.
- Important decisions: No architecture changes were made; the improvement stayed prompt-focused and preserved the existing JSON contract. The resulting characteristics are now classification-friendly, but the business summary itself can still remain more generic than the characteristic list.
- Backlog items created: None.
- Next session goal: Improve business summary specificity further if needed, while keeping the same JSON schema and prompt-first approach.

## 2026-07-05

- Date: 2026-07-05
- Sprint: OpenAI Timeout and Retry Configuration
- What was completed: Added env-driven OpenAI timeout and retry configuration in the existing AI provider layer, raised the safe default timeout for OpenAI-backed runs to `180` seconds, passed timeout and retry settings into the OpenAI SDK client, added a minimal retry loop for the existing `httpx` fallback path, and added focused AI-layer tests for default values and env overrides.
- Important decisions: No architecture changes were made; timeout and retry behavior remain centralized in `knowledge.ai.openai` so business modules continue using the existing provider interface unchanged. Retry behavior only applies to transient OpenAI transport/rate-limit failures and stays inactive unless the provider path is used.
- Backlog items created: None.
- Next session goal: Verify the updated OpenAI-backed canonical pipeline path under real environment credentials and tune timeout/retry values only if real provider behavior still warrants it.

## 2026-07-05

- Date: 2026-07-05
- Sprint: Company Intelligence Business Section Wiring
- What was completed: Updated the canonical `knowledge.cim_builder` path so `company_intelligence.json` now populates `business.dna` from `business_classification.json`, `business.industry_profile` from `business_blueprint.json`, and `business.competitive_position` from the Business Blueprint plus executed-module context from canonical BI artifacts. Added a focused regression test and verified the existing `polymatech fy25` intelligence build now produces a populated `business` section without changing the other CIM sections.
- Important decisions: No architecture changes were made; the fix reuses the existing canonical intelligence artifacts already written by Business Understanding and Business Intelligence, and keeps the mapping centralized in the CIM builder rather than duplicating business logic elsewhere.
- Backlog items created: None.
- Next session goal: Continue filling other final-intelligence sections from canonical upstream artifacts only where the current builder is still leaving already-known information behind.

## 2026-07-05

- Date: 2026-07-05
- Sprint: FY24 Discovery Index Freshness Fix
- What was completed: Added a minimal canonical pre-discovery indexing step so `pipelines/run_company_pipeline.py` now ensures the active company/year annual-report slice is present in the Chroma `company_documents` collection before discovery queries run, reusing the existing `embeddings.index_builder` path and adding focused regression coverage for discovery orchestration. Real verification against `polymatech fy24` confirmed the active slice was indexed on demand and the FY24 raw discovery outputs are no longer all empty arrays.
- Important decisions: No architecture changes were made; the fix stays at the orchestration/index-freshness layer and does not bypass Chroma or alter PDF extraction/chunking. Optional downstream extraction verification remained externally blocked by an OpenAI connection failure after the discovery fix had already succeeded.
- Backlog items created: None.
- Next session goal: Re-run the FY24 extraction/cleaning/business-understanding chain in a working AI-provider environment and verify substantive FY24 business-understanding artifacts now that discovery is populated.

## 2026-07-05

- Date: 2026-07-05
- Sprint: Archetype-Based Business Classifier Refinement
- What was completed: Refined the canonical business classifier so it now combines characteristic labels with broader business-understanding text, adds archetype-oriented text signal groups for semiconductor-style and export-style businesses, and fixes a registry state-leak bug caused by shallow-copying default discovery/extraction profiles. Focused classifier tests now cover broader semiconductor pattern detection and cross-call isolation, and direct reclassification of the existing `polymatech` FY24/FY25 blueprints confirms FY24 now maps to `Manufacturing`, `Semiconductor`, and `Export` while FY25 keeps its successful `Manufacturing` and `Semiconductor` classification.
- Important decisions: No architecture changes were made; the classifier remains deterministic and registry-driven, but detection now leans on higher-order business archetypes such as wafers, substrates, packaged chips, and export-led electronics manufacturing instead of accreting company-specific literal phrases. Live `business_understanding` and `business_intelligence` reruns were externally blocked by current Groq network connectivity, so stage-level artifact regeneration could not be completed in this workspace.
- Backlog items created: None.
- Next session goal: Re-run FY24 and FY25 stage-level Business Understanding and Business Intelligence once provider connectivity is restored, then verify refreshed persisted classification artifacts and downstream module selection from the canonical pipeline.

## 2026-07-06

- Date: 2026-07-06
- Sprint: IP Library / Platform Monetization Archetype Support
- What was completed: Extended the canonical business classifier with a new archetype family for catalogue/IP-led and platform-monetized businesses, adding reusable registry signals for content libraries, rights monetization, streaming/platform distribution, and owned-channel audience monetization. Added matching module-selection support so the resulting DNAs load the existing `technology` module, added focused classifier tests for varied wording, and directly verified that the existing `tips fy24` blueprint now classifies to `IP Library`, `Platform Monetization`, and `Export` while `polymatech fy24/fy25` behavior remains intact.
- Important decisions: No architecture changes were made; the classifier stays deterministic and registry-driven, and the new support is archetype-based rather than Tips-specific. Live pipeline reruns for Tips and Polymatech were attempted but remained externally blocked by current OpenAI connectivity failures before artifact regeneration could complete.
- Backlog items created: None.
- Next session goal: Re-run `business_understanding` and `business_intelligence` for Tips and Polymatech once provider connectivity is restored, then confirm refreshed persisted classification and BI artifacts from the canonical pipeline.

## 2026-07-06

- Date: 2026-07-06
- Sprint: Generic IP Library / Platform Module Families
- What was completed: Added two reusable question-module families, `library_economics` and `platform_dependency`, for businesses that monetize owned/licensed content or other reusable IP across digital platforms and audience channels. Wired `IP Library` and `Platform Monetization` DNAs to these modules through the existing planner/registry path, added focused question-engine tests, and directly verified that the Tips archetype now loads library-monetization, platform-concentration, owned-audience, and enforcement-risk questions while manufacturing flows still load the expected capital-allocation and technology modules.
- Important decisions: No architecture changes were made; the new modules are framed around generic business patterns like catalogue economics, rights monetization, platform dependence, and enforcement risk rather than music-company specifics. Live `tips fy24 --stage business_intelligence` verification was attempted but remained externally blocked by the current OpenAI connectivity issue before the pipeline could regenerate artifacts.
- Backlog items created: None.
- Next session goal: Re-run Tips and other archetype-diverse `business_intelligence` stage executions once provider connectivity is restored, then inspect refreshed BI artifacts from the canonical path.

## 2026-07-06

- Date: 2026-07-06
- Sprint: Classification Module Alignment
- What was completed: Aligned `business_classification.question_modules` with actual canonical planner module IDs by updating classifier registry mappings to emit real module IDs instead of alias-style or non-existent module labels. Direct verification now shows classifier output and planner-loaded modules agree for `tips fy24` (`library_economics`, `platform_dependency`, `technology`) and for `polymatech fy24/fy25` (`capital_allocation`, `technology`), and focused classifier/question-engine/CIM tests pass together.
- Important decisions: No architecture changes were made; the fix treats canonical module IDs as the single naming layer shared across classification, planner, and runtime. Placeholder classifier labels like `Innovation`, `Capex`, `Supply Chain`, `Export`, and `Regulation` are no longer emitted where they did not correspond to actual loaded module families.
- Backlog items created: None.
- Next session goal: Re-run live archetype-diverse `business_understanding` and `business_intelligence` executions once provider connectivity is restored, then confirm persisted classification and BI artifacts reflect the aligned canonical module IDs.

## 2026-07-06

- Date: 2026-07-06
- Sprint: Archetype-Aware Final Summary Prioritization

## 2026-07-09

- Date: 2026-07-09
- Sprint: Investor Panel Reasoning Quality Hardening Phase 1
- What was completed: Strengthened the CIM/PCIM contract for investor reasoning by adding richer analyst-facing PCIM sections for financial strength, governance and incentives, business economics, growth execution, and story-vs-numbers; added structured missing-evidence records; updated doctrine mappings and prompt guidance for Graham, Munger, Buffett, Fisher, and Lynch; added a `pcim` CLI stage alias; and expanded focused contract and investor-panel tests.
- Important decisions: No architecture changes were made; analysts still consume PCIM only, and the richer investor inputs are derived deterministically from CIM and yearly intelligence artifacts rather than from raw documents or new LLM calls.
- Backlog items created: None.
- Next session goal: Re-run live analyst outputs in a network-enabled environment and review whether the stronger PCIM inputs materially improve judgment quality across the panel.
- What was completed: Added deterministic archetype-aware prioritization in the final summary layer so IP-library and platform-monetization businesses now up-rank economically central signals like library scale, licensing, distribution, and audience reach while de-prioritizing low-signal housekeeping items and trivial CWIP placeholders. Also preserved richer business metadata in the final CIM output by resolving stronger report templates and carrying forward broader supporting-module context.
- Important decisions: No architecture changes were made; the improvement stays in final ranking and mapping logic, using existing business DNAs as the prioritization signal rather than company-specific exceptions.
- Backlog items created: None.
- Next session goal: Continue improving archetype coverage in the classifier and downstream planner without introducing company-specific logic.

## 2026-07-06

- Date: 2026-07-06
- Sprint: Software Platform / Compliance Infrastructure Archetype Support
- What was completed: Refined the canonical business classifier so broad software-platform and compliance-infrastructure signals no longer misroute into `Semiconductor`, added new archetype-oriented DNAs for `Enterprise Platform` and `Compliance Infrastructure`, wired those DNAs to the existing `technology` and `platform_dependency` modules, and added focused regression tests covering Tanla-style platform/compliance patterns alongside existing manufacturing and IP-library flows.
- Important decisions: No architecture changes were made; semiconductor detection is now anchored to more hardware-specific evidence, while platform/compliance businesses are classified through reusable signal clusters such as API-led architecture, enterprise communications infrastructure, telco/operator integration, and trust/compliance products.
- Backlog items created: None.
- Next session goal: Re-run Tanla and other archetype-diverse business-understanding and intelligence flows when provider connectivity is practical, then inspect refreshed persisted classification and BI artifacts.

## 2026-07-07

- Date: 2026-07-07
- Sprint: Classifier V2 Step 1
- What was completed: Refactored `knowledge.business_classifier.registry` from a flat keyword-mapping table into an archetype-definition library with explicit archetype definitions, signal bundles, and output defaults, while preserving the existing classifier contract and transitional keyword/text matching behavior. Added compatibility coverage proving legacy custom mappings and legacy `find_matches()` consumers still work, and verified the current Polymatech, Tips, and Tanla classification lanes remain broadly intact under the new structure.
- Important decisions: No architecture changes were made; this is a transitional internal refactor only. Archetype identity is now separated from matching heuristics, but the current rule-based matcher remains in place as a compatibility layer until later Classifier V2 steps.
- Backlog items created: None.
- Next session goal: Use the new archetype-library structure to prepare cleaner candidate selection and matching logic for Classifier V2 Step 2 without expanding keyword sprawl.

## 2026-07-07

- Date: 2026-07-07
- Sprint: Classifier V2 Step 2
- What was completed: Integrated archetype selection into the existing Business Understanding LLM call by adding a cheap local candidate-context builder from `CompanyMemory`, extending the Business Interpreter prompt/response format to return both a Business Blueprint and a constrained classification block, and moving deterministic question-module/profile/template assembly into local classifier finalization based on the LLM-selected DNAs. Added focused interpreter/classifier tests for candidate context, combined response parsing, LLM-selected DNA finalization, and false-positive rejection behavior.
- Important decisions: No architecture changes were made; the Business Understanding call is now the source of truth for archetype selection when it returns classification, while local classifier code remains the canonical deterministic assembler for downstream defaults and provides a backward-compatible fallback when older responses omit classification.
- Backlog items created: None.
- Next session goal: Re-run live `business_understanding` and `business_intelligence` for archetype-diverse companies in an environment where provider/network execution is available, then tune the compact candidate/evidence pack only if real output quality still warrants it.

## 2026-07-07

- Date: 2026-07-07
- Sprint: Classifier V2 Step 3
- What was completed: Upgraded the cheap local pre-LLM classifier layer from basic heuristic matching to explainable candidate scoring and filtering. Added weighted score components for strong text-group matches, supporting keyword-group matches, positive-signal overlap, evidence-pattern overlap, definition overlap, negative-signal penalties, and conflicting-archetype pressure; computed confidence and margin metadata; and filtered weak candidates before they are passed into the existing Business Understanding LLM call. Added focused classifier tests for Polymatech, Tips, and Tanla-style candidate ranking, false-positive suppression, and candidate-context debug metadata.
- Important decisions: No architecture changes were made; no new paid inference step was added, and no local embeddings or semantic-model dependency was introduced. The scorer remains deterministic and cheap, while the existing Business Understanding LLM call continues to be the final constrained judge when classification is returned.
- Backlog items created: None.
- Next session goal: Verify the updated ranked candidate context against live provider-backed `business_understanding` and `business_intelligence` runs, then decide whether Step 4 should focus on richer ambiguity handling, optional local semantic similarity, or prompt-side use of the new candidate score metadata.
- What was completed: Added deterministic archetype-aware prioritization in the final summary layer so IP-library and platform-monetization businesses now up-rank economically central signals like library scale, licensing, distribution, and audience reach while de-prioritizing low-signal housekeeping items and trivial CWIP placeholders. Also preserved richer business metadata in the final CIM output by resolving stronger report templates and carrying forward broader supporting-module context.
- Important decisions: No architecture changes were made; the improvement stays in final ranking and mapping logic, using existing business DNAs as the prioritization signal rather than company-specific exceptions.
- Backlog items created: None.
- Next session goal: Continue improving archetype coverage in the classifier and downstream planner without introducing company-specific logic.

## 2026-07-06

- Date: 2026-07-06
- Sprint: Software Platform / Compliance Infrastructure Archetype Support
- What was completed: Refined the canonical business classifier so broad software-platform and compliance-infrastructure signals no longer misroute into `Semiconductor`, added new archetype-oriented DNAs for `Enterprise Platform` and `Compliance Infrastructure`, wired those DNAs to the existing `technology` and `platform_dependency` modules, and added focused regression tests covering Tanla-style platform/compliance patterns alongside existing manufacturing and IP-library flows.
- Important decisions: No architecture changes were made; semiconductor detection is now anchored to more hardware-specific evidence, while platform/compliance businesses are classified through reusable signal clusters such as API-led architecture, enterprise communications infrastructure, telco/operator integration, and trust/compliance products.
- Backlog items created: None.
- Next session goal: Re-run Tanla and other archetype-diverse business-understanding and intelligence flows when provider connectivity is practical, then inspect refreshed persisted classification and BI artifacts.
- What was completed: Added a deterministic materiality/prioritization layer to the final management summary path so IP-library / platform-monetization businesses now up-rank library scale, release cadence, licensing/platform distribution, and audience-reach signals while down-ranking office-housekeeping / low-signal ESG items and suppressing trivial CWIP placeholder projects. Also added a small final-artifact metadata fallback so `company_intelligence` can preserve stronger `report_template` semantics from business DNAs when a stale upstream classification artifact still says `generic_v1`, and broadened `competitive_position.supporting_modules` to retain the richer module context already known from classification/runtime artifacts.
- Important decisions: No architecture changes were made; the prioritization stays generic and DNA-driven rather than company-specific, and it only changes what gets promoted in the summary layer rather than deleting underlying extracted evidence. Direct Tips verification now shows `media_v1`, no surfaced `Project 1`, richer supporting modules, and focus areas tilted toward content/library/platform economics instead of office housekeeping.
- Backlog items created: None.
- Next session goal: Re-run the full final-intelligence generation chain in a live provider environment and inspect refreshed persisted `management_summary.json` and related downstream artifacts for Tips and a manufacturing-side comparison company.

## 2026-07-07

- Date: 2026-07-07
- Sprint: Classifier V2 Step 4
- What was completed: Added an optional local semantic-similarity layer to the Step 3 business-classifier candidate ranking path by reusing the existing local sentence-transformer embedding stack already present in retrieval. The classifier now builds compact company-signal and archetype-definition texts, computes local semantic similarity when the embedding model is available, applies a capped semantic boost as a secondary score component, and exposes semantic debug metadata plus clean fallback behavior when the layer is disabled or unavailable. Added focused tests for semantic fallback metadata, semantic boost integration, and protection against fuzzy false-positive contamination. Also verified the saved `company_memory` artifacts for `polymatech fy24`, `tips fy24`, and `tanla fy25` still rank into their expected archetype lanes with local semantic similarity active.
- Important decisions: No architecture changes were made; no new paid inference call or remote embedding dependency was introduced. Deterministic scoring, anti-signals, and family-support gates remain primary, while local semantic similarity only acts as a bounded ranking assist.
- Backlog items created: None.
- Next session goal: Re-run live provider-backed `business_understanding` and `business_intelligence` flows with the richer candidate pack and inspect whether the semantic layer improves candidate retrieval under vocabulary drift without reintroducing archetype contamination.

## 2026-07-08

- Date: 2026-07-08
- Sprint: Software Platform / Compliance Downstream Alignment
- What was completed: Extended the canonical downstream question-engine path for `Enterprise Platform` and `Compliance Infrastructure` businesses with reusable `platform_economics` and `compliance_infrastructure` module families, updated classifier defaults so software-platform classifications emit those canonical module IDs, and added focused planner/classifier coverage for the richer lane. Also expanded the final-summary prioritization logic with a second archetype-aware profile for software-platform / compliance businesses, reducing CSR/admin/facilities noise and collapsing obvious alias clutter in promoted projects and initiatives. Finally, tightened `knowledge.cim_builder` so final business metadata resolves canonical module IDs from the DNA set even when a saved classification artifact is stale, keeping `company_intelligence.json` aligned with the current planner design.
- Important decisions: No architecture changes were made; the fix stayed deterministic and archetype-based rather than Tanla-specific. Enterprise-platform/compliance businesses now reuse small canonical module families and DNA-driven final-summary weighting instead of relying on generic `technology` only. Live `business_intelligence` rerun from the CLI remained externally blocked in this sandbox by an OpenAI connection error before Business Understanding could complete, so planner verification for Tanla was completed locally from the saved classification artifact while the downstream `intelligence` stage was rerun successfully.
- Backlog items created: None.
- Next session goal: Re-run the full live `business_intelligence` stage in a provider-connected environment, confirm regenerated `discovery_plan.json` / `discovery_runtime.json` with the new software-platform modules, and then decide whether any remaining summary noise should be handled in later downstream theme or focus analyzers.

## 2026-07-08

- Date: 2026-07-08
- Sprint: Generic Materiality Summary Refactor
- What was completed: Removed company-specific keyword bags from `synthesis/management_summary_generator.py` and replaced them with a generic materiality-dimension scorer driven by reusable business dimensions such as `monetization_channel`, `platform_scale`, `customer_embeddedness`, `compliance_trust`, `capacity_expansion`, `capital_deployment`, `product_differentiation`, `operational_reliability`, and low-signal dimensions such as `csr`, `hr`, `facilities`, `admin`, and `governance_boilerplate`. Summary ranking now uses DNA-family weighting profiles plus structural item-type boosts and generic penalties for placeholder projects instead of product names or company-specific regional/channel terms. Also added a short code guardrail comment in `knowledge.question_engine.module` to keep the module library focused on reusable business-question families rather than company/product families, and updated focused summary tests to use generic archetype wording rather than named products. Re-ran the local `intelligence` stage for `polymatech fy24`, `tips fy24`, and `tanla fy25` to verify the downstream summaries still promote business-native items.
- Important decisions: No architecture changes were made; the downstream summary layer remains deterministic and archetype-aware, but it no longer depends on product-name scoring such as specific platforms, channels, geographies, or partner brands. Source-derived business terms may still appear in output because they are part of the extracted evidence, but the ranking logic itself is now generic and materiality-driven.
- Backlog items created: None.
- Next session goal: Decide whether later downstream analyzers such as theme/focus builders should also adopt the same generic materiality dimensions so final output layers stay consistent beyond `management_summary.json`.

## 2026-07-08

- Date: 2026-07-08
- Sprint: Planner / Canonical Module Alignment for Software Platform BI
- What was completed: Fixed the canonical Business Intelligence planning path so it can reuse a saved `business_classification.json`, canonicalize `question_modules` through the question registry, and persist `discovery_plan.json` before runtime execution begins. This removed the stale `technology`-only plan mismatch for Tanla-style software-platform / compliance-infrastructure businesses and brought saved planning artifacts back into line with canonical business-layer modules. Also tightened software-platform summary promotion thresholds in `synthesis/management_summary_generator.py` so promoted focus areas, initiatives, and promises more aggressively filter low-signal CSR, HR, facilities, and admin noise while preserving archetype-native platform/compliance signals. Added focused regression coverage for saved-classification BI planning, Chroma missing-collection recovery, and stronger software-platform summary filtering.
- Important decisions: No architecture changes were made; the canonical source of truth remains the business classification plus registry-driven module derivation, not a separate planner-only mapping. The fix stays generic by using DNA-driven module canonicalization and materiality thresholds rather than Tanla-specific phrases. Local live BI reruns progressed further after the fix, but full runtime verification still depends on heavyweight retrieval/indexing execution in the current environment.
- Backlog items created: None.
- Next session goal: Re-run archetype-diverse `business_intelligence` executions in a provider-and-index friendly environment, confirm refreshed `discovery_runtime.json` contents alongside the already-correct `discovery_plan.json`, and decide whether later summary layers beyond `management_summary.json` need the same tighter software-platform thresholds.

## 2026-07-08

- Date: 2026-07-08
- Sprint: Archetype-Aware Major Promises Prioritization
- What was completed: Tightened `major_promises` ranking in `synthesis/management_summary_generator.py` for software-platform / compliance-infrastructure businesses by splitting promise scoring into primary promise text versus supporting context, reducing the influence of long mixed `source_chunk` text, and adding stronger promise-specific materiality adjustments for technical-control signals versus HR/ESG/admin noise. Expanded the generic materiality dimensions with reusable security, DevSecOps, infrastructure-reliability, onboarding, training, ESG, and governance terms so promise scoring can distinguish business-critical platform assurances from people-policy or sustainability boilerplate without using company-specific phrases. Added focused summary tests for promise contamination from mixed source context and for security/reliability promise promotion, then re-ran `--stage intelligence` for Tanla FY25, Tips FY24, and Polymatech FY24.
- Important decisions: No architecture changes were made; the change remains deterministic and archetype-aware rather than Tanla-specific. Promise ranking now treats direct promise wording as the primary signal and uses surrounding evidence as support, which keeps security/compliance promises prominent while preventing unrelated HR/onboarding text from borrowing platform signal from shared source paragraphs.
- Backlog items created: None.
- Next session goal: Decide whether the same primary-signal-versus-supporting-context split should also be applied to later downstream summarizers that still consume long mixed evidence blocks, especially if future software-platform runs still surface too many internally focused security-training commitments.

## 2026-07-08

- Date: 2026-07-08
- Sprint: Order-Independent Company Memory V1
- What was completed: Added a new deterministic company-level aggregation layer in `knowledge.company_memory.company_layer` that discovers all available `companies/<company>/fy*` folders, sorts them by parsed FY label, tolerates partial or missing yearly intelligence, rebuilds a derived `companies/<company>/company_memory/` folder from scratch, and writes eight structured JSON artifacts including `company_memory_index.json`, `yearly_intelligence_index.json`, `company_cim.json`, `strategy_timeline.json`, `promise_tracker.json`, `risk_evolution.json`, `capital_allocation_timeline.json`, and `entity_registry.json`. Wired a new `company_memory` CLI stage into `pipelines/run_company_pipeline.py`, with support for `python pipelines/run_company_pipeline.py <company> --stage company_memory`, and added focused tests for non-chronological year arrival, missing-year handling, idempotent rebuilds, provenance preservation, and CLI dispatch without a year argument.
- Important decisions: No architecture changes were made to year-level processing; yearly folders remain immutable snapshots, and company memory is rebuildable and order-independent rather than append-only. V1 intentionally stays file-backed and deterministic, reusing existing yearly intelligence/CIM outputs without any new LLM calls or database layers. Entity registry support is heuristic and conservative, derived only from already-generated intelligence artifacts rather than document re-extraction.
- Backlog items created: None.
- Next session goal: Decide whether later company-memory versions should tighten named-entity quality and add smarter cross-year grouping for risks and initiatives, while preserving the same rebuild-from-snapshots architecture.

## 2026-07-09

- Date: 2026-07-09
- Sprint: CIM / PCIM Contract V1
- What was completed: Added a deterministic company-level contract builder in `knowledge/cim_contract.py` that rebuilds `cim_v1.json` and `pcim_v1.json` under `companies/<company>/company_memory/` from the existing company-memory layer plus yearly intelligence artifacts. `cim_v1.json` now captures the cross-year canonical intelligence contract with business DNA, business model, management focus, projects, promises, initiatives, risks, capital allocation, entities, evidence index, source artifact inventory, and missing-data notes. `pcim_v1.json` is derived directly from CIM with panel-oriented sections for business understanding, financial strength, management quality, growth quality, moat, capital allocation, risk, incentive, and simplicity/story inputs, plus deterministic evidence maps back to CIM provenance. Wired a new `cim` CLI stage into `pipelines/run_company_pipeline.py` with support for `python pipelines/run_company_pipeline.py <company> --stage cim`, and added focused tests for CIM generation, PCIM derivation, provenance preservation, missing-section tolerance, deterministic rebuilds, CLI dispatch without a year argument, and no-LLM execution.
- Important decisions: No architecture changes were made; CIM / PCIM remains a file-backed, rebuildable intelligence contract layered on top of existing yearly intelligence and company-memory artifacts. PCIM does not duplicate extraction or call any model APIs; it is a deterministic view derived from CIM so future investor modules can consume stable inputs without reading raw documents directly.
- Backlog items created: None.
- Next session goal: Decide whether later PCIM versions should compress repeated technical-control signals into higher-level investor-ready clusters, while preserving the same provenance-rich deterministic contract.

## 2026-07-09

- Date: 2026-07-09
- Sprint: Investor Doctrine Registry V1
- What was completed: Added a new deterministic doctrine layer under `intelligence/investor_panel/` with a registry loader/validator plus five doctrine definition files for Graham, Fisher, Buffett, Munger, and Lynch. Each doctrine now declares its investor lens, primary focus, canonical principles, canonical questions, required PCIM sections, evidence to ignore or downweight, red flags, uncertainty rules, and output contract. The registry validates that doctrine files are complete, deterministic, PCIM-only, and do not instruct raw-document access. Added focused tests covering required fields, valid PCIM mappings, presence of evidence requirements and uncertainty rules, deterministic load order, and rejection of invalid doctrine files.
- Important decisions: No architecture changes were made; this is a structured doctrine/config layer only, not an investor-judgment engine. The doctrinal source of truth is the accepted architecture/philosophy/constitution documents plus the current PCIM contract, and future investor modules are expected to consume doctrine definitions and PCIM rather than reading disclosures directly.
- Backlog items created: None.
- Next session goal: Build the first actual investor analyst modules as deterministic consumers of doctrine definitions plus PCIM, starting with a small shared module-output contract and one or two doctrine-specific evaluators.

## 2026-07-09

- Date: 2026-07-09
- Sprint: Investor Panel Runner V1
- What was completed: Added a generic deterministic investor-panel runner in `intelligence/investor_panel/runner.py` that loads doctrine definitions plus `pcim_v1.json`, selects only the doctrine-declared PCIM sections, and writes structured analyst outputs plus a `panel_index.json` under `companies/<company>/company_memory/investor_panel/`. Wired a new `investor_panel` CLI stage into `pipelines/run_company_pipeline.py`, with support for `--analyst <doctrine_id>` and `INVESTOR_PANEL_MAX_ANALYSTS`. Added focused tests proving doctrine-driven section consumption, uncertainty on missing PCIM sections, raw-document avoidance, valid output schema, evidence preservation, and CLI dispatch without a year argument. Re-ran the panel for Tanla and verified per-analyst output files for Graham, Fisher, Buffett, Munger, and Lynch.
- Important decisions: No architecture changes were made; the runner is intentionally deterministic and doctrine-driven rather than a freeform LLM reasoner. Investor behaviour is taken from doctrine JSON plus the PCIM evidence map, and the runner never reads raw documents or document-level paths directly. V1 outputs are evidence-backed scaffolds for later specialist modules, not final investment recommendations.
- Backlog items created: None.
- Next session goal: Decide whether the next iteration should introduce doctrine-specific scoring heuristics or a constrained LLM summarization layer on top of the current deterministic panel outputs, while preserving PCIM-only evidence boundaries and provenance.

## 2026-07-09

- Date: 2026-07-09
- Sprint: Investor Panel LLM Reasoning V1
- What was completed: Upgraded `intelligence/investor_panel/runner.py` from deterministic scaffold-only output to doctrine-driven LLM reasoning, with one structured JSON-mode LLM call per analyst over only the doctrine-declared PCIM sections. Added bounded prompt construction from doctrine principles/questions/red flags/output contract plus a filtered PCIM view, validated the returned JSON against the required investor-panel output schema, carried forward only allowed evidence IDs from the selected PCIM evidence map, and added `analysis_mode` plus `reasoning_limits` to the persisted analyst outputs. Kept a dry-run deterministic scaffold lane behind `INVESTOR_PANEL_DRY_RUN=1` that writes separate `_dry_run.json` files so it does not overwrite LLM reasoning artifacts. Added focused tests for doctrine selection, PCIM-only prompt scoping, raw-document isolation, uncertainty handling, rating parsing from LLM output, evidence-ID preservation, invalid JSON failure, dry-run separation, and CLI dispatch.
- Important decisions: No architecture changes were made; investor-panel reasoning still consumes PCIM only and does not read raw documents, extracted chunks, or CIM directly. Rating is no longer derived from section availability heuristics in the live path; it now comes from the analyst-specific LLM output, while schema validation and evidence-ID filtering keep the result bounded to doctrine-declared sections and known PCIM provenance.
- Backlog items created: None.
- Next session goal: Run the upgraded panel against a live provider with real PCIM artifacts, inspect analyst-output quality across Graham/Fisher/Buffett/Munger/Lynch, and decide whether prompt compaction or doctrine-specific output shaping is needed before any committee-synthesis work.

## 2026-07-09

- Date: 2026-07-09
- Sprint: Investor Panel Prompt Compaction
- What was completed: Hardened `intelligence/investor_panel/runner.py` against investor-panel prompt overflows by compacting the doctrine-selected PCIM input before prompt construction. The new compact pack removes raw `source_chunk` fields, compresses `evidence_references` down to compact evidence cards, shrinks `evidence_map` to counts plus sample IDs, applies section/item budgets with env overrides, and iteratively tightens budgets until the prompt fits under the internal prompt-size guard. Added prompt-size logging with analyst, selected sections, approximate char/token counts, and before/after item counts per section. Added focused tests proving compact prompts drop `source_chunk`, preserve allowed `evidence_ids`, stay under budget on oversized synthetic PCIM, keep Munger scoped to doctrine-declared sections, and continue avoiding raw-document access. Real Tanla Munger rerun confirmed the prompt shrank from a raw-shape size of about `1,533,763` characters (`~383k` estimated tokens) to `72,621` characters (`~18k` estimated tokens) before the provider call; the remaining live failure was an external OpenAI connection error rather than context-length overflow.
- Important decisions: No architecture changes were made; the fix stays inside the investor-panel prompt-pack layer and preserves PCIM-only discipline plus evidence-ID traceability. Compacted analyst outputs now append a reasoning-limit note when truncation occurs so downstream consumers know the analyst saw a budgeted PCIM view.
- Backlog items created: None.
- Next session goal: Re-run the compacted investor-panel path in a working provider/network environment, inspect real analyst-output quality after compaction, and decide whether any doctrine-specific compact-view shaping is needed beyond the current generic budgets.
