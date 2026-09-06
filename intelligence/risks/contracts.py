"""Risk Evolution Intelligence - canonical contracts and enums."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from intelligence.progression.contracts import ProgressionAdapter

RISK_SCHEMA_VERSION = "risk.v1"
RISK_MANIFEST_SCHEMA_VERSION = "risk_manifest.v1"
RISK_GENERATOR_VERSION = "risk_builder.v1"

# Canonical risk categories
RISK_CATEGORIES = (
    "customer",
    "financial",
    "working_capital",
    "balance_sheet",
    "operational",
    "execution",
    "project",
    "capacity",
    "regulatory",
    "competitive",
    "technology",
    "product",
    "supplier",
    "governance",
    "management",
    "capital_allocation",
    "acquisition",
    "geographic",
    "currency",
    "accounting",
    "legal",
    "other",
)

# Canonical risk statuses
RISK_STATUSES = (
    "emerging",
    "increasing",
    "persistent",
    "stable",
    "reducing",
    "mitigated",
    "resolved",
    "recurring",
    "contradictory",
    "unable_to_verify",
)

# Canonical risk event types
RISK_EVENT_TYPES = (
    "risk_signal",
    "risk_confirmed",
    "risk_intensified",
    "risk_persisted",
    "mitigation_announced",
    "mitigation_started",
    "mitigation_evidence",
    "counter_evidence",
    "risk_reduced",
    "risk_resolved",
    "risk_recurred",
    "contradiction",
    "monitoring_update",
    "latest_assessment",
)

# Materiality levels
RISK_MATERIALITY_LEVELS = (
    "high",
    "medium",
    "low",
    "unclear",
)

# Mitigation statuses
RISK_MITIGATION_STATUSES = (
    "announced",
    "in_progress",
    "partially_effective",
    "effective",
    "ineffective",
    "unable_to_verify",
)


@dataclass
class RiskMitigation:
    """Represents a mitigation action for a risk."""

    mitigation_action: str
    announcement_period: str
    execution_evidence: Optional[str] = None
    latest_status: str = "announced"
    observed_effect: Optional[str] = None
    confidence: Dict[str, Any] = field(default_factory=dict)
    source_references: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, removing None values."""
        result = asdict(self)
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class RiskMateriality:
    """Transparent materiality assessment."""

    level: str  # high, medium, low, unclear
    affected_dimensions: List[str] = field(default_factory=list)
    basis: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, removing empty values."""
        result = asdict(self)
        return {k: v for k, v in result.items() if v}


@dataclass
class RiskConfidence:
    """Confidence structure for a risk assessment."""

    level: str  # high, medium, low, unavailable
    basis: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, removing empty values."""
        result = asdict(self)
        return {k: v for k, v in result.items() if v}


