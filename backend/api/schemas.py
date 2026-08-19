from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime
from backend.models.enums import ReviewOutcome, Severity, FindingCategory, AgentType


class FindingResponse(BaseModel):
    id: UUID
    review_id: UUID
    agent_type: AgentType
    severity: Severity
    category: FindingCategory
    summary: str
    file_path: str
    line_start: int
    line_end: Optional[int] = None
    suggestion: str
    confidence: float
    rationale: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewResponse(BaseModel):
    id: UUID
    repo: str
    pr_number: int
    pr_title: str
    pr_body: Optional[str] = None
    diff: str
    base_sha: str
    head_sha: str
    overall_confidence: float
    outcome: Optional[ReviewOutcome] = None
    hitl_required: bool
    github_review_id: Optional[int] = None
    findings: List[FindingResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReviewListResponse(BaseModel):
    reviews: List[ReviewResponse]
    total: int
    page: int
    page_size: int


class ReviewCreateRequest(BaseModel):
    repo: str
    pr_number: int
    pr_title: str
    pr_body: Optional[str] = None
    diff: str
    base_sha: str
    head_sha: str