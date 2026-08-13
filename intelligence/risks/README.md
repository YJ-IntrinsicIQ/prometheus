# Risk Evolution Intelligence

Canonical company-memory stream for tracking how material business and financial risks evolve over time.

## Purpose

Risk Evolution answers fundamental investor questions about company risk trajectory:

- What risk emerged?
- When did it first appear?
- Why did it emerge?
- Did it intensify, persist, reduce, or resolve?
- What evidence supports the latest assessment?
- What could worsen or disprove the risk?
- Should investor conviction change?

This module is not a static risk register. It interprets risk progression.

## Canonical Outputs

Risk Evolution writes five deterministic artifacts under `companies/<company>/company_memory/risks/`:

- `risk_registry.json` - Normalized risk definitions with canonical fields
- `risk_timelines.json` - Progression events and state transitions over time
- `risk_assessments.json` - Current assessment of each risk and conviction impact
- `risk_validation.json` - Validation report with 25+ checks
- `risk_manifest.json` - Generation metadata and statistics

## Risk Definition

A risk is a condition or uncertainty that could materially weaken:

- business economics
- execution
- cash generation
- balance-sheet resilience
- customer demand
- competitive position
- management credibility
- capital allocation
- regulatory standing
- operational continuity
- investor understanding

Valid risks include:

- customer concentration
- programme dependency
- receivable stress
- inventory build-up
- margin compression
- project delay
- capacity underutilization
- funding dependence
- regulatory dependency
- product obsolescence
- key-person dependence
- supplier concentration
- execution slippage
- aggressive accounting
- contingent liabilities
- capital misallocation
- acquisition-integration risk
- geographic concentration
- currency exposure
- governance concern

Generic risks that are NOT included:

- "The industry is competitive."
- "There may be uncertainty."
- "Growth could slow."

## Canonical Risk Contract

Each risk includes:

```json
{
  "risk_id": "risk_001",
  "risk_name": "Customer concentration from DRDO dependence",
  "normalized_name": "customer concentration drdo",
  "risk_category": "customer",
  "affected_area": "revenue concentration",
  "first_observed_period": "fy22",
  "latest_period": "fy24",
  "current_status": "persistent",
  
  "risk_mechanism": "Company generates majority of revenue from DRDO orders, exposing revenue to policy shifts",
  "progression_summary": "Mentioned across three years with no diversification evidence",
  "what_changed": "No material change in concentration ratio",
  "why_it_changed": "No new diversification initiatives detected",
  
  "conviction_impact": "unchanged",
  
  "materiality": {
    "level": "high",
    "affected_dimensions": ["revenue concentration"],
    "basis": ["persistent across three periods", "revenue >70% from single customer"],
    "limitations": ["exact customer mix not disclosed"]
  },
  
  "mitigations": [
    {
      "mitigation_action": "Pursuing diversification into commercial satellite",
      "announcement_period": "fy23",
      "latest_status": "in_progress",
      "confidence": {"level": "medium"}
    }
  ],
  
  "trigger_conditions": [
    "DRDO budget cut announcement",
    "Loss of a major DRDO contract",
    "Shift to single-source procurement policy"
  ],
  
  "disconfirming_evidence": [
    "Demonstrable revenue diversification outside DRDO",
    "Signed contracts with non-DRDO customers",
    "Revenue concentration ratio declining below 60%"
  ],
  
  "confidence": {
    "level": "high",
    "basis": ["Audited revenue composition", "Repeated annual disclosure"],
    "limitations": ["Customer segmentation not detailed"]
  },
  
  "source_references": [
    {"artifact": "company_intelligence.json", "year": "fy22", "item_id": "RISK_00001"},
    {"artifact": "company_intelligence.json", "year": "fy24", "item_id": "RISK_00001"}
  ]
}
```

## Risk Statuses

Canonical statuses:

- `emerging` - New risk signal detected
- `increasing` - Risk is intensifying
- `persistent` - Risk continues without improvement
- `stable` - Risk level unchanged
- `reducing` - Evidence of improvement
- `mitigated` - Observable mitigation evidence
- `resolved` - Explicit resolution evidence
- `recurring` - Risk was reduced/resolved but has returned
- `contradictory` - Conflicting evidence about risk status
- `unable_to_verify` - Insufficient evidence to assess

Important distinctions:

- Not mentioned again ≠ resolved
- Management reassurance ≠ mitigated
- Mitigation announced ≠ mitigation effective
- Single-period deterioration ≠ persistent risk

## Risk Categories

- `customer` - Customer concentration, order loss
- `financial` - Profitability, earnings, cash flow
- `working_capital` - Receivables, inventory, cash conversion
- `balance_sheet` - Debt, leverage, capital structure
- `operational` - Production, efficiency, supply chain
- `execution` - Project delays, milestone slippage
- `project` - Project-specific risks
- `capacity` - Utilization, bottlenecks
- `regulatory` - Compliance, licensing, standards
- `competitive` - Market share, pricing power
- `technology` - Tech obsolescence, digital transformation
- `product` - Product obsolescence, design
- `supplier` - Supplier concentration, sourcing
- `governance` - Board, management, control
- `management` - Key person, leadership quality
- `capital_allocation` - Investment decisions, ROI
- `acquisition` - M&A integration
- `geographic` - Geographic concentration
- `currency` - FX exposure, devaluation
- `accounting` - Accounting treatment, estimates
- `legal` - Litigation, contingent liabilities
- `other` - Other risks

## Materiality Model

Materiality is assessed transparently based on:

