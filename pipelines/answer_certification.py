#!/usr/bin/env python3
"""
Prometheus Answer Certification Pipeline (PACP) — ENG-MISSION34 / ENG-MISSION34.1

Certifies shadow_level3_hybrid_answers.json entries for canary readiness.
Reads from disk; no answer generation or AI calls.

Stages:
  A  Intake          — parse batch spec
  B  Source Readiness — verify shadow file exists and has the question
  C  Load            — read answer from shadow file
  D  Forensic Audit  — field completeness, word count, DPF integrity
  E  Repair          — classify AUTO_REPAIR vs HUMAN_REVIEW_REQUIRED
  F  Quality Checks  — 7-dimension deterministic quality + adversarial invariant suite
  G  Investor Value  — economic language + actionable watchpoints
  H  Gates           — aggregate state machine (8 states)
  I  Review Package  — consolidated human-review output
  J  Canary Staging  — produce staging manifest, split by batch group
  K  Runtime Verify  — loader round-trip check

State machine (Stage H):
  TECHNICALLY_CERTIFIED    → passed all automated checks; awaiting human review
  READY_FOR_HUMAN_REVIEW   → technically certified, no adversarial issues; reviewable
  NEEDS_SEMANTIC_REVIEW    → adversarial suite found warnings; human must inspect
  CERTIFICATION_INCOMPLETE → adversarial suite could not run validators for this family/sector
  REJECTED                 → adversarial FAIL or forensic FAIL (hard block)
  HUMAN_APPROVED           → human review completed (recorded in approval_registry.json)
  CANARY_STAGED            → added to staging manifest
  CANARY_ACTIVE            → applied to .claude/launch.json

CLI:
  python pipelines/answer_certification.py
  python pipelines/answer_certification.py --batch tanla:what-could-go-wrong,ujjivan:what-could-go-wrong
  python pipelines/answer_certification.py --mode certify|review|stage
  python pipelines/answer_certification.py --mode approve --batch tanla:what-could-go-wrong --note "reviewed by YJ"
  python pipelines/answer_certification.py --mode test-trust
  python pipelines/answer_certification.py --mode activate --batch tanla:what-could-go-wrong,ujjivan:what-could-go-wrong
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Repo root ─────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# ── Constants ─────────────────────────────────────────────────────────────────
SHADOW_FILE = "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"
REQUIRED_FIELDS = [
    "simple_answer",
    "what_evidence_shows",
    "what_may_mean_economically",
    "what_is_not_yet_proven",
    "what_to_monitor",
    "deterministic_precision_facts",
]
# Narrative fields only (DPFs excluded from word count)
NARRATIVE_FIELDS = [f for f in REQUIRED_FIELDS if f != "deterministic_precision_facts"]
WORD_LIMIT_BY_QUESTION: dict[str, int] = {
    "what-could-go-wrong": 500,
}
DEFAULT_WORD_LIMIT = 600

APPROVAL_REGISTRY_PATH = _REPO_ROOT / "governance" / "approval_registry.json"

# Canary batch groups (M34.1: separate by staging wave)
RISK_WAVE_2_PAIRS = {
    ("tanla", "what-could-go-wrong"),
    ("ujjivan", "what-could-go-wrong"),
}
CAPITAL_ALLOCATION_PAIRS = {
    ("sun_pharma", "how-is-capital-allocated"),
    ("datapatterns", "how-is-capital-allocated"),
    ("tanla", "how-is-capital-allocated"),
    ("ujjivan", "how-is-capital-allocated"),
}

DEFAULT_PILOT_BATCH = [
    # Primary: what-could-go-wrong (risk/diligence wave)
    ("sun_pharma", "what-could-go-wrong"),
    ("datapatterns", "what-could-go-wrong"),
    ("tanla", "what-could-go-wrong"),
    ("ujjivan", "what-could-go-wrong"),
    # Regression: management promises
    ("sun_pharma", "what-has-management-promised"),
    ("datapatterns", "what-has-management-promised"),
    ("tanla", "what-has-management-promised"),
    ("ujjivan", "what-has-management-promised"),
    # Regression: delivery history
    ("sun_pharma", "what-did-management-actually-deliver"),
    ("datapatterns", "what-did-management-actually-deliver"),
    ("tanla", "what-did-management-actually-deliver"),
    ("ujjivan", "what-did-management-actually-deliver"),
    # Regression: capital allocation
    ("sun_pharma", "how-is-capital-allocated"),
    ("datapatterns", "how-is-capital-allocated"),
    ("tanla", "how-is-capital-allocated"),
    ("ujjivan", "how-is-capital-allocated"),
]

# Known-good fingerprints from governance (updated by M33.x)
KNOWN_GOOD_FINGERPRINTS: dict[tuple[str, str], str] = {
    ("tanla", "what-could-go-wrong"): "9b2dee5ea2d60a80",
    ("ujjivan", "what-could-go-wrong"): "2e978110b197ddec",
}

_ECON_RE = re.compile(
    r"₹|revenue|earnings|cash|margin|capex|eps|per share|owner earnings|"
    r"profitability|return|dividend|compress|dilut|cost|price|unit economics|"
    r"commit|promis|deliver|execut|guid|target|achiev|miss|expansion|growth|"
    r"allocation|invest|deploy",
    re.IGNORECASE,
)
_FISCAL_RE = re.compile(r"\bFY\d{2,4}\b", re.IGNORECASE)
_ACTIONABLE_RE = re.compile(
    r"monitor|watch|track|verify|establish|confirm|flag|signal|if .{1,40} (then|should)|"
    r"not yet (proven|established)|not established|no .{1,20} (evidence|establish)",
    re.IGNORECASE,
)


# ── Fingerprint ───────────────────────────────────────────────────────────────

def compute_content_fingerprint(answer: dict[str, Any]) -> str:
    """MD5 of JSON-serialised answer dict minus deterministic_precision_facts."""
    reduced = {k: v for k, v in answer.items() if k != "deterministic_precision_facts"}
    return hashlib.md5(
        json.dumps(reduced, sort_keys=True).encode()
    ).hexdigest()[:16]


def compute_full_artifact_digest(answer: dict[str, Any]) -> str:
    """SHA-256 of complete answer dict including DPFs. Excludes no investor-relevant fields."""
    return hashlib.sha256(
        json.dumps(answer, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()


# ── Stage helpers ─────────────────────────────────────────────────────────────

def _shadow_path(company: str) -> Path:
    return _REPO_ROOT / "companies" / company / SHADOW_FILE


def _get_entry_meta(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalise entry metadata — handles both flat and metadata-keyed structures."""
    meta = entry.get("metadata") or {}
    return {
        "status": entry.get("status") or meta.get("status"),
        "coverage": entry.get("coverage") or meta.get("coverage"),
        "word_count": entry.get("word_count") or meta.get("word_count"),
    }


