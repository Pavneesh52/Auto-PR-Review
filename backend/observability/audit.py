from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from backend.database.models import AgentEvent, PRReviewRecord, FindingRecord
from backend.models.enums import AgentType, EventType, ReviewOutcome


class AuditTrail:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_review_trace(self, review_id: UUID) -> List[AgentEvent]:
        result = await self.session.execute(
            select(AgentEvent)
            .where(AgentEvent.review_id == review_id)
            .order_by(AgentEvent.ts)
        )
        return list(result.scalars().all())

    async def get_agent_trace(self, review_id: UUID, agent: AgentType) -> List[AgentEvent]:
        result = await self.session.execute(
            select(AgentEvent)
            .where(and_(AgentEvent.review_id == review_id, AgentEvent.agent == agent.value))
            .order_by(AgentEvent.ts)
        )
        return list(result.scalars().all())

    async def get_llm_calls(self, review_id: UUID) -> List[AgentEvent]:
        result = await self.session.execute(
            select(AgentEvent)
            .where(and_(
                AgentEvent.review_id == review_id,
                AgentEvent.event_type == EventType.LLM_CALL.value
            ))
            .order_by(AgentEvent.ts)
        )
        return list(result.scalars().all())

    async def reconstruct_review(self, review_id: UUID) -> Dict[str, Any]:
        review_result = await self.session.execute(
            select(PRReviewRecord).where(PRReviewRecord.id == review_id)
        )
        review = review_result.scalar_one_or_none()
        
        if not review:
            return None
        
        findings_result = await self.session.execute(
            select(FindingRecord).where(FindingRecord.review_id == review_id)
        )
        findings = list(findings_result.scalars().all())
        
        events = await self.get_review_trace(review_id)
        
        return {
            "review": {
                "id": str(review.id),
                "repo": review.repo,
                "pr_number": review.pr_number,
                "pr_title": review.pr_title,
                "overall_confidence": float(review.overall_confidence),
                "outcome": review.outcome,
                "hitl_required": review.hitl_required,
                "created_at": review.created_at.isoformat(),
            },
            "findings": [
                {
                    "id": str(f.id),
                    "agent_type": f.agent_type,
                    "severity": f.severity,
                    "category": f.category,
                    "summary": f.summary,
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "suggestion": f.suggestion,
                    "confidence": float(f.confidence),
                    "rationale": f.rationale,
                }
                for f in findings
            ],
            "trace": [
                {
                    "ts": e.ts.isoformat(),
                    "agent": e.agent,
                    "event_type": e.event_type,
                    "model": e.model,
                    "tokens_in": e.tokens_in,
                    "tokens_out": e.tokens_out,
                    "cost_usd": float(e.cost_usd) if e.cost_usd else None,
                    "latency_ms": e.latency_ms,
                    "outcome": e.outcome,
                    "confidence": float(e.confidence) if e.confidence else None,
                }
                for e in events
            ],
        }


async def create_audit_trail(session: AsyncSession) -> AuditTrail:
    return AuditTrail(session)