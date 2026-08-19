from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.database.postgres import get_db
from backend.database.repository import ReviewRepository, FindingRepository
from backend.database.models import PRReviewRecord, FindingRecord
from backend.api.schemas import ReviewResponse, ReviewListResponse, ReviewCreateRequest, FindingResponse
from backend.orchestrator.langgraph_engine import workflow_engine
from backend.observability import get_logger

router = APIRouter(prefix="/reviews", tags=["reviews"])
logger = get_logger(__name__)


@router.post("/", response_model=ReviewResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_review(
    request: ReviewCreateRequest,
    session: AsyncSession = Depends(get_db),
):
    review_repo = ReviewRepository(session)
    
    existing = await review_repo.get_review_by_repo_pr(request.repo, request.pr_number)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review for {request.repo}#{request.pr_number} already exists",
        )
    
    review = PRReviewRecord(
        repo=request.repo,
        pr_number=request.pr_number,
        pr_title=request.pr_title,
        pr_body=request.pr_body,
        diff=request.diff,
        base_sha=request.base_sha,
        head_sha=request.head_sha,
    )
    
    await review_repo.create_review(review)
    await session.commit()
    
    return ReviewResponse.from_orm(review)


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    review_repo = ReviewRepository(session)
    finding_repo = FindingRepository(session)
    
    review = await review_repo.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    findings = await finding_repo.get_findings(review_id)
    
    response = ReviewResponse.from_orm(review)
    response.findings = [FindingResponse.from_orm(f) for f in findings]
    return response


@router.get("/", response_model=ReviewListResponse)
async def list_reviews(
    repo: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    review_repo = ReviewRepository(session)
    
    query = select(PRReviewRecord)
    if repo:
        query = query.where(PRReviewRecord.repo == repo)
    
    total_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar() or 0
    
    query = query.order_by(PRReviewRecord.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await session.execute(query)
    reviews = result.scalars().all()
    
    return ReviewListResponse(
        reviews=[ReviewResponse.from_orm(r) for r in reviews],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{review_id}/run", response_model=dict)
async def run_review(
    review_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    review_repo = ReviewRepository(session)
    review = await review_repo.get_review(review_id)
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    try:
        result = await workflow_engine.execute_review(
            review_id, review.diff, review.repo, review.pr_number
        )
        return {"status": "completed", "result": result}
    except Exception as e:
        logger.error("review_execution_failed", review_id=str(review_id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Review execution failed: {e}")