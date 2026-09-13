"""Repository classes for data access.

Phases 4, 10, 12, 13, 14, 16 - Encapsulates all database queries.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from sqlalchemy import Integer, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pr_review_agent.db.models import (
    AgentResultRow,
    CodeEmbeddingRow,
    EventTraceRow,
    FeedbackRow,
    FileCacheRow,
    FindingRow,
    ReviewApprovalRow,
    ReviewRow,
)
from pr_review_agent.models.review import (
    ReviewFinding,
    ReviewStatus,
)

logger = structlog.get_logger(__name__)


class ReviewRepository:
    """Data access for reviews and their related entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_review(
        self,
        pr_number: int,
        repository_full_name: str,
        title: str = "",
        body: str = "",
        author: str = "",
        base_branch: str = "",
        head_sha: str = "",
    ) -> ReviewRow:
        """Create a new review record."""
        review = ReviewRow(
            pr_number=pr_number,
            repository_full_name=repository_full_name,
            status=ReviewStatus.PENDING,
            title=title,
            body=body,
            author=author,
            base_branch=base_branch,
            head_sha=head_sha,
        )
        self.session.add(review)
        await self.session.flush()
        logger.info(
            "review_created",
            review_id=review.id,
            pr_number=pr_number,
            repo=repository_full_name,
        )
        return review

    async def get_review(self, review_id: int) -> ReviewRow | None:
        """Get a review by ID with all relationships loaded."""
        stmt = (
            select(ReviewRow)
            .options(
                selectinload(ReviewRow.findings),
                selectinload(ReviewRow.agent_results),
            )
            .where(ReviewRow.id == review_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_review_by_pr(self, repository_full_name: str, pr_number: int) -> ReviewRow | None:
        """Get a review by repo + PR number."""
        stmt = (
            select(ReviewRow)
            .where(
                ReviewRow.repository_full_name == repository_full_name,
                ReviewRow.pr_number == pr_number,
            )
            .order_by(ReviewRow.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_reviews(
        self,
        status: str | None = None,
        repository_full_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ReviewRow]:
        """List reviews with optional filtering and pagination."""
        stmt = (
            select(ReviewRow)
            .options(
                selectinload(ReviewRow.findings),
                selectinload(ReviewRow.agent_results),
            )
            .order_by(ReviewRow.created_at.desc())
        )
        if status:
            stmt = stmt.where(ReviewRow.status == status)
        if repository_full_name:
            stmt = stmt.where(ReviewRow.repository_full_name == repository_full_name)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_status(self, review_id: int, status: ReviewStatus) -> None:
        """Update the status of a review."""
        now = datetime.now(UTC)
        values: dict = {"status": status, "updated_at": now}

        if status == ReviewStatus.IN_PROGRESS:
            values["started_at"] = now
        elif status in (ReviewStatus.COMPLETED, ReviewStatus.FAILED):
            values["completed_at"] = now

        stmt = update(ReviewRow).where(ReviewRow.id == review_id).values(**values)
        await self.session.execute(stmt)

    async def save_findings(
        self, review_id: int, findings: list[ReviewFinding]
    ) -> list[FindingRow]:
        """Save agent findings to the database."""
        rows = []
        for f in findings:
            row = FindingRow(
                review_id=review_id,
                file_path=f.file,
                line=f.line,
                end_line=f.end_line,
                severity=f.severity,
                category=f.category,
                title=f.title,
                description=f.description,
                suggestion=f.suggestion,
                confidence=f.confidence,
                source_agent=f.source_agent,
            )
            self.session.add(row)
            rows.append(row)

        await self.session.flush()
        logger.info("findings_saved", review_id=review_id, count=len(rows))
        return rows

    async def save_agent_result(
        self,
        review_id: int,
        agent_type: str,
        confidence: float,
        findings_count: int,
        tokens_used: int,
        duration_seconds: float,
        error: str | None = None,
    ) -> AgentResultRow:
        """Save per-agent result."""
        row = AgentResultRow(
            review_id=review_id,
            agent_type=agent_type,
            confidence=confidence,
            findings_count=findings_count,
            tokens_used=tokens_used,
            duration_seconds=duration_seconds,
            error=error,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update_review_totals(
        self,
        review_id: int,
        summary: str = "",
        total_comments: int = 0,
        critical_count: int = 0,
        high_count: int = 0,
        medium_count: int = 0,
        low_count: int = 0,
        total_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        """Update synthesized result totals."""
        stmt = (
            update(ReviewRow)
            .where(ReviewRow.id == review_id)
            .values(
                summary=summary,
                total_comments=total_comments,
                critical_count=critical_count,
                high_count=high_count,
                medium_count=medium_count,
                low_count=low_count,
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost_usd,
                updated_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)

    async def update_review_diff_stats(
        self,
        review_id: int,
        files_changed: int = 0,
        total_additions: int = 0,
        total_deletions: int = 0,
    ) -> None:
        """Persist the diff size for a review."""
        stmt = (
            update(ReviewRow)
            .where(ReviewRow.id == review_id)
            .values(
                files_changed=files_changed,
                total_additions=total_additions,
                total_deletions=total_deletions,
                updated_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)

    async def get_findings_for_review(self, review_id: int) -> Sequence[FindingRow]:
        """Get all findings for a review."""
        stmt = (
            select(FindingRow)
            .where(FindingRow.review_id == review_id)
            .order_by(FindingRow.severity)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # ── Phase 13: GitHub Posting ───────────────────────────────────────

    async def mark_posted(self, review_id: int, github_pr_review_id: int) -> None:
        """Mark a review as posted to GitHub."""
        now = datetime.now(UTC)
        stmt = (
            update(ReviewRow)
            .where(ReviewRow.id == review_id)
            .values(
                github_pr_review_id=github_pr_review_id,
                posted_at=now,
                updated_at=now,
            )
        )
        await self.session.execute(stmt)

    # ── Phase 12: HITL Approvals ──────────────────────────────────────

    async def create_approval(
        self,
        review_id: int,
        approver: str,
        decision: str,
        comment: str = "",
        edited_findings_json: str | None = None,
    ) -> ReviewApprovalRow:
        """Record a HITL approval/rejection."""
        row = ReviewApprovalRow(
            review_id=review_id,
            approver=approver,
            decision=decision,
            comment=comment,
            edited_findings_json=edited_findings_json,
        )
        self.session.add(row)
        await self.session.flush()
        logger.info(
            "approval_recorded",
            review_id=review_id,
            decision=decision,
            approver=approver,
        )
        return row

    async def get_latest_approval(self, review_id: int) -> ReviewApprovalRow | None:
        """Get the most recent approval for a review."""
        stmt = (
            select(ReviewApprovalRow)
            .where(ReviewApprovalRow.review_id == review_id)
            .order_by(ReviewApprovalRow.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Phase 14: File Cache ──────────────────────────────────────────

    async def get_cached_findings(
        self,
        repository_full_name: str,
        file_path: str,
        content_hash: str,
        agent_type: str,
    ) -> list[ReviewFinding] | None:
        """Get cached findings for an unchanged file."""
        stmt = (
            select(FileCacheRow)
            .where(
                FileCacheRow.repository_full_name == repository_full_name,
                FileCacheRow.file_path == file_path,
                FileCacheRow.content_hash == content_hash,
                FileCacheRow.agent_type == agent_type,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            return None

        # Update hit count
        row.hit_count += 1
        row.last_hit_at = datetime.now(UTC)
        await self.session.flush()

        # Parse cached findings
        try:
            raw = json.loads(row.findings_json)
            return [ReviewFinding(**f) for f in raw]
        except Exception:
            return None

    async def cache_findings(
        self,
        repository_full_name: str,
        file_path: str,
        content_hash: str,
        agent_type: str,
        findings: list[ReviewFinding],
    ) -> None:
        """Cache findings for a file to avoid re-analysis."""
        findings_json = json.dumps([f.model_dump() for f in findings], default=str)

        # Upsert: delete existing and insert new
        stmt = select(FileCacheRow).where(
            FileCacheRow.repository_full_name == repository_full_name,
            FileCacheRow.file_path == file_path,
            FileCacheRow.agent_type == agent_type,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.content_hash = content_hash
            existing.findings_json = findings_json
            existing.hit_count = 0
            existing.last_hit_at = None
        else:
            row = FileCacheRow(
                repository_full_name=repository_full_name,
                file_path=file_path,
                content_hash=content_hash,
                agent_type=agent_type,
                findings_json=findings_json,
            )
            self.session.add(row)

        await self.session.flush()

    # ── Phase 16: Feedback ────────────────────────────────────────────

    async def save_feedback(
        self,
        finding_id: int,
        reviewer: str,
        is_positive: bool,
        comment: str = "",
    ) -> FeedbackRow:
        """Save developer feedback on a finding."""
        row = FeedbackRow(
            finding_id=finding_id,
            reviewer=reviewer,
            is_positive=is_positive,
            comment=comment,
        )
        self.session.add(row)
        await self.session.flush()
        logger.info(
            "feedback_saved",
            finding_id=finding_id,
            reviewer=reviewer,
            positive=is_positive,
        )
        return row

    async def update_finding_accepted(self, finding_id: int, is_accepted: bool) -> None:
        """Update whether a finding was accepted by the developer."""
        stmt = update(FindingRow).where(FindingRow.id == finding_id).values(is_accepted=is_accepted)
        await self.session.execute(stmt)

    async def get_feedback_guidance(self, repository_full_name: str, limit: int = 5) -> str:
        """Build prompt guidance from findings developers marked incorrect.

        Phase 16 — closes the loop: past thumbs-down feedback is fed back
        into agent prompts so the same false positives aren't repeated.
        """
        stmt = (
            select(
                FindingRow.title,
                FindingRow.description,
                FindingRow.category,
                FindingRow.source_agent,
            )
            .join(FeedbackRow, FeedbackRow.finding_id == FindingRow.id)
            .join(ReviewRow, ReviewRow.id == FindingRow.review_id)
            .where(
                ReviewRow.repository_full_name == repository_full_name,
                FeedbackRow.is_positive.is_(False),
            )
            .order_by(FeedbackRow.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            return ""

        lines = [
            "This repository previously rejected the following findings as "
            "incorrect. Do NOT report similar false positives again:"
        ]
        for title, description, _category, source_agent in rows:
            snippet = (description or "").strip().replace("\n", " ")[:200]
            lines.append(f"- [{source_agent}] {title}: {snippet}")
        return "\n".join(lines)

    async def get_feedback_summary(self, repository_full_name: str) -> dict:
        """Get aggregated feedback stats for a repo."""
        # Join findings → feedback to get repo-level stats
        stmt = (
            select(
                func.count(FeedbackRow.id).label("total_feedback"),
                func.sum(func.cast(FeedbackRow.is_positive, Integer)).label("positive_count"),
            )
            .join(FindingRow, FindingRow.id == FeedbackRow.finding_id)
            .join(ReviewRow, ReviewRow.id == FindingRow.review_id)
            .where(ReviewRow.repository_full_name == repository_full_name)
        )
        result = await self.session.execute(stmt)
        row = result.one_or_none()

        total = row.total_feedback or 0 if row else 0
        positive = row.positive_count or 0 if row else 0
        negative = total - positive

        return {
            "total_feedback": total,
            "positive": positive,
            "negative": negative,
            "acceptance_rate": positive / total if total > 0 else 0.0,
        }

    # ── Phase 10: Embeddings ──────────────────────────────────────────

    async def save_embedding(
        self,
        repository_full_name: str,
        file_path: str,
        content_hash: str,
        embedding_json: str,
        language: str = "",
        chunk_index: int = 0,
        chunk_total: int = 1,
    ) -> CodeEmbeddingRow:
        """Save a code embedding for semantic search."""
        row = CodeEmbeddingRow(
            repository_full_name=repository_full_name,
            file_path=file_path,
            content_hash=content_hash,
            embedding_json=embedding_json,
            language=language,
            chunk_index=chunk_index,
            chunk_total=chunk_total,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def replace_embeddings(
        self,
        repository_full_name: str,
        file_path: str,
        content_hash: str,
        chunks: list[list[float]],
        language: str = "",
    ) -> int:
        """Replace all stored embeddings for a file with fresh chunks.

        Delete-then-insert keeps re-indexing idempotent.
        """
        await self.session.execute(
            delete(CodeEmbeddingRow).where(
                CodeEmbeddingRow.repository_full_name == repository_full_name,
                CodeEmbeddingRow.file_path == file_path,
            )
        )

        total = len(chunks)
        for index, vector in enumerate(chunks):
            self.session.add(
                CodeEmbeddingRow(
                    repository_full_name=repository_full_name,
                    file_path=file_path,
                    content_hash=content_hash,
                    language=language,
                    embedding_json=json.dumps(vector),
                    chunk_index=index,
                    chunk_total=total,
                )
            )

        await self.session.flush()
        return total

    async def count_embeddings(self, repository_full_name: str) -> int:
        """How many embedding chunks are indexed for a repository."""
        stmt = select(func.count(CodeEmbeddingRow.id)).where(
            CodeEmbeddingRow.repository_full_name == repository_full_name
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def semantic_search(
        self,
        repository_full_name: str,
        query_embedding: list[float],
        limit: int = 5,
        scan_limit: int = 500,
    ) -> list[str]:
        """Find the most similar indexed files for a query embedding.

        Similarity is computed in Python over stored JSON vectors. This is
        fine at small scale; a pgvector index is the upgrade path for large
        repositories (see ARCHITECTURE.md).
        """
        if not query_embedding:
            return []

        stmt = (
            select(CodeEmbeddingRow)
            .where(CodeEmbeddingRow.repository_full_name == repository_full_name)
            .order_by(CodeEmbeddingRow.updated_at.desc())
            .limit(scan_limit)
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        scored: list[tuple[float, str]] = []
        for row in rows:
            try:
                vector = json.loads(row.embedding_json)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(vector, list) or not vector:
                continue
            scored.append((_cosine_similarity(query_embedding, vector), row.file_path))

        scored.sort(key=lambda item: item[0], reverse=True)

        # Deduplicate paths (multi-chunk files) while preserving rank order
        ordered: list[str] = []
        for _score, path in scored:
            if path not in ordered:
                ordered.append(path)
            if len(ordered) >= limit:
                break
        return ordered

    # ── Observability ─────────────────────────────────────────────────

    async def record_trace(
        self,
        event_type: str,
        review_id: int | None = None,
        agent_type: str | None = None,
        detail: str = "",
        tokens: int = 0,
        duration_ms: float = 0.0,
    ) -> EventTraceRow:
        """Record a time-series event trace."""
        row = EventTraceRow(
            review_id=review_id,
            event_type=event_type,
            agent_type=agent_type,
            detail=detail,
            tokens=tokens,
            duration_ms=duration_ms,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_token_usage_summary(
        self, repository_full_name: str, since: datetime | None = None
    ) -> dict:
        """Get aggregated token usage for a repository."""
        stmt = select(
            func.sum(ReviewRow.total_tokens).label("total_tokens"),
            func.sum(ReviewRow.estimated_cost_usd).label("total_cost"),
            func.count(ReviewRow.id).label("review_count"),
        ).where(ReviewRow.repository_full_name == repository_full_name)
        if since:
            stmt = stmt.where(ReviewRow.created_at >= since)

        result = await self.session.execute(stmt)
        row = result.one_or_none()
        return {
            "total_tokens": row.total_tokens or 0 if row else 0,
            "total_cost": float(row.total_cost or 0) if row else 0.0,
            "review_count": row.review_count or 0 if row else 0,
        }

    async def get_metrics_summary(self) -> dict:
        """Get global metrics for the monitoring dashboard."""
        now = datetime.now(UTC)

        # Total reviews
        total_stmt = select(func.count(ReviewRow.id))
        total_result = await self.session.execute(total_stmt)
        total_reviews = total_result.scalar() or 0

        # Reviews in last 24 hours
        from datetime import timedelta

        since_24h = now - timedelta(hours=24)
        recent_stmt = select(func.count(ReviewRow.id)).where(ReviewRow.created_at >= since_24h)
        recent_result = await self.session.execute(recent_stmt)
        recent_reviews = recent_result.scalar() or 0

        # Total tokens and cost
        cost_stmt = select(
            func.sum(ReviewRow.total_tokens),
            func.sum(ReviewRow.estimated_cost_usd),
        )
        cost_result = await self.session.execute(cost_stmt)
        cost_row = cost_result.one_or_none()

        # Findings by severity
        severity_stmt = select(
            FindingRow.severity,
            func.count(FindingRow.id),
        ).group_by(FindingRow.severity)
        severity_result = await self.session.execute(severity_stmt)
        severity_counts = {row[0]: row[1] for row in severity_result.all()}

        # Average confidence
        avg_conf_stmt = select(
            func.avg(FindingRow.confidence),
        )
        avg_conf_result = await self.session.execute(avg_conf_stmt)
        avg_confidence = avg_conf_result.scalar() or 0.0

        return {
            "total_reviews": total_reviews,
            "reviews_last_24h": recent_reviews,
            "total_tokens": cost_row[0] or 0 if cost_row else 0,
            "total_cost_usd": float(cost_row[1] or 0) if cost_row else 0.0,
            "findings_by_severity": severity_counts,
            "avg_confidence": float(avg_confidence),
        }


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)
