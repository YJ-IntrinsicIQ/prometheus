"""Phase 9 — Part 3: Canonical theme registry.

A theme_slug is the cross-source identity key.  Evidence items sharing
a theme_slug belong to the same longitudinal commitment thread regardless
of how they are phrased or which source produced them.

Matching is keyword-based (fast, auditable, no LLM required).  The order
of entries matters: first match wins.  Add new themes at the bottom to
avoid accidentally overriding earlier ones.

## Canonical classification contract (Phase 11.2)

**Positive classification**: A theme is assigned only when evidence contains
sufficient semantic support for that theme — both required and optional
keyword sets must be satisfied.

**Ambiguous / insufficient evidence**: prefer UNCLASSIFIED (return None) over
an unsafe theme assignment.  Wrong longitudinal merge is worse than missing
one atom.

**False-positive rule — abbreviation keywords**: Short pure-alpha keywords
(≤ 3 chars, e.g. "ott", "rcs", "atp", "fx", "pat") are treated as whole-word
tokens using word-boundary regex matching.  This prevents substring false-positives:
"bottom" must not match "ott"; "allotted" must not match "ott"; "patterns"
must not match "pat".  4-char pure-alpha prefixes (e.g. "hedg") and all longer
keywords continue to use plain substring matching — "hedg" is a deliberate
prefix that must match "hedging", "hedged", etc.

**Platform-launch precision rule (Phase 11.3)**: `platform_launch` requires a
strong action verb ("launch", "gigantic") co-occurring with "platform".  Generic
words like "new" and "announce" are NOT sufficient — "new customers", "new hires",
"announced a buyback" must not classify as platform launches.  Removing "new" and
"announce" from optional eliminated all cross-company false positives (Data Patterns
iDEX/product-development texts, Tanla boilerplate quarterly pages).

**Unknown rule**: UNCLASSIFIED > wrong theme.  Never lower this bar.
"""
from __future__ import annotations

import functools
import re
from typing import Optional

from intelligence.multi_source.contracts import ClaimDomain


@functools.lru_cache(maxsize=256)
def _word_re(kw: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(kw) + r"\b")


def _kw_match(kw: str, normalised_text: str) -> bool:
    """Match one keyword against normalised (lower-cased) evidence text.

    Short pure-alpha abbreviations (≤ 3 chars, e.g. 'ott', 'fx', 'rcs', 'pat')
    use word-boundary matching so they do not fire on embedded substrings
    ('bottom' → ott, 'allotted' → ott, 'patterns' → pat).

    4-char pure-alpha keywords (e.g. 'hedg') and all longer keywords use plain
    substring matching — 'hedg' is a deliberate prefix pattern that must match
    'hedging', 'hedged', etc.
    """
    if kw.isalpha() and len(kw) <= 3:
        return bool(_word_re(kw).search(normalised_text))
    return kw in normalised_text


