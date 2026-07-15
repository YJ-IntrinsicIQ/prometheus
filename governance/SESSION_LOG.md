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

## 2026-07-12

- Date: 2026-07-12
- Sprint: Phase 3.8 Investment Committee Synthesis
- What was completed: Added the first committee-synthesis layer under `intelligence/investor_panel`, including compact analyst-input loading, analyst field validation, a single constrained LLM synthesis call using the approved committee prompts, strict committee-output validation, and a new `committee_synthesis` CLI stage that writes `committee_synthesis.json` from analyst outputs only.
- Important decisions: No architecture changes were made; committee synthesis was added in the existing `intelligence/investor_panel` package rather than creating a duplicate `knowledge/investor_panel` path, and it consumes analyst outputs only without reading raw annual reports, CIM, or PCIM directly.
- Backlog items created: None.
- Next session goal: Validate committee synthesis on a real company run and decide whether the next step is committee-quality tightening or user-facing committee brief rendering.

## 2026-07-10

- Date: 2026-07-10
- Sprint: Investor Briefs V1
- What was completed: Added a user-facing `investor_briefs` stage that reads only investor panel analysis JSON files, writes standalone markdown briefs for Graham, Buffett, Fisher, Munger, and Lynch, and preserves hidden evidence traceability in `brief_index.json`. Added focused tests for internal-term stripping, evidence-id hiding, recommendation-language suppression, missing-analyst tolerance, and CLI dispatch, then verified the stage end to end for `tanla`.
- Important decisions: No architecture changes were made; the brief layer is a pure formatter over analyst outputs and does not read raw documents, CIM, or PCIM directly.
- Backlog items created: None.
- Next session goal: Review whether the current brief tone and sectioning need further polish for broader user-facing output layers.

## 2026-07-10

- Date: 2026-07-10
- Sprint: Investor Panel Embedded Brief Contract
- What was completed: Updated the investor panel LLM contract so analyst outputs now require an embedded `user_facing_brief` alongside internal evidence-backed analysis, extended prompt and validation rules to block internal jargon and evidence IDs from the brief, kept internal evidence preservation intact, and updated the Python-only `investor_briefs` renderer to prefer the embedded brief while remaining backward-compatible with older analyst files. Added focused tests for embedded brief validation, no-LLM rendering, and markdown extraction, then verified the brief stage again for `tanla`.
- Important decisions: No architecture changes were made; the analyst LLM still makes a single call, and the user-facing brief is now part of the same canonical analyst JSON output rather than a second-generation step.
- Backlog items created: None.
- Next session goal: Re-run live investor panel analysts in a connected environment so persisted analyst JSON files are upgraded to the new embedded-brief schema.

## 2026-07-10

- Date: 2026-07-10
- Sprint: Investor Panel Brief Validation Hardening
- What was completed: Updated the investor panel JSON template to show the full combined analyst output shape, tightened `user_facing_brief` validation with analyst-specific titles, forbidden-term checks, recommendation-language blocking, bullet and character limits, and explicit failure messages, and expanded runner tests to cover missing briefs, missing keys, internal-term leakage, evidence-ID leakage, recommendation leakage, and oversized bullet lists. Focused investor-panel suites passed locally.
- Important decisions: No architecture changes were made; validation now fails clearly on unsafe or malformed user-facing brief content rather than attempting silent repair.
- Backlog items created: None.
- Next session goal: Retry a live analyst run once provider connectivity is available and confirm persisted analyst JSON includes the embedded `user_facing_brief`.

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

## 2026-07-11

- Date: 2026-07-11
- Sprint: Multi-Year Company Memory V1
- What was completed: Added a new deterministic `knowledge.company_memory.multi_year` builder that scans `companies/<company>/fy*` in financial-year order, tolerates partial yearly intelligence, and writes eight order-independent artifacts under `companies/<company>/company_memory/multi_year/`: `company_year_index.json`, `business_dna_evolution.json`, `strategy_timeline.json`, `promise_tracker.json`, `risk_evolution.json`, `capital_allocation_timeline.json`, `management_consistency.json`, and `multi_year_index.json`. Wired a new `multi_year_memory` CLI stage into `pipelines/run_company_pipeline.py`, added the stage to the canonical `all` flow after yearly intelligence generation, and added focused tests for year sorting, missing-artifact tolerance, idempotent rebuilds, promise/risk linking, capital-allocation provenance preservation, and no-LLM execution. Real local verification succeeded for `python pipelines/run_company_pipeline.py tanla --stage multi_year_memory`.
- Important decisions: No architecture redesign was introduced; year folders remain immutable yearly snapshots, and multi-year company memory is a derived, rebuildable layer written separately under `company_memory/multi_year/`. V1 stays deterministic and provenance-first, reusing yearly intelligence artifacts plus existing company-level CIM/PCIM files only as optional source references rather than introducing any new model calls or append-only state.
- Backlog items created: `ENG-010` to strengthen deterministic cross-year normalization/linking beyond the current token-overlap heuristics while preserving rebuildability and provenance.
- Next session goal: Decide whether the next multi-year iteration should deepen cross-year grouping for initiatives/strategy themes and then map the richer historical layer into future management-consistency or investor-facing trend analysis without breaking the current deterministic contract.

## 2026-07-11

