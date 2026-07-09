# Current Repository State

This governance audit was generated from repository evidence only. Production code was not modified.

## Summary

- The repository is a Python finance intelligence lab centered on the `knowledge/` package.
- `knowledge/` contains PCIM/CIM helpers, AI provider adapters, business-understanding models, classification, interpretation, discovery planning/runtime, module extraction, company memory, and retrieval.
- The primary orchestration evidence is in `pipelines/run_company_pipeline.py`, `run_business_pipeline.py`, and `knowledge/business_understanding/pipeline.py`.
- Older or script-style workflows also exist under `scripts/`.
- Automated pytest coverage exists for most newer `knowledge/` subpackages.
- Manual diagnostic scripts exist under `tests/manual/`.
- No ADR references were found by repository-wide text search for `ADR`, `Architecture Decision`, `decision record`, or `adr-`.

## Repository Evidence

- Source packages: `knowledge/`, `core/`, `discovery/`, `extractors/`, `processors/`, `synthesis/`, `pipelines/`, `scripts/`, plus supporting `configs/`, `models/`, `filters/`, `consolidators/`, `embeddings/`, and `utils/`.
- Test roots: `tests/knowledge/`, `tests/scripts/`, `tests/manual/`, and `tests/test_retrieval_package.py`.
- Runtime/generated-looking directories or files are present, including `__pycache__/`, `.pytest_cache/`, `debug/`, `hf_cache` references in code, and Chroma/cache references in script code.

## Current State Observations

- `knowledge/__init__.py` identifies the package as "Prometheus Canonical Intelligence Model (PCIM)" and exports core CIM helpers.
- `pipelines/run_company_pipeline.py` provides stage-based CLI orchestration for `business_understanding`, `discovery`, `extraction`, `cleaning`, and `intelligence`.
- `run_business_pipeline.py` provides a separate end-to-end CLI that reads a raw document, chunks it, builds company memory, runs business interpretation/classification, builds retrieval, and runs discovery runtime.
- `knowledge/business_understanding/pipeline.py` implements a reusable business-understanding stage that builds company memory, business blueprint, and business classification.
- Several scripts under `scripts/` are sample/demo-style or older workflows based on their hard-coded paths, top-level execution, or narrower CAPEX/RAG examples.
- `scripts/run_pdf_pipeline.py` imports `extract_text` from `scripts.pdf_reader`, but `scripts/pdf_reader.py` defines `extract_pages`; this is reported as current state only.

## Governance Constraints Applied

- No production code was changed.
- No files were renamed.
- No files were deleted.
- Only documentation files were added under `governance/`.

