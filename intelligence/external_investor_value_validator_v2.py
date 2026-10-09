"""
External Investor Value (EIV) Validator V2 — ENG-MISSION48

Extends EIV V1 (eiv_management_quality.v1) with 8 new semantic parity rules:
  EIV-MQ-09: Trusted Capability Parity — all 5 rich sections present
  EIV-MQ-10: Factual Granularity Parity — commitment DPF beyond total+UTV
  EIV-MQ-11: Evidence Richness Parity — what_evidence_shows >= 2 substantive items
  EIV-MQ-12: Uncertainty Parity — what_is_not_yet_proven names specific items
  EIV-MQ-13: Monitoring Specificity — what_to_monitor has 3 specific named items
  EIV-MQ-14: Management Statement Coverage — what_management_says present and substantive
  EIV-MQ-15: Economic Context Parity — what_may_mean_economically present with financial metric
  EIV-MQ-16: Semantic Regression Gate — >=2 HIGH severity parity failures block PASS

Severity classification: HIGH / MEDIUM / LOW
  HIGH failures (any single HIGH → contribute to EIV-MQ-16 gate):
    EIV-MQ-09, EIV-MQ-11, EIV-MQ-12, EIV-MQ-14
  MEDIUM failures:
    EIV-MQ-10, EIV-MQ-13, EIV-MQ-15
  EIV-MQ-16 triggers FAIL if >= 2 HIGH severity rules fail.

No AI calls. All checks are deterministic.

Design proof:
  M47 candidate (REJECT_RECOMMENDED): HIGH fails = MQ-09, MQ-11, MQ-12, MQ-14 → 4 HIGH → MQ-16 FAIL
  M45.2 candidate (REJECTED): fails most rules → MQ-16 FAIL
  Sun Pharma M37.8 (CERTIFIED): passes all → PASS
  DataPatterns/Tanla/Ujjivan M37.8 (CERTIFIED): passes all → PASS
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from intelligence.external_investor_value_validator import (
    validate_management_answer_eiv as validate_v1,
    EIV_SCHEMA_VERSION as EIV_V1_SCHEMA_VERSION,
    _get_text,
    _has_factual_specificity,
    _verdict,
)

EIV_SCHEMA_VERSION = "eiv_management_quality.v2"
EIV_V2_HIGH_SEVERITY_RULES = {"EIV-MQ-09", "EIV-MQ-11", "EIV-MQ-12", "EIV-MQ-14", "EIV-MQ-18", "EIV-MQ-19"}
EIV_V2_MEDIUM_SEVERITY_RULES = {"EIV-MQ-10", "EIV-MQ-13", "EIV-MQ-15", "EIV-MQ-17"}
EIV_V2_SEMANTIC_REGRESSION_THRESHOLD = 2  # >= 2 HIGH fails → EIV-MQ-16 FAIL

# Patterns for specificity detection
_SPECIFIC_UNCERTAINTY_RE = re.compile(
    r"(fy\d{2,4}|H\d\s*CY\d{2,4}|Q\d\s*FY\d{2,4}|by\s+20\d{2}|in\s+20\d{2}|20\d{2}|"
    r"\d+%|filing|EMA|FDA|USFDA|carbon\s+reduction|supply\s+chain|FX\s|capex|NIM|GNPA|"
    r"revenue\s+share|hard\s+commitment|MC-\d+|platform\s+revenue|specialty\s+revenue)",
    re.IGNORECASE,
)

_POSITIVE_COMMITMENT_MARKERS = re.compile(
    r"\b(hard|delivered|delayed|in.progress|partially|confirmed)\b",
    re.IGNORECASE,
)


def _eiv_mq_09_trusted_capability_parity(answer: Dict) -> Dict:
    """
    EIV-MQ-09 [HIGH]: All five rich investor-facing sections must be present.

    M47 candidate FAILS: all five absent (LLM never generated them under Contract V2).
    All M37.8 trusted artifacts PASS: all five sections present.

    Catching this is the core purpose of EIV V2.
    """
    required_sections = [
        "what_evidence_shows",
        "what_management_says",
        "where_management_was_consistent",
        "management_consistency_map",
        "what_may_mean_economically",
    ]
    missing = []
    for field in required_sections:
        val = answer.get(field)
        if val is None:
            missing.append(field)
        elif isinstance(val, (list, dict)) and len(val) == 0:
            missing.append(field + " (empty)")
        elif isinstance(val, str) and len(val.strip()) < 10:
            missing.append(field + " (trivially short)")

    if missing:
        return {
            **_verdict(False, "EIV-MQ-09",
                f"TRUSTED_CAPABILITY_PARITY FAIL — {len(missing)} of 5 rich sections absent: {'; '.join(missing)}. "
                f"All were present in M37.8. M47 candidate had all 5 absent."),
            "severity": "HIGH",
        }
    return {
        **_verdict(True, "EIV-MQ-09", f"All 5 investor-facing sections present"),
        "severity": "HIGH",
    }


def _eiv_mq_10_factual_granularity_parity(answer: Dict) -> Dict:
    """
    EIV-MQ-10 [MEDIUM]: Management commitments DPF must show status granularity
    beyond just total + single status (e.g., only 'total; N unable to verify').

    M47 FAILS: '46 total; 46 unable to verify' — no delivered/hard/delayed breakdown.
    M37.8 PASSES: '4 hard; 0 confirmed delivered' — two distinct status categories.
    DataPatterns/Tanla PASS: have delivered count, DELAYED count, etc.
    """
    dpfs = answer.get("deterministic_precision_facts", [])
    if not isinstance(dpfs, list):
        return {
            **_verdict(False, "EIV-MQ-10", "deterministic_precision_facts absent — no commitment DPF to check"),
            "severity": "MEDIUM",
        }

    # Find commitment DPF
    commit_dpf = None
    for dpf in dpfs:
        if isinstance(dpf, dict) and "commit" in str(dpf.get("metric", "")).lower():
            commit_dpf = dpf
            break

    if commit_dpf is None:
        return {
            **_verdict(False, "EIV-MQ-10", "No commitment DPF found in deterministic_precision_facts"),
            "severity": "MEDIUM",
        }

    value = str(commit_dpf.get("value", ""))
    if _POSITIVE_COMMITMENT_MARKERS.search(value):
        return {
            **_verdict(True, "EIV-MQ-10", f"Commitment DPF shows granular status: '{value[:80]}'"),
            "severity": "MEDIUM",
        }

    # Also check simple_answer for hard count
    sa = str(answer.get("simple_answer", ""))
    if re.search(r"\b\d+\s+hard\b", sa, re.IGNORECASE):
        return {
            **_verdict(True, "EIV-MQ-10", "simple_answer mentions hard commitment count"),
            "severity": "MEDIUM",
        }

    # If total commitment count is low (<=3), granularity requirement is naturally met
    total_match = re.search(r"^(\d+)\s+(total|tracked)", value, re.IGNORECASE)
    if total_match and int(total_match.group(1)) <= 3:
        return {
            **_verdict(True, "EIV-MQ-10",
                f"Low commitment count ({total_match.group(1)}) — granularity requirement inherently met"),
            "severity": "MEDIUM",
        }

    # Parenthetical detail in DPF value indicates specificity beyond bare total+UTV
    if re.search(r"\(\d+\s+\w+\)", value):
        return {
            **_verdict(True, "EIV-MQ-10", f"Commitment DPF contains specific detail: '{value[:80]}'"),
            "severity": "MEDIUM",
        }

    return {
        **_verdict(False, "EIV-MQ-10",
            f"FACTUAL_GRANULARITY_REGRESSION: commitment DPF shows only total+UTV without "
            f"hard/delivered/delayed breakdown. Value: '{value[:80]}'. "
            f"M37.8 showed '4 hard; 0 confirmed delivered'."),
        "severity": "MEDIUM",
    }


def _eiv_mq_11_evidence_richness_parity(answer: Dict) -> Dict:
    """
    EIV-MQ-11 [HIGH]: what_evidence_shows must have >= 2 substantive entries.

    M47 FAILS: what_evidence_shows absent.
    All M37.8 trusted artifacts PASS: 3 entries each.
    """
    wes = answer.get("what_evidence_shows")
    if wes is None:
        return {
            **_verdict(False, "EIV-MQ-11",
                "what_evidence_shows absent — evidence richness requirement not met. "
                "M37.8 had 3 entries; M47 candidate had 0 (section missing)."),
            "severity": "HIGH",
        }

    if isinstance(wes, list):
        substantive = [e for e in wes if len(str(e).strip()) > 15]
        if len(substantive) >= 2:
            return {
                **_verdict(True, "EIV-MQ-11", f"what_evidence_shows has {len(substantive)} substantive entries"),
                "severity": "HIGH",
            }
        return {
            **_verdict(False, "EIV-MQ-11",
                f"what_evidence_shows has only {len(substantive)} substantive entries (minimum 2). "
                f"M37.8 had 3 entries referencing specific product launches, progression counts, risk signals."),
            "severity": "HIGH",
        }

    if isinstance(wes, str) and len(wes.strip()) > 50:
        return {
            **_verdict(True, "EIV-MQ-11", "what_evidence_shows present as substantive string"),
            "severity": "HIGH",
        }

    return {
        **_verdict(False, "EIV-MQ-11", "what_evidence_shows present but too short to constitute evidence richness"),
        "severity": "HIGH",
    }


def _eiv_mq_12_uncertainty_parity(answer: Dict) -> Dict:
    """
    EIV-MQ-12 [HIGH]: what_is_not_yet_proven must name specific commitments/risks,
    not only abstract generic questions.

    M47 FAILS: raw mq_summary.unresolved — abstract questions without named specifics.
    M37.8 PASSES: names Nidlegy EMA filing H1CY24, 35% carbon reduction, supply chain FX IP.
    """
    winp = answer.get("what_is_not_yet_proven")
    if not winp:
        return {
            **_verdict(False, "EIV-MQ-12",
                "what_is_not_yet_proven absent — uncertainty parity requirement not met"),
            "severity": "HIGH",
        }

    text = _get_text(winp)
    if len(text.strip()) < 20:
        return {
            **_verdict(False, "EIV-MQ-12", "what_is_not_yet_proven too short"),
            "severity": "HIGH",
        }

    if _SPECIFIC_UNCERTAINTY_RE.search(text):
        return {
            **_verdict(True, "EIV-MQ-12",
                "what_is_not_yet_proven contains specific named items (year/filing/risk/metric)"),
            "severity": "HIGH",
        }

    return {
        **_verdict(False, "EIV-MQ-12",
            "UNCERTAINTY_CAPABILITY_REGRESSION: what_is_not_yet_proven contains only generic abstract "
            "questions without named specific commitments, risks, or targets. "
            "M47 pattern: 'Are recurring risks...? Has management explanation...?' "
            "M37.8 pattern: named Nidlegy EMA filing H1CY24, 35% carbon reduction by 2030, "
            "supply chain/FX/IP risks, disclosure pattern observation."),
        "severity": "HIGH",
    }


def _eiv_mq_13_monitoring_specificity(answer: Dict) -> Dict:
    """
    EIV-MQ-13 [MEDIUM]: what_to_monitor must have >= 3 specific named items,
    not bare category labels.

    M47 FAILS: 3 items but 2 are short generic labels ('Industry_outlook' = 16 chars).
    M37.8 PASSES: 4 specific actionable items (avg >30 chars, named products/filings).
    """
    wtm = answer.get("what_to_monitor", [])
    if not isinstance(wtm, list):
        # String format is acceptable if substantive
        text = str(wtm) if wtm else ""
        if len(text.strip()) > 20:
            return {
                **_verdict(True, "EIV-MQ-13", "what_to_monitor present as string"),
                "severity": "MEDIUM",
            }
        return {
            **_verdict(False, "EIV-MQ-13", "what_to_monitor absent or too short"),
            "severity": "MEDIUM",
        }

    if len(wtm) < 3:
        return {
            **_verdict(False, "EIV-MQ-13",
                f"what_to_monitor has only {len(wtm)} items (minimum 3 specific items required)"),
            "severity": "MEDIUM",
        }

    # Check specificity: at least 2 of the items must be substantive (>= 25 chars)
    long_items = [it for it in wtm if len(str(it)) >= 25]
    if len(long_items) >= 2:
        return {
            **_verdict(True, "EIV-MQ-13",
                f"what_to_monitor has {len(wtm)} items, {len(long_items)} are substantive (>=25 chars)"),
            "severity": "MEDIUM",
        }

    return {
        **_verdict(False, "EIV-MQ-13",
            f"what_to_monitor has {len(wtm)} items but only {len(long_items)} are substantive. "
            f"M47 pattern: generic labels like 'Industry_outlook' (16 chars). "
            f"Required: specific named items like 'US specialty revenue share', 'Nidlegy EMA filing'."),
        "severity": "MEDIUM",
    }


def _eiv_mq_14_management_statement_coverage(answer: Dict) -> Dict:
    """
    EIV-MQ-14 [HIGH]: what_management_says must be present and substantive.

    M47 FAILS: absent.
    All M37.8 trusted artifacts PASS: 2 bullets paraphrasing management intentions.
    """
    wms = answer.get("what_management_says")
    if not wms:
        return {
            **_verdict(False, "EIV-MQ-14",
                "what_management_says absent — management statement coverage not present. "
                "M37.8 had 2 bullets on management stated intentions; M47 candidate had none."),
            "severity": "HIGH",
        }

    text = _get_text(wms)
    if len(text.strip()) < 20:
        return {
            **_verdict(False, "EIV-MQ-14",
                "what_management_says too short to constitute meaningful statement coverage"),
            "severity": "HIGH",
        }

    if isinstance(wms, list):
        return {
            **_verdict(True, "EIV-MQ-14", f"what_management_says has {len(wms)} entries"),
            "severity": "HIGH",
        }

    return {
        **_verdict(True, "EIV-MQ-14", "what_management_says present and substantive"),
        "severity": "HIGH",
    }


def _eiv_mq_15_economic_context_parity(answer: Dict) -> Dict:
    """
    EIV-MQ-15 [MEDIUM]: what_may_mean_economically must be present AND contain
    at least one specific financial metric (NPM, margin %, revenue, PAT).

    M47 FAILS: what_may_mean_economically absent; DPF has revenue+PAT but no NPM.
    M37.8 PASSES: has what_may_mean_economically + NPM 19.6% in simple_answer.
    """
    wmme = answer.get("what_may_mean_economically")
    fin_terms_re = re.compile(
        r"\b(NPM|net\s+profit\s+margin|net\s+margin|margin|PAT|EBITDA|ROCE|NIM|"
        r"dividend|compounding|revenue|₹[\d,]+|earnings|returns)\b",
        re.IGNORECASE,
    )

    if wmme and len(_get_text(wmme).strip()) > 30:
        text = _get_text(wmme)
        if fin_terms_re.search(text):
            return {
                **_verdict(True, "EIV-MQ-15",
                    "what_may_mean_economically present with specific financial metric"),
                "severity": "MEDIUM",
            }
        # Present but no specific metric
        return {
            **_verdict(False, "EIV-MQ-15",
                "what_may_mean_economically present but lacks specific financial metric (NPM, margin %, PAT). "
                "M37.8 included NPM 19.6% and specialty margins insight."),
            "severity": "MEDIUM",
        }

    # Check if NPM is in DPF as partial credit (MEDIUM severity stays MEDIUM)
    dpfs = answer.get("deterministic_precision_facts", [])
    if isinstance(dpfs, list):
        for dpf in dpfs:
            if isinstance(dpf, dict) and "NPM" in str(dpf.get("value", "")):
                return {
                    **_verdict(False, "EIV-MQ-15",
                        "what_may_mean_economically absent but NPM present in DPF — partial credit; "
                        "section is still required per Contract V3"),
                    "severity": "MEDIUM",
                }

    return {
        **_verdict(False, "EIV-MQ-15",
            "what_may_mean_economically absent AND no NPM in DPFs — "
            "economic context parity requirement not met"),
        "severity": "MEDIUM",
    }


_INTERNAL_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(_[A-Za-z0-9]+)+$")
_KNOWN_INTERNAL_LABELS = frozenset([
    "industry_outlook", "Industry_outlook", "acquisition", "what_changed",
    "what_to_watch", "overall_view", "thesis_impact",
])
_PROJECTED_CONFIRMED_RE = re.compile(
    r"\bprojected\s+(?:revenue|earnings|profit|pat|sales)\b.*?₹[\d,]+\s*cr|"
    r"₹[\d,]+\s*cr.*?\bprojected\s+(?:revenue|earnings|profit|pat|sales)\b",
    re.IGNORECASE | re.DOTALL,
)


def _eiv_mq_17_generic_evidence_detection(answer: Dict) -> Dict:
    """
    EIV-MQ-17 [MEDIUM]: what_evidence_shows must have at least one substantive item
    with a named metric, ID, date, or specific identifier — not just generic descriptors.

    M49 defect: LLM produced "Management demonstrated operational improvements..."
    (no named initiative, metric, or date). M37.8: named specific projects and outcomes.
    """
    wes = answer.get("what_evidence_shows")
    if not isinstance(wes, list) or not wes:
        return {
            **_verdict(False, "EIV-MQ-17",
                "what_evidence_shows absent or empty — no evidence to check for specificity"),
            "severity": "MEDIUM",
        }

    specific_items = []
    for item in wes:
        text = str(item)
        if _SPECIFIC_UNCERTAINTY_RE.search(text) or _has_factual_specificity(text):
            specific_items.append(text[:60])

    if not specific_items:
        return {
            **_verdict(False, "EIV-MQ-17",
                f"GENERIC_EVIDENCE: all {len(wes)} what_evidence_shows items lack named metrics/IDs/dates. "
                f"First: '{str(wes[0])[:80]}'. Investor-grade evidence must name specifics."),
            "severity": "MEDIUM",
        }
    return {
        **_verdict(True, "EIV-MQ-17",
            f"{len(specific_items)} of {len(wes)} evidence items have specific named metrics/IDs/dates"),
        "severity": "MEDIUM",
    }


def _eiv_mq_18_internal_label_sanitization(answer: Dict) -> Dict:
    """
    EIV-MQ-18 [HIGH]: what_to_monitor must not contain raw internal label strings.

    M49 HIGH defect: what_to_monitor contained "Industry_outlook" (raw mq_summary field name).
    Root cause: fact_pack.py reads mq_summary.interpretation.what_to_watch, which contains
    internal labels. M37.8 certified artifact had no internal labels in what_to_monitor.
    """
    items = answer.get("what_to_monitor")
    if not isinstance(items, list):
        return {
            **_verdict(True, "EIV-MQ-18", "what_to_monitor absent — no internal labels to check"),
            "severity": "HIGH",
        }

    violations = []
    for item in items:
        text = str(item).strip()
        # Check exact known internal labels
        if text in _KNOWN_INTERNAL_LABELS or text.lower() in {x.lower() for x in _KNOWN_INTERNAL_LABELS}:
            violations.append(repr(text))
        # Check snake_case or CamelCase with no spaces (single token)
        elif " " not in text and "_" in text and _INTERNAL_LABEL_RE.match(text):
            violations.append(repr(text))

    if violations:
        return {
            **_verdict(False, "EIV-MQ-18",
                f"INTERNAL_LABEL_LEAK in what_to_monitor: {', '.join(violations)}. "
                f"These are raw internal field names — not investor-facing items. "
                f"M49 HIGH defect: 'Industry_outlook' appeared as a monitoring item."),
            "severity": "HIGH",
        }
    return {
        **_verdict(True, "EIV-MQ-18",
            f"No internal labels found in what_to_monitor ({len(items)} items checked)"),
        "severity": "HIGH",
    }


def _eiv_mq_19_temporal_status_accuracy(answer: Dict) -> Dict:
    """
    EIV-MQ-19 [HIGH]: Confirmed financial data must not be described as 'projected'.

    M49 HIGH defect: LLM called confirmed (actual) FY26 revenue 'projected revenue'
    and applied 'projected figures' framing to CONFIRMED financial outcomes.
    The financial data in sun_pharma has actual revenue — it's not projected.
    """
    fields_to_check = [
        "simple_answer",
        "what_may_mean_economically",
        "what_evidence_shows",
        "key_points",
    ]

    violations = []
    for field in fields_to_check:
        val = answer.get(field)
        texts = [val] if isinstance(val, str) else (val if isinstance(val, list) else [])
        for text in texts:
            if isinstance(text, str) and _PROJECTED_CONFIRMED_RE.search(text):
                violations.append(f"{field}: confirmed financial value described as projected")
                break

    # Also check simple string for "projected revenue/earnings" near a ₹ value
    for field in fields_to_check:
        val = answer.get(field)
        text = " ".join(val) if isinstance(val, list) else str(val or "")
        if re.search(r"\bprojected\b.{0,60}₹|\₹.{0,60}\bprojected\b", text, re.IGNORECASE):
            key = f"{field}(loose)"
            if not any(field in v for v in violations):
                violations.append(f"{field}: '₹' value appears near 'projected' — confirm temporal status")
            break

    if violations:
        return {
            **_verdict(False, "EIV-MQ-19",
                f"TEMPORAL_STATUS_MISMATCH: {'; '.join(violations)}. "
                f"Confirmed/actual financial data must not use 'projected' language. "
                f"M49 HIGH defect: LLM called actual FY26 revenue 'projected'."),
            "severity": "HIGH",
        }
    return {
        **_verdict(True, "EIV-MQ-19",
            "No confirmed-financial-data temporal status mismatch detected"),
        "severity": "HIGH",
    }


def _eiv_mq_16_semantic_regression_gate(checks: List[Dict]) -> Dict:
    """
    EIV-MQ-16 [GATE]: Fails if >= 2 HIGH severity rules from EIV-MQ-09..15 failed.

    This is the semantic regression blocker. A candidate that loses 2+ investor-critical
    capabilities is blocked from human review eligibility.

    M47: HIGH fails = MQ-09, MQ-11, MQ-12, MQ-14 → 4 HIGH → FAIL
    M45.2: most rules fail → FAIL
    M37.8: all pass → PASS
    """
    high_fails = [
        c["rule"] for c in checks
        if c["result"] == "FAIL" and c.get("severity") == "HIGH"
        and c["rule"] in EIV_V2_HIGH_SEVERITY_RULES
    ]

    if len(high_fails) >= EIV_V2_SEMANTIC_REGRESSION_THRESHOLD:
        return {
            **_verdict(False, "EIV-MQ-16",
                f"SEMANTIC_REGRESSION_GATE FAIL: {len(high_fails)} HIGH severity capabilities failed "
                f"({', '.join(sorted(high_fails))}). Threshold: {EIV_V2_SEMANTIC_REGRESSION_THRESHOLD}. "
                f"Candidate represents material semantic regression vs certified baseline."),
            "severity": "GATE",
        }

    return {
        **_verdict(True, "EIV-MQ-16",
            f"Semantic regression gate passed: {len(high_fails)} HIGH severity failures "
            f"(threshold {EIV_V2_SEMANTIC_REGRESSION_THRESHOLD})"),
        "severity": "GATE",
    }


def validate_management_answer_eiv_v2(
    answer: Dict[str, Any],
    fact_pack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run all 16 EIV rules (V1 rules 01-08 + V2 rules 09-16) against a management answer.

    Args:
        answer:    The answer dict (handles wrapped {answer: {...}} or bare answer).
        fact_pack: Optional fact pack for cross-validation (unused by V2 rules currently).

    Returns:
        {
            "overall": "PASS" | "FAIL",
            "checks": [...],  # 16 rule results
            "fails": [...],   # failing rule IDs
            "warns": [...],
            "fail_count": N,
            "v1_result": {...},  # V1 result for comparison
            "schema_version": "eiv_management_quality.v2",
        }
    """
    # Unwrap
    if "answer" in answer and isinstance(answer.get("answer"), dict):
        ans = answer["answer"]
    else:
        ans = answer

    # Run V1 first (rules 01-08)
    v1_result = validate_v1(ans, fact_pack)
    v1_checks = v1_result.get("checks", [])

    # Run V2 rules (09-15 original + 17-19 M50 quality additions)
    v2_checks_pre_gate = [
        _eiv_mq_09_trusted_capability_parity(ans),
        _eiv_mq_10_factual_granularity_parity(ans),
        _eiv_mq_11_evidence_richness_parity(ans),
        _eiv_mq_12_uncertainty_parity(ans),
        _eiv_mq_13_monitoring_specificity(ans),
        _eiv_mq_14_management_statement_coverage(ans),
        _eiv_mq_15_economic_context_parity(ans),
        _eiv_mq_17_generic_evidence_detection(ans),
        _eiv_mq_18_internal_label_sanitization(ans),
        _eiv_mq_19_temporal_status_accuracy(ans),
    ]

    # Run gate (MQ-16) based on V2 pre-gate results
    gate_check = _eiv_mq_16_semantic_regression_gate(v2_checks_pre_gate)

    all_checks = v1_checks + v2_checks_pre_gate + [gate_check]
    fails = [c["rule"] for c in all_checks if c["result"] == "FAIL"]
    warns = [c["rule"] for c in all_checks if c.get("result") == "WARN"]
    high_fails = [
        c["rule"] for c in v2_checks_pre_gate
        if c["result"] == "FAIL" and c.get("severity") == "HIGH"
    ]
    medium_fails = [
        c["rule"] for c in v2_checks_pre_gate
        if c["result"] == "FAIL" and c.get("severity") == "MEDIUM"
    ]
    gate_failed = gate_check["result"] == "FAIL"
    v1_failed = v1_result["overall"] == "FAIL"

    # Overall: FAIL if V1 fails OR gate fails OR any HIGH severity fails
    # WARN if only MEDIUM severity V2 rules fail (no gate, no V1 fail, no HIGH fail)
    # PASS if none of the above
    if v1_failed or gate_failed or high_fails:
        overall = "FAIL"
    elif medium_fails or warns:
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "schema_version": EIV_SCHEMA_VERSION,
        "overall": overall,
        "fail_count": len(fails),
        "fails": fails,
        "warns": warns,
        "checks": all_checks,
        "v1_result": {
            "schema_version": EIV_V1_SCHEMA_VERSION,
            "overall": v1_result["overall"],
            "fail_count": v1_result["fail_count"],
            "fails": v1_result["fails"],
        },
        "v2_new_fails": [
            c["rule"] for c in v2_checks_pre_gate + [gate_check] if c["result"] == "FAIL"
        ],
        "high_severity_fails": high_fails,
        "medium_severity_fails": medium_fails,
    }
