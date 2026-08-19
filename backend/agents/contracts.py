from typing import List, Optional
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from backend.models.enums import AgentType, Severity, FindingCategory, ReviewOutcome
from backend.models.findings import Finding


class AgentInput(BaseModel):
    review_id: UUID
    repo: str
    pr_number: int
    pr_title: str
    pr_body: Optional[str] = None
    diff: str
    base_sha: str
    head_sha: str


class AgentOutput(BaseModel):
    agent_type: AgentType
    findings: List[Finding]
    overall_confidence: float = Field(ge=0.0, le=1.0)
    processing_time_ms: int
    tokens_used: int = 0
    cost_usd: float = 0.0


class AggregatorInput(BaseModel):
    review_id: UUID
    agent_outputs: List[AgentOutput]


class AggregatorOutput(BaseModel):
    merged_findings: List[Finding]
    overall_confidence: float = Field(ge=0.0, le=1.0)
    hitl_required: bool
    outcome: Optional[ReviewOutcome] = None
    critical_findings: int = 0


class HITLInput(BaseModel):
    review_id: UUID
    aggregated_output: AggregatorOutput


class HITLOutput(BaseModel):
    review_id: UUID
    final_outcome: ReviewOutcome
    human_feedback: Optional[str] = None
    modified_findings: List[Finding] = []


class ReviewJob(BaseModel):
    review_id: UUID
    repo: str
    pr_number: int
    pr_title: str
    pr_body: Optional[str] = None
    diff: str
    base_sha: str
    head_sha: str
    delivery_id: str