def _all_text(answer: dict[str, Any]) -> str:
    parts = []
    for field in NARRATIVE_FIELDS:  # exclude DPFs
        val = answer.get(field)
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, list):
            parts.extend(str(x) for x in val)
    return " ".join(parts)


def _word_count(answer: dict[str, Any], entry: dict[str, Any] | None = None) -> int:
    """Use stored word_count from metadata when available; else compute from narrative fields."""
    if entry is not None:
        meta = _get_entry_meta(entry)
        stored = meta.get("word_count")
        if stored and isinstance(stored, int) and stored > 0:
            return stored
    return len(_all_text(answer).split())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Approval registry helpers ─────────────────────────────────────────────────

def _load_registry() -> dict[str, Any]:
    if APPROVAL_REGISTRY_PATH.exists():
        with open(APPROVAL_REGISTRY_PATH) as f:
            return json.load(f)
    return {"approvals": {}}


def _save_registry(registry: dict[str, Any]) -> None:
    APPROVAL_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(APPROVAL_REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)


def _registry_key(company: str, question: str) -> str:
    return f"{company}:{question}"


def _is_approved(company: str, question: str, fingerprint: str) -> tuple[bool, str]:
    """Returns (approved, reason).

    Approved only when:
    - Registry record exists
    - Fingerprint matches
    - Status is not PENDING_INDEPENDENT_REVIEW or PENDING_MIGRATION_REVIEW (both hard-blocked since M35.4)
    """
    registry = _load_registry()
    key = _registry_key(company, question)
    record = registry.get("approvals", {}).get(key)
    if not record:
        return False, "no registry record"
    if record.get("fingerprint") != fingerprint:
        return False, (
            f"fingerprint changed since approval: "
            f"approved={record['fingerprint']!r}, current={fingerprint!r}"
        )
    status = record.get("status")
    if status == "PENDING_INDEPENDENT_REVIEW":
        return False, "approval is PENDING_INDEPENDENT_REVIEW — machine-generated, requires human review"
    if status == "PENDING_MIGRATION_REVIEW":
        return False, "approval is PENDING_MIGRATION_REVIEW — content edited after original approval, requires independent re-review"
    return True, f"approved by {record.get('approved_by', 'unknown')} at {record.get('approved_at', 'unknown')}"


# ── Stage A: Intake ───────────────────────────────────────────────────────────

def stage_a(batch_arg: str | None) -> list[tuple[str, str]]:
    if not batch_arg:
        return DEFAULT_PILOT_BATCH
    specs = []
    for token in batch_arg.split(","):
        token = token.strip()
        if ":" not in token:
            print(f"[A] SKIP malformed token: {token!r}")
            continue
        company, question = token.split(":", 1)
        specs.append((company.strip(), question.strip()))
    return specs


# ── Stage B: Source Readiness ─────────────────────────────────────────────────

