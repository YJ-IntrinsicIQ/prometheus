"""Economic attribution intelligence module.

Canonical outcome and economic attribution layer.
Authority hierarchy:
  - Capital Allocation Outcomes (CAO): allocation taxonomy and attribution
  - Management Progression (MP): execution lifecycle and outcome state
  - Risk Evolution (Gold): risk trajectory and response state
  - Financial Truth Pack: verified financial metrics

Attribution taxonomy (from ENG-122, reused verbatim):
  DIRECTLY_ATTRIBUTABLE      — transaction IS the economic event
  STRONGLY_SUPPORTED         — multiple convergent evidence + explicit outcome signal
  ASSOCIATED_NOT_ATTRIBUTABLE— deployment confirmed; causality unestablished
  NO_OUTCOME_EVIDENCE        — execution exists; relevant outcome evidence absent
  NEGATIVE_OUTCOME           — evidence demonstrates adverse result defensibly
  ATTRIBUTION_UNKNOWN        — insufficient basis to classify

Chronology invariant (ENG-135A): temporal sequence ≠ causal confirmation.
"""

from .builder import build_economic_attribution_intelligence

__all__ = ["build_economic_attribution_intelligence"]