- Date: 2026-07-11
- Sprint: Multi-Year Normalization & Signal Quality
- What was completed: Hardened `knowledge.company_memory.multi_year` with a deterministic taxonomy layer for strategy themes, risks, and capital allocation; corrected capital-allocation classification so share splits no longer fall under capex and debt mutual fund investments now land under treasury investments; added separate CWIP handling while keeping CWIP-derived capex visible; introduced cautious business-DNA status handling (`continued`, `newly_detected`, `not_detected_this_year`, `possibly_discontinued`) so single-year classification gaps no longer look like true exits; canonicalized strategy/management themes for consistency tracking; deduplicated repeated risks within a year; removed full `source_chunk` carry-forward from multi-year risk outputs in favor of short excerpts; and added basic numeric/severity worsening detection including borrowings-driven liquidity-risk worsening. Re-ran `python pipelines/run_company_pipeline.py polymatech --stage multi_year_memory` and verified the refreshed Polymatech artifacts now show `Export` as `not_detected_this_year` rather than disappeared, classify FY24 share subdivision as `share_split`, classify FY25 debt mutual fund investment as `treasury_investment`, preserve CWIP under both `cwip` and capex context, merge CSR variants into canonical `csr`, and emit non-empty multi-year limitations.
- Important decisions: No architecture changes were made; the upgrade stays fully deterministic, provenance-preserving, and file-backed. The multi-year layer now intentionally prefers cautious status labels and compact evidence summaries over stronger but unsupported historical claims, which keeps it better suited for later investor-panel consumption without adding model calls.
- Backlog items created: None.
- Next session goal: Inspect whether a second deterministic pass should broaden canonical theme coverage for additional manufacturing-side management labels that still fall back to generic normalized IDs, while preserving the current architecture and evidence boundaries.

## 2026-07-11

- Date: 2026-07-11
- Sprint: Multi-Year Taxonomy Extraction
- What was completed: Refactored multi-year theme/risk/capital taxonomy knowledge out of `knowledge.company_memory.multi_year` and into repo-level JSON config under `taxonomies/`, then added a deterministic `TaxonomyLoader` in `knowledge.company_memory.taxonomy` that always loads universal themes and selectively loads domain packs from active Business DNAs. `multi_year.py` now delegates theme normalization, risk-category normalization, and capital-allocation category lookup to the loader instead of carrying domain-specific keyword lists in code. Added domain packs for manufacturing, semiconductor, media/IP, enterprise platform, and compliance infrastructure; added `taxonomy_review_candidates.json` so unknown labels are surfaced for curation instead of being silently converted into fake canonical themes; and verified the canonical Polymatech multi-year run still maps domain-specific labels correctly while keeping semiconductor-specific vocabulary out of the builder itself.
- Important decisions: No architecture changes were made; this is a separation-of-knowledge refactor, not a pipeline redesign. The builder remains deterministic and generic, while taxonomy knowledge is now curated as data so future domains can be expanded without editing multi-year orchestration code.
- Backlog items created: None.
- Next session goal: Review the newly surfaced `taxonomy_review_candidates.json` outputs across companies and decide which unknown labels deserve promotion into universal versus domain-specific packs without weakening the new generic builder boundary.

## 2026-07-11

- Date: 2026-07-11
- Sprint: Project-Level Archetype Registry V1
- What was completed: Replaced the earlier multi-year taxonomy shim with a project-level `knowledge.archetypes` registry and deterministic `ArchetypeRegistry` loader that always activates the universal pack and then resolves additional archetype packs from Business DNA via `knowledge/archetypes/registry.json`. Refactored `knowledge.company_memory.multi_year` to consume the registry for theme normalization, risk normalization, capital-allocation classification, relevant metrics, investor questions, and taxonomy-review capture, while keeping unknown labels explicit in `taxonomy_review_candidates.json`. Added broad-but-shallow archetype packs across manufacturing, semiconductor, media/IP, enterprise-platform, regulated-financial, healthcare, infrastructure, energy, industrial, and materials families so future domains can be activated through config rather than new hardcoded logic. Verified `multi_year.py` no longer contains semiconductor-specific vocabulary, reran `python pipelines/run_company_pipeline.py polymatech --stage multi_year_memory`, and confirmed the canonical nine multi-year artifacts are still generated successfully.
- Important decisions: This is a modest architecture extension, not a redesign: code remains the stable engine, `knowledge/archetypes` becomes the curated business-intelligence registry, and Business DNA decides which packs activate. The previous `knowledge.company_memory.taxonomy.TaxonomyLoader` path is preserved as a compatibility wrapper so the consumer boundary stays stable while the knowledge layer moves out of pipeline code. No LLM calls were added.
- Backlog items created: None.
- Next session goal: Decide which real `taxonomy_review_candidates.json` labels should graduate into universal packs versus domain packs, then let additional consumers beyond `multi_year_memory` reuse the same archetype registry without duplicating domain vocabulary.

## 2026-07-11

