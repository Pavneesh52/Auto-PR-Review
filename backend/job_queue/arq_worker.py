import arq
from arq.connections import RedisSettings
from typing import Dict, Any
from uuid import UUID
from backend.config import settings
from backend.orchestrator.langgraph_engine import workflow_engine
from backend.database.postgres import AsyncSessionLocal
from backend.database.repository import ReviewRepository
from backend.integrations.github_client import github_client
from backend.observability import get_logger

logger = get_logger(__name__)


async def process_review_job(ctx: Dict[str, Any], job_data: Dict[str, Any]) -> Dict[str, Any]:
    review_id = UUID(job_data["review_id"])
    
    logger.info("review_job_started", review_id=str(review_id))
    
    async with AsyncSessionLocal() as session:
        review_repo = ReviewRepository(session)
        review = await review_repo.get_review(review_id)
        
        if not review:
            logger.error("review_not_found", review_id=str(review_id))
            return {"status": "error", "error": "Review not found"}
        
        try:
            result = await workflow_engine.execute_review(
                review_id, review.diff, review.repo, review.pr_number
            )
            
            if result.get("hitl_required"):
                logger.info("review_requires_hitl", review_id=str(review_id))
                return {"status": "hitl_required", "result": result}
            
            installation_id = job_data.get("installation_id")
            if installation_id:
                await post_review_to_github(installation_id, review, result)
            
            logger.info("review_job_completed", review_id=str(review_id))
            return {"status": "completed", "result": result}
            
        except Exception as e:
            logger.error("review_job_failed", review_id=str(review_id), error=str(e))
            return {"status": "error", "error": str(e)}


async def post_review_to_github(
    installation_id: int,
    review,
    result: Dict[str, Any],
):
    findings = result.get("findings", [])
    
    if not findings:
        body = "Automated Review Complete\n\nNo issues found. The code looks good!"
        event = "APPROVE"
    else:
        critical_findings = [f for f in findings if f.get("severity") == "CRITICAL"]
        if critical_findings:
            body = f"Critical Issues Found ({len(critical_findings)} critical, {len(findings)} total)\n\n"
            event = "REQUEST_CHANGES"
        else:
            body = f"Review Complete ({len(findings)} findings)\n\n"
            event = "COMMENT"
        
        body += "## Findings\n\n"
        for f in findings:
            severity_emoji = {
                "CRITICAL": "[CRITICAL]",
                "HIGH": "[HIGH]",
                "MEDIUM": "[MEDIUM]",
                "LOW": "[LOW]",
                "INFO": "[INFO]",
            }.get(f.get("severity", "INFO"), "[INFO]")
            
            body += f"{severity_emoji} **{f.get('severity', 'INFO')}** [{f.get('category', 'general')}] "
            body += f"`{f.get('file_path', '')}:{f.get('line_start', 0)}`\n"
            body += f"> {f.get('summary', '')}\n\n"
            body += f"> **Suggestion:** {f.get('suggestion', '')}\n\n"
            body += f"> *Confidence: {f.get('confidence', 0):.0%}*\n\n---\n\n"
    
    comments = []
    for f in findings:
        comments.append({
            "path": f.get("file_path", ""),
            "line": f.get("line_start", 1),
            "side": "RIGHT",
            "body": f"**{f.get('severity', 'INFO')} [{f.get('category', 'general')}]**\n\n"
                    f"{f.get('summary', '')}\n\n"
                    f"**Suggestion:** {f.get('suggestion', '')}\n\n"
                    f"*Confidence: {f.get('confidence', 0):.0%}*",
        })
    
    await github_client.post_review(
        installation_id=installation_id,
        repo_full_name=review.repo,
        pr_number=review.pr_number,
        body=body,
        event=event,
        comments=comments,
    )


class WorkerSettings:
    functions = [process_review_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.max_concurrent_reviews
    job_timeout = settings.review_timeout_seconds
    keep_result = 86400


async def get_queue_stats() -> Dict[str, Any]:
    redis = arq.create_pool(settings.redis_url)
    try:
        info = await redis.info()
        return {
            "redis_connected": True,
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
        }
    except Exception as e:
        return {"redis_connected": False, "error": str(e)}
    finally:
        await redis.close()