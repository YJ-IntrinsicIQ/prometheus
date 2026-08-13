# Management Quality Synthesis

This module is the canonical company-memory synthesis layer for management quality.

It does not create new upstream intelligence.
It reads the longitudinal memory already built by Prometheus and turns it into a qualitative management-quality view.

The stage answers:

- Does management generally do what it says?
- Does execution improve over time?
- Does management revise plans transparently?
- Does capital allocation look rational?
- Do actions improve per-share economics?
- Are risks handled early?
- Has credibility strengthened, weakened, or stayed mixed?
- What still remains unproven?

## Canonical outputs

The stage writes five artifacts under:

`companies/<company>/company_memory/management_quality/`

- `management_quality_summary.json`
- `management_quality_dimensions.json`
- `management_quality_evidence.json`
- `management_quality_validation.json`
- `management_quality_manifest.json`

## Upstream evidence

The synthesis consumes canonical company-memory sources such as:

- Management Commitments
- Projects Intelligence
- Capacity Evolution
- Risk Evolution
- Management Commentary Evolution
- Capital Allocation Outcomes
- Owner Earnings
- Per-Share Compounding
- Financial Truth

Investor Panel and Committee outputs are downstream consumers. They are never Management Quality evidence.

## Core rule

Do not collapse the evidence into one opaque score.

Prometheus must explain management quality through separate dimensions:

1. execution_discipline
2. capital_allocation_discipline
3. candor_and_consistency
4. strategic_clarity
5. risk_handling
6. owner_alignment
7. adaptability
8. evidence_confidence

Each dimension stays qualitative and evidence-backed.

## Output contract

Public conclusions should remain disciplined:

Question
→ Conclusion
→ Progression
→ Why it matters
→ Evidence
→ Raw numbers, where helpful

## Guardrails

- No LLM call
- No numerical management score
- No buy/sell/hold advice
- No inference of intent without evidence
- No hiding conflict in the evidence
- No downstream panel or committee dependency
- Stale dependency timestamps fail lineage validation
- Missing critical risk or capital-allocation evidence caps conclusions and confidence
- No drift back into a traditional screener
