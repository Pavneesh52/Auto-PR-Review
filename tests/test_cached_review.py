"""Tests for Phase 14 caching behaviour and the review-history schema."""

from __future__ import annotations

from pr_review_agent.db.models import ReviewRow
from pr_review_agent.models.review import FindingSeverity, ReviewFinding, ReviewStatus
from pr_review_agent.orchestrator.graph import run_review


def _cached_finding() -> ReviewFinding:
    return ReviewFinding(
        file="app.py",
        line=12,
        severity=FindingSeverity.MEDIUM,
        category="quality",
        title="Cached issue",
        description="from cache",
        confidence=0.95,
        source_agent="quality",
    )


class TestFullyCachedReview:
    async def test_cached_only_review_skips_llm_agents(self):
        """When every file is a cache hit there is nothing to analyse: the
        pipeline must synthesize directly instead of calling the LLM four times."""
        state = await run_review(
            review_id=1,
            pr_number=42,
            repository_full_name="org/repo",
            cached_findings=[_cached_finding()],
        )

        assert state["status"] == ReviewStatus.COMPLETED.value
        assert state["total_comments"] == 1
        assert state["sorted_findings"][0].title == "Cached issue"
        # No agents ran, so there are no agent results and no token spend
        assert state["agent_results"] == {}
        assert state["total_tokens"] == 0

    async def test_empty_review_with_no_cache_still_fails_gracefully(self):
        """No diff and no cache is a real error, not a silent success."""
        state = await run_review(
            review_id=1,
            pr_number=42,
            repository_full_name="org/repo",
        )
        assert state["status"] == ReviewStatus.FAILED.value
        assert state["error"]


class TestReviewHistorySchema:
    def test_repo_pr_index_is_not_unique(self):
        """Regression: a unique (repo, PR) index made the second push for a PR
        blow up with an IntegrityError, silently dropping the review."""
        indexes = {index.name: index for index in ReviewRow.__table__.indexes}
        assert "ix_reviews_repo_pr" in indexes
        assert indexes["ix_reviews_repo_pr"].unique is False
