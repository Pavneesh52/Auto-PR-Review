from typing import Optional, List
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from .enums import ReviewOutcome, AgentType
from .findings import Finding


class ReviewBase(BaseModel):
    repo: str
    pr_number: int
    pr_title: str
    pr_body: Optional[str] = None
    diff: str
    base_sha: str
    head_sha: str


class ReviewCreate(ReviewBase):
    pass


class ReviewResponse(ReviewBase):
    id: UUID
    findings: List[Finding] = []
    overall_confidence: float = 0.0
    outcome: Optional[ReviewOutcome] = None
    hitl_required: bool = False
    github_review_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReviewSummary(BaseModel):
    id: UUID
    repo: str
    pr_number: int
    pr_title: str
    overall_confidence: float
    outcome: Optional[ReviewOutcome]
    hitl_required: bool
    findings_count: int
    critical_findings: int
    created_at: datetime

    class Config:
        from_attributes = True