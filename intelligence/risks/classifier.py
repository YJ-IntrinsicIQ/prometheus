"""Risk classification and sanitization."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .contracts import RISK_CATEGORIES


def _compact_lower(text: Any) -> str:
    """Normalize text: lowercase, strip, single spaces."""
    if not isinstance(text, str):
        return ""
    return " ".join(text.lower().strip().split())


def sanitize_public_text(text: str) -> str:
    """Remove internal pipeline terminology from public-facing text."""
    if not text:
        return ""
    
    # Remove internal terms
    internal_terms = [
        r"\b(company_memory|intelligence_stream|progression_engine|fy\d{2,4})\b",
        r"\bsource_chunk\b",
        r"\braw_text\b",
        r"\bfull_text\b",
        r"\bartifact\b(?!\s+of)",
        r"\b(ev_|ci_|proj_|cap_|risk_|cpt_|fin_|pan_)\w+\b",
    ]
    
    result = text
    for pattern in internal_terms:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    
    # Clean up whitespace
    result = " ".join(result.split())
    return result.strip()


def classify_risk_category(
    description: str,
    affected_area: Optional[str] = None,
) -> str:
    """
    Classify a risk into a canonical category using keyword matching.
    
    Returns one of RISK_CATEGORIES.
    """
    text = _compact_lower(description)
    area = _compact_lower(affected_area or "")
    full_text = f"{text} {area}".lower()
    
    # Category patterns
    category_patterns: Dict[str, tuple] = {
        "customer": (
            r"\b(customer|client|buyer|end.?user|demand|concentration|dependence|loss of|major order)\b",
        ),
        "financial": (
            r"\b(profit|earnings|revenue|margin|cash flow|fcf|liquidity|solvency|financial position|equity|credit)\b",
        ),
        "working_capital": (
            r"\b(working.?capital|receivable|payable|inventory|cash conversion|collection|payment term)\b",
        ),
        "balance_sheet": (
            r"\b(debt|leverage|balance.?sheet|asset|liability|net worth|capital structure)\b",
        ),
        "operational": (
            r"\b(operation|process|production|efficiency|productivity|cost|waste|supply chain)\b",
        ),
        "execution": (
            r"\b(execution|delay|schedule|milestone|timeline|completion|performance|delivery)\b",
        ),
        "project": (
            r"\b(project|programme|initiative|capex|construction|facility|expansion|commissioning)\b",
        ),
        "capacity": (
            r"\b(capacity|utilization|throughput|output|bottleneck|constraint|scale|infrastructure)\b",
        ),
        "regulatory": (
            r"\b(regulatory|compliance|certification|license|permit|standard|regulation|approval|audit)\b",
        ),
        "competitive": (
            r"\b(competitive|competition|market share|competitive advantage|competitor|position|pricing)\b",
        ),
        "technology": (
            r"\b(technology|tech|software|system|digital|automation|cyber|it|innovation|r&d)\b",
        ),
        "product": (
            r"\b(product|service|offering|feature|quality|obsolescence|design|specification)\b",
        ),
        "supplier": (
            r"\b(supplier|vendor|partner|sourcing|procurement|supply|raw material|component)\b",
        ),
        "governance": (
            r"\b(governance|board|management|control|oversight|accountability|policy|internal)\b",
        ),
        "management": (
            r"\b(management|leadership|key person|key.?man|expertise|succession|promise|commitment)\b",
        ),
        "capital_allocation": (
            r"\b(capital allocation|investment|roi|return|capex|allocation|misallocation|strategic)\b",
        ),
        "acquisition": (
            r"\b(acquisition|merger|integration|integration risk|synergy|takeover)\b",
        ),
        "geographic": (
            r"\b(geographic|geographic concentration|location|region|country|export|market)\b",
        ),
        "currency": (
            r"\b(currency|foreign exchange|fx|exchange rate|devaluation|revaluation)\b",
        ),
        "accounting": (
            r"\b(accounting|accounting treatment|estimate|judgment|policy|method|disclosure)\b",
        ),
        "legal": (
            r"\b(legal|litigation|dispute|lawsuit|contract|contingent|liability|infringement)\b",
        ),
    }
    
    # Score each category
    scores: Dict[str, int] = {}
    
    for category, patterns in category_patterns.items():
        score = 0
        for pattern in patterns:
            matches = len(re.findall(pattern, full_text, re.IGNORECASE))
            score += matches
        
        if score > 0:
            scores[category] = score
    
    # Return highest scoring category, default to "other"
    if scores:
        return max(scores, key=scores.get)
    
    return "other"


def is_generic_boilerplate(description: str) -> bool:
    """
    Check if a risk description is generic boilerplate that should not become a risk.
    
    Returns True if the risk appears to be vague language rather than specific evidence.
    """
    if not description:
        return True
    
    text = _compact_lower(description)
    
    # Patterns that indicate generic boilerplate
    boilerplate_patterns = [
        r"^(industry is competitive|the industry may|may be uncertainty|growth could|there could be|potentially|subject to)",
        r"^(general business risk|various risk|typical risk|normal business)",
        r"^(like any|similar to other|as with most|as is common)",
        r"^(subject to|may involve|may include|could involve)",
        r"^(this company|like most|like all|general)",
    ]
    
    for pattern in boilerplate_patterns:
        if re.search(pattern, text):
            return True
    
    # Check if it's too generic (very short or only common words)
    words = text.split()
    if len(words) < 5:
        return True
    
    # Check word frequency - if mostly common words, likely boilerplate
    common_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "be", "may", "could", "would"
    }
    
    content_words = [w for w in words if w not in common_words and len(w) > 3]
    if len(content_words) < 3:
        return True
    
    return False


def extract_affected_area(description: str, category: str) -> Optional[str]:
    """
    Extract the specific business area affected by a risk.
    
    Returns a label like "cash generation", "revenue concentration", etc.
    """
    text = _compact_lower(description)
    
    area_mapping = {
        "financial": ["profitability", "earnings", "cash generation", "financial position"],
        "working_capital": ["cash generation", "working capital", "cash conversion"],
        "customer": ["revenue concentration", "revenue", "sales", "demand"],
        "execution": ["execution", "operations", "delivery"],
        "capacity": ["capacity utilization", "throughput", "output"],
        "competitive": ["competitive position", "market share", "pricing power"],
        "operational": ["operational efficiency", "operations", "cost structure"],
        "product": ["product demand", "product viability", "revenue quality"],
        "balance_sheet": ["balance sheet resilience", "financial stability", "leverage"],
        "regulatory": ["regulatory standing", "operational continuity", "market access"],
    }
    
    if category in area_mapping:
        for area in area_mapping[category]:
            if area.lower() in text:
                return area
    
    # Default based on category
    defaults = {
        "financial": "financial position",
        "working_capital": "working capital",
        "customer": "revenue concentration",
        "execution": "execution",
        "capacity": "capacity utilization",
        "competitive": "competitive position",
        "operational": "operations",
        "regulatory": "regulatory standing",
        "governance": "management credibility",
    }
    
    return defaults.get(category)
