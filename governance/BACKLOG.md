# Backlog

Future engineering improvements intentionally deferred. This is not a bug list.

| ID | Title | Description | Priority | Module | Status |
| --- | --- | --- | --- | --- | --- |
| ENG-001 | Decide canonical production pipeline | `pipelines/run_company_pipeline.py` is canonical production. `run_business_pipeline.py` is experimental, with validated behavior merging into the canonical pipeline. | High | Pipeline orchestration | Completed |
| ENG-002 | Define canonical chunking interface | `scripts/smart_chunker.py` is canonical. `scripts/chunker.py` is deprecated. | Medium | Chunking utilities | Completed |
| ENG-003 | Define retrieval runtime policy | `knowledge/retrieval` is canonical. `scripts/embed.py`, `scripts/chunk_and_embed.py`, and `scripts/rag.py` are experimental/manual tools only. | Medium | `knowledge/retrieval/` | Completed |
| ENG-004 | Clarify CIM versus company knowledge artifacts | CIM / PCIM is the canonical intelligence contract. `company_memory` is transient runtime, `business_blueprint` is reasoning, and `business_classification` is classification. | Medium | `knowledge/cim*`, `knowledge/company_memory`, `knowledge/business_blueprint`, `knowledge/business_classifier` | Completed |
| ENG-005 | Establish prompt and schema version governance | All AI prompts and AI output schemas require versioning. Breaking changes require version bumps. | Medium | `knowledge.ai`, `knowledge.business_interpreter`, `knowledge.module_extractor` | Completed |
| ENG-006 | Align pipeline tests with explicit context flow | Updated focused pipeline tests to assert explicit `CompanyContext` reuse and fail-fast bundle validation without relying on no-argument monkeypatches. | Medium | `pipelines/run_company_pipeline.py` | Completed |
| ENG-007 | Define default mock behavior for pipeline smoke runs | The canonical business-understanding command uses a deterministic default Business Blueprint fixture when `AI_MOCK_RESPONSE` is not configured. | Medium | `knowledge.ai`, `pipelines/run_company_pipeline.py` | Completed |
| ENG-008 | Align classifier registry with real Business Understanding taxonomy | Real Groq-backed Business Understanding now produces meaningful characteristics, and the classifier registry has been aligned so the richer characteristic vocabulary maps to canonical Business DNAs and question modules. | Medium | `knowledge.business_classifier` | Completed |
| ENG-009 | Wire canonical Business Intelligence stage to evidence retrieval | The canonical Business Intelligence stage now builds and uses the retrieval path during execution, passes retrieved chunks into module execution, and records non-zero retrieval statistics in the canonical runtime flow. | Medium | `pipelines/run_company_pipeline.py`, `knowledge.discovery_runtime`, `knowledge.retrieval` | Completed |
| ENG-010 | Tighten multi-year normalization and linking | `multi_year_memory` now applies deterministic theme, risk, and capital-allocation normalization; deduplicates repeated risk disclosures; preserves compact provenance; and treats missing business-DNA detection more cautiously across years. | Medium | `knowledge.company_memory.multi_year` | Completed |
