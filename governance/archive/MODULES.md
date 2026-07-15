# Knowledge Module Inventory

This inventory covers packages under `knowledge/` and root-level `knowledge/*.py` modules visible in source. Purpose statements are based on filenames, exports, classes, and imports only.

## `knowledge`

- Purpose: PCIM/CIM core API package; `knowledge/__init__.py` exports CIM creation, loading/saving, section updates, entity operations, IDs, and evidence helpers.
- Primary classes: None at package root.
- Primary root modules: `cim.py`, `cim_builder.py`, `cim_schema.py`, `company_knowledge_builder.py`, `constants.py`, `entity_matcher.py`, `evidence.py`, `ids.py`.
- Dependencies: `core.context_paths`, `pipelines.pipeline_context`, `knowledge.constants`, `knowledge.ids`, `knowledge.evidence`, `knowledge.entity_matcher`, standard `json`, `copy`, `datetime`, `collections`, `re`, `difflib`, `sys`, `pathlib`.
- Tests: No direct `tests/knowledge/test_*.py` root package suite found. Related root-level retrieval package test exists at `tests/test_retrieval_package.py`.

## `knowledge.ai`

- Purpose: AI provider abstraction and provider factory.
- Primary classes: `BaseAIProvider`, `AIProviderError`, `AIRateLimitError`, `AIResponseError`, `AITimeoutError`, `GroqProvider`, `MockProvider`, `AIRequest`, `AIResponse`.
- Dependencies: `httpx`, `dotenv`, `os`, `json`, `time`, `typing`, `dataclasses`, `abc`, `pathlib`.
- Tests: `tests/knowledge/ai/test_exceptions.py`, `test_factory.py`, `test_groq.py`, `test_mock.py`, `test_schema.py`.

## `knowledge.business_blueprint`

- Purpose: Business blueprint data model, defaults, and validation.
- Primary classes: `Metadata`, `BusinessUnderstanding`, `BusinessCharacteristic`, `BusinessDNA`, `ReasoningStatement`, `BusinessBlueprint`, `BlueprintValidationError`.
- Dependencies: `dataclasses`, `typing`, package `constants`.
- Tests: `tests/knowledge/business_blueprint/test_business_blueprint.py`.

## `knowledge.business_classifier`

- Purpose: Deterministic classification of business blueprints into discovery/extraction/reporting profiles.
- Primary classes: `BusinessClassifier`, `Registry`, `ClassificationValidationError`.
- Dependencies: `knowledge.business_blueprint`, package `constants`, `registry`, `validator`, `typing`.
- Tests: `tests/knowledge/business_classifier/test_business_classifier.py`; manual diagnostic `tests/manual/test_business_classifier.py`.

## `knowledge.business_interpreter`

- Purpose: Convert company memory into a business blueprint using prompt construction, parsing, and validation.
- Primary classes: `BusinessInterpreter`, `ParserError`, `ValidationError`.
- Dependencies: `knowledge.business_blueprint`, `knowledge.company_memory`, `json`, `datetime`, `typing`.
- Tests: `tests/knowledge/business_interpreter/test_business_interpreter.py`; manual diagnostic `tests/manual/test_business_interpreter.py`.

## `knowledge.business_understanding`

- Purpose: Pipeline stage that loads document evidence, builds/updates company memory, runs business interpretation, and classifies the blueprint.
- Primary classes: `BusinessUnderstandingError`.
- Dependencies: `core.context_paths`, `knowledge.ai`, `knowledge.business_blueprint`, `knowledge.business_classifier`, `knowledge.business_interpreter`, `knowledge.company_memory`, `pipelines.pipeline_context`, `json`, `pathlib`, `typing`.
- Tests: `tests/knowledge/business_understanding/test_business_understanding.py`.

## `knowledge.company_memory`

- Purpose: Company memory schema, merge/update, IDs, persistence, and validation.
- Primary classes: `CurrentState`, `Evidence`, `Event`, `Entity`, `CompanyMemory`, `CompanyMemoryBuilder`.
- Dependencies: `hashlib`, `datetime`, `json`, `pathlib`, `dataclasses`, `typing`, package `constants`, `ids`, `schema`, `updater`.
- Tests: `tests/knowledge/company_memory/test_company_memory.py`; manual diagnostics load company memory in `tests/manual/test_business_classifier.py` and `tests/manual/test_business_interpreter.py`.

## `knowledge.discovery_runtime`

- Purpose: Execute question-engine discovery plans through retrieval and module extraction, merge results, collect statistics, and validate output.
- Primary classes: `_FallbackLLMClient`, `DiscoveryRuntime`, `ModuleMerger`, `ExecutionStatistics`, `DiscoveryResult`, `ValidationError`.
- Dependencies: `knowledge.module_extractor`, `knowledge.question_engine`, `json`, `time`, `dataclasses`, `typing`.
- Tests: `tests/knowledge/discovery_runtime/test_discovery_runtime.py`.

## `knowledge.module_extractor`

- Purpose: Prompt, parse, validate, and represent LLM extraction answers for question modules.
- Primary classes: `ModuleExtractor`, `ModuleAnswer`, `ModuleExtractionResult`, `ParserError`, `ValidationError`.
- Dependencies: `knowledge.question_engine.schema`, `json`, `dataclasses`, `typing`.
- Tests: `tests/knowledge/module_extractor/test_module_extractor.py`.

## `knowledge.question_engine`

- Purpose: Define discovery questions/modules, registry, planner, and validation.
- Primary classes: `Question`, `QuestionModule`, `DiscoveryPlan`, `QuestionPlanner`, `QuestionRegistry`, `QuestionEngineValidationError`.
- Dependencies: `dataclasses`, `typing`, package `constants`, `module`, `schema`, `validator`.
- Tests: `tests/knowledge/question_engine/test_question_engine.py`.

## `knowledge.retrieval`

- Purpose: Load clean chunks, embed/index them, perform BM25 and hybrid retrieval, and validate retrieval results.
- Primary classes: `BM25`, `_InMemoryCollection`, `ChunkIndexer`, `HybridRetriever`, `RetrievedChunk`, `RetrievalResult`.
- Dependencies: `chromadb`, `sentence_transformers`, `json`, `math`, `os`, `pathlib`, `re`, `collections`, `dataclasses`, `typing`, package `constants`, `schema`, `loader`, `indexer`, `bm25`, `hybrid`.
- Tests: `tests/test_retrieval_package.py`; manual diagnostic `tests/manual/test_retrieval_foundation.py`.

