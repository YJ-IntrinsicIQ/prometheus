# Deprecation Inventory

This file does not recommend deletion. It only records duplicate, stale-looking, or unused-looking implementations for human review.

## Duplicate or Overlapping Implementations

- `pipelines/run_company_pipeline.py` and `run_business_pipeline.py`
  - Both orchestrate business understanding plus downstream discovery/intelligence concepts.
  - They differ in input handling, chunking/retrieval integration, and stage coverage.
  - Needs human confirmation.

- `knowledge/business_understanding/pipeline.py` and business-understanding logic inside `run_business_pipeline.py`
  - Both build company memory, business blueprint, and business classification.
  - Needs human confirmation.

- `scripts/chunker.py` and `scripts/smart_chunker.py`
  - Both expose chunking behavior.
  - `scripts/smart_chunker.py` has pytest coverage and persistence/page helpers; `scripts/chunker.py` is used by `scripts/run_pdf_pipeline.py`.
  - Needs human confirmation.

- `scripts/embed.py`, `scripts/chunk_and_embed.py`, and `knowledge/retrieval/embedder.py` / `knowledge/retrieval/indexer.py`
  - All cover embedding/indexing concerns.
  - Script versions use hard-coded sample paths and top-level execution; retrieval package has reusable modules.
  - Needs human confirmation.

- `knowledge/company_knowledge_builder.py` and `knowledge/cim_builder.py`
  - Both aggregate cleaned extraction outputs into intelligence artifacts.
  - The former builds `company_knowledge.json`; the latter builds canonical CIM structures.
  - Needs human confirmation.

- CAPEX-specific flow in `scripts/run_pdf_pipeline.py` / `scripts/run_pipeline.py` and broader discovery/extraction/cleaning stages in `pipelines/run_company_pipeline.py`
  - Both represent extraction workflows, but one is CAPEX-only and one is multi-domain.
  - Needs human confirmation.

## Modules That Appear Unused or Unreferenced

The following are not proven unused. They appeared unreferenced by direct static source imports or appear to be standalone entry points/scripts. Dynamic imports, package exports, CLI usage, and manual usage may exist. Needs human confirmation.

- `knowledge/company_knowledge_builder.py`
- `knowledge/business_understanding/runner.py`
- `scripts/chunk_and_embed.py`
- `scripts/embed.py`
- `scripts/rag.py`
- `scripts/run_pipeline.py`
- `scripts/run_pdf_pipeline.py`
- `scripts/verify_clean_chunks.py`
- `embeddings/index_builder.py`
- `discovery/commentary_discovery.py`
- `extractors/commentary_extractor.py`
- `processors/commentary_cleaner.py`
- `synthesis/theme_intelligence_generator.py`
- `test_ai.py`

## Stale-Looking Evidence

- `scripts/run_pdf_pipeline.py` imports `extract_text` from `scripts.pdf_reader`; `scripts/pdf_reader.py` defines `extract_pages`.
- `scripts/run_pdf_pipeline.py` uses a hard-coded `polymatech.pdf` path.
- `scripts/run_pipeline.py`, `scripts/embed.py`, `scripts/chunk_and_embed.py`, and `scripts/rag.py` execute sample or interactive flows at module top level.

## Confirmation

Needs human confirmation.

