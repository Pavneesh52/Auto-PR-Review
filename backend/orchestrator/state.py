from typing import List, Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel
from backend.models.enums import AgentType, ReviewOutcome
from backend.models.findings import Finding


class ReviewState(BaseModel):
    review_id: UUID
    repo: str
    pr_number: int
    pr_title: str
    pr_body: Optional[str] = None
    diff: str
    base_sha: str
    head_sha: str
    
    security_findings: List[Finding] = []
    quality_findings: List[Finding] = []
    tests_findings: List[Finding] = []
    docs_findings: List[Finding] = []
    
    merged_findings: List[Finding] = []
    overall_confidence: float = 0.0
    hitl_required: bool = False
    outcome: Optional[ReviewOutcome] = None
    
    error: Optional[str] = None
    current_agent: Optional[AgentType] = None
    
    class Config:
        arbitrary_types_allowed = True