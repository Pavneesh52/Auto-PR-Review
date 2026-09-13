"""LangGraph ReviewState definition.

Phase 5 - The state object that flows through the entire review graph.
Every node reads from and writes to this state.

Uses reducers for fields that multiple parallel nodes write to.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, TypedDict

from pr_review_agent.models.review import (
    AgentResult,
    ChangedFile,
    RepoMetadata,
    ReviewFinding,
    ReviewStatus,
)


def merge_agent_results(
    left: dict[str, AgentResult], right: dict[str, AgentResult]
) -> dict[str, AgentResult]:
    """Reducer: merge agent results from parallel nodes."""
    merged = left.copy()
    merged.update(right)
    return merged


class ReviewState(TypedDict, total=False):
    """State object for the review graph.

    This is the single source of truth that every node in the
    LangGraph pipeline reads from and writes to.

    Fields marked with (input) are set before the graph runs.
    Fields marked with (output) are read after the graph completes.

    For fields written by multiple parallel nodes (agent_results),
    we use Annotated with a reducer function.
    """

    # --- Input (set by processor before graph.run()) ---
    review_id: int
    pr_number: int
    repository_full_name: str
    title: str
    body: str
    author: str
    base_branch: str
    head_sha: str

    # --- Context (assembled by context node) ---
    diff: str
    changed_files: list[ChangedFile]
    total_additions: int
    total_deletions: int
    context_files: dict[str, str]
    repo_metadata: RepoMetadata | None

    # --- Cache (Phase 14) ---
    # Findings reused from the file cache; merged during synthesis instead
    # of being re-derived by the agents.
    cached_findings: list[ReviewFinding]

    # --- Feedback loop (Phase 16) ---
    # Human-readable guidance derived from past developer feedback, injected
    # into every agent prompt.
    feedback_guidance: str

    # --- Agent results (populated by agent nodes, parallel writes) ---
    # Uses a reducer so parallel agent nodes can each write their results
    agent_results: Annotated[dict[str, AgentResult], merge_agent_results]

    # --- Synthesis (populated by synthesis node) ---
    all_findings: list[ReviewFinding]
    deduplicated_findings: list[ReviewFinding]
    sorted_findings: list[ReviewFinding]

    # --- Output (read by processor after graph completes) ---
    status: str  # ReviewStatus value as string
    summary: str
    total_comments: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int

    # --- Timing ---
    started_at: datetime | None
    completed_at: datetime | None

    # --- Cost ---
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    estimated_cost_usd: float

    # --- Control flow ---
    should_escalate_to_hitl: bool
    error: str | None


def create_initial_state(
    review_id: int,
    pr_number: int,
    repository_full_name: str,
    title: str = "",
    body: str = "",
    author: str = "",
    base_branch: str = "",
    head_sha: str = "",
) -> ReviewState:
    """Create the initial state for a review run."""
    return ReviewState(
        review_id=review_id,
        pr_number=pr_number,
        repository_full_name=repository_full_name,
        title=title,
        body=body,
        author=author,
        base_branch=base_branch,
        head_sha=head_sha,
        # Empty defaults
        diff="",
        changed_files=[],
        total_additions=0,
        total_deletions=0,
        context_files={},
        repo_metadata=None,
        cached_findings=[],
        feedback_guidance="",
        agent_results={},
        all_findings=[],
        deduplicated_findings=[],
        sorted_findings=[],
        status=ReviewStatus.PENDING.value,
        summary="",
        total_comments=0,
        critical_count=0,
        high_count=0,
        medium_count=0,
        low_count=0,
        started_at=None,
        completed_at=None,
        total_tokens=0,
        total_prompt_tokens=0,
        total_completion_tokens=0,
        estimated_cost_usd=0.0,
        should_escalate_to_hitl=False,
        error=None,
    )
