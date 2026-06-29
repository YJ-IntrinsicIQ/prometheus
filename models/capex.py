from pydantic import BaseModel
from typing import Optional


class CapexProject(BaseModel):
    project_name: Optional[str] = None

    allocated_budget: Optional[float] = None
    budget_evidence: Optional[str] = None

    location: Optional[str] = None
    location_evidence: Optional[str] = None

    capacity_increase_percent: Optional[float] = None
    capacity_evidence: Optional[str] = None

    target_completion_date: Optional[str] = None
    completion_evidence: Optional[str] = None

    ownership_type: Optional[str] = None

    source_chunk: Optional[str] = None