"""Allow multiple reviews per PR (one per push).

The initial schema made (repository_full_name, pr_number) unique, which
meant the second `synchronize` webhook for a PR raised an IntegrityError
and the review was silently dropped. Reviews now form a history: one row
per analyzed head SHA.

Revision ID: 002_review_history
Revises: 001_initial
Create Date: 2025-01-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "002_review_history"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_reviews_repo_pr", table_name="reviews")
    op.create_index(
        "ix_reviews_repo_pr",
        "reviews",
        ["repository_full_name", "pr_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_reviews_repo_pr", table_name="reviews")
    op.create_index(
        "ix_reviews_repo_pr",
        "reviews",
        ["repository_full_name", "pr_number"],
        unique=True,
    )
