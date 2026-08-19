from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database.postgres import get_db
from backend.database.repository import HITLRepository, ReviewRepository, FindingRepository
from backend.database.models import HITLReviewRecord, HITLFeedbackRecord, PRReviewRecord, FindingRecord
from backend.models.enums import ReviewOutcome
from backend.observability import get_logger

router = APIRouter(prefix="/hitl", tags=["hitl"])
logger = get_logger(__name__)


class HITLDecisionRequest(BaseModel):
    decision: ReviewOutcome
    reviewer_id: str
    feedback: Optional[str] = None


class HITLFeedbackRequest(BaseModel):
    finding_id: UUID
    developer_id: str
    is_valid: bool
    comment: Optional[str] = None


@router.get("/queue")
async def get_hitl_queue(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
):
    hitl_repo = HITLRepository(session)
    review_repo = ReviewRepository(session)
    
    query = select(HITLReviewRecord).join(PRReviewRecord)
    if status:
        query = query.where(HITLReviewRecord.status == status)
    
    query = query.order_by(HITLReviewRecord.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    hitl_reviews = result.scalars().all()
    
    return [
        {
            "hitl_id": str(h.id),
            "review_id": str(h.review_id),
            "repo": h.review.repo,
            "pr_number": h.review.pr_number,
            "pr_title": h.review.pr_title,
            "status": h.status,
            "overall_confidence": float(h.review.overall_confidence),
            "created_at": h.created_at.isoformat(),
        }
        for h in hitl_reviews
    ]


@router.get("/{hitl_id}")
async def get_hitl_review(
    hitl_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    hitl_repo = HITLRepository(session)
    hitl = await hitl_repo.get_hitl_review_by_id(hitl_id)
    if not hitl:
        raise HTTPException(status_code=404, detail="HITL review not found")
    
    review_repo = ReviewRepository(session)
    finding_repo = FindingRepository(session)
    
    review = await review_repo.get_review(hitl.review_id)
    findings = await finding_repo.get_findings(hitl.review_id)
    
    return {
        "hitl": {
            "id": str(hitl.id),
            "review_id": str(hitl.review_id),
            "status": hitl.status,
            "reviewer_id": hitl.reviewer_id,
            "decision": hitl.decision,
            "feedback": hitl.feedback,
            "created_at": hitl.created_at.isoformat(),
        },
        "review": {
            "id": str(review.id),
            "repo": review.repo,
            "pr_number": review.pr_number,
            "pr_title": review.pr_title,
            "overall_confidence": float(review.overall_confidence),
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
    }


@router.post("/{hitl_id}/decide")
async def decide_hitl_review(
    hitl_id: UUID,
    request: HITLDecisionRequest,
    session: AsyncSession = Depends(get_db),
):
    hitl_repo = HITLRepository(session)
    hitl = await hitl_repo.get_hitl_review_by_id(hitl_id)
    if not hitl:
        raise HTTPException(status_code=404, detail="HITL review not found")
    
    hitl.status = "completed"
    hitl.reviewer_id = request.reviewer_id
    hitl.decision = request.decision.value
    hitl.feedback = request.feedback
    
    review_repo = ReviewRepository(session)
    await review_repo.update_review(
        hitl.review_id,
        outcome=request.decision,
        hitl_required=False,
    )
    
    await session.commit()
    
    return {"status": "completed", "decision": request.decision.value}


@router.post("/{hitl_id}/feedback")
async def submit_feedback(
    hitl_id: UUID,
    request: HITLFeedbackRequest,
    session: AsyncSession = Depends(get_db),
):
    hitl_repo = HITLRepository(session)
    hitl = await hitl_repo.get_hitl_review_by_id(hitl_id)
    if not hitl:
        raise HTTPException(status_code=404, detail="HITL review not found")
    
    feedback = HITLFeedbackRecord(
        review_id=hitl.review_id,
        finding_id=request.finding_id,
        developer_id=request.developer_id,
        is_valid=request.is_valid,
        comment=request.comment,
    )
    
    await hitl_repo.create_feedback(feedback)
    await session.commit()
    
    return {"status": "feedback_recorded"}