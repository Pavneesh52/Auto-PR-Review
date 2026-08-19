from typing import Dict, Any, Optional
from uuid import UUID
from backend.orchestrator.state import ReviewState
from backend.orchestrator.graph import create_review_graph, run_review_workflow
from backend.core.workflow_engine import WorkflowEngine
from backend.database.postgres import AsyncSessionLocal
from backend.database.repository import ReviewRepository, FindingRepository, HITLRepository
from backend.database.models import PRReviewRecord, FindingRecord, HITLReviewRecord
from backend.models.enums import ReviewOutcome
from backend.observability import get_logger
from backend.config import settings

logger = get_logger(__name__)


class LangGraphEngine(WorkflowEngine):
    def __init__(self):
        self.graph = create_review_graph()
        self.app = self.graph.compile()

    async def execute_review(self, review_id: UUID, diff: str, repo: str, pr_number: int) -> Dict[str, Any]:
        async with AsyncSessionLocal() as session:
            review_repo = ReviewRepository(session)
            review_record = await review_repo.get_review(review_id)
            
            if not review_record:
                raise ValueError(f"Review {review_id} not found")
            
            state = ReviewState(
                review_id=review_id,
                repo=repo,
                pr_number=pr_number,
                pr_title=review_record.pr_title,
                pr_body=review_record.pr_body,
                diff=diff,
                base_sha=review_record.base_sha,
                head_sha=review_record.head_sha,
            )
            
            result = await self.app.ainvoke(state, config={"configurable": {"session": session}})
            
            await self._persist_results(session, review_id, result)
            
            return {
                "review_id": str(review_id),
                "findings": [f.dict() for f in result.get("merged_findings", [])],
                "overall_confidence": result.get("overall_confidence", 0.0),
                "hitl_required": result.get("hitl_required", False),
                "outcome": result.get("outcome"),
            }

    async def resume_review(self, review_id: UUID, checkpoint: Dict[str, Any]) -> Dict[str, Any]:
        pass

    async def get_state(self, review_id: UUID) -> Optional[Dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            review_repo = ReviewRepository(session)
            review_record = await review_repo.get_review(review_id)
            if review_record:
                return {
                    "review_id": str(review_record.id),
                    "outcome": review_record.outcome,
                    "hitl_required": review_record.hitl_required,
                    "overall_confidence": float(review_record.overall_confidence),
                }
        return None

    async def _persist_results(self, session, review_id: UUID, result: ReviewState):
        review_repo = ReviewRepository(session)
        finding_repo = FindingRepository(session)
        hitl_repo = HITLRepository(session)
        
        await review_repo.update_review(
            review_id,
            merged_findings=result.merged_findings,
            overall_confidence=result.overall_confidence,
            hitl_required=result.hitl_required,
            outcome=result.outcome.value if result.outcome else None,
        )
        
        if result.merged_findings:
            finding_records = [
                FindingRecord(
                    review_id=review_id,
                    agent_type=f.agent_type.value,
                    severity=f.severity.value,
                    category=f.category.value,
                    summary=f.summary,
                    file_path=f.file_path,
                    line_start=f.line_start,
                    line_end=f.line_end,
                    suggestion=f.suggestion,
                    confidence=f.confidence,
                    rationale=f.rationale,
                )
                for f in result.merged_findings
            ]
            await finding_repo.create_findings(finding_records)
        
        if result.hitl_required:
            await hitl_repo.create_hitl_review(
                HITLReviewRecord(
                    review_id=review_id,
                    status="pending",
                )
            )


workflow_engine = LangGraphEngine()