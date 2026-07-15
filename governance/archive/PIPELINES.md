# Pipeline Inventory

Statuses describe what each workflow appears to be from repository evidence. When repository evidence does not prove ownership or operational status, this file says "Needs human confirmation."

## `pipelines/run_company_pipeline.py`

- Appears to be: Production candidate.
- Evidence: CLI with `company`, `year`, and `--stage`; stage registry for `business_understanding`, `discovery`, `extraction`, `cleaning`, and `intelligence`; creates `CompanyContext`; calls current discovery, extractor, processor, and synthesis modules.
- Outputs: Prints raw/extracted/intelligence directories; writes discovery plan/runtime/module result JSON during business intelligence.
- Dependencies: `core.company_context`, `pipelines.pipeline_context`, `knowledge.business_understanding`, `knowledge.discovery_runtime`, `knowledge.question_engine`, `discovery/*`, `extractors/*`, `processors/*`, `knowledge.cim_builder`, `synthesis/*`.
- Confirmation: Needs human confirmation.

## `run_business_pipeline.py`

- Appears to be: Production candidate or newer end-to-end experimental pipeline.
- Evidence: CLI with `company`, `year`, optional raw document path; resolves PDF/TXT input; chunks pages; builds company memory, business blueprint, business classification, retrieval index, discovery plan, and discovery runtime output.
- Outputs: `clean_chunks.json`, `company_memory.json`, `business_blueprint.json`, `business_classification.json`, `discovery_plan.json`, `module_results.json`, `discovery_runtime.json`.
- Dependencies: `scripts.pdf_reader`, `scripts.smart_chunker`, `knowledge.company_memory`, `knowledge.business_interpreter`, `knowledge.business_classifier`, `knowledge.retrieval`, `knowledge.question_engine`, `knowledge.discovery_runtime`.
- Confirmation: Needs human confirmation.

## `knowledge/business_understanding/pipeline.py`

- Appears to be: Production stage.
- Evidence: Imported by `pipelines/run_company_pipeline.py`; has pytest coverage; writes company memory, business blueprint, and business classification.
- Outputs: `company_memory.json`, `business_blueprint.json`, `business_classification.json`.
- Dependencies: `knowledge.ai`, `knowledge.company_memory`, `knowledge.business_interpreter`, `knowledge.business_classifier`, `core.context_paths`, `pipelines.pipeline_context`.
- Confirmation: Needs human confirmation.

## `knowledge/business_understanding/runner.py`

- Appears to be: Thin CLI wrapper for business-understanding stage.
- Evidence: Calls `run_business_understanding()` from the package pipeline.
- Confirmation: Needs human confirmation.

## `scripts/run_pdf_pipeline.py`

- Appears to be: Legacy or stale CAPEX PDF pipeline.
- Evidence: Hard-coded `PDF_PATH = data/annual_reports/polymatech.pdf`; focuses only on CAPEX extraction/consolidation/filtering; imports `extract_text` from `scripts.pdf_reader`, but `scripts/pdf_reader.py` defines `extract_pages`.
- Dependencies: `scripts.pdf_reader`, `scripts.chunker`, `extractors.capex_extractor`, `consolidators.capex_consolidator`, `filters.capex_filter`.
- Confirmation: Needs human confirmation.

## `scripts/run_pipeline.py`

- Appears to be: Experimental sample CAPEX pipeline.
- Evidence: Hard-coded sample chunks at module top level; no CLI; prints raw extraction and merged projects.
- Dependencies: `extractors.capex_extractor`, `consolidators.capex_consolidator`.
- Confirmation: Needs human confirmation.

## `scripts/chunk_and_embed.py`

- Appears to be: Experimental embedding script.
- Evidence: Hard-coded `data/sample.txt`, `chroma_db`, `finance_docs`, `sample_company`, and `year: 2025`; runs at module top level.
- Dependencies: `sentence_transformers`, `chromadb`.
- Confirmation: Needs human confirmation.

## `scripts/embed.py`

- Appears to be: Experimental embedding script.
- Evidence: Hard-coded `data/sample.txt`, `chroma_db`, `finance_docs`, `doc1`; runs at module top level.
- Dependencies: `sentence_transformers`, `chromadb`.
- Confirmation: Needs human confirmation.

## `scripts/rag.py`

- Appears to be: Experimental interactive RAG script.
- Evidence: Interactive `input("Ask a question: ")`; hard-coded Chroma collection `finance_docs`; direct Groq client usage; runs at module top level.
- Dependencies: `dotenv`, `sentence_transformers`, `groq`, `chromadb`.
- Confirmation: Needs human confirmation.

## `scripts/verify_clean_chunks.py`

- Appears to be: Manual verification utility.
- Evidence: Imports `CompanyContext`, sets pipeline context, extracts pages, chunks pages, and verifies clean chunk generation.
- Confirmation: Needs human confirmation.

## `scripts/chunker.py` and `scripts/smart_chunker.py`

- Appears to be: Supporting chunking utilities, not full pipelines.
- Evidence: `scripts/chunker.py` exposes `chunk_text`; `scripts/smart_chunker.py` exposes cleaning, chunking, persistence, and page-chunking helpers; `scripts/smart_chunker.py` has pytest coverage.
- Confirmation: Needs human confirmation.

