# INVESTOR_CERTIFICATION_V2.0 — Human-Readable Contract

**Status**: FROZEN  
**Frozen**: 2026-09-03  
**Phase**: Prometheus Phase 15.2  
**Machine-readable canonical**: `governance/certification/investor_certification_v2.json`  
**Contract SHA-256**: `4769d7f3328e0a54973b2ce396ca5df23ada8bcd8574f1899e2926cb5e56ebb4`  
**Calibration tests**: `tests/certification/test_v2_contract_integrity.py` — 66 passed, 0 failed

> **This document is for human readability only. The canonical source of truth is the JSON file. In case of conflict, the JSON governs.**

---

## Product Claim

Prometheus provides serious long-term investors with reliable, evidence-backed intelligence about companies derived from canonical document processing — enabling informed investor judgment about business model evolution, financial progression, management accountability, material risks, and multi-lens investor analysis. It must show what changed, why it changed, and whether conviction should change as a result.

---

## What This Contract Defines

1. The 25 questions that constitute a certification run
2. The three-tier verdict system (ACCEPTED / PARTIAL / REJECTED)
3. The critical failure taxonomy (auto-detectable + manual-audit)
4. The investor-grade gate formula
5. The grade taxonomy (CERTIFIED → NEAR_CERTIFICATION → DEVELOPING → UNSAFE)
6. The evaluator contract (deterministic Python, no LLM)
7. Evidence boundary and answer generation path
8. Provenance, temporal, and financial causality rules
9. Persistence requirements
10. Immutable freeze commitment

---

## The 25 Questions

| # | Question ID | Domain |
|---|-------------|--------|
| 1 | `what-does-company-do` | Business Understanding |
| 2 | `who-are-the-customers` | Business Understanding |
| 3 | `how-does-it-make-money` | Business Understanding |
| 4 | `are-profits-converting-into-cash` | Financial Intelligence |
| 5 | `what-is-owner-earnings` | Financial Intelligence |
| 6 | `is-working-capital-a-concern` | Financial Intelligence |
| 7 | `are-per-share-economics-improving` | Financial Intelligence |
| 8 | `what-has-management-promised` | Management Accountability |
| 9 | `did-past-claims-come-true` | Management Accountability |
| 10 | `what-projects-are-underway` | Operational Intelligence |
| 11 | `how-is-capacity-changing` | Operational Intelligence |
| 12 | `what-is-management-commentary-saying` | Management Accountability |
| 13 | `how-is-capital-allocated` | Financial Intelligence |
| 14 | `what-incentives-matter` | Management Accountability |
| 15 | `what-can-break-the-thesis` | Risk & Diligence |
| 16 | `which-disclosure-is-missing` | Risk & Diligence |
| 17 | `what-evidence-would-change-the-view` | Risk & Diligence |
| 18 | `what-needs-management-clarification` | Risk & Diligence |
| 19 | `what-should-i-ask-ir` | Risk & Diligence |
| 20 | `what-remains-unresolved` | Risk & Diligence |
| 21 | `what-would-graham-worry-about` | Investor Judgment |
| 22 | `what-would-buffett-focus-on` | Investor Judgment |
| 23 | `where-would-fisher-be-curious` | Investor Judgment |
| 24 | `what-would-munger-avoid` | Investor Judgment |
| 25 | `how-would-lynch-explain-it` | Investor Judgment |

---

## Verdict Taxonomy (3-Tier)

### ACCEPTED
The answer is materially reliable and decision-useful for a serious long-term investor. All applicable semantic checks PASS (N/A checks excluded). No critical failures detected.

### PARTIAL
The answer contains useful and materially correct intelligence, but an important limitation prevents investor-grade acceptance. Hard-floor checks PASS. No critical failures. At least one soft-floor check FAILS.

Typical PARTIAL causes: incomplete chronology, weak financial linkage, material unknown omitted, insufficient source breadth, important investor implication missing.

### REJECTED
The answer is materially unreliable, misleading, or unusable. Caused by: `evidence_backed=FAIL`, `internally_consistent=FAIL`, or any critical failure detected.

---

## Hard vs Soft Floor Checks

| Check | Type | Fail → |
|-------|------|--------|
| `evidence_backed` | **Hard floor** | REJECTED |
| `internally_consistent` | **Hard floor** | REJECTED |
| `specific` | Soft floor | PARTIAL |
| `longitudinal` | Soft floor | PARTIAL |
| `economically_relevant` | Soft floor | PARTIAL |
| `uncertainty_aware` | Soft floor | PARTIAL |
| `non_generic` | Soft floor | PARTIAL |
| `decision_useful` | Soft floor | PARTIAL |

---

## Critical Failure Taxonomy

### Auto-Detectable (CF-A)