@dataclass
class RiskDefinition:
    """Canonical risk definition record."""

    risk_id: str
    risk_name: str
    normalized_name: str
    risk_category: str
    affected_area: Optional[str] = None
    first_observed_period: str = ""
    latest_period: str = ""
    current_status: str = "unable_to_verify"
    
    # Progression and evidence
    risk_mechanism: str = ""
    progression_summary: str = ""
    what_changed: Optional[str] = None
    why_it_changed: Optional[str] = None
    
    # Conviction impact
    conviction_impact: Optional[str] = None  # strengthened, weakened, unchanged, unclear

    # Canonical evolution identity and trajectory (propagated from multi_year/risk_evolution.json)
    evo_canonical_id: Optional[str] = None   # e.g. "risk_foreign_exchange_risk"
    evo_trajectory: Optional[str] = None     # "worsening" | "improving" | "recurring" | None
    evo_severity_by_year: Dict[str, Any] = field(default_factory=dict)
    evo_latest_severity: Optional[str] = None

    # Relationships
    related_commitment_ids: List[str] = field(default_factory=list)
    related_project_ids: List[str] = field(default_factory=list)
    related_capacity_ids: List[str] = field(default_factory=list)
    related_financial_metrics: List[str] = field(default_factory=list)
    
    # Materiality and assessment
    materiality: Optional[RiskMateriality] = None
    
    # Mitigation tracking
    mitigations: List[RiskMitigation] = field(default_factory=list)
    mitigation_evidence: Optional[str] = None
    
    # Counter-evidence
    counter_evidence: Optional[str] = None
    
    # Triggers and conditions
    trigger_conditions: List[str] = field(default_factory=list)
    disconfirming_evidence: List[str] = field(default_factory=list)
    
    # Investor implication
    investor_implication: str = ""
    
    # Confidence and evidence status
    confidence: RiskConfidence = field(default_factory=lambda: RiskConfidence(level="unavailable"))
    evidence_status: str = "missing"
    
    # Source tracking
    source_references: List[Dict[str, Any]] = field(default_factory=list)
    semantic_quality: Dict[str, Any] = field(default_factory=dict)
    
    # Unresolved questions
    unresolved_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, removing None values."""
        result = asdict(self)
        
        # Convert dataclass fields
        if isinstance(result.get("materiality"), dict) and not result["materiality"]:
            result["materiality"] = None
        elif isinstance(result.get("materiality"), dict):
            result["materiality"] = {k: v for k, v in result["materiality"].items() if v}
        
        if isinstance(result.get("confidence"), dict):
            result["confidence"] = {k: v for k, v in result["confidence"].items() if v}
        
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class RiskAssessment:
    """Assessment of a risk and its progression."""

    risk_id: str
    current_status: str
    what_changed: str
    why_it_changed: str
    conviction_impact: str = "unclear"
    trajectory: Optional[str] = None          # "worsening" | "improving" | "recurring" | None
    evo_canonical_id: Optional[str] = None    # canonical evolution risk ID for cross-artifact linking
    latest_evidence: List[str] = field(default_factory=list)
    unresolved_items: List[str] = field(default_factory=list)
    investor_implication: str = ""
    semantic_quality: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        return {k: v for k, v in result.items() if v is not None}


class RiskProgressionAdapter(ProgressionAdapter):
    """Adapter to integrate Risk Evolution with the shared Progression Engine."""

    stream_type: str = "risk"

    def normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a risk event for progression tracking."""
        return event
    
    def deduplicate_key(self, event: Dict[str, Any]) -> str:
        """Compute a deterministic deduplication key for risk events."""
        subject_id = event.get("subject_id", "")
        event_type = event.get("event_type", "")
        period = event.get("period", "")
        title = event.get("title", "").lower().strip()
        return f"{subject_id}:{event_type}:{period}:{title}"

    def derive_current_state(self, events: List[Dict[str, Any]]) -> str:
        """Derive current risk status from ordered events."""
        if not events:
            return "unable_to_verify"
        
        latest = events[-1] if events else {}
        event_type = latest.get("event_type", "")
        
        status_map = {
            "risk_signal": "emerging",
            "risk_confirmed": "persistent",
            "risk_intensified": "increasing",
            "risk_persisted": "persistent",
            "mitigation_announced": "persistent",
            "mitigation_started": "persistent",
            "mitigation_evidence": "reducing",
            "counter_evidence": "contradictory",
            "risk_reduced": "reducing",
            "risk_resolved": "resolved",
            "risk_recurred": "recurring",
            "contradiction": "contradictory",
            "monitoring_update": "stable",
            "latest_assessment": "persistent",
        }
        
        return status_map.get(event_type, "unable_to_verify")

    def validate_transition(self, previous_state: Any, event: Dict[str, Any], next_state: Any) -> Dict[str, Any]:
        event_type = str(event.get("event_type") or "risk_signal")
        accepted = bool(next_state) and (
            previous_state in (None, "", "unable_to_verify")
            or previous_state == next_state
            or self.is_valid_transition(str(previous_state), str(next_state), event_type)
        )
        reason = "" if accepted else "Risk state transition is not supported by the event sequence."
        return {
            "accepted": accepted,
            "transition_type": event_type,
            "reason": reason,
            "confidence": {"level": "high" if accepted else "medium", "basis": ["deterministic risk progression"], "limitations": [reason] if reason else []},
        }
    
    def build_investor_implication(self, timeline_info: Dict[str, Any]) -> Dict[str, Any]:
        """Build investor implication from timeline info."""
        return {
            "summary": "Risk trajectory unclear",
            "conviction_impact": "unclear",
        }

    def get_deduplication_key(self, event: Dict[str, Any]) -> str:
        """Compute a deterministic deduplication key for risk events."""
        return self.deduplicate_key(event)

    def is_valid_transition(
        self,
        from_state: str,
        to_state: str,
        transition_reason: str = "",
    ) -> bool:
        """Validate whether a risk status transition is allowed."""
        valid_transitions = {
            "unable_to_verify": {"emerging", "persistent", "increasing", "unable_to_verify"},
            "emerging": {"increasing", "persistent", "confirmed", "reducing", "unable_to_verify"},
            "increasing": {"persistent", "reducing", "mitigated", "unable_to_verify"},
            "persistent": {"increasing", "reducing", "mitigated", "resolved", "recurring", "unable_to_verify"},
            "stable": {"persistent", "increasing", "reducing", "unable_to_verify"},
            "reducing": {"persistent", "mitigated", "resolved", "recurring", "unable_to_verify"},
            "mitigated": {"reducing", "recurring", "resolved", "unable_to_verify"},
            "resolved": {"recurring", "unable_to_verify"},
            "recurring": {"persistent", "increasing", "reducing", "mitigated", "unable_to_verify"},
            "contradictory": {"persistent", "reducing", "mitigated", "unable_to_verify"},
        }
        
        return to_state in valid_transitions.get(from_state, set())
