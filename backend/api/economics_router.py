from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from backend.database.postgres import get_db
from backend.economics.cost_repository import CostRepository
from backend.observability import get_logger

router = APIRouter(prefix="/economics", tags=["economics"])
logger = get_logger(__name__)


@router.get("/costs/daily")
async def get_daily_costs(
    days: int = Query(7, ge=1, le=30),
    session: AsyncSession = Depends(get_db),
):
    cost_repo = CostRepository(session)
    return await cost_repo.get_daily_costs(days)


@router.get("/costs/by-agent")
async def get_costs_by_agent(
    days: int = Query(7, ge=1, le=30),
    session: AsyncSession = Depends(get_db),
):
    cost_repo = CostRepository(session)
    return await cost_repo.get_costs_by_agent(days)


@router.get("/costs/by-review/{review_id}")
async def get_review_cost(
    review_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    cost_repo = CostRepository(session)
    return await cost_repo.get_review_cost(review_id)


@router.get("/health")
async def get_agent_health(
    minutes: int = Query(60, ge=1, le=1440),
    session: AsyncSession = Depends(get_db),
):
    cost_repo = CostRepository(session)
    return await cost_repo.get_agent_health(minutes)


@router.get("/budget/status")
async def get_budget_status(
    session: AsyncSession = Depends(get_db),
):
    cost_repo = CostRepository(session)
    return await cost_repo.get_budget_status()