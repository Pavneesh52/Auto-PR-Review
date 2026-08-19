from typing: Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database.models import HITLReviewRecord, PRReviewRecord
from backend.models.enums import ReviewOutcome
from backend.observability import get_logger
from backend.observability.events import emit_escalation

logger = get_logger(__name__)


class EscalationEngine:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def escalate_review(
        self,
        review_id: UUID,
        reason: str,
        agent: str = "aggregator",
        confidence: float = 0.0,
    ) -> Dict[str, Any]:
        result = await self.session.execute(
            select(HITLReviewRecord).where(HITLReviewRecord.review_id == review_id)
        )
        hitl = result.scalar_one_or_none()
        
        if not hitl:
            hitl = HITLReviewRecord(
                review_id=review_id,
                status="pending",
            )
            self.session.add(hitl)
            await self.session.flush()
        
        hitl.status = "escalated"
        hitl.feedback = reason
        await self.session.flush()
        
        await emit_escalation(self.session, review_id, agent, reason, confidence)
        
        logger.warning("review_escalated", review_id=str(review_id), reason=reason)
        
        return {
            "hitl_id": str(hitl.id),
            "review_id": str(review_id),
            "status": "escalated",
            "reason": reason,
        }

    async def auto_escalate_critical(self, review_id: UUID) -> Dict[str, Any]:
        return await self.escalate_review(
            review_id,
            "Critical severity finding detected",
            "aggregator",
            1.0,
        )

    async def auto_escalate_low_confidence(self, review_id: UUID, confidence: float) -> Dict[str, Any]:
        return await self.escalate_review(
            review_id,
            f"Overall confidence {confidence:.0%} below threshold",
            "aggregator",
            confidence,
        )


async def create_escalation_engine(session: AsyncSession) -> EscalationEngine:
    return EscalationEngine(session)