from typing import Optional
from pydantic import BaseModel, Field
from uuid import UUID
from .enums import AgentType, Severity, FindingCategory


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
    id: Optional[UUID] = None


class FindingCreate(Finding):
    pass


class FindingResponse(Finding):
    id: UUID
    review_id: UUID
    created_at: str

    class Config:
        from_attributes = True