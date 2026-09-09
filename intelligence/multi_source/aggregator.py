"""Phase 9 — Multi-source evidence aggregator.

Reads from all 6 processor output families and normalises every claim
into a MultiSourceEvidence atom.  No company-specific logic lives here;
the company root path is passed in.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional

from intelligence.multi_source.contracts import (
    ClaimDomain,
    MultiSourceEvidence,
    SourceAuthority,
)
from intelligence.multi_source.paths import (
    annual_intelligence_dirs,
    earnings_call_dirs,
    earnings_release_dirs,
    exchange_disclosure_dirs,
    presentation_dirs,
    quarterly_report_dirs,
    safe_json_load,
)
from intelligence.multi_source.theme_registry import classify_theme


def _uid(prefix: str, text: str) -> str:
    return prefix + ":" + hashlib.sha1(text.encode()).hexdigest()[:12]


def _claim_type_to_domain(claim_type: str) -> ClaimDomain:
    mapping = {
        "COMMITMENT": ClaimDomain.COMMITMENT,
        "INTENTION": ClaimDomain.COMMITMENT,
        "TARGET": ClaimDomain.COMMITMENT,
        "EXPECTATION": ClaimDomain.COMMITMENT,
        "STRATEGIC_PRIORITY": ClaimDomain.STRATEGIC_PRIORITY,
        "RISK_ACKNOWLEDGEMENT": ClaimDomain.RISK,
        "FINANCIAL_STATEMENT": ClaimDomain.FINANCIAL_METRIC,
        "FACTUAL_STATEMENT": ClaimDomain.FACTUAL_EVENT,
        "EXPLANATION": ClaimDomain.FACTUAL_EVENT,
    }
    return mapping.get(claim_type.upper(), ClaimDomain.FACTUAL_EVENT)


# ---------------------------------------------------------------------------
# Transcript / Earnings Call — management_claims.json
# ---------------------------------------------------------------------------

def _load_transcript_evidence(
    company: str, period: str, artifact_dir: Path
) -> List[MultiSourceEvidence]:
    data = safe_json_load(artifact_dir / "management_claims.json")
    if not data:
        return []
    fiscal_year = data.get("fiscal_year", period)
    source_period = data.get("source_period", period)
    items = []
    for claim in data.get("claims", []):
        raw_text = claim.get("raw_text", "").strip()
        if not raw_text:
            continue
        theme = classify_theme(raw_text)
        if not theme:
            continue
        slug, label, domain = theme
        claim_type = claim.get("claim_type", "FACTUAL_STATEMENT")
        speaker = claim.get("normalized_speaker") or claim.get("speaker")
        items.append(MultiSourceEvidence(
            evidence_id=claim.get("claim_id") or _uid(f"transcript:{period}", raw_text),
            company=company,
            fiscal_year=fiscal_year,
            source_period=source_period,
            source_type="EARNINGS_CALL_TRANSCRIPT",
            authority=SourceAuthority.TRANSCRIPT,
            claim_domain=domain,
            theme_slug=slug,
            claim_type=claim_type,
            speaker=speaker,
            speaker_role=claim.get("speaker_role"),
            text=raw_text,
            qualifiers=claim.get("qualifiers", []),
            target_period=claim.get("target_period"),
            provenance={"document_hash": artifact_dir.name, "source_period": source_period},
        ))
    return items


# ---------------------------------------------------------------------------
# Exchange Disclosures — disclosure_events.json
# ---------------------------------------------------------------------------

def _load_disclosure_evidence(
    company: str, period: str, artifact_dir: Path
) -> List[MultiSourceEvidence]:
    data = safe_json_load(artifact_dir / "disclosure_events.json")
    if not data:
        return []
    source_period = data.get("source_period", data.get("filing_date", period))
    fiscal_year = data.get("fiscal_year") or period
    # records key (Phase 8.1 schema); fall back to events for future schemas
    records = data.get("records") or data.get("events", [])
    items = []
    for rec in records:
        raw_text = rec.get("raw_text", "").strip()
        if not raw_text:
            # Reconstruct from structured fields
            parts = []
            if rec.get("event_type"):
                parts.append(rec["event_type"].replace("_", " ").lower())
            if rec.get("executives"):
                parts.append(", ".join(rec["executives"]))
            raw_text = " ".join(filter(None, parts))
        if not raw_text:
            continue
        # For disclosures, default to leadership_change if theme unrecognised
        match = classify_theme(raw_text)
        if match:
            slug, label, domain = match
        else:
            slug, label, domain = (
                "leadership_change",
                "Leadership / Executive Change",
                ClaimDomain.FACTUAL_EVENT,
            )
        items.append(MultiSourceEvidence(
            evidence_id=rec.get("record_id") or rec.get("event_id") or _uid(f"disclosure:{period}", raw_text[:80]),
            company=company,
            fiscal_year=fiscal_year,
            source_period=source_period,
            source_type="EXCHANGE_DISCLOSURE",
            authority=SourceAuthority.EXCHANGE_DISCLOSURE,
            claim_domain=domain,
            theme_slug=slug,
            claim_type=rec.get("event_type", "FACTUAL_EVENT"),
            speaker=None,
            speaker_role=None,
            text=raw_text[:500],
            qualifiers=[],
            target_period=None,
            provenance={"document_hash": artifact_dir.name, "event_status": rec.get("event_status")},
        ))
    return items


# ---------------------------------------------------------------------------
# Investor Presentation — chunks / extracted facts
# ---------------------------------------------------------------------------

def _load_presentation_evidence(
    company: str, period: str, artifact_dir: Path
) -> List[MultiSourceEvidence]:
    # Primary: presentation_chunks.json (chunked text with financial content)
    data = safe_json_load(artifact_dir / "presentation_chunks.json")
    if not data:
        return []
    source_period = data.get("source_period", period)
    fiscal_year = data.get("year") or data.get("fiscal_year") or period
    items = []
    for chunk in data.get("chunks", []):
        raw_text = chunk.get("text", "").strip()
        if not raw_text or len(raw_text) < 25:
            continue
        theme = classify_theme(raw_text)
        if not theme:
            continue
        slug, label, domain = theme
        items.append(MultiSourceEvidence(
            evidence_id=chunk.get("chunk_id") or _uid(f"presentation:{period}", raw_text[:80]),
            company=company,
            fiscal_year=fiscal_year,
            source_period=source_period,
            source_type="INVESTOR_PRESENTATION",
            authority=SourceAuthority.INVESTOR_PRESENTATION,
            claim_domain=domain,
            theme_slug=slug,
            claim_type="FINANCIAL_STATEMENT" if any(
                kw in raw_text for kw in ["₹", "Mn", "Cr", "%", "Growth", "Margin"]
            ) else "FACTUAL_STATEMENT",
            speaker=None,
            speaker_role=None,
            text=raw_text[:400],
            qualifiers=[],
            target_period=None,
            provenance={"document_hash": artifact_dir.name, "page": chunk.get("page")},
        ))
    return items


# ---------------------------------------------------------------------------
# Earnings Release — release_chunks.json + management_claims.json
# ---------------------------------------------------------------------------

def _load_earnings_release_evidence(
    company: str, period: str, artifact_dir: Path
) -> List[MultiSourceEvidence]:
    items: List[MultiSourceEvidence] = []

    # management claims (structured)
    mc = safe_json_load(artifact_dir / "management_claims.json")
    if mc:
        source_period = mc.get("source_period", period)
        for claim in mc.get("claims", []):
            raw_text = claim.get("raw_text", "").strip()
            if not raw_text:
                continue
            theme = classify_theme(raw_text)
            if not theme:
                continue
            slug, label, domain = theme
            items.append(MultiSourceEvidence(
                evidence_id=claim.get("claim_id") or _uid(f"er-claims:{period}", raw_text),
                company=company,
                fiscal_year=period,
                source_period=source_period,
                source_type="EARNINGS_RELEASE",
                authority=SourceAuthority.EARNINGS_RELEASE,
                claim_domain=domain,
                theme_slug=slug,
                claim_type=claim.get("claim_type", "FACTUAL_STATEMENT"),
                speaker=claim.get("speaker"),
                speaker_role=claim.get("speaker_role"),
                text=raw_text[:400],
                qualifiers=claim.get("qualifiers", []),
                target_period=claim.get("target_period"),
                provenance={"document_hash": artifact_dir.name},
            ))

    # release chunks (full text blocks)
    rc = safe_json_load(artifact_dir / "release_chunks.json")
    if rc:
        source_period = rc.get("source_period", period)
        for chunk in rc.get("chunks", []):
            raw_text = chunk.get("text", "").strip()
            if not raw_text or len(raw_text) < 30:
                continue
            theme = classify_theme(raw_text)
            if not theme:
                continue
            slug, label, domain = theme
            items.append(MultiSourceEvidence(
                evidence_id=_uid(f"er-chunk:{period}", raw_text[:80]),
                company=company,
                fiscal_year=period,
                source_period=source_period,
                source_type="EARNINGS_RELEASE",
                authority=SourceAuthority.EARNINGS_RELEASE,
                claim_domain=domain,
                theme_slug=slug,
                claim_type="FINANCIAL_STATEMENT" if any(
                    kw in raw_text for kw in ["₹", "%", "Cr", "Mn", "revenue", "profit"]
                ) else "FACTUAL_STATEMENT",
                speaker=None,
                speaker_role=None,
                text=raw_text[:400],
                qualifiers=[],
                target_period=None,
                provenance={"document_hash": artifact_dir.name, "page": chunk.get("page")},
            ))

    return items


# ---------------------------------------------------------------------------
# Quarterly Report — quarterly_chunks.json
# ---------------------------------------------------------------------------

def _load_quarterly_evidence(
    company: str, period: str, quarter_dir: Path
) -> List[MultiSourceEvidence]:
    data = safe_json_load(quarter_dir / "quarterly_chunks.json")
    if not data:
        return []
    year = data.get("year", period)
    items = []
    for chunk in data.get("chunks", []):
        raw_text = chunk.get("text", "").strip()
        if not raw_text or len(raw_text) < 30:
            continue
        theme = classify_theme(raw_text)
        if not theme:
            continue
        slug, label, domain = theme
        items.append(MultiSourceEvidence(
            evidence_id=chunk.get("chunk_id") or _uid(f"quarterly:{period}", raw_text[:80]),
            company=company,
            fiscal_year=year,
            source_period=period,
            source_type="QUARTERLY_REPORT",
            authority=SourceAuthority.QUARTERLY_REPORT,
            claim_domain=domain,
            theme_slug=slug,
            claim_type="FINANCIAL_STATEMENT" if any(
                kw in raw_text for kw in ["₹", "%", "Cr", "Mn", "revenue", "profit", "EBITDA"]
            ) else "FACTUAL_STATEMENT",
            speaker=None,
            speaker_role=None,
            text=raw_text[:400],
            qualifiers=[],
            target_period=None,
            provenance={"quarter_dir": str(quarter_dir), "page": chunk.get("page")},
        ))
    return items


# ---------------------------------------------------------------------------
# Annual Report — management promises from company_intelligence.json
# ---------------------------------------------------------------------------

def _load_annual_evidence(
    company: str, period: str, intel_dir: Path
) -> List[MultiSourceEvidence]:
    data = safe_json_load(intel_dir / "company_intelligence.json")
    if not data:
        return []
    items = []
    promises = (
        data.get("management", {}).get("promises", {}).get("items", [])
    )
    for i, p in enumerate(promises):
        raw_text = p.get("promise") or p.get("value", "")
        if not raw_text:
            continue
        theme = classify_theme(raw_text) or (
            "profitability",
            "Profitability / Cash Flow",
            ClaimDomain.COMMITMENT,
        )
        slug, label, domain = theme
        items.append(MultiSourceEvidence(
            evidence_id=f"annual:{period}:promise:{i:04d}",
            company=company,
            fiscal_year=period,
            source_period=period,
            source_type="ANNUAL_REPORT",
            authority=SourceAuthority.ANNUAL_REPORT,
            claim_domain=domain,
            theme_slug=slug,
            claim_type="COMMITMENT",
            speaker=p.get("actor"),
            speaker_role=None,
            text=raw_text,
            qualifiers=[],
            target_period=p.get("timeline"),
            provenance={"source_dir": str(intel_dir)},
        ))
    return items


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def aggregate(company: str, company_root: Path) -> List[MultiSourceEvidence]:
    """Load all processor outputs and return normalised evidence atoms."""
    evidence: List[MultiSourceEvidence] = []

    for period, artifact_dir in earnings_call_dirs(company_root):
        evidence.extend(_load_transcript_evidence(company, period, artifact_dir))

    for period, artifact_dir in exchange_disclosure_dirs(company_root):
        evidence.extend(_load_disclosure_evidence(company, period, artifact_dir))

    for period, artifact_dir in presentation_dirs(company_root):
        evidence.extend(_load_presentation_evidence(company, period, artifact_dir))

    for period, artifact_dir in earnings_release_dirs(company_root):
        evidence.extend(_load_earnings_release_evidence(company, period, artifact_dir))

    for period, quarter_dir in quarterly_report_dirs(company_root):
        evidence.extend(_load_quarterly_evidence(company, period, quarter_dir))

    for period, intel_dir in annual_intelligence_dirs(company_root):
        evidence.extend(_load_annual_evidence(company, period, intel_dir))

    return evidence