- Date: 2026-07-11
- Sprint: Archetype Pack Curation & Field-Aware Matching
- What was completed: Curated the `knowledge.archetypes` packs to improve real multi-year output quality without changing the registry architecture. Expanded `universal/themes.json` with separate `csr`, `energy_efficiency`, `resource_efficiency`, stronger `quality_improvement`, better `capacity_expansion`, and tighter `governance_compliance` coverage; added priority metadata so CSR wins before generic sustainability and governance/control risks win before broad fallbacks. Expanded `capex_heavy_manufacturing`, `electronics_esdm`, and `semiconductor_components` themes so construction, LED/electronics manufacturing, and wafer/component language classify more cleanly. Hardened `universal/risks.json` with explicit `internal_control_risk`, `related_party_risk`, `regulatory_risk`, and `derivative_hedging_risk` coverage plus matching priority. Updated `knowledge.archetypes.registry_loader` so theme/risk/capital matching is field-aware across value/category/status/evidence category rather than raw label only, and updated `knowledge.company_memory.multi_year` to pass that structured context through while restricting borrowings-derived numeric signals to liquidity and rate-sensitive risk lanes. Re-ran `python -m pytest tests/knowledge/company_memory/test_multi_year_memory.py -q` and `python pipelines/run_company_pipeline.py polymatech --stage multi_year_memory`; Polymatech review-candidate count dropped from 13 to 0, CSR now remains distinct from sustainability, capacity/construction labels classify into manufacturing/construction buckets, and borrowings no longer leak into FX or generic market-risk buckets.
- Important decisions: No architecture changes were made; the fix stayed inside curated pack data plus deterministic matching logic in the registry loader. Field-aware matching deliberately uses compact structured context and avoids broad `source_chunk` matching, so the engine remains generic and explainable rather than turning into ad hoc text scraping.
- Backlog items created: None.
- Next session goal: Review whether the now-empty Polymatech taxonomy review queue reflects healthy pack coverage or whether future companies should preserve a small curation queue through narrower universal keywords, then decide which other consumers beyond `multi_year_memory` should start using the same field-aware archetype matching.

## 2026-07-11

- Date: 2026-07-11
- Sprint: Risk Evolution Grouping + Project Theme Inclusion
- What was completed: Tightened `knowledge.company_memory.multi_year` so same-year risk grouping now classifies each risk item primarily from its own category and value rather than from a shared financial-note excerpt, which stopped cross-risk pollution inside the canonical `risk_evolution.json` output. Added bounded risk QA warnings for canonical/value mismatches and numeric-signal leakage, kept borrowings-derived numeric attachment limited to liquidity and explicit rate-sensitive lanes, and improved representative risk-value selection so the carried-forward wording stays inside the correct canonical risk bucket. Also routed `major_projects` through the same archetype normalization path as management focus and initiatives, compacted project evidence into page plus short excerpt form, and made project-derived canonical themes contribute to `strategy_timeline.json`, `management_consistency.json`, and shift detection. Re-ran `python -m pytest tests/knowledge/company_memory/test_multi_year_memory.py -q` and `python pipelines/run_company_pipeline.py polymatech --stage multi_year_memory`; Polymatech FY24 now yields clean separate risk records for `credit_risk`, `liquidity_risk`, `interest_rate_risk`, `foreign_exchange_risk`, `internal_control_risk`, `related_party_risk`, `risk_management_weakness`, and `market_risk`, while FY25 project themes now include `manufacturing_capacity_expansion` and `semiconductor_manufacturing` from the Atal manufacturing-facility projects.
- Important decisions: No architecture changes were made; the fix stayed inside deterministic grouping, validation, and normalization logic already owned by `multi_year_memory`. Project-theme inclusion reuses the existing archetype registry rather than adding a separate project-only classifier, and project evidence remains provenance-preserving while dropping raw `source_chunk` payloads from the derived multi-year artifact.
- Backlog items created: None.
- Next session goal: Decide whether a small additional curation pass should absorb the remaining FY25 project `unclassified_theme` cases like low-energy membrane transitions and employee energy-program labels, while keeping the registry generic and the review queue honest.

## 2026-07-12

- Date: 2026-07-12
- Sprint: Phase 3.5 Multi-Year PCIM Integration
- What was completed: Added a deterministic `knowledge.company_memory.pcim_multi_year_builder` adapter that compacts the existing multi-year company-memory artifacts into a bounded `multi_year_inputs` section inside `pcim_v1.json`. The new PCIM section now carries years covered, cautious business-DNA evolution, management-consistency observations, strategy evolution, promise follow-through, recurring-risk summaries, capital-allocation pattern signals, a compact multi-year evidence map, and carried-forward limitations without copying raw `source_chunk` payloads into PCIM. Wired the builder into `knowledge.cim_contract.CIMContractBuilder`, added focused contract tests for presence, fallback behavior, cautious `not_detected_this_year` handling, recurring-risk evidence preservation, CWIP amount retention, share-split preservation, strategy-shift wording, compactness, and deterministic rebuilds, then verified `python -m pytest tests/knowledge/test_cim_contract.py -q`, `python -m pytest tests/knowledge/company_memory/test_multi_year_memory.py -q`, and `python pipelines/run_company_pipeline.py polymatech --stage pcim`.
- Important decisions: No architecture changes were made; PCIM now consumes multi-year history through a dedicated compact adapter rather than embedding full multi-year JSON or adding new model calls. The integration stays deterministic, provenance-aware, and investor-panel-friendly while keeping multi-year status language cautious when later-year evidence is missing.
- Backlog items created: None.
- Next session goal: Let the investor-panel path start consuming `multi_year_inputs`, then inspect whether any analyst-specific prompt pack needs further compaction or tighter selection once real multi-year history is included.

## 2026-07-12

