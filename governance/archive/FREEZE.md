# Freeze Notes

This audit does not impose a code freeze. It records areas where governance review may be useful before production changes.

## Freeze Candidates

- Pipeline entry points: `pipelines/run_company_pipeline.py`, `run_business_pipeline.py`, `knowledge/business_understanding/pipeline.py`.
- Retrieval foundation: `knowledge/retrieval/*`, because it depends on external vector/embedding libraries and is used by end-to-end discovery.
- AI provider layer: `knowledge/ai/*`, because it controls provider selection, API behavior, and error mapping.
- Business model contracts: `knowledge/business_blueprint/*`, `knowledge/company_memory/*`, `knowledge/question_engine/*`, `knowledge/module_extractor/*`, `knowledge/discovery_runtime/*`.

## Rationale

- These modules are covered by tests and/or imported by orchestration code.
- Multiple overlapping workflows exist, so changing one pipeline without clarifying its status could create drift.

## Confirmation

Needs human confirmation.

