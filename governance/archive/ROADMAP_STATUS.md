# Roadmap Status

This file records observed maturity signals only. It does not infer a roadmap beyond repository evidence.

## Appears Implemented With Automated Tests

- AI provider abstraction: `knowledge/ai/*`.
- Business blueprint schema and validation: `knowledge/business_blueprint/*`.
- Business classifier: `knowledge/business_classifier/*`.
- Business interpreter: `knowledge/business_interpreter/*`.
- Business-understanding pipeline stage: `knowledge/business_understanding/*`.
- Company memory: `knowledge/company_memory/*`.
- Discovery runtime: `knowledge/discovery_runtime/*`.
- Module extractor: `knowledge/module_extractor/*`.
- Question engine: `knowledge/question_engine/*`.
- Retrieval package basics: `knowledge/retrieval/*`.
- Smart chunking: `scripts/smart_chunker.py`.

## Appears Implemented As Pipeline Orchestration

- Stage CLI: `pipelines/run_company_pipeline.py`.
- End-to-end document pipeline: `run_business_pipeline.py`.
- Business-understanding stage: `knowledge/business_understanding/pipeline.py`.

## Appears Experimental, Legacy, or Manual

- `scripts/run_pipeline.py`: sample CAPEX chunks.
- `scripts/run_pdf_pipeline.py`: hard-coded CAPEX PDF workflow and stale-looking `extract_text` import.
- `scripts/embed.py` and `scripts/chunk_and_embed.py`: hard-coded local embedding examples.
- `scripts/rag.py`: interactive RAG script using direct Groq/Chroma calls.
- `tests/manual/*`: diagnostic manual verification tools.

## Unknowns

- Which pipeline is canonical for production use. Needs human confirmation.
- Whether CAPEX-only scripts are retained for historical/manual use. Needs human confirmation.
- Whether `company_knowledge.json` and CIM outputs are both active contracts. Needs human confirmation.
- Whether commentary discovery/extraction/cleaning modules are intentionally excluded from `pipelines/run_company_pipeline.py` stages. Needs human confirmation.

