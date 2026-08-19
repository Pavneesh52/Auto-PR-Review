from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.models import AgentEvent
from backend.models.enums import AgentType, EventType, ReviewOutcome
from contextvars import ContextVar

current_span: ContextVar[Optional[UUID]] = ContextVar("current_span", default=None)
current_review: ContextVar[Optional[UUID]] = ContextVar("current_review", default=None)


async def emit_agent_event(
    session: AsyncSession,
    review_id: UUID,
    agent: AgentType,
    event_type: EventType,
    model: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    cost_usd: Optional[float] = None,
    latency_ms: Optional[int] = None,
    outcome: Optional[ReviewOutcome] = None,
    confidence: Optional[float] = None,
    payload: Optional[Dict[str, Any]] = None,
    parent_span: Optional[UUID] = None,
) -> AgentEvent:
    span_id = current_span.get() or uuid4()
    
    event = AgentEvent(
        ts=datetime.utcnow(),
        review_id=review_id,
        agent=agent.value,
        span_id=span_id,
        parent_span=parent_span,
        event_type=event_type.value,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        outcome=outcome.value if outcome else None,
        confidence=confidence,
        payload=payload,
    )
    
    session.add(event)
    await session.flush()
    return event


class SpanContext:
    def __init__(self, session: AsyncSession, review_id: UUID, agent: AgentType):
        self.session = session
        self.review_id = review_id
        self.agent = agent
        self.span_id = uuid4()
        self.parent_span = current_span.get()

    async def __aenter__(self) -> "SpanContext":
        current_span.set(self.span_id)
        current_review.set(self.review_id)
        await emit_agent_event(
            self.session,
            self.review_id,
            self.agent,
            EventType.SPAN_START,
            parent_span=self.parent_span,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await emit_agent_event(
            self.session,
            self.review_id,
            self.agent,
            EventType.SPAN_END,
            parent_span=self.parent_span,
        )
        if self.parent_span:
            current_span.set(self.parent_span)
        else:
            current_span.set(None)
        current_review.set(None)


async def emit_llm_call(
    session: AsyncSession,
    review_id: UUID,
    agent: AgentType,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: int,
    confidence: Optional[float] = None,
    payload: Optional[Dict[str, Any]] = None,
):
    await emit_agent_event(
        session,
        review_id,
        agent,
        EventType.LLM_CALL,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        confidence=confidence,
        payload=payload,
    )


async def emit_tool_call(
    session: AsyncSession,
    review_id: UUID,
    agent: AgentType,
    tool_name: str,
    latency_ms: int,
    payload: Optional[Dict[str, Any]] = None,
):
    await emit_agent_event(
        session,
        review_id,
        agent,
        EventType.TOOL_CALL,
        latency_ms=latency_ms,
        payload={"tool": tool_name, **(payload or {})},
    )


async def emit_decision(
    session: AsyncSession,
    review_id: UUID,
    agent: AgentType,
    outcome: ReviewOutcome,
    confidence: float,
    payload: Optional[Dict[str, Any]] = None,
):
    await emit_agent_event(
        session,
        review_id,
        agent,
        EventType.DECISION,
        outcome=outcome,
        confidence=confidence,
        payload=payload,
    )


async def emit_escalation(
    session: AsyncSession,
    review_id: UUID,
    agent: AgentType,
    reason: str,
    confidence: float,
):
    await emit_agent_event(
        session,
        review_id,
        agent,
        EventType.ESCALATION,
        confidence=confidence,
        payload={"reason": reason},
    )