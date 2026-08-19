from typing: Dict, Any, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database.models import HITLFeedbackRecord
from backend.observability import get_logger

logger = get_logger(__name__)


class FeedbackManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_feedback(
        self,
        review_id: UUID,
        finding_id: UUID,
        developer_id: str,
        is_valid: bool,
        comment: str = None,
    ) -> Dict[str, Any]:
        feedback = HITLFeedbackRecord(
            review_id=review_id,
            finding_id=finding_id,
            developer_id=developer_id,
            is_valid=is_valid,
            comment=comment,
        )
        self.session.add(feedback)
        await self.session.flush()
        
        logger.info("feedback_recorded", review_id=str(review_id), finding_id=str(finding_id), is_valid=is_valid)
        
        return {
            "id": str(feedback.id),
            "review_id": str(review_id),
            "finding_id": str(finding_id),
            "is_valid": is_valid,
        }

    async def get_feedback_for_review(self, review_id: UUID) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(HITLFeedbackRecord).where(HITLFeedbackRecord.review_id == review_id)
        )
        feedback_list = result.scalars().all()
        
        return [
            {
                "id": str(f.id),
                "finding_id": str(f.finding_id),
                "developer_id": f.developer_id,
                "is_valid": f.is_valid,
                "comment": f.comment,
                "created_at": f.created_at.isoformat(),
            }
            for f in feedback_list
        ]

    async def get_feedback_stats(self, review_id: UUID = None) -> Dict[str, Any]:
        query = select(HITLFeedbackRecord)
        if review_id:
            query = query.where(HITLFeedbackRecord.review_id == review_id)
        
        result = await self.session.execute(query)
        feedback_list = result.scalars().all()
        
        total = len(feedback_list)
        valid = sum(1 for f in feedback_list if f.is_valid)
        invalid = total - valid
        
        return {
            "total": total,
            "valid": valid,
            "invalid": invalid,
            "validity_rate": valid / total if total > 0 else 0,
        }


async def create_feedback_manager(session: AsyncSession) -> FeedbackManager:
    return FeedbackManager(session)