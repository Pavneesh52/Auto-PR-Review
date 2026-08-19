from typing: Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database.models import HITLReviewRecord, PRReviewRecord, FindingRecord, HITLFeedbackRecord
from backend.models.enums import ReviewOutcome
from backend.observability import get_logger

logger = get_logger(__name__)


class DisputeManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_dispute(
        self,
        review_id: UUID,
        developer_id: str,
        finding_id: UUID,
        reason: str,
    ) -> Dict[str, Any]:
        result = await self.session.execute(
            select(HITLReviewRecord).where(HITLReviewRecord.review_id == review_id)
        )
        hitl = result.scalar_one_or_none()
        
        if not hitl:
            hitl = HITLReviewRecord(
                review_id=review_id,
                status="disputed",
            )
            self.session.add(hitl)
        else:
            hitl.status = "disputed"
            hitl.feedback = reason
        
        await self.session.flush()
        
        logger.info("dispute_created", review_id=str(review_id), finding_id=str(finding_id), developer_id=developer_id)
        
        return {
            "hitl_id": str(hitl.id),
            "review_id": str(review_id),
            "finding_id": str(finding_id),
            "status": "disputed",
            "reason": reason,
        }

    async def resolve_dispute(
        self,
        review_id: UUID,
        resolver_id: str,
        decision: ReviewOutcome,
        resolution_note: str = None,
    ) -> Dict[str, Any]:
        result = await self.session.execute(
            select(HITLReviewRecord).where(HITLReviewRecord.review_id == review_id)
        )
        hitl = result.scalar_one_or_none()
        
        if not hitl:
            raise ValueError(f"No HITL review found for {review_id}")
        
        hitl.status = "resolved"
        hitl.reviewer_id = resolver_id
        hitl.decision = decision.value
        if resolution_note:
            hitl.feedback = (hitl.feedback or "") + f"\n\nResolution: {resolution_note}"
        
        review_result = await self.session.execute(
            select(PRReviewRecord).where(PRReviewRecord.id == review_id)
        )
        review = review_result.scalar_one_or_none()
        if review:
            review.outcome = decision.value
            review.hitl_required = False
        
        await self.session.flush()
        
        logger.info("dispute_resolved", review_id=str(review_id), decision=decision.value)
        
        return {
            "hitl_id": str(hitl.id),
            "review_id": str(review_id),
            "status": "resolved",
            "decision": decision.value,
        }


async def create_dispute_manager(session: AsyncSession) -> DisputeManager:
    return DisputeManager(session)