# (slug, label, domain, required_keywords, optional_keywords)
# A text matches if it contains ALL required_keywords and at least one
# optional_keyword (or optional_keywords is empty).
_THEMES = [
    # ---------------- executive / leadership ----------------
    (
        "leadership_change",
        "Leadership / Executive Change",
        ClaimDomain.FACTUAL_EVENT,
        [],  # any one of the optional keywords is sufficient
        ["resign", "appoint", "ceo", "cfo", "cxo", "chief executive", "chief financial",
         "director", "management change", "change in senior management", "smp", "md "],
    ),
    (
        "leadership_stability",
        "Leadership Stability",
        ClaimDomain.RISK,
        ["management", "leadership"],
        ["stability", "departure", "attrition"],
    ),
    # ---------------- ATP / anti-phishing platform ----------
    (
        "atp_bank_program",
        "ATP (Anti-phishing / Bank) Program",
        ClaimDomain.COMMITMENT,
        ["atp"],
        [],
    ),
    # ---------------- Wisely AI -----------------------------
    (
        "wisely_ai_growth",
        "Wisely AI Platform Growth",
        ClaimDomain.COMMITMENT,
        ["wisely"],
        [],
    ),
    # ---------------- platform launch -----------------------
    (
        "platform_launch",
        "New Platform Launch",
        ClaimDomain.COMMITMENT,
        ["platform"],
        ["launch", "gigantic"],
    ),
    # ---------------- RCS channel ---------------------------
    (
        "rcs_channel_adoption",
        "RCS Channel Adoption",
        ClaimDomain.STRATEGIC_PRIORITY,
        ["rcs"],
        [],
    ),
    # ---------------- OTT / WhatsApp ------------------------
    (
        "ott_whatsapp_growth",
        "OTT / WhatsApp Growth",
        ClaimDomain.STRATEGIC_PRIORITY,
        [],
        ["ott", "whatsapp"],
    ),
    # ---------------- EBITDA margin -------------------------
    (
        "ebitda_margin_trajectory",
        "EBITDA Margin Trajectory",
        ClaimDomain.COMMITMENT,
        ["ebitda", "margin"],
        [],
    ),
    # ---------------- revenue growth guidance ---------------
    (
        "revenue_growth_guidance",
        "Revenue Growth Guidance",
        ClaimDomain.COMMITMENT,
        ["revenue", "growth"],
        ["10%", "double digit", "target", "guidance", "aspire"],
    ),
    # ---------------- FX / hedging --------------------------
    (
        "fx_hedging_policy",
        "FX Hedging Policy",
        ClaimDomain.COMMITMENT,
        [],
        ["hedg", "fx", "forex", "usd-inr", "currency"],
    ),
    # ---------------- capital allocation --------------------
    (
        "capital_allocation",
        "Capital Allocation (Dividend / Buyback / M&A)",
        ClaimDomain.STRATEGIC_PRIORITY,
        [],
        ["dividend", "buyback", "acquisition", "build versus buy", "capex"],
    ),
    # ---------------- international expansion ---------------
    (
        "international_expansion",
        "International Expansion",
        ClaimDomain.COMMITMENT,
        [],
        ["international", "outside india", "global"],
    ),
    # ---------------- market share --------------------------
    (
        "market_share_growth",
        "Market Share Growth",
        ClaimDomain.COMMITMENT,
        ["market share"],
        [],
    ),
    # ---------------- new logo / customer acquisition -------
    (
        "new_logo_acquisition",
        "New Logo / Customer Acquisition",
        ClaimDomain.STRATEGIC_PRIORITY,
        [],
        ["new logo", "new customer", "new client", "rbi", "bank of baroda"],
    ),
    # ---------------- wallet share expansion ----------------
    (
        "wallet_share_expansion",
        "Wallet Share Expansion",
        ClaimDomain.STRATEGIC_PRIORITY,
        ["wallet share"],
        [],
    ),
    # ---------------- ESG -----------------------------------
    (
        "esg_sustainability",
        "ESG / Sustainability",
        ClaimDomain.STRATEGIC_PRIORITY,
        [],
        ["esg", "carbon", "sustainability", "iso 14001"],
    ),
    # ---------------- GTM investment ------------------------
    (
        "gtm_investment",
        "GTM / Sales Investment",
        ClaimDomain.STRATEGIC_PRIORITY,
        ["gtm"],
        [],
    ),
    # ---------------- profitability -------------------------
    (
        "profitability",
        "Profitability / Cash Flow",
        ClaimDomain.FINANCIAL_METRIC,
        [],
        ["profit", "cash flow", "net income", "pat"],
    ),
]


def _normalise(text: str) -> str:
    return text.lower()


def classify_theme(text: str) -> Optional[tuple[str, str, ClaimDomain]]:
    """Return (slug, label, domain) for the first matching theme, or None.

    Returns None when no theme has sufficient evidence — caller should treat
    the atom as UNCLASSIFIED rather than forcing an unsafe assignment.
    """
    t = _normalise(text)
    for slug, label, domain, required, optional in _THEMES:
        if not all(_kw_match(kw, t) for kw in required):
            continue
        if optional and not any(_kw_match(kw, t) for kw in optional):
            continue
        return slug, label, domain
    return None
