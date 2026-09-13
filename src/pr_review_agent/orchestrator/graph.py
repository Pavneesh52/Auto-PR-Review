"""LangGraph state graph definition.

Phase 5 - Builds the review pipeline as a stateful graph:

    ┌─────────────────┐
    │ context_assembly │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  (fan-out to    │
    │   4 agents in   │
    │   parallel)     │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │    synthesis    │
    └────────┬────────┘
             │
      ┌──────▼──────┐
      │ should_hitl? │
      └──┬──────┬───┘
         │      │
      done   hitl (pause for approval)
         │      │
      ┌──▼──┐ ┌─▼────────┐
      │ END │ │ hitl_gate │
      └─────┘ └──────────┘
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import structlog
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from pr_review_agent.models.review import ReviewFinding, ReviewStatus
from pr_review_agent.orchestrator.nodes import (
    architecture_agent_node,
    context_assembly_node,
    documentation_agent_node,
    hitl_gate_node,
    quality_agent_node,
    security_agent_node,
    should_escalate,
    synthesis_node,
    synthesize,
)
from pr_review_agent.orchestrator.state import ReviewState, create_initial_state

logger = structlog.get_logger(__name__)


def build_review_graph() -> StateGraph:
    """Build the review pipeline graph.

    Architecture:
        context_assembly
            → [security, architecture, quality, documentation] (parallel)
            → synthesis
            → (conditional) should_escalate?
                → if no: END
                → if yes: hitl_gate → END
    """
    graph = StateGraph(ReviewState)

    # --- Nodes ---
    graph.add_node("context_assembly", context_assembly_node)
    graph.add_node("security_agent", security_agent_node)
    graph.add_node("architecture_agent", architecture_agent_node)
    graph.add_node("quality_agent", quality_agent_node)
    graph.add_node("documentation_agent", documentation_agent_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("hitl_gate", hitl_gate_node)

    # --- Entry point ---
    graph.set_entry_point("context_assembly")

    # --- Edges ---

    # After context assembly, fan out to all agents in parallel
    # LangGraph executes nodes that share no dependency in parallel
    graph.add_edge("context_assembly", "security_agent")
    graph.add_edge("context_assembly", "architecture_agent")
    graph.add_edge("context_assembly", "quality_agent")
    graph.add_edge("context_assembly", "documentation_agent")

    # All agents converge to synthesis
    graph.add_edge("security_agent", "synthesis")
    graph.add_edge("architecture_agent", "synthesis")
    graph.add_edge("quality_agent", "synthesis")
    graph.add_edge("documentation_agent", "synthesis")

    # Synthesis → conditional HITL check
    graph.add_conditional_edges(
        "synthesis",
        should_escalate,
        {
            "hitl": "hitl_gate",
            "done": END,
        },
    )

    # HITL gate → END (processor handles actual approval flow)
    graph.add_edge("hitl_gate", END)

    return graph


# Compiled graph (module-level singleton for performance)
_compiled_graph: CompiledStateGraph | None = None


def get_compiled_graph() -> CompiledStateGraph:
    """Get the compiled review graph (lazy singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_review_graph().compile()
    return _compiled_graph


async def run_review(
    review_id: int,
    pr_number: int,
    repository_full_name: str,
    title: str = "",
    body: str = "",
    author: str = "",
    base_branch: str = "",
    head_sha: str = "",
    diff: str = "",
    changed_files: list | None = None,
    context_files: dict[str, str] | None = None,
    cached_findings: list[ReviewFinding] | None = None,
    feedback_guidance: str = "",
) -> ReviewState:
    """Run the full review pipeline.

    This is the main entry point that the EventProcessor calls.

    Args:
        review_id: Database review ID.
        pr_number: PR number.
        repository_full_name: "owner/repo" format.
        title, body, author, base_branch, head_sha: PR metadata.
        diff: Raw diff string.
        changed_files: Files that still need LLM analysis.
        context_files: Dict of path -> content for context.
        cached_findings: Findings reused from the Phase 14 cache.
        feedback_guidance: Prompt guidance derived from past feedback (Phase 16).

    Returns:
        Final ReviewState after the graph completes.
    """
    # Build initial state
    state = create_initial_state(
        review_id=review_id,
        pr_number=pr_number,
        repository_full_name=repository_full_name,
        title=title,
        body=body,
        author=author,
        base_branch=base_branch,
        head_sha=head_sha,
    )

    # Populate context
    state["diff"] = diff
    state["changed_files"] = changed_files or []
    state["total_additions"] = sum(f.additions for f in (changed_files or []))
    state["total_deletions"] = sum(f.deletions for f in (changed_files or []))
    state["context_files"] = context_files or {}
    state["cached_findings"] = cached_findings or []
    state["feedback_guidance"] = feedback_guidance

    # Fast path: every changed file came from the cache, so there is nothing
    # for the LLM agents to analyse. Synthesize directly.
    if not state["changed_files"] and state["cached_findings"]:
        updates = synthesize({}, state["cached_findings"])
        updates["completed_at"] = datetime.now(UTC)
        state.update(updates)  # type: ignore[typeddict-item]
        logger.info(
            "review_pipeline_completed_from_cache",
            review_id=review_id,
            pr_number=pr_number,
            findings=state["total_comments"],
        )
        return state

    graph = get_compiled_graph()

    logger.info(
        "review_pipeline_started",
        review_id=review_id,
        pr_number=pr_number,
        repo=repository_full_name,
        files_changed=len(changed_files or []),
        cached_findings=len(cached_findings or []),
    )

    # Run the graph
    try:
        final_state = await graph.ainvoke(state)

        logger.info(
            "review_pipeline_completed",
            review_id=review_id,
            pr_number=pr_number,
            status=final_state.get("status"),
            findings=final_state.get("total_comments", 0),
        )

        return cast("ReviewState", final_state)

    except Exception as e:
        logger.error(
            "review_pipeline_failed",
            review_id=review_id,
            pr_number=pr_number,
            error=str(e),
        )
        state["status"] = ReviewStatus.FAILED.value
        state["error"] = str(e)
        return state