- Date: 2026-07-12
- Sprint: Phase 3.6 Multi-Year Inputs into Investor Panel
- What was completed: Extended the investor doctrine registry and panel runner so `multi_year_inputs` is now a first-class allowed PCIM section for Graham, Buffett, Fisher, Munger, and Lynch where relevant. Updated doctrine mappings, prompt guidance, compact prompt packing, and output validation so analysts can consume bounded multi-year context without loading raw multi-year JSON files, while preserving `evidence_ids`, `years_covered`, and limitations and continuing to strip `source_chunk` from prompt payloads. Added focused tests for analyst-by-analyst section inclusion, compact multi-year prompt content, evidence preservation, supporting-section validation for `multi_year_inputs`, no raw multi-year file access, optional historical metadata fields, and missing-multi-year tolerance. Verified `python -m pytest tests/test_investor_doctrine_registry.py tests/test_investor_panel_runner.py -q` and `python -m pytest tests/knowledge/company_memory/test_multi_year_memory.py -q`. A live `python pipelines/run_company_pipeline.py polymatech --stage investor_panel --analyst graham` run reached the provider call with the new compact prompt and correct section selection, but failed on external OpenAI connection error; a dry-run rerun succeeded and produced `graham_analysis_dry_run.json` with `multi_year_inputs` present in `supporting_pcim_sections`.
- Important decisions: No architecture changes were made; investor-panel history remains PCIM-only and multi-year data enters only through the compact `multi_year_inputs` contract, not through direct file reads. Historical context is explicitly treated as provisional when only two years are available, and deterministic strategy-shift or `not_detected_this_year` signals are framed cautiously in prompt guidance rather than as confirmed business change.
- Backlog items created: None.
- Next session goal: Re-run a live investor-panel analyst in a provider-connected environment, inspect how real doctrine reasoning uses the new historical context, and decide whether analyst-specific prompt compaction or section-order tuning is needed now that multi-year context is available.

## 2026-07-12

- Date: 2026-07-12
- Sprint: Phase 3.6.1 Analyst Evidence Grounding QA
- What was completed: Added a deterministic evidence-grounding layer for investor-panel outputs in `intelligence.investor_panel.evidence_grounding`. The runner now builds a compact evidence lookup from PCIM, validates cited evidence IDs against claim categories for findings, red flags, uncertainties, and evidence-bearing assessment text, and records `evidence_grounding_status` plus structured `evidence_grounding_warnings` in persisted analyst outputs. Also added prompt-payload QA to block `source_chunk` leakage and ensure multi-year context still comes only from `pcim_v1.json` while preserving `limitations`. Added focused tests for evidence lookup capture, risk/category compatibility rules, missing-ID failure, mixed-evidence warnings, prompt-payload safety, and updated investor-panel runner tests to include the new grounding fields. Verified `python -m pytest tests/knowledge/investor_panel/test_evidence_grounding.py -q`, `python -m pytest tests/test_investor_panel_runner.py tests/test_investor_doctrine_registry.py -q`, and `python -m pytest tests/knowledge/company_memory/test_multi_year_memory.py -q`. A live `python pipelines/run_company_pipeline.py polymatech --stage investor_panel --analyst graham` rerun again reached the provider call but failed on external OpenAI connection error; a dry-run rerun succeeded and produced `graham_analysis_dry_run.json` with `evidence_grounding_status: pass`.
- Important decisions: No architecture changes were made; the new grounding QA is a validator layer on top of the existing PCIM-only panel flow, not a prompt or doctrine redesign. V1 prefers warnings over automatic evidence mutation, except for already-existing supporting-section repair logic, so mismatches are surfaced clearly without silently rewriting analyst reasoning.
- Backlog items created: None.
- Next session goal: Re-run a live analyst once provider connectivity is available and inspect whether real LLM outputs produce any grounding warnings that suggest tighter claim-specific evidence assignment or narrower top-level evidence usage.

## 2026-07-12

- Date: 2026-07-12
- Sprint: Phase 3.6.2 Evidence QA Noise Reduction + Evidence ID Normalization
- What was completed: Reduced investor-panel evidence-grounding noise in `intelligence.investor_panel.evidence_grounding` by adding canonical evidence-ID normalization, lookup aliases for common `company_intelligence` and `business_classification` variants, sentence/claim splitting for broad assessment paragraphs, claim-local evidence matching that ignores unrelated evidence instead of warning on it, uncertainty-aware handling for missing-data claims, and warning dedupe/priority limiting. Updated `intelligence.investor_panel.runner` so saved analyst outputs canonicalize alias evidence IDs before persistence while still preserving normalization warnings during validation. Expanded focused tests for alias resolution, claim splitting, claim-specific compatibility, ignored unrelated evidence, uncertainty-backed missing-data claims, warning cleanup, and canonicalized saved output behavior. Revalidated the existing `companies/polymatech/company_memory/investor_panel/graham_analysis.json` with the new grounding logic, which reduced the warning set from noisy multi-topic false positives to one actionable warning about weak metadata on a business-classification evidence reference.
- Important decisions: No architecture changes were made; the fix stays inside deterministic grounding and output validation rather than changing PCIM, doctrine structure, or analyst prompts. Evidence normalization is permissive for lookup and persistence, but missing IDs still fail, and unrelated evidence is now ignored rather than treated as incompatible support.
- Backlog items created: None.
- Next session goal: Decide whether the remaining weak-metadata warning should be addressed by tightening how governance/compliance claims choose supporting evidence IDs upstream, without widening doctrine scope or loosening the grounding gate.

## 2026-07-12

