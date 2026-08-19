from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


class AgentType(str, Enum):
    SECURITY = "security"
    QUALITY = "quality"
    TESTS = "tests"
    DOCS = "docs"
    AGGREGATOR = "aggregator"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class FindingCategory(str, Enum):
    INJECTION = "injection"
    SECRETS = "secrets"
    AUTH_BYPASS = "auth_bypass"
    UNSAFE_DESERIALIZATION = "unsafe_deserialization"
    LOGIC_ERROR = "logic_error"
    CODE_SMELL = "code_smell"
    UNNECESSARY_COMPLEXITY = "unnecessary_complexity"
    MISSING_TEST = "missing_test"
    UNTESTED_EDGE_CASE = "untested_edge_case"
    BRITTLE_ASSERTION = "brittle_assertion"
    COVERAGE_GAP = "coverage_gap"
    MISSING_DOCSTRING = "missing_docstring"
    OUTDATED_COMMENT = "outdated_comment"
    UNDOCUMENTED_PUBLIC_API = "undocumented_public_api"
    UNEXPLAINED_DECISION = "unexplained_decision"


class ReviewOutcome(str, Enum):
    APPROVED = "approved"
    REQUEST_CHANGES = "request_changes"
    CRITICAL_BLOCK = "critical_block"
    ESCALATED = "escalated"


class EventType(str, Enum):
    SPAN_START = "span.start"
    SPAN_END = "span.end"
    LLM_CALL = "llm.call"
    TOOL_CALL = "tool.call"
    DECISION = "decision"
    ESCALATION = "escalation"


class Finding(BaseModel):
    agent_type: AgentType
    severity: Severity
    category: FindingCategory
    summary: str
    file_path: str
    line_start: int
    line_end: Optional[int] = None
    suggestion: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class ReviewState(BaseModel):
    review_id: UUID
    repo: str
    pr_number: int
    pr_title: str
    pr_body: Optional[str] = None
    diff: str
    base_sha: str
    head_sha: str
    findings: List[Finding] = []
    overall_confidence: float = 0.0
    outcome: Optional[ReviewOutcome] = None
    hitl_required: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class WebhookEvent(BaseModel):
    event_type: str
    delivery_id: str
    payload: dict
    signature: str


class AgentEvent(BaseModel):
    ts: datetime
    review_id: UUID
    agent: AgentType
    span_id: UUID
    parent_span: Optional[UUID] = None
    event_type: EventType
    model: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[int] = None
    outcome: Optional[ReviewOutcome] = None
    confidence: Optional[float] = None
    payload: Optional[dict] = None


class HITLReview(BaseModel):
    id: UUID
    review_id: UUID
    status: str = "pending"
    reviewer_id: Optional[str] = None
    decision: Optional[ReviewOutcome] = None
    feedback: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class HITLFeedback(BaseModel):
    id: UUID
    review_id: UUID
    finding_id: UUID
    developer_id: str
    is_valid: bool
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)