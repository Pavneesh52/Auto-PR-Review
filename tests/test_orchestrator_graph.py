"""Integration test for the LangGraph review graph.

Tests the full pipeline: context → agents → synthesis.
"""

from __future__ import annotations

from pr_review_agent.orchestrator.graph import build_review_graph
from pr_review_agent.orchestrator.state import create_initial_state


class TestReviewGraph:
    def test_graph_builds_successfully(self):
        """Verify the graph compiles without errors."""
        graph = build_review_graph()
        compiled = graph.compile()
        assert compiled is not None

    async def test_full_pipeline_with_empty_review(self):
        """Run the full pipeline with no findings — should produce LGTM."""
        graph = build_review_graph()
        compiled = graph.compile()

        initial_state = create_initial_state(
            review_id=1,
            pr_number=42,
            repository_full_name="org/repo",
            title="Test PR",
            body="Adds new feature",
            author="dev",
            base_branch="main",
            head_sha="abc123",
        )
        initial_state["diff"] = "@@ -1,3 +1,4 @@\n+import os"
        initial_state["changed_files"] = []

        final_state = await compiled.ainvoke(initial_state)

        assert final_state["status"] == "completed"
        assert final_state["total_comments"] == 0
        assert final_state["summary"] == "No issues found. LGTM! 🎉"
        assert final_state["error"] is None

    async def test_full_pipeline_executes_all_agents(self):
        """Verify all 4 agent nodes run and produce results."""
        graph = build_review_graph()
        compiled = graph.compile()

        state = create_initial_state(
            review_id=2,
            pr_number=10,
            repository_full_name="org/app",
        )
        state["diff"] = "+new code"
        state["changed_files"] = []

        final_state = await compiled.ainvoke(state)

        # All 4 agents should have produced results
        agent_results = final_state.get("agent_results", {})
        assert "security" in agent_results
        assert "architecture" in agent_results
        assert "quality" in agent_results
        assert "documentation" in agent_results