- Date: 2026-07-12
- Sprint: Phase 3.6.3 Auto-Normalize Analyst Evidence IDs Before Save
- What was completed: Extended the investor-panel save path so analyst evidence IDs are canonicalized against PCIM before grounding validation and persistence. Added reusable structured normalization helpers in `intelligence.investor_panel.evidence_grounding` for evidence-ID lists and inline evidence-ID text, then updated `intelligence.investor_panel.runner` to normalize top-level evidence IDs, per-finding/per-red-flag/per-uncertainty evidence bindings, merged saved evidence IDs, and any inline `ev_...` references in assessment prose when safe. Added a new top-level `evidence_id_normalization` summary to saved analyst outputs with `applied`, `replacements`, and `unresolved_ids`, and kept unresolved IDs visible so real grounding failures still surface instead of being silently dropped. Expanded focused tests for risk/capalloc alias replacement, business-classification alias safety, unresolved-ID preservation, deduped canonical saved IDs, normalization summaries, and the absence of normalization-only warnings after canonical save. Revalidated the existing `companies/polymatech/company_memory/investor_panel/graham_analysis.json` through the new path; its saved evidence IDs are now canonical and the normalization summary records the applied replacements.
- Important decisions: No architecture changes were made; this remains a deterministic validation-and-save refinement inside the existing investor-panel path. Safe normalization only occurs when the canonical ID exists in the PCIM evidence lookup; otherwise the original ID is preserved and can still trigger a real warning or failure.
- Backlog items created: None.
- Next session goal: Decide whether the remaining Graham governance-related warnings should be reduced by narrower evidence selection for integrity/governance claims, or whether the current warnings are the right signal because the cited evidence is still only weakly categorized.

## 2026-07-12

- Date: 2026-07-12
- Sprint: Phase 3.6.4 Strip Inline Evidence Prose + Promise Alias Routing
- What was completed: Tightened `intelligence.investor_panel.evidence_grounding` so inline parenthetical evidence notes like `(supporting evidence: ev_...)` are stripped from claim text before splitting and validation, while inline evidence IDs are still recoverable as a fallback only when no structured evidence binding exists. Extended evidence normalization/allowed-ID handling so canonical promise aliases like `ev_fy24_company_intelligence_prom_00001` and `ev_fy25_company_intelligence_prom_00001/00002` now resolve safely to their `..._json_prom_...` forms when the canonical PCIM IDs exist. Added promise-aware routing rules so promise evidence is ignored for Graham-style liquidity, interest-rate, capex, and downside-protection claims unless the claim explicitly discusses promises, targets, guidance, or follow-through. Expanded focused tests for promise alias normalization, inline evidence stripping, fake-claim prevention, and promise-evidence routing, then revalidated the existing `companies/polymatech/company_memory/investor_panel/graham_analysis.json`; unresolved promise IDs disappeared and the warning set fell to one real governance-evidence mismatch.
- Important decisions: No architecture changes were made; the fix stays inside the deterministic evidence-grounding layer and continues to prefer structured evidence bindings over prose-embedded IDs. Promise evidence remains available for uncertainty/follow-through reasoning, but it is no longer treated as financial support for Graham downside claims by default.
- Backlog items created: None.
- Next session goal: Decide whether the last remaining Graham governance warning should be addressed by improving analyst-side evidence selection for governance/disclosure claims, or preserved as a legitimate signal that the current evidence bundle is still mismatched for that specific claim.

## 2026-07-12

- Date: 2026-07-12
- Sprint: Phase 3.7.1 Cross-Analyst Evidence QA Consistency Patch
- What was completed: Hardened cross-analyst grounding consistency in `intelligence.investor_panel.evidence_grounding` and `intelligence.investor_panel.runner`. Added a status guard so analyst outputs with non-empty `evidence_id_normalization.unresolved_ids` can no longer remain `pass`; they now downgrade to `warning` or `fail` depending on whether unresolved IDs back material findings/assessment text. Improved business-classification alias handling by preferring richer canonical business-understanding DNA evidence over coarser multi-year aliases when both exist, which cleared Lynch’s stale unresolved export-DNA alias. Tightened routing so governance/incentive claims no longer accidentally match on substrings like `conduct` inside `semiconductor`, and capital-allocation/business-quality claims ignore stray risk evidence instead of misrouting it through governance logic. Added more nuanced support rules so Buffett-style business-model evidence is acceptable for business description/understandability, but still only weak support for strong moat claims about pricing power or durable advantage. Expanded focused tests for unresolved-ID status consistency, business-classification alias normalization, governance/risk routing, and Buffett business-model support, then revalidated the saved `lynch_analysis.json`, `munger_analysis.json`, and `buffett_analysis.json` artifacts locally through the updated validator path.
- Important decisions: No architecture changes were made; this remains a deterministic QA/routing refinement inside the existing investor-panel save-and-validate flow. Local artifact refreshes were used for verification because the environment still has intermittent provider/network constraints for live reruns.
- Backlog items created: None.
- Next session goal: Decide whether the remaining Munger and Buffett warnings reflect acceptable evidence-bound caution, or whether the analyst outputs themselves should be nudged to cite cleaner governance/incentive evidence for those specific claims before committee synthesis begins.

## 2026-07-12

