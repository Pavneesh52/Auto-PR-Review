"""SQLAlchemy ORM models.

Phases 4, 10, 12, 16 - Unified data layer in Postgres:
1. Relational truth: reviews, findings, agent results
2. Time-series traces: agent invocations, tokens, latencies
3. Feedback: developer reactions on findings
4. Vector embeddings: semantic code search (Phase 10)
5. HITL approvals: human review gates (Phase 12)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from pr_review_agent.models.review import FindingSeverity, ReviewStatus


class Base(DeclarativeBase):
    pass


# ── Phase 4: Core Models ─────────────────────────────────────────────


class ReviewRow(Base):
    """A PR review record.

    Tracks the full lifecycle: pending → in_progress → completed → (posted).
    """

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    repository_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False
    )

    # PR metadata (cached from webhook)
    title: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(255), default="")
    base_branch: Mapped[str] = mapped_column(String(255), default="")
    head_sha: Mapped[str] = mapped_column(String(40), default="")

    # Diff summary
    total_additions: Mapped[int] = mapped_column(Integer, default=0)
    total_deletions: Mapped[int] = mapped_column(Integer, default=0)
    files_changed: Mapped[int] = mapped_column(Integer, default=0)

    # Synthesized result
    summary: Mapped[str] = mapped_column(Text, default="")
    total_comments: Mapped[int] = mapped_column(Integer, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, default=0)
    low_count: Mapped[int] = mapped_column(Integer, default=0)

    # Cost tracking
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Phase 13: GitHub posting
    github_pr_review_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # GitHub's PR review ID after posting
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    findings: Mapped[list[FindingRow]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )
    agent_results: Mapped[list[AgentResultRow]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )
    traces: Mapped[list[EventTraceRow]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )
    approvals: Mapped[list[ReviewApprovalRow]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Not unique: a PR gets a new review on every push (synchronize),
        # and keeping the history is what makes metrics and feedback useful.
        Index("ix_reviews_repo_pr", "repository_full_name", "pr_number"),
        Index("ix_reviews_status", "status"),
        Index("ix_reviews_created_at", "created_at"),
    )


class FindingRow(Base):
    """A single finding from an agent review."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"), nullable=False)

    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(Enum(FindingSeverity), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    suggestion: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    source_agent: Mapped[str] = mapped_column(String(50), default="")

    # Feedback
    is_accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    review: Mapped[ReviewRow] = relationship(back_populates="findings")

    __table_args__ = (
        Index("ix_findings_review_id", "review_id"),
        Index("ix_findings_severity", "severity"),
    )


class AgentResultRow(Base):
    """Per-agent output before synthesis."""

    __tablename__ = "agent_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"), nullable=False)

    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    review: Mapped[ReviewRow] = relationship(back_populates="agent_results")

    __table_args__ = (
        Index("ix_agent_results_review_id", "review_id"),
        Index("ix_agent_results_agent_type", "agent_type"),
    )


class EventTraceRow(Base):
    """Time-series event traces for observability."""

    __tablename__ = "event_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int | None] = mapped_column(ForeignKey("reviews.id"), nullable=True)

    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")

    # Metrics
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    review: Mapped[ReviewRow | None] = relationship(back_populates="traces")

    __table_args__ = (
        Index("ix_event_traces_review_id", "review_id"),
        Index("ix_event_traces_event_type", "event_type"),
        Index("ix_event_traces_timestamp", "timestamp"),
    )


class FeedbackRow(Base):
    """Developer feedback on individual findings.

    Phase 16 — thumbs up/down on PR comments.
    """

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(255), nullable=False)
    is_positive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_feedback_finding_id", "finding_id"),)


# ── Phase 10: Semantic Search ─────────────────────────────────────────


class CodeEmbeddingRow(Base):
    """Vector embedding for a code file/chunk.

    Phase 10 — enables semantic code search across the repo.
    Uses pgvector for cosine similarity search.
    """

    __tablename__ = "code_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(50), default="")

    # The embedding vector (stored as pgvector type in Postgres)
    # We store as JSON list and use pgvector for similarity search
    embedding_json: Mapped[str] = mapped_column(Text, default="[]")

    # Chunk info for large files
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    chunk_total: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "ix_embeddings_repo_file",
            "repository_full_name",
            "file_path",
        ),
        Index("ix_embeddings_content_hash", "content_hash"),
    )


# ── Phase 12: HITL Approvals ─────────────────────────────────────────


class ReviewApprovalRow(Base):
    """Human approval/rejection record for a review.

    Phase 12 — HITL gate: developers can approve or reject
    the AI-generated review before it's posted to GitHub.
    """

    __tablename__ = "review_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"), nullable=False)

    approver: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "approved", "rejected", "edited"
    comment: Mapped[str] = mapped_column(Text, default="")
    edited_findings_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON of findings after editing

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    review: Mapped[ReviewRow] = relationship(back_populates="approvals")

    __table_args__ = (Index("ix_approvals_review_id", "review_id"),)


# ── Phase 14: File Cache ──────────────────────────────────────────────


class FileCacheRow(Base):
    """Cache entry for file review results.

    Phase 14 — skip re-analyzing unchanged files between PR updates.
    """

    __tablename__ = "file_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    findings_json: Mapped[str] = mapped_column(Text, default="[]")
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)

    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "ix_file_cache_repo_file_agent",
            "repository_full_name",
            "file_path",
            "agent_type",
            unique=True,
        ),
    )
