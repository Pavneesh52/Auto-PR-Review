from typing import Dict, Any, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.graph import StateGraph
from backend.orchestrator.state import ReviewState
from backend.agents import security_agent, quality_agent, test_agent, docs_agent
from backend.models.enums import AgentType, ReviewOutcome
from backend.observability import get_logger
from backend.config import settings

logger = get_logger(__name__)


async def security_node(state: ReviewState, session: AsyncSession) -> ReviewState:
    logger.info("security_agent_started", review_id=str(state.review_id))
    state.current_agent = AgentType.SECURITY
    
    try:
        findings = await security_agent.review(
            session, state.review_id, state.diff, state.repo
        )
        state.security_findings = findings
        logger.info("security_agent_completed", review_id=str(state.review_id), findings=len(findings))
    except Exception as e:
        logger.error("security_agent_failed", review_id=str(state.review_id), error=str(e))
        state.error = f"Security agent failed: {e}"
    
    return state


async def quality_node(state: ReviewState, session: AsyncSession) -> ReviewState:
    logger.info("quality_agent_started", review_id=str(state.review_id))
    state.current_agent = AgentType.QUALITY
    
    try:
        findings = await quality_agent.review(
            session, state.review_id, state.diff, state.repo
        )
        state.quality_findings = findings
        logger.info("quality_agent_completed", review_id=str(state.review_id), findings=len(findings))
    except Exception as e:
        logger.error("quality_agent_failed", review_id=str(state.review_id), error=str(e))
        state.error = f"Quality agent failed: {e}"
    
    return state


async def tests_node(state: ReviewState, session: AsyncSession) -> ReviewState:
    logger.info("tests_agent_started", review_id=str(state.review_id))
    state.current_agent = AgentType.TESTS
    
    try:
        findings = await test_agent.review(
            session, state.review_id, state.diff, state.repo
        )
        state.tests_findings = findings
        logger.info("tests_agent_completed", review_id=str(state.review_id), findings=len(findings))
    except Exception as e:
        logger.error("tests_agent_failed", review_id=str(state.review_id), error=str(e))
        state.error = f"Tests agent failed: {e}"
    
    return state


async def docs_node(state: ReviewState, session: AsyncSession) -> ReviewState:
    logger.info("docs_agent_started", review_id=str(state.review_id))
    state.current_agent = AgentType.DOCS
    
    try:
        findings = await docs_agent.review(
            session, state.review_id, state.diff, state.repo
        )
        state.docs_findings = findings
        logger.info("docs_agent_completed", review_id=str(state.review_id), findings=len(findings))
    except Exception as e:
        logger.error("docs_agent_failed", review_id=str(state.review_id), error=str(e))
        state.error = f"Docs agent failed: {e}"
    
    return state


def merge_findings(findings_lists: List[List]) -> List:
    all_findings = []
    for findings in findings_lists:
        all_findings.extend(findings)
    
    deduped = {}
    for f in all_findings:
        key = (f.file_path, f.line_start, f.category)
        if key not in deduped or f.confidence > deduped[key].confidence:
            deduped[key] = f
    
    return list(deduped.values())


async def aggregator_node(state: ReviewState, session: AsyncSession) -> ReviewState:
    logger.info("aggregator_started", review_id=str(state.review_id))
    state.current_agent = AgentType.AGGREGATOR
    
    all_findings = merge_findings([
        state.security_findings,
        state.quality_findings,
        state.tests_findings,
        state.docs_findings,
    ])
    
    state.merged_findings = all_findings
    
    if all_findings:
        state.overall_confidence = sum(f.confidence for f in all_findings) / len(all_findings)
    else:
        state.overall_confidence = 1.0
    
    critical_count = sum(1 for f in all_findings if f.severity.value == "CRITICAL")
    
    if critical_count > 0:
        state.hitl_required = True
        state.outcome = ReviewOutcome.CRITICAL_BLOCK
    elif state.overall_confidence < settings.confidence_threshold:
        state.hitl_required = True
        state.outcome = ReviewOutcome.ESCALATED
    else:
        state.hitl_required = False
        state.outcome = ReviewOutcome.APPROVED
    
    logger.info(
        "aggregator_completed",
        review_id=str(state.review_id),
        total_findings=len(all_findings),
        overall_confidence=state.overall_confidence,
        hitl_required=state.hitl_required,
        outcome=state.outcome.value if state.outcome else None,
    )
    
    return state


async def hitl_gate_node(state: ReviewState, session: AsyncSession) -> ReviewState:
    logger.info("hitl_gate_evaluated", review_id=str(state.review_id), hitl_required=state.hitl_required)
    
    if state.hitl_required:
        state.outcome = ReviewOutcome.ESCALATED
    
    return state


async def error_handler_node(state: ReviewState, session: AsyncSession) -> ReviewState:
    logger.error("review_error", review_id=str(state.review_id), error=state.error)
    state.outcome = ReviewOutcome.ESCALATED
    state.hitl_required = True
    return state