- Date: 2026-07-12
- Sprint: Phase 3.8.1 Committee Synthesis Cleanup
- What was completed: Added a deterministic committee-synthesis cleanup pass that canonicalizes committee-level evidence IDs, records an `evidence_id_normalization` summary, recalculates `evidence_quality_notes` directly from saved analyst artifacts, and tags every disagreement with `disagreement_type`. Added `--cleanup-only` support to the `committee_synthesis` stage so an existing `committee_synthesis.json` can be repaired without another LLM call, and tightened moat-language cleanup so Buffett is no longer mislabeled as positive on moat durability when his analysis says the moat is still unproven.
- Important decisions: No architecture changes were made; cleanup stays inside the existing `intelligence/investor_panel` package and operates as deterministic post-processing on analyst outputs plus the saved committee artifact. Committee validation now treats canonical evidence-ID normalization and disagreement typing as part of the contract rather than optional polish.
- Backlog items created: None.
- Next session goal: Run the cleaned committee synthesis on real saved artifacts, then decide whether the next step is committee-level user-facing briefing or tighter synthesis prompt guidance for future first-pass outputs.

## 2026-07-13

- Date: 2026-07-13
- Sprint: Phase 3.8.1A Final Committee Evidence Alias Patch
- What was completed: Extended committee cleanup so committee evidence normalization can safely reuse the canonical PCIM evidence lookup in addition to analyst evidence IDs. This lets committee cleanup resolve management-summary aliases like `ev_fy24_management_summary_init_00007` to `ev_fy24_management_summary_json_init_00007` when the canonical ID exists in the evidence lookup, while still leaving unresolved IDs visible when no safe canonical target exists. Added focused committee tests for safe management-summary alias replacement via PCIM, unsafe alias preservation, and cleanup-only behavior without any LLM call.
- Important decisions: No architecture changes were made; this remains a deterministic post-processing refinement inside committee cleanup and validation. Canonicalization is still conservative: if the canonical ID is absent from analyst evidence, the committee evidence pool, and the PCIM evidence lookup, cleanup records the raw alias under `unresolved_ids` instead of inventing a replacement.
- Backlog items created: None.
- Next session goal: Re-run the real saved committee artifact and confirm evidence normalization is fully clean before moving on to the next committee-facing output layer.

## 2026-07-13

- Date: 2026-07-13
- Sprint: Phase 3.9 Committee Brief Renderer
- What was completed: Added a Python-only committee brief renderer that reads only `committee_synthesis.json`, validates the committee artifact for required structure and forbidden recommendation language, and renders `committee_brief.md` in a fixed investor-facing Markdown structure. Wired a new `committee_brief` CLI stage into `pipelines/run_company_pipeline.py` with optional `--include-evidence-ids` support, and added focused renderer tests covering default rendering, optional evidence-reference inclusion, missing optional evidence-quality notes, forbidden-language rejection, source-chunk rejection, and stage dispatch without any LLM call.
- Important decisions: No architecture changes were made; the renderer was added inside the existing `intelligence/investor_panel` package so committee-facing code stays in one canonical lane instead of creating a parallel `knowledge/investor_panel` stack. Evidence IDs remain hidden by default in the human brief and only appear in an optional final references section when explicitly requested.
- Backlog items created: None.
- Next session goal: Run the renderer on real committee synthesis output, inspect the readability of `committee_brief.md`, and then decide whether the next layer should be richer committee-facing markdown polish or a higher-level final-report assembly step.

## 2026-07-13

- Date: 2026-07-13
- Sprint: Phase 3.10 Committee Brief QA Gate
- What was completed: Added a deterministic committee-brief QA gate in `intelligence/investor_panel/committee_brief_qa.py` that compares `committee_brief.md` directly against `committee_synthesis.json`, checks required section coverage, forbidden recommendation/valuation language, evidence-ID visibility rules, analyst-name validity, and source-fidelity for major committee content. Wired a new `committee_brief_qa` CLI stage into `pipelines/run_company_pipeline.py`, and also made the existing `committee_brief` stage automatically emit `committee_brief_qa.json` after rendering. Added focused tests covering valid brief pass, missing sections, forbidden language, evidence-ID visibility defaults and opt-in allowance, unknown analyst names, missing agreement/risk/question fidelity, synthesis-limit preservation, and stage dispatch without any LLM call.
- Important decisions: No architecture changes were made; the QA gate remains a deterministic validation layer over the existing committee brief and does not rewrite the brief or call models. The gate is intentionally strict in V1: missing major source items, forbidden language, or evidence IDs showing up without the opt-in flag all fail the artifact rather than being softened into warnings.
- Backlog items created: None.
- Next session goal: Run the QA gate on the real committee brief, confirm a clean pass on Polymatech, and then decide whether the next step is stronger markdown polish or a higher-level committee-to-report assembly layer.

## 2026-07-13

- Date: 2026-07-13
- Sprint: Phase 3.11 Panel Run Command
- What was completed: Added a new `panel` stage to `pipelines/run_company_pipeline.py` that orchestrates the full investment-panel chain from PCIM check through five analysts, committee synthesis, committee cleanup, committee brief rendering, and committee brief QA. Added deterministic analyst-output validation, fail-fast stage handling, console summary output, and `panel_run_summary.json` generation with per-stage, per-analyst, and committee status tracking. Hardened the stage so execution exceptions in analyst, synthesis, brief, or brief-QA steps still produce a saved summary artifact before failing. Added focused pipeline tests for parser exposure, missing-PCIM failure, analyst order, fail-fast analyst stop, warning aggregation, committee-QA failure handling, and summary persistence on execution exceptions.
- Important decisions: No architecture changes were made; the new `panel` command is an orchestration layer over the existing canonical investor-panel, committee, and brief stages rather than a new reasoning path. The stage is intentionally strict: analyst execution failures, analyst validation failures, committee cleanup failures, or a non-pass committee brief QA status all stop the run immediately instead of letting later stages continue on a broken chain.
- Backlog items created: None.
- Next session goal: Re-run the full `panel` command in a provider-connected environment, confirm the summary file captures any remaining analyst warnings cleanly, and decide whether the next step is better retry ergonomics or a higher-level report assembly command.