| ID | Name | Trigger |
|----|------|---------|
| CF-A001 | Internal contradiction | `internally_consistent` check FAIL |
| CF-A002 | Stale artifact serving wrong data | STALE_ARTIFACT + BAD_EVIDENCE_LINK defects |
| CF-A003 | Pre-2020 event as current project | `what-projects-are-underway` + year pattern 201x |
| CF-A004 | Builder template in user output | BAD_RENDERING + template regex matches |

### Manual Audit Required (CF-M)

| ID | Name |
|----|------|
| CF-M001 | Fabricated material evidence |
| CF-M002 | Promise presented as delivered outcome |
| CF-M003 | Announced project presented as operational |
| CF-M004 | Material contradiction silently resolved |
| CF-M005 | Unsupported financial causality |
| CF-M006 | Future target presented as current fact |
| CF-M007 | Order value treated as recognized revenue |

**Phase 15.3 obligation**: Manual audit pass for all CF-M failures before certification is declared complete.

---

## Investor-Grade Gate

ALL conditions must be met simultaneously:

| Condition | Threshold |
|-----------|-----------|
| ACCEPTED count | ≥ 15 (≥60%) |
| REJECTED count | ≤ 2 |
| Critical failures | = 0 |
| Financial Intelligence domain | ≥ 1 ACCEPTED |
| Management Accountability domain | ≥ 1 ACCEPTED |

Domain floors cannot be averaged away by other domain excellence.

---

## Grade Taxonomy

| Grade | Condition |
|-------|-----------|
| **CERTIFIED** | All investor-grade gate conditions met |
| **NEAR_CERTIFICATION** | 0 CFs + 4/5 gate conditions met |
| **DEVELOPING** | 0 CFs + ≤3/5 gate conditions met |
| **UNSAFE** | Any CF present, OR < 8 ACCEPTED |

---

## Scoring Policy

**NUMERIC_SCORING_ENABLED = NO**

Rationale: The historical non-reproducible baseline (63/100) was lost precisely because its formula was never recorded. V2 deliberately avoids this failure mode. The three-tier verdict + grade taxonomy provides sufficient diagnostic signal for engineering decisions without implying spurious quantitative comparability.

---

## Evaluator Contract

- **Type**: Deterministic Python only — no LLM judge
- **Implementation**: `pipelines/run_investor_acceptance.py`
- **Functions**: `_determine_verdict_v2()`, `_detect_critical_failures_v2()`, `_compute_grade_v2()`
- **Stability**: Fully deterministic — same inputs always produce same verdict
- **No retry**: Not applicable (deterministic evaluator)

---

## Evidence Boundary

- **Canonical source**: `intelligence.ask_intrinsiciq.loader.load_company_memory_sources()`
- **Answer generation**: `intelligence.ask_intrinsiciq.answer_cards.build_answer_for_question()`
- **Side-channel payloads** (permitted): `business_journey.json`, `products_services.json`
- **Forbidden**: Manually curated evidence, custom per-question context, raw unprocessed chunks

---

## Critical Rules

### Temporal Discipline
- Pre-2020 events serving as active projects = CF-A003
- Future target as current fact = CF-M006 (manual audit)

### Financial Causality
- Correlation ≠ attribution
- Order value ≠ recognized revenue
- Announced capacity ≠ operational
- Management expectation ≠ confirmed outcome

### Correct Uncertainty Preservation
An answer that honestly says "insufficient evidence — here is what would be needed" CAN be ACCEPTED. The system must not be penalized for honest uncertainty preservation. Correct uncertainty ≠ universal agnosticism.

---

## Persistence Contract

Certification runs must write to:
```
acceptance_reports/<company>/v2/<run_timestamp>/acceptance_summary_v2.json
acceptance_reports/<company>/v2/<run_timestamp>/question_traces/<question_id>.json
```

Once written, trace files must not be modified. A new run creates a new timestamped directory.

---

## Versioning Rules

| Change Type | Action Required |
|-------------|----------------|
| Documentation correction only | PATCH — hash changes, new baseline NOT required |
| New question or non-breaking addition | MINOR — judgment required on baseline comparability |
| Any change to verdicts, questions, gate, evaluator | MAJOR — new certification ID (V3.0), new baseline required |

**Silent edits are forbidden.** Any change to the contract must produce a hash change.

---

## What This Contract Deliberately Does NOT Define

- Which company to certify first (Phase 15.3 decision)
- Certification frequency or schedule
- What actions are triggered by each grade
- Manual audit SLA for CF-M failures

These are operational decisions left to Phase 15.3 and beyond.

---

## Immutable Freeze Record

```
Certification ID:    INVESTOR_CERTIFICATION_V2.0
Frozen:              2026-09-03
Phase:               Prometheus Phase 15.2
Contract SHA-256:    4769d7f3328e0a54973b2ce396ca5df23ada8bcd8574f1899e2926cb5e56ebb4
Calibration:         66 tests passed, 0 failed
Closure gate:        CERTIFICATION_V2_CONTRACT_FROZEN
```
