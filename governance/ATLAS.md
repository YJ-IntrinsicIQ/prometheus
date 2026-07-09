# Atlas

Single Source of Truth for Prometheus engineering sessions. Read this before development work.

## 1. Project Overview

Prometheus is a Python finance intelligence repository centered on the `knowledge/` package. It ingests company documents, creates company memory and business understanding artifacts, plans discovery questions, retrieves supporting chunks, and produces intelligence outputs.

Atlas governs engineering work: architecture first, no duplicate modules, and governance updates when implementation changes architecture or module status.

## 2. Current Phase & Sprint

- Phase: Atlas architecture review.
- Sprint: Architecture Review Round 1.
- Rule: Documentation-only work unless a later sprint explicitly authorizes production code changes.

## 3. Canonical Architecture

Canonical architecture, summarized:

1. Company/year context is created.
2. Raw documents are read and chunked by `scripts/smart_chunker.py`.
3. Company memory is built.
4. Business blueprint is interpreted.
5. Business classification is produced.
6. Discovery questions are planned.
7. `knowledge/retrieval` provides supporting chunks.
8. Discovery runtime executes module extraction.
9. CIM / PCIM intelligence artifacts are written.

Artifact roles:

- CIM / PCIM: canonical intelligence contract.
- `company_memory`: transient runtime artifact.
- `business_blueprint`: reasoning artifact.
- `business_classification`: classification artifact.

## 4. Canonical Pipelines

- Production pipeline: `pipelines/run_company_pipeline.py`.
- Business-understanding stage: `knowledge/business_understanding/pipeline.py`.
- Experimental pipeline: `run_business_pipeline.py`.
- Merge target: validated work from `run_business_pipeline.py` merges into `pipelines/run_company_pipeline.py`.

## 5. Canonical Modules

| Module | Status |
| --- | --- |
| `knowledge.ai` | Testing |
| `knowledge.company_memory` | Integrated |
| `knowledge.business_blueprint` | Integrated |
| `knowledge.business_interpreter` | Integrated |
| `knowledge.business_classifier` | Integrated |
| `knowledge.question_engine` | Integrated |
| `knowledge.retrieval` | Production |
| `knowledge.module_extractor` | Integrated |
| `knowledge.discovery_runtime` | Integrated |
| `knowledge.business_understanding` | Integrated |
| `knowledge.cim*` / PCIM helpers | Production |
| `scripts.smart_chunker` | Production |
| `scripts/chunker.py` | Deprecated |
| `run_business_pipeline.py` | Development |
| `scripts/embed.py` | Development |
| `scripts/chunk_and_embed.py` | Development |
| `scripts/rag.py` | Development |

`scripts/embed.py`, `scripts/chunk_and_embed.py`, and `scripts/rag.py` are experimental/manual tools only.

## 6. Current Focus

Merge validated experimental pipeline behavior into `pipelines/run_company_pipeline.py` without creating duplicate production paths.

## 7. Current Priorities

1. Plan the merge from `run_business_pipeline.py` into `pipelines/run_company_pipeline.py`.
2. Keep `scripts/smart_chunker.py` as the canonical chunker and avoid extending `scripts/chunker.py`.
3. Treat CIM / PCIM as the canonical intelligence contract.
4. Keep retrieval work inside `knowledge/retrieval`.
5. Add versioning for all AI prompts and AI output schemas before breaking changes.

## 8. Known Architectural Debt

- `run_business_pipeline.py` contains validated behavior that is not yet merged into `pipelines/run_company_pipeline.py`.
- `scripts/chunker.py` remains present but deprecated.
- Experimental embedding/RAG scripts remain as manual tools.
- Prompt and AI output schema versioning still needs implementation.
- Breaking-change version bump rules are approved but not yet enforced in code.

## 9. Active Decisions

- `pipelines/run_company_pipeline.py` is the canonical production pipeline.
- `run_business_pipeline.py` is experimental; validated behavior should merge into the canonical pipeline.
- `scripts/smart_chunker.py` is the canonical chunker; `scripts/chunker.py` is deprecated.
- `knowledge/retrieval` is canonical retrieval; embedding/RAG scripts are experimental/manual tools only.
- CIM / PCIM is the canonical intelligence contract.
- AI prompts and AI output schemas require versioning; breaking changes require version bumps.

## 10. Next Milestone

Prepare the implementation plan for merging validated behavior from `run_business_pipeline.py` into `pipelines/run_company_pipeline.py`.