## 2026-07-13

- Date: 2026-07-13
- Sprint: Pipeline Orchestration Audit & Fix
- What was completed: Audited the actual stage dependencies in `pipelines/run_company_pipeline.py` and corrected the canonical `all` orchestration order to `preflight -> discovery -> extraction -> cleaning -> business_understanding -> business_intelligence -> intelligence -> cim/pcim -> multi_year_memory`. Added a fail-fast internal preflight that checks for raw annual-report documents, extractable text, non-empty chunk generation, and a non-zero active company/year retrieval index before discovery runs. Added stage dependency guards for discovery, extraction, cleaning, intelligence, investor panel, committee synthesis, committee brief, and committee brief QA; company-level guards for company-memory/CIM/multi-year stages; `--list-stages` output with dependencies and LLM usage; company-vs-year argument validation; and `run_summary.json` generation for `--stage all`. Added focused orchestration tests for stage order, preflight failure, zero-chunk failure, discovery/extraction/cleaning/intelligence dependency checks, stage listing, company-level year rejection, and one-year multi-year warnings.
- Important decisions: The audit showed `intelligence` depends on Business Understanding and Business Intelligence artifacts to produce a populated business section, so the repo-backed canonical order keeps `intelligence` after those stages rather than moving it earlier. Raw-source support now prefers company/year raw documents when present but still honors the legacy `data/annual_reports` location so the orchestration fix does not force a storage migration.
- Backlog items created: None.
- Next session goal: Re-run the full `all` pipeline in a provider-connected environment, confirm the later stages write fully populated intelligence/CIM artifacts under the new order, and then decide whether any additional empty-artifact status marking should move from orchestration into lower-level stage writers.

## 2026-07-14

- Date: 2026-07-14
- Sprint: Panel Validator Patch - Forbidden-Language Precision
- What was completed: Replaced the blunt forbidden-language substring checks across the investor-panel and committee validation path with a shared phrase-aware matcher in `intelligence.investor_panel.forbidden_language`. The new helper returns structured matches, masks an allowlist of neutral corporate-action phrases such as `offer-for-sale`, `sale of shares`, `QIP`, `equity issuance`, and `capital raising`, and only fails on actual recommendation or valuation language such as `buy this stock`, `recommendation: buy`, `target price`, `undervalued`, or `looks like a buy`. Updated the panel-stage analyst validator, committee synthesis validator, committee brief source validator, committee brief QA gate, and analyst brief validation to reuse the same logic. Added focused regression tests for false-positive corporate-action phrases, true recommendation language, panel-stage continuation with Munger-style `offer-for-sale` wording, committee validator allowlisting, and committee brief QA allowlisting.
- Important decisions: No architecture changes were made; this is a deterministic validator-precision patch inside the existing investor-panel and committee layers. The recommendation guardrail remains strict, but it now keys off recommendation intent and valuation phrasing instead of raw token presence, which avoids false failures on factual disclosure language while preserving hard stops for real investment calls.
- Backlog items created: None.
- Next session goal: Re-run the real `datapatterns --stage panel` flow in a provider-connected environment and confirm the run reaches or passes the old Munger boundary without a forbidden-language false positive, then decide whether any remaining panel failures are genuine evidence/LLM issues rather than validator noise.

## 2026-07-14

- Date: 2026-07-14
- Sprint: Committee Synthesis Validation Order Patch
- What was completed: Split `intelligence.investor_panel.committee_validator.validate_committee_output` into two explicit validation modes: `raw` for first-pass LLM output and `final` for post-cleanup committee artifacts. Raw mode now validates the core committee schema, evidence-id shape, forbidden recommendation/valuation language, and `source_chunk` exclusion without requiring post-cleanup fields like `evidence_id_normalization` or `disagreement_type`. Final mode keeps the strict contract, including `evidence_id_normalization`, `replacements`, `unresolved_ids`, and final disagreement typing. Updated `intelligence.investor_panel.committee_synthesizer` so live synthesis now follows `LLM -> raw validate -> cleanup/normalization -> final validate -> save`, and cleanup-only runs now load the saved artifact, apply cleanup, then final-validate before writing. Added focused regression tests proving raw outputs without normalization pass raw validation but fail final validation, that cleanup adds normalization/disagreement typing before final save, and that unresolved committee aliases now fail final validation instead of slipping through.
- Important decisions: No architecture changes were made; this is a validation-order correction inside the existing committee synthesis path. The final committee artifact remains strict, but the raw LLM response is now judged against the right contract stage instead of being forced to contain cleanup-added fields.
- Backlog items created: None.
- Next session goal: Re-run the full panel in a provider-connected environment so the committee path can be exercised past analyst execution, then confirm the old early `evidence_id_normalization` failure no longer occurs and that any remaining failures are genuine provider/output issues rather than validator ordering.

## 2026-07-14

