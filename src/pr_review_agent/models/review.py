"""Review domain models.

These are the core data structures that flow through the entire
review pipeline (Phases 3-20).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware now(), so stored timestamps are unambiguous."""
    return datetime.now(UTC)


class FindingSeverity(StrEnum):
    """Severity levels for review findings."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ReviewStatus(StrEnum):
    """Lifecycle status of a review."""

    PENDING = "pending"
    CONTEXT_GATHERING = "context_gathering"
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ChangedFile(BaseModel):
    """A single file changed in the PR diff."""

    path: str
    status: str = "modified"  # added, removed, modified, renamed
    additions: int = 0
    deletions: int = 0
    patch: str = ""  # the actual diff hunk
    language: str = ""  # detected language


class ReviewContext(BaseModel):
    """Complete context assembled for a review.

    Phase 3 builds this object. It flows to all agents in later phases.
    """

    # PR metadata
    pr_number: int
    repository_full_name: str
    title: str = ""
    body: str = ""
    author: str = ""
    base_branch: str = ""
    head_sha: str = ""

    # Diff content
    diff: str = ""
    changed_files: list[ChangedFile] = Field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0

    # Context files (fetched by the context assembly engine)
    context_files: dict[str, str] = Field(default_factory=dict)
    # path -> file content (e.g., imports, shared types, called functions)

    # Repository metadata
    repo_metadata: RepoMetadata | None = None

    # Timing
    assembled_at: datetime = Field(default_factory=_utcnow)

    @property
    def is_large_pr(self) -> bool:
        return (self.total_additions + self.total_deletions) > 500


class RepoMetadata(BaseModel):
    """Repository-level metadata for context."""

    default_branch: str = "main"
    languages: dict[str, float] = Field(default_factory=dict)
    recent_commits: list[dict[str, Any]] = Field(default_factory=list)
    coding_patterns: dict[str, Any] = Field(default_factory=dict)


class ReviewFinding(BaseModel):
    """A single finding from an agent review."""

    file: str
    line: int | None = None
    end_line: int | None = None
    severity: FindingSeverity
    category: str  # e.g., "security", "architecture", "quality"
    title: str
    description: str
    suggestion: str = ""  # concrete fix suggestion
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    source_agent: str = ""  # which agent produced this


class ReviewResult(BaseModel):
    """Aggregated result from all agents after synthesis."""

    pr_number: int
    repository_full_name: str
    status: ReviewStatus = ReviewStatus.PENDING
    findings: list[ReviewFinding] = Field(default_factory=list)
    summary: str = ""
    total_comments: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    # Per-agent results (before synthesis)
    agent_results: dict[str, AgentResult] = Field(default_factory=dict)

    # Timing
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_duration_seconds: float = 0.0

    # Cost tracking
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class AgentResult(BaseModel):
    """Result from a single specialized agent."""

    agent_type: str
    findings: list[ReviewFinding] = Field(default_factory=list)
    confidence: float = 0.0
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_seconds: float = 0.0
    error: str | None = None
