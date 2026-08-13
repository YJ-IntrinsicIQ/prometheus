# Capacity Evolution Intelligence

Capacity Evolution is the canonical company-memory stream for productive capability.

It answers:

- what capacity was planned
- why it was needed
- whether it was funded
- whether it was built or commissioned
- whether it became operational
- whether it was utilized
- whether any economic effect is visible
- whether investor conviction should change

This stream is intentionally conservative.

It is not an asset register.
It is not a project dashboard.
It does not infer utilization from commissioning.
It does not infer economic success from capex alone.
It does not call an LLM.

## Canonical outputs

The stream writes:

- `companies/<company>/company_memory/capacity/capacity_registry.json`
- `companies/<company>/company_memory/capacity/capacity_timelines.json`
- `companies/<company>/company_memory/capacity/capacity_assessments.json`
- `companies/<company>/company_memory/capacity/capacity_validation.json`
- `companies/<company>/company_memory/capacity/capacity_manifest.json`

## Inputs

The builder reads existing company-memory evidence only, especially:

- `clean_capacity.json`
- `clean_projects.json`
- `company_intelligence.json`
- `management_summary.json`
- Projects Intelligence outputs
- Management Commitments outputs
- company-memory financial truth, when present

## Progression

Capacity uses the shared `intelligence/progression` kernel to keep chronology, deduplication, state transitions, turning points, unresolved questions, and confidence consistent across streams.

## Validation

Validation checks for:

- unique ids
- valid chronology
- valid state transitions
- explicit installation, commissioning, operational, and utilization evidence where needed
- valid project and commitment links
- visible unresolved questions
- no internal pipeline terminology in public fields