- Date: 2026-07-14
- Sprint: PCIM Multi-Year Freshness & Source Integrity Patch
- What was completed: Hardened `knowledge.company_memory.pcim_multi_year_builder` so each PCIM build now loads the current company-level multi-year source files directly, derives `multi_year_inputs` fresh from those files, and emits a new top-level `pcim_source_manifest` in `pcim_v1.json`. The manifest records per-file existence/load state, modified time, content hash, detected years, warnings, overall years available, years actually covered in `multi_year_inputs`, missing years, stale-source warnings, and pass/warning/fail status. Expanded the compact multi-year PCIM view to preserve richer yearly DNA status, strategy evolution, promise follow-through, risk evolution, and capital-allocation timeline summaries without leaking `source_chunk`. Added structural PCIM validation in `knowledge.cim_contract` so manifest coverage, missing-year computation, `generated_at`, and `source_chunk` exclusion are checked before save. Updated the investor-panel entrypoint and panel orchestration so PCIM source-manifest failures stop the run clearly, while source-manifest warnings stay visible and allow execution to continue. Added focused synthetic-fixture tests for full year coverage, fresh rebuild pickup after a new year appears, partial-coverage warning behavior, no-source-chunk leakage, and panel-stage handling of source-manifest warning/fail status.
- Important decisions: No architecture changes were made; this remains a deterministic PCIM/build-time integrity patch rather than a doctrine, prompt, or committee-layer change. PCIM still consumes multi-year memory as a derived file-backed source, but it now declares source freshness and partial coverage explicitly instead of silently carrying forward stale or incomplete historical context.
- Backlog items created: None.
- Next session goal: Re-run a real company `--stage pcim` and then `--stage panel` flow on current artifacts to confirm the new manifest surfaces any live multi-year freshness gaps honestly and that analysts are consuming the refreshed historical context as expected.

## 2026-07-14

- Date: 2026-07-14
- Sprint: Business Blueprint / Classification Contract Alignment Patch
- What was completed: Audited the business-understanding path and tightened the contract between `business_blueprint.json` and `business_classification.json` so classification is now the explicit authoritative source of official Business DNA. Added `knowledge.business_identity` with deterministic alignment and validation helpers, updated `knowledge.business_understanding.pipeline` to mirror official classification DNAs into blueprint `dnas` with `dnas_source="business_classification"`, and fail fast on invalid identity contracts. Extended the blueprint schema to carry optional `candidate_dna_signals`, updated the interpreter prompt/validator so candidate DNA signals are produced or safely derived from constrained LLM-selected DNAs, and relaxed blueprint validation so missing standalone blueprint `dnas` no longer breaks a valid run. Hardened `knowledge.business_classifier.classifier` so fallback local classifications still emit rationale and evidence-backed support, preventing valid registry-based classifications from failing the stricter contract. Added `business.identity_manifest` to year-level company intelligence and `business_identity_manifest` to CIM/PCIM so downstream artifacts declare the official DNA source, candidate signals, confidence, and any warnings/failures. Added focused synthetic tests for source-of-truth alignment, conflict detection, empty-classification warning behavior, CIM manifest wiring, and PCIM official-source carry-forward, while updating blueprint/interpreter/business-understanding tests to match the canonical contract.
- Important decisions: No architecture changes were made; this is a contract-and-validation tightening inside the existing business-understanding, CIM, and PCIM flow. Official Business DNA now comes from `business_classification.json`, while blueprint DNA content is mirrored/deprecated metadata only and is not treated as an independent authority downstream.
- Backlog items created: None.
- Next session goal: Re-run a real company `--stage business_understanding`, inspect the saved `business_blueprint.json` and `business_classification.json` pair for clean mirrored DNA alignment and candidate-signal quality, and then confirm downstream CIM/PCIM artifacts surface the new identity manifest clearly on real outputs.

## 2026-07-14

- Date: 2026-07-14
- Sprint: LLM Context Budget & Input Pack Contract
- What was completed: Added a shared deterministic input-pack layer in `knowledge.ai.input_packs` so active production LLM call paths no longer pass large raw artifacts directly. The new helper set builds stage-scoped `LLMInputPack` payloads, strips raw/debug/validation noise, compacts evidence references, estimates prompt size, enforces configurable stage budgets, validates forbidden fields, and appends stage-local `llm_call_manifest` entries after each call. Wired this contract into the canonical extraction path (`core.base_extractor`), Business Understanding interpreter path (`knowledge.business_interpreter` plus `knowledge.business_understanding.pipeline`), Business Intelligence module-extraction path (`knowledge.module_extractor` plus `pipelines/run_company_pipeline.py` runtime adapter), investor-panel analyst path (`intelligence.investor_panel.runner`), and committee synthesis (`intelligence.investor_panel.committee_synthesizer`). Tightened the investor-panel prompt compaction loop so final analyst prompts now shrink against the actual stage token budget instead of only a loose character cap. Added focused synthetic tests for raw-artifact rejection, source-chunk stripping, validation-noise stripping, budget enforcement, generic multi-company pack reuse, investor-panel doctrine-only input selection, committee-synthesis analyst-only isolation, and orchestration/test-fixture compatibility.
- Important decisions: No architecture changes were made; this is a shared prompt-input hygiene layer over existing canonical call sites, not a new reasoning path. The investor-panel and committee prompts now render prompt-safe input-pack views without re-exposing policy internals, while manifests and validation still retain the stricter metadata contract off-prompt.
- Backlog items created: None.
- Next session goal: Run a real provider-backed `business_understanding` and `panel` flow, inspect the generated `llm_call_manifest` files for practical token/cost visibility, and decide whether any stage needs tighter relevance ranking beyond the current deterministic compaction rules.
