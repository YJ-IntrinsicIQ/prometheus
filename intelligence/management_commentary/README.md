# Management Commentary Evolution Intelligence

This package builds the canonical company-memory stream for longitudinal management language.

It tracks:

- strategic priorities
- performance explanations
- confidence and caution
- execution language
- shifts in emphasis or specificity
- whether later evidence supports the narrative

The stage is deterministic and LLM-free.

Canonical outputs are written to:

`companies/<company>/company_memory/management_commentary/`

with these artifacts:

- `commentary_themes.json`
- `commentary_timelines.json`
- `commentary_assessments.json`
- `commentary_validation.json`
- `commentary_manifest.json`

The stream intentionally stays separate from management commitments, projects, capacity, and risks. It may link to them, but it does not duplicate them.

