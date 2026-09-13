"""Tests for the LangGraph orchestrator (Phase 5)."""

from __future__ import annotations

from pr_review_agent.models.review import (
    AgentResult,
    ChangedFile,
    FindingSeverity,
    ReviewFinding,
    ReviewStatus,
)
from pr_review_agent.orchestrator.nodes import (
    architecture_agent_node,
    context_assembly_node,
    documentation_agent_node,
    quality_agent_node,
    security_agent_node,
    should_escalate,
    synthesis_node,
)
from pr_review_agent.orchestrator.state import ReviewState, create_initial_state


class TestReviewState:
    def test_create_initial_state(self):
        state = create_initial_state(
            review_id=1,
            pr_number=42,
            repository_full_name="org/repo",
            title="Test PR",
        )
        assert state["review_id"] == 1
        assert state["pr_number"] == 42
        assert state["repository_full_name"] == "org/repo"
        assert state["title"] == "Test PR"
        assert state["status"] == ReviewStatus.PENDING.value
        assert state["diff"] == ""
        assert state["changed_files"] == []
        assert state["agent_results"] == {}
        assert state["error"] is None

    def test_initial_state_defaults(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")
        assert state["total_additions"] == 0
        assert state["total_deletions"] == 0
        assert state["context_files"] == {}
        assert state["total_tokens"] == 0
        assert state["should_escalate_to_hitl"] is False


class TestContextAssemblyNode:
    async def test_success_with_diff(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")
        state["diff"] = "@@ -1,3 +1,4 @@\n+import os"

        result = await context_assembly_node(state)
        assert result["status"] == ReviewStatus.IN_PROGRESS.value
        assert "error" not in result

    async def test_failure_without_context(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")
        # No diff, no changed_files
        result = await context_assembly_node(state)
        assert result["status"] == ReviewStatus.FAILED.value
        assert "error" in result


class TestAgentNodes:
    """Test that all agent nodes return proper AgentResult structure."""

    async def test_security_agent_returns_result(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")
        state["diff"] = "+import os"
        state["changed_files"] = [
            ChangedFile(path="app.py", additions=1, deletions=0, patch="+import os")
        ]

        result = await security_agent_node(state)
        assert "agent_results" in result
        ar = result["agent_results"]["security"]
        assert isinstance(ar, AgentResult)
        assert ar.agent_type == "security"
        assert ar.duration_seconds >= 0

    async def test_architecture_agent_returns_result(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")
        result = await architecture_agent_node(state)
        ar = result["agent_results"]["architecture"]
        assert ar.agent_type == "architecture"

    async def test_quality_agent_returns_result(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")
        result = await quality_agent_node(state)
        ar = result["agent_results"]["quality"]
        assert ar.agent_type == "quality"

    async def test_documentation_agent_returns_result(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")
        result = await documentation_agent_node(state)
        ar = result["agent_results"]["documentation"]
        assert ar.agent_type == "documentation"


class TestSynthesisNode:
    async def test_synthesis_with_no_findings(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")
        state["agent_results"] = {
            "security": AgentResult(agent_type="security"),
            "quality": AgentResult(agent_type="quality"),
        }

        result = await synthesis_node(state)
        assert result["total_comments"] == 0
        assert result["summary"] == "No issues found. LGTM! 🎉"
        assert result["status"] == ReviewStatus.COMPLETED.value

    async def test_synthesis_deduplicates_findings(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")

        # Two agents find the same issue at same file+line+category
        duplicate_finding = ReviewFinding(
            file="app.py",
            line=10,
            severity=FindingSeverity.HIGH,
            category="security",
            title="SQL injection",
            description="Direct interpolation",
            confidence=0.9,
        )
        state["agent_results"] = {
            "security": AgentResult(
                agent_type="security",
                findings=[duplicate_finding],
                tokens_used=100,
            ),
            "quality": AgentResult(
                agent_type="quality",
                findings=[duplicate_finding],  # Same finding
                tokens_used=50,
            ),
        }

        result = await synthesis_node(state)
        assert result["total_comments"] == 1  # Deduplicated
        assert result["high_count"] == 1
        assert result["total_tokens"] == 150

    async def test_synthesis_sorts_by_severity(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")

        findings = [
            ReviewFinding(
                file="a.py",
                line=1,
                severity=FindingSeverity.LOW,
                category="quality",
                title="Low issue",
                description="",
            ),
            ReviewFinding(
                file="b.py",
                line=2,
                severity=FindingSeverity.CRITICAL,
                category="security",
                title="Critical issue",
                description="",
            ),
            ReviewFinding(
                file="c.py",
                line=3,
                severity=FindingSeverity.MEDIUM,
                category="quality",
                title="Medium issue",
                description="",
            ),
        ]

        state["agent_results"] = {
            "security": AgentResult(agent_type="security", findings=findings),
        }

        result = await synthesis_node(state)
        sorted_findings = result["sorted_findings"]

        # Should be sorted: CRITICAL first, then MEDIUM, then LOW
        assert sorted_findings[0].severity == FindingSeverity.CRITICAL
        assert sorted_findings[1].severity == FindingSeverity.MEDIUM
        assert sorted_findings[2].severity == FindingSeverity.LOW

    async def test_synthesis_applies_max_comments_cap(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")

        # Generate more findings than the cap (default 10)
        findings = [
            ReviewFinding(
                file=f"f{i}.py",
                line=i,
                severity=FindingSeverity.LOW,
                category="quality",
                title=f"Issue {i}",
                description="",
            )
            for i in range(20)
        ]

        state["agent_results"] = {
            "quality": AgentResult(agent_type="quality", findings=findings),
        }

        result = await synthesis_node(state)
        # Should be capped at max_comments_per_pr (10)
        assert result["total_comments"] <= 10


class TestShouldEscalate:
    def test_no_hitl_when_confidence_high(self):
        state: ReviewState = {"should_escalate_to_hitl": False}
        assert should_escalate(state) == "done"

    def test_hitl_when_confidence_low(self):
        state: ReviewState = {"should_escalate_to_hitl": True}
        assert should_escalate(state) == "hitl"

    def test_no_hitl_default(self):
        state = create_initial_state(review_id=1, pr_number=1, repository_full_name="r")
        assert should_escalate(state) == "done"
