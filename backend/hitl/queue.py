from typing: List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.database.models import HITLReviewRecord, PRReviewRecord
from backend.models.enums import ReviewOutcome
from backend.observability import get_logger

logger = get_logger(__name__)


class HITLQueue:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_pending_reviews(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(HITLReviewRecord)
            .join(PRReviewRecord)
            .where(HITLReviewRecord.status == "pending")
            .order_by(HITLReviewRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        hitl_reviews = result.scalars().all()
        
        return [
            {
                "hitl_id": str(h.id),
                "review_id": str(h.review_id),
                "repo": h.review.repo,
                "pr_number": h.review.pr_number,
                "pr_title": h.review.pr_title,
                "overall_confidence": float(h.review.overall_confidence),
                "created_at": h.created_at.isoformat(),
            }
            for h in hitl_reviews
        ]

    async def get_queue_stats(self) -> Dict[str, Any]:
        pending_result = await self.session.execute(
            select(func.count(HITLReviewRecord.id)).where(HITLReviewRecord.status == "pending")
        )
        pending = pending_result.scalar() or 0
        
        completed_result = await self.session.execute(
            select(func.count(HITLReviewRecord.id)).where(HITLReviewRecord.status == "completed")
        )
        completed = completed_result.scalar() or 0
        
        return {
            "pending": pending,
            "completed": completed,
            "total": pending + completed,
        }


async def create_hitl_queue(session: AsyncSession) -> HITLQueue:
    return HITLQueue(session)