- **Persistence**: Does the risk appear across multiple years?
- **Evidence quality**: Audited, derived, partial, conflicting, or missing?
- **Business impact**: Which critical areas are affected?
- **Concentration**: Does it create concentration exposure?
- **Quantification**: Is there financial impact evidence?

Materiality is NOT a binary "severe/not severe". Instead, it documents:
- What dimensions make the risk material
- What evidence supports that assessment
- What limitations constrain confidence

## Mitigation Model

Mitigation is tracked separately from risk status:

- `announced` - Management disclosed intention
- `in_progress` - Execution underway
- `partially_effective` - Partial evidence of effect
- `effective` - Clear evidence of reduction
- `ineffective` - Mitigation did not reduce risk
- `unable_to_verify` - Insufficient follow-up evidence

Rules:

1. Announced mitigation does NOT automatically reduce risk status
2. Effective mitigation requires observable evidence
3. Management reassurance alone is NOT mitigation evidence
4. Risk may remain persistent while mitigation is underway
5. Multiple mitigation actions may exist for one risk

## Conviction Impact

Conviction impact measures change in investor conviction, not risk change:

- `strengthened` - Risk reduced or resolved with evidence
- `weakened` - Risk intensified or persisted longer than expected
- `unchanged` - Risk stable with no new decision-useful information
- `unclear` - Evidence insufficient or conflicting

## Progression Engine Integration

Risk Evolution uses the shared `intelligence/progression` kernel for:

- Event ordering and deduplication
- State transition validation
- Confidence aggregation
- Turning-point detection
- Timeline construction
- Deterministic serialization

The risk adapter owns:

- Risk-specific event types
- Risk status semantics
- Risk category classification
- Risk materiality assessment
- Mitigation effectiveness
- Investor implication

## Sources and Evidence Hierarchy

Risk Evolution uses existing canonical Company Memory inputs only:

- Yearly company intelligence
- Financial truth registry
- Working-capital analysis
- Management commitments
- Projects Intelligence
- Capacity Evolution
- Capital-allocation records
- Management summaries
- Auditor observations
- Business understanding

Evidence hierarchy (strongest to weakest):

1. Audited financial or legal evidence
2. Explicit operational outcome
3. Repeated multi-period evidence
4. Project or capacity progression evidence
5. Management admission or disclosure
6. Management mitigation statement
7. Inferred risk from structured facts
8. Generic narrative language

## Validation

`risk_validation.json` enforces 25+ rules:

1. Unique risk IDs
2. Non-empty risk names
3. Valid risk categories
4. Valid risk statuses
5. Chronological event ordering
6. First-observed ≤ latest-period
7. Resolved requires evidence
8. Mitigated requires observable evidence
9. Persistent requires multi-period evidence
10. Absence of mention ≠ resolved
11. Management reassurance ≠ mitigation
12. Materiality contains basis and limitations
13. Conviction impact uses investor-conviction meaning
14. Linked IDs validate correctly
15. Source references preserved
16. Trigger conditions for material risks
17. Disconfirming evidence for material risks
18. Confidence contains basis and limitations
19. Investor implication doesn't overstate certainty
20. No generic boilerplate
21. Serialization is deterministic
22. No internal terminology leaks
23. Unresolved questions remain visible
24. Duplicate risks handled conservatively
25. Conviction impact aligned with status

## Non-Responsibilities

This module does NOT:

- Create UI
- Call new LLMs
- Hardcode company-specific risks
- Treat every uncertainty as material risk
- Infer resolution from silence
- Score entire company with one number
- Convert absence of evidence into absence of risk
- Duplicate Financial Truth or Projects logic
- Make investment recommendations

## Files

Core modules:

- `contracts.py` - Data model and canonical enums
- `normalizer.py` - Risk normalization and deduplication
- `classifier.py` - Risk categorization and sanitization
- `progression.py` - Timeline tracking and trajectory analysis
- `materiality.py` - Materiality assessment
- `mitigation.py` - Mitigation tracking and effectiveness
- `validators.py` - 25+ validation rules
- `builder.py` - Main orchestrator
- `manifest.py` - Metadata generation
- `writer.py` - Output serialization
- `paths.py` - File path helpers

## Pipeline Integration

Risk Evolution runs as a company-memory stage:

```bash
python pipelines/run_company_pipeline.py <company> --stage risk_evolution
```

Example:

```bash
python pipelines/run_company_pipeline.py datapatterns --stage risk_evolution
```

The stage reads existing company memory artifacts and writes five canonical outputs under `companies/<company>/company_memory/risks/`.

## Testing

Synthetic fixtures test:

- Company-specific risk signals
- Generic boilerplate exclusion
- Repeated evidence marking
- Stronger evidence marking
- Single-period non-persistence
- Mitigation announcement without risk reduction
- Demonstrated mitigation marking
- Lack of mention as non-resolution
- Explicit resolution
- Risk recurrence
- Management reassurance rejection
- Project/capacity linking
- Commitment linking
- ID validation
- Risk deduplication
- Materiality assessment
- Trigger conditions
- Disconfirming evidence
- Conviction impact semantics
- Chronological consistency
- No raw-document search
- No LLM calls
- Company-generic logic

## Known Limitations

- Risks detected only from existing company memory (no new raw-document search)
- Generic risk-factor boilerplate excluded
- Absence of mention does not imply resolution
- Mitigation requires observable evidence
- Severity (impact × likelihood) not calculated
- Some risks remain unable-to-verify due to upstream gaps
- Cross-stream relationship mapping deferred
