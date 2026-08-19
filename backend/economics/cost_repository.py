from typing import List, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from backend.database.models import AgentEvent
from backend.observability import get_logger

logger = get_logger(__name__)


class CostRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_daily_costs(self, days: int = 7) -> List[Dict[str, Any]]:
        result = await self.session.execute(text("""
            SELECT 
                date(ts) as day,
                sum(cost_usd) as total_cost,
                sum(tokens_in + tokens_out) as total_tokens,
                count(distinct review_id) as reviews_count
            FROM agent_events
            WHERE ts >= now() - interval ':days days'
            AND event_type = 'llm.call'
            GROUP BY date(ts)
            ORDER BY day DESC
        """), {"days": days})
        
        return [
            {
                "day": row.day.isoformat() if row.day else None,
                "total_cost_usd": float(row.total_cost or 0),
                "total_tokens": int(row.total_tokens or 0),
                "reviews_count": int(row.reviews_count or 0),
            }
            for row in result.all()
        ]

    async def get_costs_by_agent(self, days: int = 7) -> List[Dict[str, Any]]:
        result = await self.session.execute(text("""
            SELECT 
                agent,
                sum(cost_usd) as total_cost,
                sum(tokens_in + tokens_out) as total_tokens,
                count(*) as call_count,
                avg(latency_ms) as avg_latency_ms
            FROM agent_events
            WHERE ts >= now() - interval ':days days'
            AND event_type = 'llm.call'
            GROUP BY agent
            ORDER BY total_cost DESC
        """), {"days": days})
        
        return [
            {
                "agent": row.agent,
                "total_cost_usd": float(row.total_cost or 0),
                "total_tokens": int(row.total_tokens or 0),
                "call_count": int(row.call_count or 0),
                "avg_latency_ms": float(row.avg_latency_ms or 0),
            }
            for row in result.all()
        ]

    async def get_review_cost(self, review_id: UUID) -> Dict[str, Any]:
        result = await self.session.execute(text("""
            SELECT 
                agent,
                sum(cost_usd) as total_cost,
                sum(tokens_in) as tokens_in,
                sum(tokens_out) as tokens_out,
                count(*) as call_count,
                sum(latency_ms) as total_latency_ms
            FROM agent_events
            WHERE review_id = :review_id
            AND event_type = 'llm.call'
            GROUP BY agent
        """), {"review_id": review_id})
        
        agents = []
        total_cost = 0.0
        total_tokens = 0
        
        for row in result.all():
            cost = float(row.total_cost or 0)
            tokens = int((row.tokens_in or 0) + (row.tokens_out or 0))
            agents.append({
                "agent": row.agent,
                "cost_usd": cost,
                "tokens_in": int(row.tokens_in or 0),
                "tokens_out": int(row.tokens_out or 0),
                "total_tokens": tokens,
                "call_count": int(row.call_count or 0),
                "total_latency_ms": int(row.total_latency_ms or 0),
            })
            total_cost += cost
            total_tokens += tokens
        
        return {
            "review_id": str(review_id),
            "total_cost_usd": total_cost,
            "total_tokens": total_tokens,
            "by_agent": agents,
        }

    async def get_agent_health(self, minutes: int = 60) -> List[Dict[str, Any]]:
        result = await self.session.execute(text("""
            SELECT 
                bucket,
                agent,
                llm_calls,
                cost_usd,
                p95_ms,
                rejection_rate
            FROM agent_health_1m
            WHERE bucket >= now() - interval ':minutes minutes'
            ORDER BY bucket DESC, agent
        """), {"minutes": minutes})
        
        return [
            {
                "bucket": row.bucket.isoformat() if row.bucket else None,
                "agent": row.agent,
                "llm_calls": int(row.llm_calls or 0),
                "cost_usd": float(row.cost_usd or 0),
                "p95_latency_ms": int(row.p95_ms or 0),
                "rejection_rate": float(row.rejection_rate or 0),
            }
            for row in result.all()
        ]

    async def get_budget_status(self) -> Dict[str, Any]:
        from backend.config import settings
        
        today_result = await self.session.execute(text("""
            SELECT sum(cost_usd) as today_cost
            FROM agent_events
            WHERE date(ts) = date(now())
            AND event_type = 'llm.call'
        """))
        
        today_cost = float(today_result.scalar() or 0)
        
        return {
            "daily_budget_usd": settings.daily_cost_budget_usd,
            "today_spend_usd": today_cost,
            "remaining_usd": settings.daily_cost_budget_usd - today_cost,
            "percentage_used": (today_cost / settings.daily_cost_budget_usd) * 100 if settings.daily_cost_budget_usd > 0 else 0,
            "daily_token_budget": settings.daily_token_budget,
        }