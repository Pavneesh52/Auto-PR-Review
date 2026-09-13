"""Initial schema — all tables for phases 1-16.

Revision ID: 001_initial
Revises: None
Create Date: 2025-01-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reviews table
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("repository_full_name", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "context_gathering",
                "in_progress",
                "awaiting_approval",
                "completed",
                "failed",
                "skipped",
                name="reviewstatus",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), server_default=""),
        sa.Column("body", sa.Text(), server_default=""),
        sa.Column("author", sa.String(255), server_default=""),
        sa.Column("base_branch", sa.String(255), server_default=""),
        sa.Column("head_sha", sa.String(40), server_default=""),
        sa.Column("total_additions", sa.Integer(), server_default="0"),
        sa.Column("total_deletions", sa.Integer(), server_default="0"),
        sa.Column("files_changed", sa.Integer(), server_default="0"),
        sa.Column("summary", sa.Text(), server_default=""),
        sa.Column("total_comments", sa.Integer(), server_default="0"),
        sa.Column("critical_count", sa.Integer(), server_default="0"),
        sa.Column("high_count", sa.Integer(), server_default="0"),
        sa.Column("medium_count", sa.Integer(), server_default="0"),
        sa.Column("low_count", sa.Integer(), server_default="0"),
        sa.Column("total_tokens", sa.Integer(), server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("github_pr_review_id", sa.Integer(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_reviews_repo_pr",
        "reviews",
        ["repository_full_name", "pr_number"],
        unique=True,
    )
    op.create_index("ix_reviews_status", "reviews", ["status"])
    op.create_index("ix_reviews_created_at", "reviews", ["created_at"])

    # Findings table
    op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "review_id",
            sa.Integer(),
            sa.ForeignKey("reviews.id"),
            nullable=False,
        ),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("end_line", sa.Integer(), nullable=True),
        sa.Column(
            "severity",
            sa.Enum("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", name="findingseverity"),
            nullable=False,
        ),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("suggestion", sa.Text(), server_default=""),
        sa.Column("confidence", sa.Float(), server_default="0.8"),
        sa.Column("source_agent", sa.String(50), server_default=""),
        sa.Column("is_accepted", sa.Boolean(), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_findings_review_id", "findings", ["review_id"])
    op.create_index("ix_findings_severity", "findings", ["severity"])

    # Agent results table
    op.create_table(
        "agent_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "review_id",
            sa.Integer(),
            sa.ForeignKey("reviews.id"),
            nullable=False,
        ),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0"),
        sa.Column("findings_count", sa.Integer(), server_default="0"),
        sa.Column("tokens_used", sa.Integer(), server_default="0"),
        sa.Column("duration_seconds", sa.Float(), server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_agent_results_review_id", "agent_results", ["review_id"])
    op.create_index("ix_agent_results_agent_type", "agent_results", ["agent_type"])

    # Event traces table
    op.create_table(
        "event_traces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "review_id",
            sa.Integer(),
            sa.ForeignKey("reviews.id"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("agent_type", sa.String(50), nullable=True),
        sa.Column("detail", sa.Text(), server_default=""),
        sa.Column("tokens", sa.Integer(), server_default="0"),
        sa.Column("duration_ms", sa.Float(), server_default="0"),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_event_traces_review_id", "event_traces", ["review_id"])
    op.create_index("ix_event_traces_event_type", "event_traces", ["event_type"])
    op.create_index("ix_event_traces_timestamp", "event_traces", ["timestamp"])

    # Feedback table
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "finding_id",
            sa.Integer(),
            sa.ForeignKey("findings.id"),
            nullable=False,
        ),
        sa.Column("reviewer", sa.String(255), nullable=False),
        sa.Column("is_positive", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_feedback_finding_id", "feedback", ["finding_id"])

    # Code embeddings table (Phase 10)
    op.create_table(
        "code_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("repository_full_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("language", sa.String(50), server_default=""),
        sa.Column("embedding_json", sa.Text(), server_default="[]"),
        sa.Column("chunk_index", sa.Integer(), server_default="0"),
        sa.Column("chunk_total", sa.Integer(), server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_embeddings_repo_file",
        "code_embeddings",
        ["repository_full_name", "file_path"],
    )
    op.create_index(
        "ix_embeddings_content_hash",
        "code_embeddings",
        ["content_hash"],
    )

    # Review approvals table (Phase 12)
    op.create_table(
        "review_approvals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "review_id",
            sa.Integer(),
            sa.ForeignKey("reviews.id"),
            nullable=False,
        ),
        sa.Column("approver", sa.String(255), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("comment", sa.Text(), server_default=""),
        sa.Column("edited_findings_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_approvals_review_id", "review_approvals", ["review_id"])

    # File cache table (Phase 14)
    op.create_table(
        "file_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("repository_full_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("findings_json", sa.Text(), server_default="[]"),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("hit_count", sa.Integer(), server_default="0"),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_file_cache_repo_file_agent",
        "file_cache",
        ["repository_full_name", "file_path", "agent_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("file_cache")
    op.drop_table("review_approvals")
    op.drop_table("code_embeddings")
    op.drop_table("feedback")
    op.drop_table("event_traces")
    op.drop_table("agent_results")
    op.drop_table("findings")
    op.drop_table("reviews")
    op.execute("DROP TYPE IF EXISTS findingseverity")
    op.execute("DROP TYPE IF EXISTS reviewstatus")
