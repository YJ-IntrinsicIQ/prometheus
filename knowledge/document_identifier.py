"""Phase 2 Document Intake — Content-Based Document Identification.

Single entry point:
    identify_document(path) -> DocumentIntakeManifest

Pipeline stages (executed in order):
  S1  File validation       — exists, readable, MIME from extension
  S2  Content hash          — sha256 via compute_content_hash
  S3  Content probe         — lightweight text from first pages/headers only
  S4  Company identification — content → canonical company key (no LLM)
  S5  Source-type classifier — multi-signal classification (7+ source types)
  S6  Reporting period       — fiscal year + quarter from content + filename
  S7  Document dates         — publication / filing / event dates from content
  S8  Entity scope           — CONSOLIDATED / STANDALONE from content keywords
  S9  Language detection     — basic character-set analysis
  S10 Confidence engine      — per-field HIGH/MEDIUM/LOW/UNKNOWN
  S11 Manifest construction  — assemble and validate DocumentIntakeManifest

Design principles:
  - Filename is evidence at most, never identity authority.
  - No LLM dependency. No company-specific rules.
  - Every detected field has an IdentityEvidence record (excerpt + page + method).
  - Contradictory signals are recorded as warnings and reduce confidence.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import fitz
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False

from knowledge.document_intake import (
    ClassificationState,
    ClassificationStatus,
    CompanyIdentity,
    ConfidenceLevel,
    DocumentDates,
    DocumentIdentity,
    DocumentIntakeManifest,
    DetectionMethod,
    EntityScope,
    FileIdentity,
    FiscalQuarter,
    IdentityEvidence,
    IntakeProvenance,
    ReportingPeriod,
    SourceChannel,
    SourceType,
    compute_content_hash,
)
from knowledge.document_ownership import infer_document_reporting_period

IDENTIFIER_VERSION = "document_identifier.v4"
CONTENT_PROBE_MAX_PAGES = 5
CONTENT_PROBE_MAX_CHARS = 5000
CONTENT_PROBE_WRAPPER_PAGES = 1   # Pages checked for exchange-filing wrapper (cover letter = page 1)
CONTENT_PROBE_PAYLOAD_PAGES = 8   # Total pages probed when wrapper is detected
IDENTITY_TRAILER_PAGES = 2        # Pages read from the END for corporate identity signals


# ── Stage helpers ─────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


def _evidence(
    field: str,
    excerpt: str,
    confidence: ConfidenceLevel,
    page: Optional[int] = None,
    method: str = "content_scan",
) -> IdentityEvidence:
    return IdentityEvidence(
        field=field,
        excerpt=excerpt[:300],
        confidence=confidence,
        source_artifact=IDENTIFIER_VERSION,
        page=page,
        chunk_id="",
        evidence_id=f"{field}:{method}",
    )


def _mime_from_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".txt", ".md"}:
        return "text/plain"
    return "application/octet-stream"


# ── S3: Content probe ─────────────────────────────────────────────────────────

def _probe_content(path: Path, max_pages: int = CONTENT_PROBE_MAX_PAGES) -> Tuple[str, str]:
    """Return (text, probe_description). Reads first max_pages pages only.

    For text files, reads up to CONTENT_PROBE_MAX_CHARS characters.
    For PDFs, reads first max_pages pages via fitz.
    Returns ("", "no_text") when extraction is not possible.
    """
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            return raw[:CONTENT_PROBE_MAX_CHARS], f"text_file:chars_{min(CONTENT_PROBE_MAX_CHARS, len(raw))}"
        except OSError:
            return "", "read_error"

    if suffix == ".pdf":
        if not _FITZ_AVAILABLE:
            return "", "fitz_unavailable"
        try:
            doc = fitz.open(path)
            pages_to_read = min(max_pages, doc.page_count)
            texts: List[str] = []
            for i in range(pages_to_read):
                page = doc.load_page(i)
                page_text = _clean(page.get_text("text"))
                if page_text:
                    texts.append(page_text)
            doc.close()
            combined = " ".join(texts)
            return combined[:CONTENT_PROBE_MAX_CHARS], f"pdf:pages_1_to_{pages_to_read}"
        except Exception:
            return "", "pdf_read_error"

    return "", "unsupported_format"


def _probe_pages(path: Path, start_idx: int, end_idx: int) -> str:
    """Extract text from a PDF page range (0-indexed, end exclusive)."""
    if not _FITZ_AVAILABLE or path.suffix.lower() != ".pdf":
        return ""
    try:
        doc = fitz.open(path)
        texts: List[str] = []
        for i in range(start_idx, min(end_idx, doc.page_count)):
            page = doc.load_page(i)
            page_text = _clean(page.get_text("text"))
            if page_text:
                texts.append(page_text)
        doc.close()
        return " ".join(texts)[:CONTENT_PROBE_MAX_CHARS]
    except Exception:
        return ""


def _probe_content_adaptive(path: Path) -> Tuple[str, str, str]:
    """Probe document content with wrapper/payload separation.

    Returns:
        (wrapper_text, payload_text, desc)
        wrapper_text: first CONTENT_PROBE_WRAPPER_PAGES pages — for channel detection
        payload_text: pages [CONTENT_PROBE_WRAPPER_PAGES, CONTENT_PROBE_PAYLOAD_PAGES) —
                      for source-type classification when wrapper is detected
        desc:         probe description string
    """
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md"}:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            text = raw[:CONTENT_PROBE_MAX_CHARS]
            return text, "", f"text_file:chars_{len(text)}"
        except OSError:
            return "", "", "read_error"

    if suffix == ".pdf":
        if not _FITZ_AVAILABLE:
            return "", "", "fitz_unavailable"
        try:
            doc = fitz.open(path)
            page_texts: List[str] = []
            pages_to_read = min(CONTENT_PROBE_PAYLOAD_PAGES, doc.page_count)
            for i in range(pages_to_read):
                page = doc.load_page(i)
                page_texts.append(_clean(page.get_text("text")))
            doc.close()

            wrapper_pages = page_texts[:CONTENT_PROBE_WRAPPER_PAGES]
            payload_pages = page_texts[CONTENT_PROBE_WRAPPER_PAGES:]

            wrapper_text = " ".join(t for t in wrapper_pages if t)[:CONTENT_PROBE_MAX_CHARS]
            payload_text = " ".join(t for t in payload_pages if t)[:CONTENT_PROBE_MAX_CHARS]
            return wrapper_text, payload_text, f"pdf:pages_1_to_{pages_to_read}"
        except Exception:
            return "", "", "pdf_read_error"

    return "", "", "unsupported_format"


def _probe_identity_trailer(path: Path, max_pages: int = IDENTITY_TRAILER_PAGES) -> str:
    """Read the last max_pages of a PDF for corporate identity signals.

    Indian corporate filings routinely place the company registration block —
    legal name, CIN, corporate website domain, registered address — on the
    final page(s) or back cover.  This trailer probe is separate from the main
    content probe so the identity signal can strengthen company confidence
    without expanding the classification-probe window (D3 deferred).

    Returns empty string for non-PDF files, when fitz is unavailable, or on
    any read error — callers must treat "" as "no additional evidence".
    """
    if path.suffix.lower() != ".pdf":
        return ""
    if not _FITZ_AVAILABLE:
        return ""
    try:
        doc = fitz.open(path)
        total = doc.page_count
        start = max(0, total - max_pages)
        parts = [_clean(doc.load_page(i).get_text("text")) for i in range(start, total)]
        doc.close()
        return " ".join(p for p in parts if p)[:CONTENT_PROBE_MAX_CHARS]
    except Exception:
        return ""


# CIN detection pattern: 21-char Indian Corporate Identity Number (L/U prefix)
_CIN_PATTERN = re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b", re.IGNORECASE)


def _detect_exchange_wrapper(first_pages_text: str) -> bool:
    """Return True when the first pages show a BSE/NSE exchange-filing cover letter."""
    score, _ = _score_signals(first_pages_text, _EXCHANGE_WRAPPER_SIGNALS)
    return score >= _EXCHANGE_WRAPPER_THRESHOLD


def _extract_legal_company_name(text: str) -> str:
    """Extract the most prominent Indian corporate legal name from document text.

    Searches the title zone first (first 800 chars), then falls back to the
    first 2000 chars.  Returns empty string when nothing useful is found.
    No company-specific rules — purely structural pattern matching.
    """
    if not text:
        return ""
    for search_text in (text[:800], text[:2000]):
        m = _LEGAL_NAME_PATTERN.search(search_text)
        if m:
            name = m.group(1).strip()
            if len(name) >= 6:  # Reject trivial matches like bare "Ltd."
                return name
    return ""


# ── S4: Company registry + identification ─────────────────────────────────────

def _slug_to_name_variants(slug: str) -> List[str]:
    """Derive candidate name tokens from a company slug. No company-specific logic."""
    slug_lower = slug.lower()
    variants: List[str] = [slug_lower]
    spaced = slug_lower.replace("_", " ")
    if spaced != slug_lower:
        variants.append(spaced)
    words = [w for w in slug_lower.split("_") if len(w) >= 3]
    variants.extend(words)
    return list(dict.fromkeys(variants))


def _build_company_registry(companies_root: Path) -> Dict[str, List[str]]:
    """Scan companies_root directory to build {slug: [name_variants]}.

    Reads company_model.json and company_names.json for legally-recorded name hints.
    All name variants are lowercased for matching.

    company_names.json schema (operator-managed, lives at companies/<slug>/company_names.json):
        {
            "legal_names": ["Data Patterns (India) Limited"],
            "short_names":  ["Data Patterns"],
            "aliases":      ["data patterns india limited", "dpil"]
        }
    Any of these keys may be absent.  All values are added as lowercased variants.
    """
    registry: Dict[str, List[str]] = {}
    if not companies_root.exists():
        return registry

    for slug_dir in sorted(companies_root.iterdir()):
        if not slug_dir.is_dir() or slug_dir.name.startswith("."):
            continue
        slug = slug_dir.name
        variants = _slug_to_name_variants(slug)

        # company_model.json — legacy source for legal/display name
        model_path = slug_dir / "company_memory" / "company_model" / "company_model.json"
        if model_path.exists():
            try:
                data: Any = json.loads(model_path.read_text(encoding="utf-8"))
                identity = data.get("company_identity") or {}
                for key in ("legal_name", "name"):
                    val = str(identity.get(key) or "").strip().lower()
                    if val and val not in variants and val != slug:
                        variants.append(val)
            except Exception:
                pass

        # company_names.json — canonical operator-managed name registry
        names_path = slug_dir / "company_names.json"
        if names_path.exists():
            try:
                names_data: Any = json.loads(names_path.read_text(encoding="utf-8"))
                for key in ("legal_names", "short_names", "aliases"):
                    for entry in names_data.get(key) or []:
                        val = str(entry).strip().lower()
                        if val and val not in variants and val != slug:
                            variants.append(val)
            except Exception:
                pass

        registry[slug] = list(dict.fromkeys(variants))

    return registry


def _score_company_match(
    text_lower: str,
    title_zone: str,
    variants: List[str],
    trailer_lower: str = "",
) -> int:
    """Return a match score for this company's variants against the document text.

    Scoring (main probe):
      +3 per variant found in title zone (first 500 chars of combined probe)
      +1 per variant found anywhere in the main probe text
      +2 bonus when compound slug (multi-word) matches as a phrase

    Scoring (identity trailer — last IDENTITY_TRAILER_PAGES pages):
      +3 corporate website domain: www.{slug}.com or email @{slug}.domain
          Domain anchors issuer identity; only the document owner prints their
          own domain on the back cover / registration block.
      +2 legal name block: variant near "Limited"/"Ltd" in trailer text
          Finds the company's own registration entry when it is placed on the
          final pages rather than page 1 (common in quarterly / shareholder letters).
      +2 CIN present in trailer alongside a variant match
          Adds confirmation when the Indian Corporate Identity Number co-occurs
          with the company name in the corporate-identity block.

    Each trailer bonus category is applied at most once per company to prevent
    runaway inflation from repeated footer text.
    """
    score = 0

    for variant in variants:
        if not variant:
            continue
        if variant in title_zone:
            score += 3
        elif variant in text_lower:
            score += 1
        # Compound phrase bonus: multi-word variant matches as a phrase
        words = variant.split()
        if len(words) >= 2:
            pattern = r"\b" + r"\W+".join(re.escape(w) for w in words) + r"\b"
            if re.search(pattern, text_lower):
                score += 2

    if not trailer_lower:
        return score

    # ── Trailer bonuses ───────────────────────────────────────────────────────
    # Build compact forms (strip spaces/underscores/hyphens) for domain matching.
    # Require len >= 4 to avoid false positives from short words ("sun", "air").
    domain_scored = False
    legal_name_scored = False
    cin_scored = False
    has_cin_in_trailer = bool(_CIN_PATTERN.search(trailer_lower))

    for variant in variants:
        if not variant or len(variant) < 4:
            continue
        compact = re.sub(r"[\s_\-]", "", variant)  # "sun pharma" → "sunpharma"

        # Corporate domain: www.{compact}.com or @{compact}.  (email domain)
        if not domain_scored:
            if f"www.{compact}.com" in trailer_lower or f"@{compact}." in trailer_lower:
                score += 3
                domain_scored = True

        # Legal name block: variant + within 80 chars + corporate suffix
        if not legal_name_scored:
            legal_re = re.compile(
                r"\b" + re.escape(variant) + r"[\w\s,\.]{0,80}(?:limited|ltd\.?|private)\b",
                re.IGNORECASE,
            )
            if legal_re.search(trailer_lower):
                score += 2
                legal_name_scored = True
                # CIN co-occurrence: CIN appears in trailer alongside this legal name
                if has_cin_in_trailer and not cin_scored:
                    score += 2
                    cin_scored = True

    return score


def _identify_company(
    probe_text: str,
    registry: Dict[str, List[str]],
    trailer_text: str = "",
) -> Tuple[Optional[str], ConfidenceLevel, List[IdentityEvidence]]:
    """Match probe text against company registry.

    Returns (resolved_slug, confidence, evidence_list).
    Confidence:
      HIGH   — winning score ≥ 6, and no tie
      MEDIUM — winning score 3–5, and no tie
      LOW    — winning score 1–2, OR any tie
      UNKNOWN — no match (score 0)

    trailer_text: optional text from the last IDENTITY_TRAILER_PAGES of the
    document (identity trailer probe).  When provided, corporate domain, legal
    name, and CIN signals from the trailer contribute to the score.
    """
    if not probe_text or not registry:
        return None, ConfidenceLevel.UNKNOWN, []

    text_lower = probe_text.lower()
    title_zone = text_lower[:500]
    trailer_lower = trailer_text.lower() if trailer_text else ""

    scores: Dict[str, int] = {}
    for slug, variants in registry.items():
        scores[slug] = _score_company_match(text_lower, title_zone, variants, trailer_lower)

    best_slug = max(scores, key=lambda s: scores[s])
    best_score = scores[best_slug]

    if best_score == 0:
        return None, ConfidenceLevel.UNKNOWN, []

    # Check for a tie (two companies with equal score) → reduce confidence
    tied = [s for s, sc in scores.items() if sc == best_score and s != best_slug]
    has_tie = len(tied) > 0

    if best_score >= 6 and not has_tie:
        confidence = ConfidenceLevel.HIGH
    elif best_score >= 3 and not has_tie:
        confidence = ConfidenceLevel.MEDIUM
    elif has_tie:
        confidence = ConfidenceLevel.LOW
    else:
        confidence = ConfidenceLevel.LOW

    # Find the matched variant for the excerpt
    matched_variant = next(
        (v for v in registry.get(best_slug, []) if v in text_lower),
        best_slug,
    )
    # Find where in the text it was found
    idx = text_lower.find(matched_variant)
    excerpt_start = max(0, idx - 30)
    excerpt = probe_text[excerpt_start: idx + len(matched_variant) + 60]

    ev = _evidence(
        "company_identity.resolved_company_key",
        excerpt,
        confidence,
        page=1,
        method="registry_content_scan",
    )

    if has_tie:
        ev = _evidence(
            "company_identity.resolved_company_key",
            f"Tied score {best_score} between {best_slug} and {', '.join(tied)}. Matched: {excerpt}",
            confidence,
            page=1,
            method="registry_content_scan_tied",
        )

    return best_slug, confidence, [ev]


# ── S5: Source-type classifier ────────────────────────────────────────────────

_ANNUAL_REPORT_SIGNALS: List[Tuple[re.Pattern[str], int]] = [
    (re.compile(r"\bannual\s+report\b", re.IGNORECASE), 5),
    (re.compile(r"\bintegrated\s+report\b", re.IGNORECASE), 4),
    (re.compile(r"\bdirectors['']?\s+report\b", re.IGNORECASE), 3),
    (re.compile(r"\bboard\s+of\s+directors\b", re.IGNORECASE), 2),
    (re.compile(r"\b(standalone|consolidated)\s+financial\s+statements\b", re.IGNORECASE), 2),
    (re.compile(r"\bindependent\s+auditor['']?s?\s+report\b", re.IGNORECASE), 3),
]

_QUARTERLY_SIGNALS: List[Tuple[re.Pattern[str], int]] = [
    # Weight lowered to 4: "Q4 FY26 Results" appears in presentations too;
    # genuine quarterly filings also hit quarterly_results + quarter_ended + unaudited signals.
    (re.compile(r"\bq[1-4]\s+(fy)?\d{2,4}\s+results?\b", re.IGNORECASE), 4),
    (re.compile(r"\bquarterly\s+results?\b", re.IGNORECASE), 5),
    (re.compile(r"\bquarter\s+ended\b", re.IGNORECASE), 4),
    (re.compile(r"\bunaudited\s+(standalone|consolidated)\b", re.IGNORECASE), 3),
    (re.compile(r"\blimited\s+review\b", re.IGNORECASE), 3),
    # Broader quarterly-filing formats used by company-issued shareholder reports:
    # "Quarterly Disclosures" is a statutory section heading specific to periodic results.
    (re.compile(r"\bquarterly\s+disclosures?\b", re.IGNORECASE), 4),
    # "Three months ended" is the standard Ind AS period header for a condensed quarterly P&L.
    (re.compile(r"\bthree\s+months\s+ended\b", re.IGNORECASE), 4),
]

_PRESENTATION_SIGNALS: List[Tuple[re.Pattern[str], int]] = [
    (re.compile(r"\binvestor\s+presentation\b", re.IGNORECASE), 6),
    # "Investor Update" is filed by Indian companies via BSE/NSE under Reg 30;
    # it is a presentation/slide-deck format, not a formal quarterly results filing.
    (re.compile(r"\binvestor\s+update\b", re.IGNORECASE), 6),
    (re.compile(r"\binvestor\s+day\b", re.IGNORECASE), 5),
    (re.compile(r"\banalyst\s+(meet|meeting|day)\b", re.IGNORECASE), 5),
    (re.compile(r"\bearnings\s+presentation\b", re.IGNORECASE), 4),
    (re.compile(r"\bSlide\s+\d+\b", re.IGNORECASE), 2),
]

_EARNINGS_RELEASE_SIGNALS: List[Tuple[re.Pattern[str], int]] = [
    (re.compile(r"\bpress\s+release\b", re.IGNORECASE), 7),
    (re.compile(r"\bearnings\s+release\b", re.IGNORECASE), 7),
    (re.compile(r"\bresults?\s+release\b", re.IGNORECASE), 6),
    (re.compile(r"\binvestor\s+release\b", re.IGNORECASE), 5),
    (re.compile(r"\bfinancial\s+(?:results?\s+)?highlights\b", re.IGNORECASE), 4),
    (re.compile(r"\bmedia\s+release\b", re.IGNORECASE), 4),
    (re.compile(r"\bannounced\s+its\s+results?\s+for\s+the\s+(?:first|second|third|fourth|quarter)\b", re.IGNORECASE), 5),
    (re.compile(r"\b(?:ceo|cfo|managing\s+director).{0,80}\bsaid\b", re.IGNORECASE | re.DOTALL), 3),
    (re.compile(r"\bhighlights\s+for\s+q[1-4]\s*fy\d{2,4}\s+include\b", re.IGNORECASE), 5),
]

_TRANSCRIPT_SIGNALS: List[Tuple[re.Pattern[str], int]] = [
    # Definitive transcript labels
    (re.compile(r"\bearnings\s+call\s+transcript\b", re.IGNORECASE), 7),
    (re.compile(r"\bconference\s+call\s+transcript\b", re.IGNORECASE), 7),
    # Operator/moderator phrases that only appear in call transcripts
    (re.compile(r"\byour\s+next\s+question\s+(?:is\s+)?(?:comes?\s+)?from\b", re.IGNORECASE), 7),
    (re.compile(r"\boperator\s*:", re.IGNORECASE), 5),
    (re.compile(r"\bmoderw?ator\s*:", re.IGNORECASE), 5),
    # Structural section markers
    (re.compile(r"\bprepared\s+remarks\b", re.IGNORECASE), 6),
    (re.compile(r"\bquestion[\s\-]+and[\s\-]+answer\s+session\b", re.IGNORECASE), 6),
    (re.compile(r"\bq\s*&\s*a\s+session\b", re.IGNORECASE), 5),
    # Participant list header (nearly exclusive to transcripts)
    (re.compile(r"^participants\s*:?\s*$", re.IGNORECASE | re.MULTILINE), 5),
    # Opening greeting specific to call transcripts
    (re.compile(r"\bgood\s+(?:morning|afternoon|evening)[,.]?\s+(?:ladies|everyone|participants)\b", re.IGNORECASE), 5),
    # General earnings-call language (weaker — also present in presentations)
    (re.compile(r"\bearnings\s+call\b", re.IGNORECASE), 4),
    (re.compile(r"\bconcall\b", re.IGNORECASE), 4),
    (re.compile(r"\bconference\s+call\b", re.IGNORECASE), 3),
    # NOTE: "management discussion and analysis" deliberately omitted — it is an
    # annual-report section header and would produce false positives for transcripts.
]

_DISCLOSURE_SIGNALS: List[Tuple[re.Pattern[str], int]] = [
    # Outcome of board meeting — strongest exclusive signal
    (re.compile(r"\boutcome\s+of\s+(the\s+)?board\s+meeting\b", re.IGNORECASE), 8),
    # Canonical Regulation 30 read-with phrasing — only appears in event disclosures,
    # not in annual-report cover letters (which cite Regulation 34).
    (re.compile(r"\bregulation\s+30\s+read\s+with\b", re.IGNORECASE), 9),
    # Change in management personnel — SE Intimation subject-line pattern
    (re.compile(r"\bchange\s+in\s+(?:senior\s+management|key\s+managerial|directors?)\b", re.IGNORECASE), 7),
    # SE Intimation / exchange intimation — specific to event-centric filings
    (re.compile(r"\b(?:se|stock\s+exchange)\s+intimation\b|\bintimation\s+(?:of|under|pursuant)\b", re.IGNORECASE), 6),
    # Specific event types
    (re.compile(r"\border\s+(award|win|receiv|secur)\b", re.IGNORECASE), 6),
    (re.compile(r"\bcontract\s+(award|signing|execution)\b", re.IGNORECASE), 6),
    (re.compile(r"\bacquisition\s+of\b|\bacquires?\b", re.IGNORECASE), 6),
    (re.compile(r"\bappointment\s+of\s+(managing\s+director|ceo|cfo|director)\b", re.IGNORECASE), 6),
    (re.compile(r"\bcessation\s+of\b|\bresignation\s+of\b", re.IGNORECASE), 6),
    # Resignation / appointment in SMP context — broad enough to catch "has resigned"
    (re.compile(r"\b(?:chief\s+\w+\s+officer|managing\s+director)\b.{0,80}(?:resign|appoint|cessat)", re.IGNORECASE | re.DOTALL), 6),
    (re.compile(r"\bcredit\s+rating\s+(assigned|reaffirmed|upgraded|downgraded)\b", re.IGNORECASE), 6),
    (re.compile(r"\bregulatory\s+appro(val|ved)\b", re.IGNORECASE), 5),
    # Board meeting / SEBI regulation 30 disclosure
    (re.compile(r"\bpursuant\s+to\s+regulation\s+30\b", re.IGNORECASE), 7),
    (re.compile(r"\bmaterial\s+(information|event|development)\b", re.IGNORECASE), 5),
    (re.compile(r"\bpreferred\s+allotment\b|\bright\s+issue\b|\bqip\b", re.IGNORECASE), 5),
    # Negative signals: these phrases are common in periodic reports but rare in
    # standalone event disclosures.  They are not applied here — over-penalisation
    # risks false negatives for disclosures that mention the current quarter.
]

_EXCHANGE_FILING_SIGNALS: List[Tuple[re.Pattern[str], int]] = [
    (re.compile(r"\bregulation\s+34\b", re.IGNORECASE), 5),
    (re.compile(r"\bsebi\s*\(\s*lodr\s*\)", re.IGNORECASE), 5),
    (re.compile(r"\b(bse|nse)\s+(limited|india)\b", re.IGNORECASE), 4),
    (re.compile(r"\blisting\s+(department|compliance)\b", re.IGNORECASE), 4),
    (re.compile(r"\bpursuant\s+to\s+regulation\b", re.IGNORECASE), 3),
    (re.compile(r"\bstock\s+exchange\b", re.IGNORECASE), 2),
]

# Wrapper-detection signals: applied to the FIRST pages only to decide whether
# this is a BSE/NSE submission cover letter wrapping the real document.
_EXCHANGE_WRAPPER_SIGNALS: List[Tuple[re.Pattern[str], int]] = [
    (re.compile(r"\bregulation\s+3[04]\b", re.IGNORECASE), 6),
    (re.compile(r"\bsebi\s*\(\s*lodr\s*\)", re.IGNORECASE), 5),
    (re.compile(r"\bplease\s+find\s+(enclosed|attached|herewith)\b", re.IGNORECASE), 4),
    # "we are enclosing herewith" / "attaching herewith" — alternate phrasing used
    # by many Indian companies in BSE/NSE cover letters without "please find".
    (re.compile(r"\b(enclosing|attaching|submitting)\s+herewith\b", re.IGNORECASE), 4),
    (re.compile(r"\blisting\s+(department|compliance)\b", re.IGNORECASE), 3),
    (re.compile(r"\b(bse|nse)\s+(limited|india)\b", re.IGNORECASE), 3),
    (re.compile(r"\bnational\s+stock\s+exchange\b", re.IGNORECASE), 3),
]
_EXCHANGE_WRAPPER_THRESHOLD = 8

# Pattern for extracting Indian corporate legal names from document text.
_LEGAL_NAME_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z&()\'. ]{2,60}"
    r"(?:Private\s+Limited|Pvt\.?\s*Ltd\.?|Limited|Ltd\.?))\b"
)


def _score_signals(text: str, signals: List[Tuple[re.Pattern[str], int]]) -> Tuple[int, Optional[str]]:
    """Score text against a signal list. Returns (total_score, first_matched_excerpt)."""
    total = 0
    first_match: Optional[str] = None
    for pattern, weight in signals:
        m = pattern.search(text)
        if m:
            total += weight
            if first_match is None:
                start = max(0, m.start() - 20)
                first_match = text[start: m.end() + 40]
    return total, first_match


def _classify_source_type(
    probe_text: str,
    filename_stem: str,
) -> Tuple[SourceType, ConfidenceLevel, List[IdentityEvidence]]:
    """Multi-signal source type classification.

    Content is primary authority; filename contributes a small bonus only.
    Returns (source_type, confidence, evidence_list).
    """
    evidences: List[IdentityEvidence] = []
    combined = probe_text

    scores: Dict[str, Tuple[int, Optional[str]]] = {
        "annual": _score_signals(combined, _ANNUAL_REPORT_SIGNALS),
        "quarterly": _score_signals(combined, _QUARTERLY_SIGNALS),
        "presentation": _score_signals(combined, _PRESENTATION_SIGNALS),
        "earnings_release": _score_signals(combined, _EARNINGS_RELEASE_SIGNALS),
        "transcript": _score_signals(combined, _TRANSCRIPT_SIGNALS),
        "disclosure": _score_signals(combined, _DISCLOSURE_SIGNALS),
        "exchange_filing": _score_signals(combined, _EXCHANGE_FILING_SIGNALS),
    }

    # Filename bonus (max +2 per type — evidence only, not authority)
    fn_lower = filename_stem.lower()
    filename_bonuses: Dict[str, int] = {
        "annual": 2 if any(kw in fn_lower for kw in ("annual", "ar", "report")) else 0,
        "quarterly": 2 if any(kw in fn_lower for kw in ("q1", "q2", "q3", "q4", "quarterly", "qr")) else 0,
        "presentation": 2 if any(kw in fn_lower for kw in ("presentation", "investor", "analyst")) else 0,
        "earnings_release": 2 if any(kw in fn_lower for kw in ("release", "earnings", "results")) else 0,
        "transcript": 2 if any(kw in fn_lower for kw in ("transcript", "call", "concall")) else 0,
        "disclosure": 2 if any(kw in fn_lower for kw in ("disclosure", "bm", "board", "order", "award")) else 0,
        "exchange_filing": 2 if any(kw in fn_lower for kw in ("filing", "exchange", "bse", "nse")) else 0,
    }

    final_scores = {k: scores[k][0] + filename_bonuses[k] for k in scores}
    best_type = max(final_scores, key=lambda k: final_scores[k])
    best_score = final_scores[best_type]

    if best_score == 0:
        return SourceType.UNKNOWN, ConfidenceLevel.UNKNOWN, []

    source_type_map = {
        "annual": SourceType.ANNUAL_REPORT,
        "quarterly": SourceType.QUARTERLY_REPORT,
        "presentation": SourceType.INVESTOR_PRESENTATION,
        "earnings_release": SourceType.EARNINGS_RELEASE,
        "transcript": SourceType.EARNINGS_CALL_TRANSCRIPT,
        "disclosure": SourceType.EXCHANGE_DISCLOSURE,
        "exchange_filing": SourceType.EXCHANGE_FILING,
    }
    source_type = source_type_map.get(best_type, SourceType.OTHER)

    # Confidence by score magnitude and separation from runner-up
    sorted_scores = sorted(final_scores.values(), reverse=True)
    gap = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else sorted_scores[0]

    if best_score >= 8 and gap >= 3:
        confidence = ConfidenceLevel.HIGH
    elif best_score >= 4 and gap >= 2:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.LOW

    excerpt = scores[best_type][1] or ""
    ev = _evidence(
        "document_identity.source_type",
        f"[score:{best_score}] {excerpt}",
        confidence,
        page=1,
        method="multi_signal_classifier",
    )
    evidences.append(ev)

    return source_type, confidence, evidences


# ── S6: Reporting period detection ────────────────────────────────────────────

_DIRECT_FY_LABEL = re.compile(r"\bfy\s*(?P<year>\d{2,4})\b", re.IGNORECASE)

_QUARTER_PATTERNS: List[Tuple[re.Pattern[str], FiscalQuarter]] = [
    (re.compile(r"\bq1\b", re.IGNORECASE), FiscalQuarter.Q1),
    (re.compile(r"\bq2\b", re.IGNORECASE), FiscalQuarter.Q2),
    (re.compile(r"\bq3\b", re.IGNORECASE), FiscalQuarter.Q3),
    (re.compile(r"\bq4\b", re.IGNORECASE), FiscalQuarter.Q4),
    (re.compile(r"\bfirst\s+quarter\b", re.IGNORECASE), FiscalQuarter.Q1),
    (re.compile(r"\bsecond\s+quarter\b", re.IGNORECASE), FiscalQuarter.Q2),
    (re.compile(r"\bthird\s+quarter\b", re.IGNORECASE), FiscalQuarter.Q3),
    (re.compile(r"\bfourth\s+quarter\b", re.IGNORECASE), FiscalQuarter.Q4),
]

_INDIAN_FY_PATTERN = re.compile(
    r"\b(?P<start>20\d{2})\s*[-–]\s*(?P<end>\d{2}|20\d{2})\b"
)
_YEAR_END_MARCH = re.compile(
    r"\b(?:year|period)\s+ended\s+March\s+31(?:st)?,?\s+(?P<year>20\d{2})\b"
    r"|"
    r"\b(?:year|period)\s+ended\s+31(?:st)?\s+March\s*,?\s*(?P<year2>20\d{2})\b",
    re.IGNORECASE,
)

# Patterns indicating STRONG reporting-period semantic context (score +10)
_STRONG_PERIOD_CTX = re.compile(
    r"annual\s+report"
    r"|integrated\s+report"
    r"|financial\s+year"
    r"|for\s+the\s+(?:financial\s+)?year"
    r"|reporting\s+period"
    r"|year\s+ended"
    r"|half.{0,5}year\s+ended"
    r"|quarter\s+ended"
    r"|six\s+months\s+ended"
    r"|three\s+months\s+ended"
    r"|results?\s+for\s+the",
    re.IGNORECASE,
)

# Patterns indicating MEDIUM reporting-period context (score +3)
_MEDIUM_PERIOD_CTX = re.compile(
    r"revenue|profit|turnover|results?|earnings|balance\s+sheet|cash\s+flow",
    re.IGNORECASE,
)


def _is_filing_reference(probe_text: str, match: "re.Match[str]") -> bool:
    """True when an FY range is embedded in a filing serial or reference number.

    Detects generic slash-delimited identifiers such as CORP/CS/SE/2025-26/27
    without hardcoding any company prefix.  Two conditions must both hold:
      1. A forward-slash appears within 3 characters of the match boundary.
      2. At least 3 slashes exist in the 60-character window around the match,
         indicating a multi-segment path rather than an isolated slash.
    """
    start, end = match.start(), match.end()
    before = probe_text[max(0, start - 3) : start]
    after  = probe_text[end : min(len(probe_text), end + 3)]
    if "/" not in before and "/" not in after:
        return False
    window = probe_text[max(0, start - 40) : min(len(probe_text), end + 20)]
    return window.count("/") >= 3


def _score_fy_candidate(probe_text: str, match: "re.Match[str]") -> int:
    """Return a semantic strength score for a single Indian FY range match.

    Score semantics:
      +10  strong reporting-period phrase in context (Annual Report, Financial Year, …)
      +3   medium financial keyword in context (revenue, profit, results, …)
       0   bare year range with no contextual signal — usable but weak
      -100 embedded in a filing serial / reference number (slash-heavy path)

    The context window is ±100 characters around the match.
    """
    if _is_filing_reference(probe_text, match):
        return -100

    start, end = match.start(), match.end()
    ctx = probe_text[max(0, start - 100) : min(len(probe_text), end + 100)]

    if _STRONG_PERIOD_CTX.search(ctx):
        return 10
    if _MEDIUM_PERIOD_CTX.search(ctx):
        return 3
    return 0


def _select_best_fy_candidate(
    probe_text: str,
) -> "Optional[Tuple[str, str, str, bool]]":
    """Score all Indian FY range matches and return the best one.

    Returns (fy_str, basis_label, evidence_text, is_weak) where is_weak
    signals a filing-reference or no-context match.  Returns None when no
    match exists at all.

    A later strong candidate always outranks an earlier weak one.
    Filing references (score -100) lose to any non-filing match (score ≥ 0).
    If every match is a filing reference, the least-penalised one is returned
    as is_weak=True so the caller can add a warning.
    """
    matches = list(_INDIAN_FY_PATTERN.finditer(probe_text))
    if not matches:
        return None

    scored: List[Tuple[int, int, "re.Match[str]"]] = [
        (_score_fy_candidate(probe_text, m), m.start(), m) for m in matches
    ]
    # Highest score first; earlier position breaks ties.
    scored.sort(key=lambda x: (-x[0], x[1]))

    best_score, _, best_match = scored[0]
    end_str = best_match.group("end")
    fy_str = f"fy{end_str[-2:]}"

    if best_score >= 10:
        basis = "indian_fy_range_strong_context"
        is_weak = False
    elif best_score >= 0:
        basis = "indian_fy_range_pattern"
        is_weak = False
    else:
        basis = "indian_fy_range_filing_reference"
        is_weak = True

    return fy_str, basis, best_match.group(0), is_weak


def _detect_reporting_period(
    probe_text: str,
    filename: str,
    source_type: SourceType,
) -> Tuple[Optional[ReportingPeriod], List[str]]:
    """Detect fiscal year and quarter from content + filename.

    Indian fiscal year semantics: April to March.
    "2024-25" → FY25 (ending March 2025).

    Evidence precedence (highest first):
      1. infer_document_reporting_period — Annual Report heading + year range
      2. _YEAR_END_MARCH — explicit "year ended March 31, YYYY" phrase
      3. _select_best_fy_candidate — semantically scored Indian FY range matches
         (filing serial numbers are de-ranked; strong reporting-period phrases win)
      4. _DIRECT_FY_LABEL — bare "FY25" / "FY2025" label fallback
    """
    warnings: List[str] = []

    # Stage 1: existing document_ownership helper (Annual Report heading context)
    inferred = infer_document_reporting_period(probe_text, filename=filename)
    fy_str: Optional[str] = inferred.get("reporting_period") or None
    fy_basis: List[str] = inferred.get("basis") or []
    fy_evidence_texts: List[str] = inferred.get("evidence") or []

    # Stage 2: "year ended March" pattern (common in Indian filings)
    march_match = _YEAR_END_MARCH.search(probe_text)
    if march_match:
        raw_year = march_match.group("year") or march_match.group("year2")
        year_int = int(raw_year)
        fy_from_march = f"fy{str(year_int)[-2:]}"
        if not fy_str:
            fy_str = fy_from_march
            fy_basis = ["year_ended_march_pattern"]
            fy_evidence_texts = [march_match.group(0)]
        elif fy_str != fy_from_march:
            warnings.append(
                f"Reporting period conflict: {fy_str} from text vs "
                f"{fy_from_march} from year-ended-March pattern"
            )

    # Stage 3: semantically scored Indian FY range candidate selection.
    # Replaces the former "first match wins" approach.  Strong reporting-period
    # context (Annual Report, Financial Year, …) outranks filing serial numbers
    # and other incidental year-like text regardless of position in the document.
    if not fy_str:
        candidate = _select_best_fy_candidate(probe_text)
        if candidate is not None:
            cand_fy, cand_basis, cand_ev, cand_is_weak = candidate
            fy_str = cand_fy
            fy_basis = [cand_basis]
            fy_evidence_texts = [cand_ev]
            if cand_is_weak:
                warnings.append(
                    f"Reporting period {fy_str!r} inferred from a filing reference "
                    "or reference-number context — may not be the document reporting "
                    "period; treat with low confidence"
                )
            # Check for contradicting strong candidates
            all_scored: List[Tuple[int, int, "re.Match[str]"]] = sorted(
                [(_score_fy_candidate(probe_text, m), m.start(), m)
                 for m in _INDIAN_FY_PATTERN.finditer(probe_text)],
                key=lambda x: (-x[0], x[1]),
            )
            for other_score, _, other_match in all_scored[1:]:
                if other_score < 5:
                    break  # only surface genuine strong contradictions
                other_end = other_match.group("end")
                other_fy = f"fy{other_end[-2:]}"
                if other_fy != fy_str:
                    warnings.append(
                        f"Contradicting strong reporting-period signals: "
                        f"{fy_str!r} (score {all_scored[0][0]}) vs "
                        f"{other_fy!r} (score {other_score}) — "
                        "using higher-scored candidate"
                    )
                    break

    # Stage 4: direct FY label fallback ("FY25", "FY2025", "FY 25")
    if not fy_str:
        fy_match = _DIRECT_FY_LABEL.search(probe_text)
        if fy_match:
            raw = fy_match.group("year")
            fy_str = f"fy{raw[-2:]}"
            fy_basis = ["direct_fy_label"]
            fy_evidence_texts = [fy_match.group(0)]

    if not fy_str:
        return None, warnings

    # Quarter detection: run for source types that may carry explicit quarter labels.
    # Full-year language ("Annual", "Full Year", "Twelve Months") never matches
    # _QUARTER_PATTERNS, so this branch cannot fabricate a quarter from FY-only text.
    _QUARTER_DETECTING_TYPES = {
        SourceType.QUARTERLY_REPORT,
        SourceType.INVESTOR_PRESENTATION,
        SourceType.EARNINGS_CALL_TRANSCRIPT,  # earnings calls reference their reporting quarter
        SourceType.EARNINGS_RELEASE,
    }
    fiscal_quarter: Optional[FiscalQuarter] = None
    if source_type in _QUARTER_DETECTING_TYPES:
        for pattern, quarter in _QUARTER_PATTERNS:
            if pattern.search(probe_text):
                fiscal_quarter = quarter
                break

    conf = ConfidenceLevel.HIGH if inferred.get("status") == "resolved" else ConfidenceLevel.MEDIUM
    if warnings:
        conf = ConfidenceLevel.LOW

    ev_list: List[IdentityEvidence] = []
    for et in fy_evidence_texts[:2]:
        ev_list.append(_evidence(
            "reporting_period.fiscal_year",
            et,
            conf,
            page=1,
            method="; ".join(fy_basis) if fy_basis else "content_scan",
        ))

    return ReportingPeriod(
        fiscal_year=fy_str,
        fiscal_quarter=fiscal_quarter,
        confidence=conf,
        evidence=ev_list,
    ), warnings


# ── S7: Document dates ────────────────────────────────────────────────────────

_DATE_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("publication", re.compile(
        r"\bdate\s*:\s*(?P<d>\d{1,2}\w*\s+\w+\s+20\d{2}|\w+\s+\d{1,2},?\s+20\d{2})",
        re.IGNORECASE,
    )),
    ("filing", re.compile(
        r"\bfiled\s+on\s+(?P<d>\d{1,2}[\s/]\w+[\s/]20\d{2}|\w+\s+\d{1,2},?\s+20\d{2})",
        re.IGNORECASE,
    )),
    ("event", re.compile(
        r"\bmeeting\s+held\s+on\s+(?P<d>\d{1,2}[\s/]\w+[\s/]20\d{2})",
        re.IGNORECASE,
    )),
]


def _detect_document_dates(probe_text: str) -> DocumentDates:
    pub: Optional[str] = None
    fil: Optional[str] = None
    evt: Optional[str] = None
    for kind, pattern in _DATE_PATTERNS:
        m = pattern.search(probe_text)
        if not m:
            continue
        raw = m.group("d").strip()
        if kind == "publication" and not pub:
            pub = raw
        elif kind == "filing" and not fil:
            fil = raw
        elif kind == "event" and not evt:
            evt = raw
    return DocumentDates(publication_date=pub, filing_date=fil, event_date=evt)


# ── S8: Entity scope ──────────────────────────────────────────────────────────

def _detect_entity_scope(probe_text: str) -> Tuple[EntityScope, ConfidenceLevel, Optional[IdentityEvidence]]:
    text_lower = probe_text.lower()
    has_consolidated = bool(re.search(r"\bconsolidated\b", text_lower))
    has_standalone = bool(re.search(r"\bstandalone\b|\bseparate\b", text_lower))

    if has_consolidated and has_standalone:
        ev = _evidence(
            "entity_scope",
            "Both 'consolidated' and 'standalone' found in probe text.",
            ConfidenceLevel.MEDIUM,
            method="keyword_scan",
        )
        return EntityScope.MIXED, ConfidenceLevel.MEDIUM, ev

    if has_consolidated:
        m = re.search(r"(?i).{0,40}\bconsolidated\b.{0,40}", probe_text)
        excerpt = m.group(0) if m else "consolidated"
        ev = _evidence("entity_scope", excerpt, ConfidenceLevel.HIGH, method="keyword_scan")
        return EntityScope.CONSOLIDATED, ConfidenceLevel.HIGH, ev

    if has_standalone:
        m = re.search(r"(?i).{0,40}\b(?:standalone|separate)\b.{0,40}", probe_text)
        excerpt = m.group(0) if m else "standalone"
        ev = _evidence("entity_scope", excerpt, ConfidenceLevel.HIGH, method="keyword_scan")
        return EntityScope.STANDALONE, ConfidenceLevel.HIGH, ev

    return EntityScope.UNKNOWN, ConfidenceLevel.UNKNOWN, None


# ── S9: Language detection ────────────────────────────────────────────────────

def _detect_language(probe_text: str) -> str:
    if not probe_text:
        return "unknown"
    ascii_chars = sum(1 for c in probe_text if ord(c) < 128)
    ratio = ascii_chars / max(len(probe_text), 1)
    if ratio >= 0.85:
        return "en"
    if ratio >= 0.5:
        return "mixed"
    return "non-latin"


# ── S10: Confidence engine + classification status ────────────────────────────

def _compute_classification(
    company_resolved: Optional[str],
    company_conf: ConfidenceLevel,
    source_type: SourceType,
    source_conf: ConfidenceLevel,
    reporting_period: Optional[ReportingPeriod],
    warnings: List[str],
    detected_legal_name: str = "",
) -> Tuple[ClassificationStatus, ConfidenceLevel, List[str]]:
    """Determine status and overall confidence from field confidences.

    IDENTIFIED requires:
      - company_conf in {HIGH, MEDIUM}
      - source_conf in {HIGH, MEDIUM}
      - source_type != UNKNOWN
      - for periodic reports (ANNUAL, QUARTERLY): reporting_period.fiscal_year must exist
      - no warnings that would reduce to LOW

    REVIEW_REQUIRED:
      - company identified but source_conf LOW or periodic report lacks period
      - OR: company LOW confidence
      - OR: company name detected in text but not mapped to canonical registry key

    UNIDENTIFIED:
      - company not detected in document text at all (no name, no registry match)

    REJECTED:
      - already handled upstream (no text / corrupt file) — not set here
    """
    unresolved: List[str] = []

    _HIGH_MED = {ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM}
    _PERIODIC = {
        SourceType.ANNUAL_REPORT,
        SourceType.QUARTERLY_REPORT,
        SourceType.EARNINGS_RELEASE,
    }

    if not company_resolved:
        unresolved.append("company_identity.resolved_company_key")
        if detected_legal_name:
            # Name detected but not in registry → operator can map it
            return ClassificationStatus.REVIEW_REQUIRED, ConfidenceLevel.LOW, unresolved
        return ClassificationStatus.UNIDENTIFIED, ConfidenceLevel.UNKNOWN, unresolved

    if company_conf not in _HIGH_MED or source_type == SourceType.UNKNOWN:
        unresolved.append("company_identity.confidence" if company_conf not in _HIGH_MED else "document_identity.source_type")
        return ClassificationStatus.REVIEW_REQUIRED, ConfidenceLevel.LOW, unresolved

    if source_type in _PERIODIC:
        if not reporting_period or not reporting_period.fiscal_year:
            unresolved.append("reporting_period.fiscal_year")
            return ClassificationStatus.REVIEW_REQUIRED, ConfidenceLevel.MEDIUM, unresolved
        if source_type in {SourceType.QUARTERLY_REPORT, SourceType.EARNINGS_RELEASE} and not reporting_period.fiscal_quarter:
            unresolved.append("reporting_period.fiscal_quarter")
            return ClassificationStatus.REVIEW_REQUIRED, ConfidenceLevel.MEDIUM, unresolved

    if warnings:
        return ClassificationStatus.REVIEW_REQUIRED, ConfidenceLevel.MEDIUM, unresolved

    # Determine overall confidence
    conf_levels = [company_conf, source_conf]
    if reporting_period:
        conf_levels.append(reporting_period.confidence)

    if all(c == ConfidenceLevel.HIGH for c in conf_levels):
        overall = ConfidenceLevel.HIGH
    elif ConfidenceLevel.LOW in conf_levels:
        overall = ConfidenceLevel.MEDIUM
    else:
        overall = ConfidenceLevel.MEDIUM

    return ClassificationStatus.IDENTIFIED, overall, unresolved


# ── S11: Main entry point ─────────────────────────────────────────────────────

def identify_document(
    path: "Path | str",
    *,
    companies_root: "Path | str | None" = None,
) -> DocumentIntakeManifest:
    """Content-based document identification.

    Args:
        path: Path to the document file (PDF, TXT, or MD).
        companies_root: Root of the companies directory. Defaults to
            Path("companies") relative to the working directory.

    Returns:
        A populated DocumentIntakeManifest. On fatal errors (file not found,
        no extractable text), returns a manifest with status=REJECTED.
    """
    path = Path(path)
    if companies_root is None:
        companies_root = Path("companies")
    companies_root = Path(companies_root)

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    warnings: List[str] = []

    # ── S1: File validation ───────────────────────────────────────────────────
    if not path.exists():
        return _make_rejected_manifest(path, "File does not exist", timestamp)

    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        return _make_rejected_manifest(path, f"Cannot stat file: {exc}", timestamp)

    if size_bytes == 0:
        return _make_rejected_manifest(path, "File is empty", timestamp)

    mime = _mime_from_suffix(path.suffix)
    if mime == "application/octet-stream":
        return _make_rejected_manifest(path, f"Unsupported file type: {path.suffix}", timestamp)

    # ── S2: Content hash ─────────────────────────────────────────────────────
    try:
        content_hash = compute_content_hash(path)
    except OSError as exc:
        return _make_rejected_manifest(path, f"Cannot read file for hashing: {exc}", timestamp)

    document_id = content_hash

    file_identity = FileIdentity(
        original_filename=path.name,
        content_hash=content_hash,
        mime_type=mime,
        size_bytes=size_bytes,
        storage_path=str(path),
    )

    # ── S3: Adaptive content probe ────────────────────────────────────────────
    # For PDFs: probe first CONTENT_PROBE_WRAPPER_PAGES pages as the "wrapper zone"
    # and pages [CONTENT_PROBE_WRAPPER_PAGES, CONTENT_PROBE_PAYLOAD_PAGES) as the
    # "payload zone".  For text files, both are the same content.
    wrapper_probe, payload_probe, probe_desc = _probe_content_adaptive(path)

    if not wrapper_probe.strip():
        return _make_rejected_manifest(
            path,
            f"No text extractable from document ({probe_desc})",
            timestamp,
            file_identity=file_identity,
            document_id=document_id,
        )

    # ── S3a: Source channel detection ────────────────────────────────────────
    # Detect whether the document arrived via an exchange-filing submission wrapper.
    # Only applies to PDFs; text files are always treated as DIRECT.
    if path.suffix.lower() == ".pdf":
        is_wrapper = _detect_exchange_wrapper(wrapper_probe)
        source_channel = SourceChannel.EXCHANGE_FILING if is_wrapper else SourceChannel.DIRECT
    else:
        is_wrapper = False
        source_channel = SourceChannel.DIRECT

    # ── S3b: Select probes for downstream stages ──────────────────────────────
    # combined_probe: used for company identification, reporting period,
    #                 entity scope, language, and legal-name extraction.
    # classification_probe: used for source-type classification.
    #   → When a wrapper is detected and payload text exists, classify on the
    #     payload so the cover letter's EXCHANGE_FILING signals do not override
    #     the document's substantive content type.
    _combined = (wrapper_probe + " " + payload_probe).strip()
    _combined = _combined[:CONTENT_PROBE_MAX_CHARS * 2]
    if is_wrapper and payload_probe.strip():
        # For long multi-section documents (annual reports, quarterly filings), the
        # payload pages carry all the substantive source-type signals and the cover
        # letter should be ignored for classification.  However, for short event-centric
        # disclosures (SE Intimations, board-meeting outcomes), the regulatory boilerplate
        # sits on page 1 — the "wrapper" page — and pages 2+ are only tabular annexures
        # with no source-type signals.  To handle both correctly: try classifying on the
        # payload alone first; if the payload scores UNKNOWN (no signal fires), fall back
        # to the combined probe so the substantive page 1 content is included.
        # When the combined probe also returns only EXCHANGE_FILING signals (already
        # captured as source_channel), preserve UNKNOWN — the payload type is genuinely
        # unresolvable and must not be guessed from the cover letter alone.
        _payload_type, _, _ = _classify_source_type(payload_probe.strip(), "")
        if _payload_type not in (SourceType.UNKNOWN, SourceType.EXCHANGE_FILING):
            # Payload has recognizable signals — classify on payload only.
            classification_probe = payload_probe
        else:
            # Payload has no recognizable signals — include wrapper page so
            # event-centric disclosure signals on page 1 can be detected.
            # Re-check combined; EXCHANGE_FILING winner on combined still means UNKNOWN.
            classification_probe = _combined
        combined_probe = _combined
    else:
        # No exchange wrapper: the entire probed window is substantive content.
        # Use wrapper + payload combined so company identification and source-type
        # classification see all pages 1–CONTENT_PROBE_PAYLOAD_PAGES, not just page 1.
        combined_probe = _combined
        classification_probe = combined_probe

    # ── S3c: Legal company name extraction ───────────────────────────────────
    # Extract corporate legal name from text even when the company is not in
    # the registry.  Preserves identity evidence for REVIEW_REQUIRED manifests.
    detected_legal_name = _extract_legal_company_name(combined_probe)

    # ── S3d: Identity trailer probe ───────────────────────────────────────────
    # Read the last IDENTITY_TRAILER_PAGES of the document for corporate identity
    # signals: domain (www.company.com), legal name blocks, CIN.  Indian corporate
    # filings commonly place the company registration block on the final page(s)
    # or back cover, which falls outside the main content probe window.
    # This probe only supplements company-confidence scoring; it does not change
    # source-type classification, reporting period, or entity scope.
    if path.suffix.lower() == ".pdf":
        identity_trailer = _probe_identity_trailer(path)
        # Also check trailer for legal name when the main probe missed it
        if not detected_legal_name and identity_trailer:
            detected_legal_name = _extract_legal_company_name(identity_trailer)
    else:
        identity_trailer = ""

    # ── S4: Company identification ────────────────────────────────────────────
    registry = _build_company_registry(companies_root)
    company_slug, company_conf, company_evs = _identify_company(
        combined_probe, registry, trailer_text=identity_trailer
    )

    company_identity = CompanyIdentity(
        resolved_company_key=company_slug,
        detected_legal_name=detected_legal_name,
        detected_display_name="",
        confidence=company_conf,
        evidence=company_evs,
    )

    # ── S5: Source-type classification (payload-aware) ────────────────────────
    # Classify on classification_probe so exchange-filing cover-letter signals
    # cannot override the substantive document type in the payload.
    source_type, source_conf, source_evs = _classify_source_type(classification_probe, path.stem)

    # When source_channel is EXCHANGE_FILING and the classifier returns EXCHANGE_FILING
    # as the source_type, that means no recognizable payload type was found — the
    # classification probe was dominated by exchange-filing boilerplate (BSE/NSE address,
    # LODR reference) without any substantive payload signals.  EXCHANGE_FILING already
    # describes the channel; using it also as the payload type is circular and wrong.
    # Demote to UNKNOWN so the router correctly routes as UNSUPPORTED.
    if is_wrapper and source_type == SourceType.EXCHANGE_FILING:
        source_type = SourceType.UNKNOWN
        source_conf = ConfidenceLevel.UNKNOWN
        source_evs = []

    doc_identity = DocumentIdentity(
        source_type=source_type,
        source_channel=source_channel,
        document_subtype=source_type.value.lower(),
        confidence=source_conf,
        evidence=source_evs,
    )

    # ── S6: Reporting period ──────────────────────────────────────────────────
    # When a wrapper is present, use only the payload for period detection so
    # filing-reference dates in the cover letter do not contradict the payload FY.
    period_probe = classification_probe if (is_wrapper and classification_probe.strip()) else combined_probe
    reporting_period, period_warnings = _detect_reporting_period(period_probe, path.name, source_type)
    warnings.extend(period_warnings)

    # ── S7: Document dates ────────────────────────────────────────────────────
    document_dates = _detect_document_dates(combined_probe)

    # ── S8: Entity scope ──────────────────────────────────────────────────────
    # Same payload-first logic: wrapper cover letters don't define entity scope.
    scope_probe = classification_probe if (is_wrapper and classification_probe.strip()) else combined_probe
    entity_scope, scope_conf, scope_ev = _detect_entity_scope(scope_probe)

    # ── S9: Language detection ────────────────────────────────────────────────
    language = _detect_language(combined_probe)

    # ── S10: Confidence engine ────────────────────────────────────────────────
    if company_conf == ConfidenceLevel.UNKNOWN and company_slug is None:
        if detected_legal_name:
            warnings.append(
                f"Company name detected ('{detected_legal_name}') but not mapped to canonical key."
            )
        else:
            warnings.append("Company could not be identified from content alone.")

    status, overall_conf, unresolved = _compute_classification(
        company_resolved=company_slug,
        company_conf=company_conf,
        source_type=source_type,
        source_conf=source_conf,
        reporting_period=reporting_period,
        warnings=warnings,
        detected_legal_name=detected_legal_name,
    )

    classification = ClassificationState(
        overall_confidence=overall_conf,
        status=status,
        unresolved_fields=unresolved,
        warnings=warnings,
    )

    # ── S11: Manifest construction ────────────────────────────────────────────
    return DocumentIntakeManifest(
        document_id=document_id,
        file=file_identity,
        company_identity=company_identity,
        document_identity=doc_identity,
        reporting_period=reporting_period,
        document_dates=document_dates,
        entity_scope=entity_scope,
        language=language,
        classification=classification,
        provenance=IntakeProvenance(
            ingestion_timestamp=timestamp,
            classifier_version=IDENTIFIER_VERSION,
            detection_method=DetectionMethod.AUTOMATIC_CLASSIFIER,
        ),
    )


def _make_rejected_manifest(
    path: Path,
    reason: str,
    timestamp: str,
    *,
    file_identity: Optional[FileIdentity] = None,
    document_id: Optional[str] = None,
) -> DocumentIntakeManifest:
    """Build a REJECTED manifest for a file that cannot be identified."""
    if file_identity is None:
        try:
            size_bytes = path.stat().st_size if path.exists() else 0
        except OSError:
            size_bytes = 0
        file_identity = FileIdentity(
            original_filename=path.name,
            content_hash="",
            mime_type=_mime_from_suffix(path.suffix),
            size_bytes=size_bytes,
            storage_path=str(path),
        )

    return DocumentIntakeManifest(
        document_id=document_id or f"rejected:{path.name}",
        file=file_identity,
        company_identity=CompanyIdentity(confidence=ConfidenceLevel.UNKNOWN),
        document_identity=DocumentIdentity(source_type=SourceType.UNKNOWN, confidence=ConfidenceLevel.UNKNOWN),
        reporting_period=None,
        document_dates=DocumentDates(),
        entity_scope=EntityScope.UNKNOWN,
        language="unknown",
        classification=ClassificationState(
            overall_confidence=ConfidenceLevel.UNKNOWN,
            status=ClassificationStatus.REJECTED,
            unresolved_fields=["all"],
            warnings=[reason],
        ),
        provenance=IntakeProvenance(
            ingestion_timestamp=timestamp,
            classifier_version=IDENTIFIER_VERSION,
            detection_method=DetectionMethod.AUTOMATIC_CLASSIFIER,
        ),
    )
