# Engineering Rules

Purpose: Engineering working agreement for the Prometheus repository.

## Core Rules

1. Architecture before implementation.
2. Read governance before coding.
3. Never create duplicate modules.
4. Every experimental module must have a merge target.
5. Every architectural decision must be reflected in governance.
6. Every completed implementation updates governance.
7. Do not invent architecture.
8. If uncertain, ask for human confirmation or write `Needs Architecture Review`.
9. Do not infer production readiness from file names, tests, or apparent completeness alone.
10. Do not rename, move, or delete modules without an explicit lifecycle decision.

## Governance Rules

- Before modifying code, read the relevant documents in `governance/`.
- New modules must be added to `MODULES.md` or a successor module inventory.
- New pipelines must be added to `PIPELINES.md`.
- New architecture decisions must be recorded in governance before implementation proceeds.
- New experiments must be added to `INTEGRATION_PLAN.md` with a merge target.
- Deferred engineering improvements must be added to `ENGINEERING_BACKLOG.md`.
- Completed implementation work must add a `SESSION_LOG.md` entry.

## Architecture Rules

- Prefer existing canonical modules once canonical ownership is established.
- If two implementations overlap, stop and document the overlap before extending either one.
- If no canonical implementation exists, mark the decision `Needs Architecture Review`.
- Do not use sample scripts as production architecture unless governance explicitly promotes them.
- Do not create a new data contract without documenting its producer, consumer, tests, and lifecycle.

## Testing Rules

- Standalone module tests are required before integration status can be marked complete.
- Integration readiness requires tests at the boundary where the module is consumed.
- Manual diagnostics do not replace pytest coverage.
- External-provider or model-dependent behavior must have deterministic test coverage where feasible.
- Test gaps discovered during implementation must be recorded in governance or backlog.

## Lifecycle Rules

- Every important module should have a lifecycle state from `MODULE_LIFECYCLE.md`.
- Experimental modules must not remain indefinitely without an owner, merge target, and next step.
- Frozen modules accept only documented allowed changes.
- Deprecated modules remain in place until a documented removal decision is made.
- Removed is a lifecycle state, not an ad hoc action.

## Code Change Rules

- Do not modify production code during governance-only phases.
- Do not rename files during governance-only phases.
- Do not move files during governance-only phases.
- Do not delete files during governance-only phases.
- Keep governance-only changes limited to `governance/`.

