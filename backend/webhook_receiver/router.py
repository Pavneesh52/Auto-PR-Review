from typing import Dict, Any
from uuid import uuid4
from backend.database.postgres import AsyncSessionLocal
from backend.database.repository import ReviewRepository, IdempotencyRepository
from backend.database.models import PRReviewRecord
from backend.job_queue.arq_worker import process_review_job
from backend.webhook_receiver.validator import validate_webhook
from backend.webhook_receiver.parser import parse_webhook_payload, extract_review_job
from backend.core.exceptions import IdempotencyError
from backend.observability import get_logger

logger = get_logger(__name__)


async def route_webhook(
    payload: bytes,
    signature: str,
    delivery_id: str,
) -> Dict[str, Any]:
    await validate_webhook(payload, signature, delivery_id)
    
    webhook = parse_webhook_payload(json.loads(payload))
    
    idempotency_key = delivery_id
    async with AsyncSessionLocal() as session:
        idempotency_repo = IdempotencyRepository(session)
        is_new = await idempotency_repo.check_and_set(idempotency_key)
        
        if not is_new:
            logger.info("webhook_duplicate", delivery_id=delivery_id)
            return {"status": "duplicate", "delivery_id": delivery_id}
    
    review_job = await extract_review_job(webhook)
    if not review_job:
        return {"status": "ignored", "reason": "Not a reviewable action"}
    
    review_id = uuid4()
    review_job.review_id = str(review_id)
    review_job.delivery_id = delivery_id
    
    async with AsyncSessionLocal() as session:
        review_repo = ReviewRepository(session)
        review = PRReviewRecord(
            id=review_id,
            repo=review_job.repo,
            pr_number=review_job.pr_number,
            pr_title=review_job.pr_title,
            pr_body=review_job.pr_body,
            diff=review_job.diff,
            base_sha=review_job.base_sha,
            head_sha=review_job.head_sha,
        )
        await review_repo.create_review(review)
        await session.commit()
    
    installation_id = webhook.installation.get("id") if webhook.installation else None
    
    job_data = {
        "review_id": str(review_id),
        "installation_id": installation_id,
    }
    
    from arq import create_pool
    redis = await create_pool()
    await redis.enqueue_job("process_review_job", job_data)
    await redis.close()
    
    logger.info("review_job_enqueued", review_id=str(review_id), repo=review_job.repo, pr=review_job.pr_number)
    
    return {"status": "enqueued", "review_id": str(review_id)}


import json