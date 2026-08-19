from fastapi import APIRouter, Depends
from backend.job_queue.arq_worker import get_queue_stats
from backend.observability import get_logger

router = APIRouter(prefix="/queue", tags=["queue"])
logger = get_logger(__name__)


@router.get("/stats")
async def queue_stats():
    return await get_queue_stats()


@router.get("/health")
async def queue_health():
    stats = await get_queue_stats()
    return {
        "healthy": stats.get("redis_connected", False),
        "stats": stats,
    }