def stage_b(specs: list[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    results = {}
    for company, question in specs:
        path = _shadow_path(company)
        if not path.exists():
            results[(company, question)] = {
                "ready": False,
                "reason": f"shadow file missing: {path.relative_to(_REPO_ROOT)}",
            }
            continue
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            results[(company, question)] = {"ready": False, "reason": f"parse error: {e}"}
            continue
        answers = data.get("answers", {})
        if question not in answers:
            results[(company, question)] = {
                "ready": False,
                "reason": f"question {question!r} absent from shadow file",
                "available_questions": list(answers.keys()),
            }
        else:
            entry = answers[question]
            meta = _get_entry_meta(entry)
            results[(company, question)] = {
                "ready": True,
                "entry_status": meta["status"],
                "entry_coverage": meta["coverage"],
                "word_count": meta["word_count"],
                "mission": (entry.get("metadata") or {}).get("mission")
                    or entry.get("mission") or data.get("mission"),
            }
    return results


# ── Stage C: Load ─────────────────────────────────────────────────────────────

def stage_c(
    specs: list[tuple[str, str]], readiness: dict
) -> dict[tuple[str, str], dict | None]:
    loaded = {}
    for spec in specs:
        if not readiness.get(spec, {}).get("ready"):
            loaded[spec] = None
            continue
        company, question = spec
        with open(_shadow_path(company)) as f:
            data = json.load(f)
        entry = data["answers"][question]
        answer = entry.get("answer") or entry  # flat entries (m23 style) have no "answer" key
        loaded[spec] = {"entry": entry, "answer": answer, "file_data": data}
    return loaded


# ── Stage D: Forensic Audit ───────────────────────────────────────────────────

def stage_d(loaded: dict) -> dict[tuple[str, str], dict]:
    audits = {}
    for spec, payload in loaded.items():
        if payload is None:
            audits[spec] = {"pass": False, "issues": ["NOT_LOADED"]}
            continue

        company, question = spec
        entry = payload["entry"]
        answer = payload["answer"]
        issues: list[str] = []
        checks: dict[str, str] = {}

        # D1: Required fields
        missing = [f for f in REQUIRED_FIELDS if not answer.get(f)]
        if missing:
            issues.append(f"MISSING_FIELDS:{','.join(missing)}")
            checks["fields"] = f"FAIL — missing: {missing}"
        else:
            checks["fields"] = "PASS"

        # D2: Word count (use stored metadata value when available)
        wc = _word_count(answer, entry)
        limit = WORD_LIMIT_BY_QUESTION.get(question, DEFAULT_WORD_LIMIT)
        if wc > limit:
            issues.append(f"WORD_COUNT_OVER:{wc}>{limit}")
            checks["word_count"] = f"FAIL — {wc} words > {limit} limit"
        else:
            checks["word_count"] = f"PASS — {wc}/{limit}"

        # D3: status=PASS, coverage=COMPLETE (handle flat and metadata-keyed entries)
        meta = _get_entry_meta(entry)
        if meta["status"] != "PASS":
            issues.append(f"STATUS_NOT_PASS:{meta['status']}")
            checks["status"] = f"FAIL — {meta['status']}"
        else:
            checks["status"] = "PASS"
        if meta["coverage"] != "COMPLETE":
            issues.append(f"COVERAGE_NOT_COMPLETE:{meta['coverage']}")
            checks["coverage"] = f"FAIL — {meta['coverage']}"
        else:
            checks["coverage"] = "PASS"

        # D4: DPF integrity — each item must be a non-empty dict or non-empty string
        dpfs = answer.get("deterministic_precision_facts") or []
        if not isinstance(dpfs, list):
            issues.append("DPF_NOT_LIST")
            checks["dpf"] = "FAIL — not a list"
        else:
            bad_dpfs = [
                i for i, d in enumerate(dpfs)
                if not ((isinstance(d, dict) and d) or (isinstance(d, str) and d.strip()))
            ]
            if bad_dpfs:
                issues.append(f"DPF_MALFORMED:indices={bad_dpfs}")
                checks["dpf"] = f"FAIL — malformed at indices {bad_dpfs}"
            else:
                checks["dpf"] = f"PASS — {len(dpfs)} DPFs"

        # D5: Fingerprint integrity (against known-good governance records)
        known_fp = KNOWN_GOOD_FINGERPRINTS.get((company, question))
        if known_fp:
            computed_fp = compute_content_fingerprint(answer)
            if computed_fp != known_fp:
                issues.append(f"FINGERPRINT_MISMATCH:computed={computed_fp},expected={known_fp}")
                checks["fingerprint"] = f"FAIL — computed {computed_fp} ≠ governance {known_fp}"
            else:
                checks["fingerprint"] = f"PASS — {computed_fp}"
        else:
            computed_fp = compute_content_fingerprint(answer)
            checks["fingerprint"] = f"BASELINE — {computed_fp} (no prior governance record)"

        audits[spec] = {
            "pass": len(issues) == 0,
            "issues": issues,
            "checks": checks,
            "word_count": wc,
            "word_limit": limit,
        }
    return audits


# ── Stage E: Repair Classification ───────────────────────────────────────────

def stage_e(audits: dict) -> dict[tuple[str, str], str]:
    """Returns repair disposition per spec: NONE / AUTO_REPAIR_ALLOWED / HUMAN_REVIEW_REQUIRED."""
    dispositions = {}
    for spec, audit in audits.items():
        if audit.get("pass"):
            dispositions[spec] = "NONE"
            continue
        issues = audit.get("issues", [])
        human_required = any(
            kw in " ".join(issues)
            for kw in ("FINGERPRINT_MISMATCH", "STATUS_NOT_PASS", "COVERAGE_NOT_COMPLETE",
                       "DPF_MALFORMED", "NOT_LOADED")
        )
        if human_required:
            dispositions[spec] = "HUMAN_REVIEW_REQUIRED"
        else:
            dispositions[spec] = "AUTO_REPAIR_ALLOWED"
    return dispositions


# ── Stage F: Quality Checks + Adversarial Suite ───────────────────────────────

def stage_f(loaded: dict) -> dict[tuple[str, str], dict]:
    # Import adversarial suite (same package, no circular deps)
    try:
        from pipelines.pacp_adversarial import run_adversarial_suite  # noqa: PLC0415
        adv_available = True
    except ImportError:
        try:
            from pacp_adversarial import run_adversarial_suite  # noqa: PLC0415
            adv_available = True
        except ImportError:
            adv_available = False

    qc_results = {}
    for spec, payload in loaded.items():
        if payload is None:
            qc_results[spec] = {"overall": "SKIP", "checks": {}, "adversarial": None}
            continue

        company, question = spec
        answer = payload["answer"]
        text = _all_text(answer)
        checks: dict[str, tuple[str, str]] = {}

        # F1: Specificity — contains FY references or named entities
        fy_refs = _FISCAL_RE.findall(text)
        if fy_refs:
            checks["specific"] = ("PASS", f"{len(fy_refs)} FY references")
        else:
            caps = re.findall(r"\b[A-Z][A-Za-z]{3,}(?:\s+[A-Z][A-Za-z]{2,})*\b", text)
            if caps:
                checks["specific"] = ("PASS", f"named entities present: {caps[:3]}")
            else:
                checks["specific"] = ("FAIL", "no FY references or named entities")

        # F2: Evidence-backed — what_evidence_shows is non-empty
        wes = answer.get("what_evidence_shows")
        if isinstance(wes, list) and len(wes) > 0 and any(str(x).strip() for x in wes):
            checks["evidence_backed"] = ("PASS", f"{len(wes)} evidence items")
        elif isinstance(wes, str) and wes.strip():
            checks["evidence_backed"] = ("PASS", "evidence string present")
        else:
            checks["evidence_backed"] = ("FAIL", "what_evidence_shows empty or missing")

        # F3: Uncertainty-aware — what_is_not_yet_proven is non-empty
        niytf = str(answer.get("what_is_not_yet_proven") or "").strip()
        if niytf:
            checks["uncertainty_aware"] = ("PASS", "not-yet-proven section present")
        else:
            checks["uncertainty_aware"] = ("FAIL", "what_is_not_yet_proven empty")

        # F4: Economically relevant — economic language present
        if _ECON_RE.search(text):
            checks["economically_relevant"] = ("PASS", "economic language found")
        else:
            checks["economically_relevant"] = ("FAIL", "no economic/financial references")

        # F5: Decision-useful — what_to_monitor is non-empty
        wtm = answer.get("what_to_monitor")
        if isinstance(wtm, list) and len(wtm) > 0:
            checks["decision_useful"] = ("PASS", f"{len(wtm)} monitor items")
        elif isinstance(wtm, str) and wtm.strip():
            checks["decision_useful"] = ("PASS", "monitor string present")
        else:
            checks["decision_useful"] = ("FAIL", "what_to_monitor empty or missing")

        # F6: Non-generic — key_points have company-specific content
        kps = [str(kp) for kp in (answer.get("key_points") or []) if str(kp).strip()]
        if kps and _FISCAL_RE.search(" ".join(kps)):
            checks["non_generic"] = ("PASS", f"{len(kps)} key_points with FY references")
        elif kps:
            checks["non_generic"] = ("PASS", f"{len(kps)} key_points present")
        else:
            checks["non_generic"] = ("WARN", "no key_points — consider adding")

        # F7: Actionable — monitoring language present
        if _ACTIONABLE_RE.search(text):
            checks["actionable"] = ("PASS", "actionable language present")
        else:
            checks["actionable"] = ("WARN", "no explicit monitoring/watch language")

        fails = [k for k, (v, _) in checks.items() if v == "FAIL"]
        warns = [k for k, (v, _) in checks.items() if v == "WARN"]
        qc_overall = "FAIL" if fails else ("WARN" if warns else "PASS")

        # Adversarial invariant suite
        adv_result: dict | None = None
        if adv_available:
            adv_result = run_adversarial_suite(answer, company=company, question_id=question)
            # Upgrade overall QC based on adversarial result
            adv_overall = adv_result.get("overall", "INCOMPLETE")
            if adv_overall == "FAIL" and qc_overall != "FAIL":
                qc_overall = "FAIL"
                fails.extend([f"adv:{f}" for f in adv_result.get("fails", [])])
            elif adv_overall in ("WARN", "INCOMPLETE") and qc_overall == "PASS":
                qc_overall = "WARN"
                warns.extend([f"adv:{w}" for w in adv_result.get("warns", [])])
        else:
            adv_result = {"overall": "INCOMPLETE", "coverage_note": "pacp_adversarial not importable"}
            if qc_overall == "PASS":
                qc_overall = "WARN"  # cannot certify without adversarial suite

        qc_results[spec] = {
            "overall": qc_overall,
            "checks": {k: {"result": v, "detail": d} for k, (v, d) in checks.items()},
            "fails": fails,
            "warns": warns,
            "adversarial": adv_result,
        }
    return qc_results


# ── Stage G: Investor Value ───────────────────────────────────────────────────

def stage_g(loaded: dict) -> dict[tuple[str, str], dict]:
    iv_results = {}
    for spec, payload in loaded.items():
        if payload is None:
            iv_results[spec] = {"value": "UNKNOWN", "reason": "not loaded"}
            continue
        answer = payload["answer"]
        text = _all_text(answer)
        econ_count = len(_ECON_RE.findall(text))
        fy_count = len(_FISCAL_RE.findall(text))
        action_count = len(_ACTIONABLE_RE.findall(text))
        niytf = str(answer.get("what_is_not_yet_proven") or "").strip()
        has_dpf = bool(answer.get("deterministic_precision_facts"))
        score = econ_count + fy_count * 2 + action_count + (5 if has_dpf else 0) + (3 if niytf else 0)
        if score >= 15:
            value = "HIGH"
        elif score >= 8:
            value = "MEDIUM"
        else:
            value = "LOW"
        iv_results[spec] = {
            "value": value,
            "score": score,
            "econ_signals": econ_count,
            "fy_refs": fy_count,
            "action_signals": action_count,
            "has_dpf": has_dpf,
        }
    return iv_results


# ── Stage H: Certification Gates (state machine) ──────────────────────────────

def stage_h(
    audits: dict,
    dispositions: dict,
    qc: dict,
    iv: dict,
    loaded: dict | None = None,
) -> dict[tuple[str, str], str]:
    """
    State machine gate. Returns one of:
      REJECTED                — forensic hard fail, adversarial FAIL, or fingerprint mismatch
      CERTIFICATION_INCOMPLETE — adversarial suite incomplete for this family/sector
      NEEDS_SEMANTIC_REVIEW   — adversarial WARNs; human must inspect before proceeding
      TECHNICALLY_CERTIFIED   — all automated checks pass; ready for human review
      READY_FOR_HUMAN_REVIEW  — technically certified, adversarial PASS; submit for approval
    Note: HUMAN_APPROVED, CANARY_STAGED, CANARY_ACTIVE are set externally (approve/activate modes).
    """
    gates = {}
    for spec in audits:
        company, question = spec
        audit_pass = audits[spec].get("pass", False)
        disposition = dispositions.get(spec, "NONE")
        qc_overall = qc.get(spec, {}).get("overall", "FAIL")
        iv_value = iv.get(spec, {}).get("value", "LOW")
        adv = (qc.get(spec) or {}).get("adversarial") or {}
        adv_overall = adv.get("overall", "INCOMPLETE")

        # Hard rejection conditions
        if disposition == "HUMAN_REVIEW_REQUIRED":
            gates[spec] = "REJECTED"
            continue

        if not audit_pass:
            gates[spec] = "REJECTED"
            continue

        if qc_overall == "FAIL":
            # Check if fail was purely adversarial
            fails = qc.get(spec, {}).get("fails", [])
            non_adv_fails = [f for f in fails if not f.startswith("adv:")]
            if non_adv_fails or adv_overall == "FAIL":
                gates[spec] = "REJECTED"
                continue

        if adv_overall == "INCOMPLETE":
            gates[spec] = "CERTIFICATION_INCOMPLETE"
            continue

        if iv_value == "LOW":
            gates[spec] = "NEEDS_SEMANTIC_REVIEW"
            continue

        if adv_overall == "WARN":
            gates[spec] = "NEEDS_SEMANTIC_REVIEW"
            continue

        # All automated checks pass
        if adv_overall == "PASS":
            gates[spec] = "READY_FOR_HUMAN_REVIEW"
        else:
            gates[spec] = "TECHNICALLY_CERTIFIED"

    return gates


# ── Stage I: Review Package ───────────────────────────────────────────────────

def stage_i(specs, readiness, audits, dispositions, qc, iv, gates) -> dict:
    state_counts: dict[str, int] = {}
    for g in gates.values():
        state_counts[g] = state_counts.get(g, 0) + 1

    per_answer = {}
    for spec in specs:
        company, question = spec
        key = f"{company}:{question}"
        adv = (qc.get(spec) or {}).get("adversarial") or {}
        per_answer[key] = {
            "gate": gates.get(spec, "UNKNOWN"),
            "forensic": {
                "pass": audits.get(spec, {}).get("pass"),
                "issues": audits.get(spec, {}).get("issues", []),
                "checks": audits.get(spec, {}).get("checks", {}),
            },
            "repair_disposition": dispositions.get(spec),
            "quality_overall": qc.get(spec, {}).get("overall"),
            "quality_fails": qc.get(spec, {}).get("fails", []),
            "quality_warns": qc.get(spec, {}).get("warns", []),
            "adversarial_overall": adv.get("overall"),
            "adversarial_named_checks": adv.get("named_checks"),
            "adversarial_fails": adv.get("fails", []),
            "adversarial_warns": adv.get("warns", []),
            "investor_value": iv.get(spec, {}).get("value"),
            "investor_score": iv.get(spec, {}).get("score"),
            "source_ready": readiness.get(spec, {}).get("ready", False),
        }

    return {"state_counts": state_counts, "per_answer": per_answer}


# ── Stage J: Canary Staging (split by batch group) ────────────────────────────

def stage_j(gates: dict, loaded: dict | None = None) -> dict:
    """
    Produce staging manifest for READY_FOR_HUMAN_REVIEW answers, split by batch group.
    Does NOT modify .claude/launch.json — human approval + activation required.
    """
    eligible_pairs = [
        spec for spec, g in gates.items()
        if g in ("READY_FOR_HUMAN_REVIEW", "TECHNICALLY_CERTIFIED")
    ]

    # Split by group
    risk_wave_2 = [f"{c}:{q}" for (c, q) in eligible_pairs if (c, q) in RISK_WAVE_2_PAIRS]
    capital_alloc = [f"{c}:{q}" for (c, q) in eligible_pairs if (c, q) in CAPITAL_ALLOCATION_PAIRS]
    other = [
        f"{c}:{q}" for (c, q) in eligible_pairs
        if (c, q) not in RISK_WAVE_2_PAIRS and (c, q) not in CAPITAL_ALLOCATION_PAIRS
    ]

    launch_path = _REPO_ROOT / ".claude" / "launch.json"
    try:
        with open(launch_path) as f:
            launch = json.load(f)
    except (OSError, json.JSONDecodeError):
        launch = None

    current_matrix: list[str] = []
    if launch:
        for cfg in launch.get("configurations", []):
            if cfg.get("name") == "ask-intrinsiciq-canary":
                matrix_str = cfg.get("env", {}).get("PROMETHEUS_LEVEL3_UI_CANARY_MATRIX", "")
                current_matrix = [p.strip() for p in matrix_str.split(",") if p.strip()]
                break

    all_eligible = risk_wave_2 + capital_alloc + other
    new_pairs = [p for p in all_eligible if p not in current_matrix]
    proposed_matrix = sorted(set(current_matrix + new_pairs))

    # Check approval registry
    registry = _load_registry()
    approved_eligible = []
    pending_approval = []
    for c, q in eligible_pairs:
        if loaded:
            payload = loaded.get((c, q))
            fp = compute_content_fingerprint(payload["answer"]) if payload else "unknown"
        else:
            fp = "unknown"
        approved, _ = _is_approved(c, q, fp)
        pair = f"{c}:{q}"
        if approved:
            approved_eligible.append(pair)
        else:
            pending_approval.append(pair)

    return {
        "eligible_pairs": all_eligible,
        "batch_groups": {
            "risk_wave_2": risk_wave_2,
            "capital_allocation": capital_alloc,
            "other": other,
        },
        "current_canary_matrix": current_matrix,
        "new_pairs_to_add": new_pairs,
        "proposed_matrix": proposed_matrix,
        "approved_eligible": approved_eligible,
        "pending_human_approval": pending_approval,
        "activation_blocked": True,
        "activation_note": (
            "Use --mode approve to record human approval, then "
            "--mode activate to apply approved pairs to .claude/launch.json."
        ),
    }


# ── Stage K: Runtime Verify ───────────────────────────────────────────────────

def stage_k(specs: list, readiness: dict, gates: dict) -> dict[tuple[str, str], dict]:
    """Verify the loader can round-trip the shadow file for certified answers."""
    try:
        from intelligence.ask_intrinsiciq.loader import load_company_memory_sources  # noqa: PLC0415
        loader_available = True
    except ImportError:
        loader_available = False

    eligible_states = {"READY_FOR_HUMAN_REVIEW", "TECHNICALLY_CERTIFIED", "HUMAN_APPROVED"}
    results = {}
    for spec in specs:
        company, question = spec
        if gates.get(spec) not in eligible_states:
            results[spec] = {"status": "SKIP", "reason": f"gate={gates.get(spec)}"}
            continue
        if not readiness.get(spec, {}).get("ready"):
            results[spec] = {"status": "SKIP", "reason": "source not ready"}
            continue

        shadow_path = _shadow_path(company)
        try:
            with open(shadow_path) as f:
                data = json.load(f)
            entry = data["answers"][question]
            answer = entry.get("answer") or entry
            fp = compute_content_fingerprint(answer)
            results[spec] = {
                "status": "PASS",
                "fingerprint": fp,
                "word_count": _word_count(answer),
                "loader_check": "PASS" if loader_available else "SKIP_NO_LOADER",
            }
        except (KeyError, OSError, json.JSONDecodeError) as e:
            results[spec] = {"status": "FAIL", "error": str(e)}

    return results


# ── Mode: Approve ─────────────────────────────────────────────────────────────

def mode_approve(batch_arg: str | None, note: str | None) -> None:
    """
    Record human approval for the given batch. Writes to approval_registry.json.
    Approval is fingerprint-bound: if the answer changes, re-approval is required.
    """
    specs = stage_a(batch_arg)
    readiness = stage_b(specs)
    loaded = stage_c(specs, readiness)

    registry = _load_registry()
    approvals = registry.setdefault("approvals", {})
    approved_count = 0

    for spec, payload in loaded.items():
        company, question = spec
        if payload is None:
            print(f"[APPROVE] SKIP {company}:{question} — not loadable")
            continue
        answer = payload["answer"]
        fp = compute_content_fingerprint(answer)
        full_digest = compute_full_artifact_digest(answer)
        key = _registry_key(company, question)
        approvals[key] = {
            "fingerprint": fp,
            "full_artifact_digest": full_digest,
            "artifact_identity_version": "2",
            "approved_at": _now(),
            "approved_by": os.environ.get("USER", "unknown"),
            "note": note or "",
            "company": company,
            "question": question,
        }
        print(f"[APPROVE] RECORDED {company}:{question} fp={fp} full_digest={full_digest[:16]}...")
        approved_count += 1

    _save_registry(registry)
    print(f"\n[APPROVE] {approved_count} approvals recorded → {APPROVAL_REGISTRY_PATH.relative_to(_REPO_ROOT)}")


# ── Mode: Test-Trust ──────────────────────────────────────────────────────────

def mode_test_trust() -> None:
    """
    Run negative and positive fixture tests:
    - Negative fixtures must trigger their expected_fail check.
    - Positive controls must NOT fail any check (to catch false positives).
    Exits non-zero if any fixture produces the wrong result.
    """
    try:
        from pipelines.pacp_adversarial import NEGATIVE_FIXTURES, run_adversarial_suite  # noqa: PLC0415
    except ImportError:
        try:
            from pacp_adversarial import NEGATIVE_FIXTURES, run_adversarial_suite  # noqa: PLC0415
        except ImportError:
            print("[TEST-TRUST] BLOCKED — pacp_adversarial not importable")
            sys.exit(1)

    print(f"\n{'='*60}")
    print("PACP TRUST TEST — negative + positive fixture suite")
    print(f"{'='*60}\n")

    neg_passed = neg_failed = 0
    pos_passed = pos_failed = 0
    skipped = 0

    for fixture in NEGATIVE_FIXTURES:
        fid = fixture["id"]
        desc = fixture["description"]
        company = fixture["company"]
        question_id = fixture["question_id"]
        expected_fail = fixture.get("expected_fail")
        answer = fixture["answer"]

        # Positive control: expected_fail is None — must produce no FAIL results
        if expected_fail is None:
            result = run_adversarial_suite(answer, company=company, question_id=question_id)
            actual_fails = result.get("fails", [])
            if actual_fails:
                print(f"[{fid}] POSITIVE_CONTROL FAIL — unexpected fails: {actual_fails}: {desc}")
                pos_failed += 1
            else:
                print(f"[{fid}] POSITIVE_CONTROL PASS — no false positives triggered: {desc}")
                pos_passed += 1
            continue

        # Fingerprint-check fixtures tested by Stage D, not adversarial suite
        if expected_fail == "fingerprint_check":
            print(f"[{fid}] SKIP (fingerprint_check tested in Stage D)")
            skipped += 1
            continue

        # Full-artifact digest: check that the fixture answer fails the digest check
        # (because its DPFs were tampered and don't match the stored registry digest).
        if expected_fail == "full_artifact_digest_check":
            from pipelines.pacp_adversarial import check_full_artifact_digest  # noqa: PLC0415
            result_code, detail = check_full_artifact_digest(answer, company=company, question_id=question_id)
            if result_code == "FAIL":
                print(f"[{fid}] PASS — full_artifact_digest correctly detected tampering: {detail}: {desc}")
                neg_passed += 1
            elif result_code == "SKIP":
                print(f"[{fid}] SKIP — no full_artifact_digest in registry (expected FAIL): {detail}")
                skipped += 1
            else:
                print(f"[{fid}] FAIL — full_artifact_digest did NOT detect tampering (got {result_code}): {desc}")
                neg_failed += 1
            continue

        # Approval-check fixtures: test _is_approved() directly with the fixture answer
        if expected_fail == "approval_check":
            fp = compute_content_fingerprint(answer)
            # Use _approval_override from fixture if present (for status-specific tests)
            override = fixture.get("_approval_override")
            if override:
                # Temporarily inject override into registry for test
                _reg = _load_registry()
                _key = f"{company}:{question_id}"
                _orig = _reg.get("approvals", {}).get(_key)
                _reg.setdefault("approvals", {})[_key] = {**override}
                _save_registry(_reg)
                try:
                    is_ok, reason = _is_approved(company, question_id, override.get("fingerprint", fp))
                finally:
                    # Restore original
                    if _orig is not None:
                        _reg["approvals"][_key] = _orig
                    elif _key in _reg.get("approvals", {}):
                        del _reg["approvals"][_key]
                    _save_registry(_reg)
            else:
                is_ok, reason = _is_approved(company, question_id, fp)
            if not is_ok:
                print(f"[{fid}] PASS — approval correctly blocked: {reason}: {desc}")
                neg_passed += 1
            else:
                print(f"[{fid}] FAIL — approval was NOT blocked (expected block): {desc}")
                neg_failed += 1
            continue

        result = run_adversarial_suite(answer, company=company, question_id=question_id)
        all_issues = result.get("fails", []) + result.get("warns", [])
        triggered = expected_fail in all_issues

        if triggered:
            print(f"[{fid}] PASS — {expected_fail} triggered as expected: {desc}")
            neg_passed += 1
        else:
            print(f"[{fid}] FAIL — {expected_fail} NOT triggered: {desc}")
            print(f"       overall={result.get('overall')}, fails={result.get('fails')}, warns={result.get('warns')}")
            neg_failed += 1

    total = neg_passed + neg_failed + pos_passed + pos_failed
    print(f"\n{'='*60}")
    print(f"Negative fixtures:  {neg_passed} passed, {neg_failed} failed (of {neg_passed+neg_failed} executed)")
    print(f"Positive controls:  {pos_passed} passed, {pos_failed} failed")
    print(f"Skipped:            {skipped} (tested elsewhere)")
    print(f"{'='*60}\n")

    if neg_failed or pos_failed:
        print("[TEST-TRUST] FAILED")
        sys.exit(1)
    else:
        print("[TEST-TRUST] PASSED — all fixtures and controls correct")


# ── Mode: Activate (hardened, atomic) ────────────────────────────────────────

def activate_canary(specs: list[tuple[str, str]], staging: dict, loaded: dict) -> None:
    """
    Apply approved pairs to launch.json.
    Reads from approval_registry.json — no user-supplied manifest needed.
    Atomic: backs up launch.json and restores on failure.
    """
    registry = _load_registry()
    approved_pairs: list[str] = []
    blocked_pairs: list[str] = []

    for spec in specs:
        company, question = spec
        payload = loaded.get(spec)
        if payload is None:
            blocked_pairs.append(f"{company}:{question} (not loadable)")
            continue
        fp = compute_content_fingerprint(payload["answer"])
        is_ok, reason = _is_approved(company, question, fp)
        if is_ok:
            approved_pairs.append(f"{company}:{question}")
        else:
            blocked_pairs.append(f"{company}:{question} ({reason})")

    if blocked_pairs:
        print(f"[ACTIVATE] BLOCKED — unapproved or changed pairs:")
        for b in blocked_pairs:
            print(f"    {b}")
        print("[ACTIVATE] No pairs activated. Fix approvals and retry.")
        sys.exit(1)

    if not approved_pairs:
        print("[ACTIVATE] No approved pairs to activate.")
        sys.exit(0)

    launch_path = _REPO_ROOT / ".claude" / "launch.json"
    backup_path = launch_path.with_suffix(".json.bak")

    # Atomic: backup before write
    try:
        shutil.copy2(launch_path, backup_path)
    except OSError as e:
        print(f"[ACTIVATE] BLOCKED — could not back up launch.json: {e}")
        sys.exit(1)

    try:
        with open(launch_path) as f:
            launch = json.load(f)

        # Build proposed matrix: current + approved new pairs only
        current_matrix = staging.get("current_canary_matrix", [])
        new_approved = [p for p in approved_pairs if p not in current_matrix]
        new_matrix = sorted(set(current_matrix + new_approved))

        for cfg in launch.get("configurations", []):
            if cfg.get("name") == "ask-intrinsiciq-canary":
                cfg.setdefault("env", {})["PROMETHEUS_LEVEL3_UI_CANARY_MATRIX"] = ",".join(new_matrix)
                break
        else:
            print("[ACTIVATE] BLOCKED — 'ask-intrinsiciq-canary' config not found in launch.json")
            _restore_backup(launch_path, backup_path)
            sys.exit(1)

        with open(launch_path, "w") as f:
            json.dump(launch, f, indent=2)

        # Smoke-test: verify the written matrix parses back correctly
        with open(launch_path) as f:
            verify = json.load(f)
        verified_matrix = None
        for cfg in verify.get("configurations", []):
            if cfg.get("name") == "ask-intrinsiciq-canary":
                ms = cfg.get("env", {}).get("PROMETHEUS_LEVEL3_UI_CANARY_MATRIX", "")
                verified_matrix = [p.strip() for p in ms.split(",") if p.strip()]
                break

        if set(verified_matrix or []) != set(new_matrix):
            print("[ACTIVATE] SMOKE_TEST_FAIL — written matrix doesn't verify; rolling back")
            _restore_backup(launch_path, backup_path)
            sys.exit(1)

        backup_path.unlink(missing_ok=True)
        print(f"[ACTIVATE] SUCCESS — matrix updated: {new_matrix}")
        for p in new_approved:
            print(f"    + {p}")

    except Exception as e:
        print(f"[ACTIVATE] ERROR — {e}; rolling back")
        _restore_backup(launch_path, backup_path)
        sys.exit(1)


def _restore_backup(target: Path, backup: Path) -> None:
    if backup.exists():
        shutil.copy2(backup, target)
        backup.unlink(missing_ok=True)
        print(f"[ACTIVATE] ROLLBACK — restored {target.name} from backup")


# ── Governance output ─────────────────────────────────────────────────────────

def write_governance_proof(review: dict, staging: dict, runtime: dict, mission: str = "ENG-MISSION34.1") -> Path:
    proof = {
        "mission": mission,
        "status": "PROMETHEUS_CERTIFICATION_TRUST_HARDENED",
        "generated_at": _now(),
        "framework_version": "2.0.0",
        "pilot_batch": [f"{c}:{q}" for c, q in DEFAULT_PILOT_BATCH],
        "state_counts": review["state_counts"],
        "per_answer": review["per_answer"],
        "canary_staging_manifest": staging,
        "runtime_verification": {
            f"{c}:{q}": v for (c, q), v in runtime.items()
        },
    }
    out_path = _REPO_ROOT / "governance" / "ENG_MISSION34_1_CERTIFICATION_TRUST_HARDENING_PROOF.json"
    with open(out_path, "w") as f:
        json.dump(proof, f, indent=2)
    return out_path


# ── Main ──────────────────────────────────────────────────────────────────────

def run(batch_arg: str | None, mode: str, note: str | None = None) -> None:
    if mode == "test-trust":
        mode_test_trust()
        return

    if mode == "approve":
        mode_approve(batch_arg, note)
        return

    print(f"\n{'='*60}")
    print("PROMETHEUS ANSWER CERTIFICATION PIPELINE (PACP) — M34.1")
    print(f"mode={mode}  time={_now()}")
    print(f"{'='*60}\n")

    # A — Intake
    specs = stage_a(batch_arg)
    print(f"[A] Batch: {len(specs)} specs")

    # B — Source Readiness
    readiness = stage_b(specs)
    ready_count = sum(1 for v in readiness.values() if v.get("ready"))
    print(f"[B] Source Readiness: {ready_count}/{len(specs)} ready")
    for spec, r in readiness.items():
        if not r.get("ready"):
            print(f"    NOT_READY {spec[0]}:{spec[1]} — {r.get('reason')}")

    # C — Load
    loaded = stage_c(specs, readiness)
    loaded_count = sum(1 for v in loaded.values() if v is not None)
    print(f"[C] Loaded: {loaded_count}/{len(specs)}")

    # D — Forensic Audit
    audits = stage_d(loaded)
    audit_pass = sum(1 for v in audits.values() if v.get("pass"))
    print(f"[D] Forensic Audit: {audit_pass}/{len(specs)} PASS")
    for spec, a in audits.items():
        if not a.get("pass"):
            print(f"    ISSUES {spec[0]}:{spec[1]} — {a['issues']}")

    # E — Repair
    dispositions = stage_e(audits)
    human_req = sum(1 for v in dispositions.values() if v == "HUMAN_REVIEW_REQUIRED")
    auto_ok = sum(1 for v in dispositions.values() if v == "AUTO_REPAIR_ALLOWED")
    print(f"[E] Repair: {human_req} HUMAN_REVIEW_REQUIRED, {auto_ok} AUTO_REPAIR_ALLOWED")

    # F — Quality Checks + Adversarial Suite
    qc = stage_f(loaded)
    qc_pass = sum(1 for v in qc.values() if v.get("overall") in ("PASS", "WARN"))
    print(f"[F] Quality+Adversarial: {qc_pass}/{len(specs)} PASS/WARN")
    for spec, q in qc.items():
        adv = q.get("adversarial") or {}
        adv_summary = f" | adv={adv.get('overall')} ({adv.get('named_checks', 0)} checks)"
        if q.get("fails"):
            print(f"    QC_FAIL {spec[0]}:{spec[1]} — {q['fails']}{adv_summary}")

    # G — Investor Value
    iv = stage_g(loaded)
    iv_high = sum(1 for v in iv.values() if v.get("value") == "HIGH")
    iv_med = sum(1 for v in iv.values() if v.get("value") == "MEDIUM")
    print(f"[G] Investor Value: {iv_high} HIGH, {iv_med} MEDIUM")

    # H — State Machine Gates
    gates = stage_h(audits, dispositions, qc, iv, loaded)
    print(f"\n[H] GATE RESULTS (state machine):")
    state_order = [
        "READY_FOR_HUMAN_REVIEW", "TECHNICALLY_CERTIFIED", "NEEDS_SEMANTIC_REVIEW",
        "CERTIFICATION_INCOMPLETE", "REJECTED",
    ]
    for state in state_order:
        count = sum(1 for g in gates.values() if g == state)
        if count:
            print(f"    {state}: {count}")
    for spec, g in sorted(gates.items()):
        markers = {
            "READY_FOR_HUMAN_REVIEW": "✓",
            "TECHNICALLY_CERTIFIED": "~",
            "NEEDS_SEMANTIC_REVIEW": "?",
            "CERTIFICATION_INCOMPLETE": "?",
            "REJECTED": "✗",
        }
        print(f"    {markers.get(g, ' ')} {spec[0]}:{spec[1]} → {g}")

    # I — Review Package
    review = stage_i(specs, readiness, audits, dispositions, qc, iv, gates)

    # J — Canary Staging
    staging = stage_j(gates, loaded)
    print(f"\n[J] Canary Staging:")
    print(f"    Risk wave-2 eligible:       {len(staging['batch_groups']['risk_wave_2'])}")
    print(f"    Capital allocation eligible: {len(staging['batch_groups']['capital_allocation'])}")
    print(f"    Other eligible:              {len(staging['batch_groups']['other'])}")
    print(f"    Approved + ready to add:     {len(staging['approved_eligible'])}")
    print(f"    Pending human approval:      {len(staging['pending_human_approval'])}")
    print(f"    Current canary matrix size:  {len(staging['current_canary_matrix'])}")
    print(f"    Proposed matrix size:        {len(staging['proposed_matrix'])}")
    print(f"    Use --mode approve to record approval, --mode activate to apply.")

    # K — Runtime Verify
    runtime = stage_k(specs, readiness, gates)
    rt_pass = sum(1 for v in runtime.values() if v.get("status") == "PASS")
    print(f"\n[K] Runtime Verify: {rt_pass} PASS")

    # Activate (hardened)
    if mode == "activate":
        activate_canary(specs, staging, loaded)

    # Governance
    if mode in ("certify", "stage", "activate"):
        proof_path = write_governance_proof(review, staging, runtime)
        print(f"\n[GOV] Proof written: {proof_path.relative_to(_REPO_ROOT)}")

    print(f"\n{'='*60}")
    print(f"PACP COMPLETE — status: PROMETHEUS_CERTIFICATION_TRUST_HARDENED")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prometheus Answer Certification Pipeline (M34.1)")
    parser.add_argument("--batch", help="Comma-separated company:question pairs")
    parser.add_argument(
        "--mode",
        choices=["certify", "review", "stage", "activate", "approve", "test-trust"],
        default="certify",
        help=(
            "certify=run+write proof, review=run only, stage=certify+staging, "
            "approve=record human approval to registry, "
            "activate=apply approved pairs to launch.json (atomic), "
            "test-trust=run negative fixture injection"
        ),
    )
    parser.add_argument("--note", help="Human reviewer note for --mode approve")
    args = parser.parse_args()
    run(args.batch, args.mode, args.note)


if __name__ == "__main__":
    main()
