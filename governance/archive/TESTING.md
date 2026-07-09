# Testing Inventory

## Pytest Suites

- `tests/knowledge/ai/test_exceptions.py`
  - Tests AI exception inheritance/base behavior.
- `tests/knowledge/ai/test_factory.py`
  - Tests default provider selection, mock provider configuration, Groq provider configuration, and unknown provider rejection.
- `tests/knowledge/ai/test_groq.py`
  - Tests Groq provider API key handling, construction from environment, JSON-mode payload, timeout mapping, rate-limit mapping, and malformed JSON handling.
- `tests/knowledge/ai/test_mock.py`
  - Tests predefined mock responses.
- `tests/knowledge/ai/test_schema.py`
  - Tests `AIRequest` defaults and `AIResponse` metadata.
- `tests/knowledge/business_blueprint/test_business_blueprint.py`
  - Tests valid blueprint validation and duplicate DNA rejection.
- `tests/knowledge/business_classifier/test_business_classifier.py`
  - Tests deterministic classifier output, custom registry mappings, and duplicate DNA validation rejection.
- `tests/knowledge/business_interpreter/test_business_interpreter.py`
  - Tests interpreter blueprint construction, parser malformed JSON rejection, duplicate characteristic rejection, and prompt content.
- `tests/knowledge/business_understanding/test_business_understanding.py`
  - Tests artifact persistence, business-intelligence stage persistence, and pipeline ordering before discovery.
- `tests/knowledge/company_memory/test_company_memory.py`
  - Tests builder adds entities, events, and evidence.
- `tests/knowledge/discovery_runtime/test_discovery_runtime.py`
  - Tests runtime execution/statistics, registry module resolution, and running without a retriever.
- `tests/knowledge/module_extractor/test_module_extractor.py`
  - Tests parser acceptance of valid payload and extractor use of LLM response.
- `tests/knowledge/question_engine/test_question_engine.py`
  - Tests deterministic plan building, data-driven registry extension, duplicate question merge behavior, duplicate question rejection, invalid module/priority rejection, and duplicate module rejection.
- `tests/scripts/test_smart_chunker.py`
  - Tests `chunk_pages` persists `clean_chunks.json`.
- `tests/test_retrieval_package.py`
  - Tests loading chunks from outputs and retriever returns results.

## Manual Tests

- `tests/manual/test_ai_provider.py`
  - Manual provider smoke test; expects exact response text `Hello Prometheus`.
- `tests/manual/test_business_classifier.py`
  - Manual verification for business classification using `companies/tips/2024/intelligence` artifacts.
- `tests/manual/test_business_interpreter.py`
  - Manual verification for business interpreter using real AI via Groq; writes `business_blueprint.generated.json` and debug artifacts.
- `tests/manual/test_retrieval_foundation.py`
  - Manual retrieval diagnostic using real loader, embeddings, Chroma indexing, semantic search, BM25, and hybrid retrieval.

## Other Test-Like Files

- `test_ai.py`
  - Root-level script importing `get_llm`; contains no pytest test functions.

## ADR References

- No ADR references found by repository-wide search for `ADR`, `Architecture Decision`, `decision record`, or `adr-`.

## Test Coverage Gaps From Inventory

- `knowledge/cim.py`, `knowledge/cim_builder.py`, `knowledge/cim_schema.py`, `knowledge/company_knowledge_builder.py`, `knowledge/entity_matcher.py`, `knowledge/evidence.py`, and `knowledge/ids.py` do not have obvious direct pytest files under `tests/knowledge/`.
- Top-level orchestration scripts are partially covered through `tests/knowledge/business_understanding/test_business_understanding.py`, but direct CLI behavior for `pipelines/run_company_pipeline.py` and `run_business_pipeline.py` is not listed as a dedicated suite.
- Needs human confirmation.

