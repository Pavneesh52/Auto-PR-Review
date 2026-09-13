"""FastAPI webhook receiver and API endpoints.

Phases 2, 12, 16, 18 - Webhook receiver + HITL + Feedback + Metrics.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from pr_review_agent import __version__
from pr_review_agent.config.settings import settings
from pr_review_agent.models.events import WebhookEvent
from pr_review_agent.queue.event_queue import EventQueue
from pr_review_agent.webhooks.hmac import HMACVerificationError, verify_github_signature

logger = structlog.get_logger(__name__)


def _findings_for_approval(findings: list[Any], edited_findings_json: str | None) -> list[Any]:
    """Resolve the findings to post after an approval decision.

    Uses the operator's edited JSON when supplied, otherwise the stored
    findings. Raises HTTPException on malformed edited payloads.
    """
    from pr_review_agent.models.review import ReviewFinding

    if edited_findings_json:
        try:
            raw = json.loads(edited_findings_json)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400, detail=f"edited_findings_json is not valid JSON: {e}"
            ) from e

        if not isinstance(raw, list):
            raise HTTPException(status_code=400, detail="edited_findings_json must be a JSON array")

        try:
            return [ReviewFinding(**item) for item in raw]
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"edited findings failed validation: {e}"
            ) from e

    return [
        ReviewFinding(
            file=row.file_path,
            line=row.line,
            end_line=row.end_line,
            severity=row.severity,
            category=row.category,
            title=row.title,
            description=row.description or "",
            suggestion=row.suggestion or "",
            confidence=row.confidence or 0.0,
            source_agent=row.source_agent or "",
        )
        for row in findings
    ]


# ── Request/Response Models ───────────────────────────────────────────


class ApprovalRequest(BaseModel):
    """Phase 12: HITL approval request body."""

    approver: str
    decision: str  # "approved", "rejected", "edited"
    comment: str = ""
    edited_findings_json: str | None = None


class FeedbackRequest(BaseModel):
    """Phase 16: Feedback request body."""

    reviewer: str
    is_positive: bool
    comment: str = ""


def create_app(event_queue: EventQueue, lifespan: Any = None) -> FastAPI:
    """Create the FastAPI app with all routes.

    Args:
        event_queue: Shared event queue instance.
        lifespan: Optional lifespan context manager owning startup/shutdown.
    """
    app = FastAPI(title="PR Review Agent", version=__version__, lifespan=lifespan)

    # ── Phase 2: Health Check ─────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    # ── Phase 2: Webhook Receiver ─────────────────────────────────────

    @app.post("/webhook")
    async def webhook(
        request: Request,
        x_hub_signature_256: str = Header(default=""),
        x_github_event: str = Header(default=""),
        x_github_delivery: str = Header(default=""),
    ) -> dict[str, object]:
        """Handle incoming GitHub webhook.

        Flow:
        1. Read raw body
        2. Verify HMAC signature
        3. Parse payload into our event model
        4. Enqueue with idempotency check
        5. Return 200 immediately (processing is async)
        """
        # Step 1: Read raw body
        body = await request.body()

        # Step 2: Verify HMAC signature
        try:
            verify_github_signature(body, x_hub_signature_256)
        except HMACVerificationError as e:
            logger.warning("hmac_verification_failed", error=str(e))
            raise HTTPException(status_code=401, detail="Invalid signature") from e

        # Step 3: Parse payload
        try:
            payload = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

        # Only handle pull_request events
        if x_github_event != "pull_request":
            return {"status": "ignored", "event": x_github_event}

        # Step 4: Parse into our event model
        try:
            event = WebhookEvent.from_github_payload(payload, delivery_id=x_github_delivery)
        except ValueError as e:
            # Unhandled action — not an error, just skip
            logger.info("skipped_action", action=payload.get("action"), reason=str(e))
            return {"status": "skipped", "reason": str(e)}
        except Exception as e:
            logger.error("payload_parse_error", error=str(e))
            raise HTTPException(status_code=400, detail="Failed to parse event") from e

        # Step 5: Enqueue with idempotency
        event_type = f"pr_{event.action.value}"
        enqueued = await event_queue.enqueue(
            event_type=event_type,
            payload=payload,
            delivery_id=x_github_delivery,
        )

        if not enqueued:
            logger.info(
                "duplicate_event_ignored",
                delivery_id=x_github_delivery,
                pr_number=event.pr_number,
            )
            return {"status": "duplicate", "pr_number": event.pr_number}

        logger.info(
            "event_enqueued",
            event_type=event_type,
            pr_number=event.pr_number,
            repo=event.repository_full_name,
            delivery_id=x_github_delivery,
        )

        return {"status": "queued", "pr_number": event.pr_number}

    # ── Phase 12: HITL Approval ───────────────────────────────────────

    @app.post("/reviews/{review_id}/approve")
    async def approve_review(review_id: int, body: ApprovalRequest) -> dict:
        """Approve, reject, or edit a review before posting to GitHub.

        Phase 12 - Human-in-the-loop gate. Approving (or editing) posts the
        findings to GitHub and marks the review completed. Rejecting marks it
        skipped. If posting fails, the review stays `awaiting_approval` so the
        decision can be retried.
        """
        from pr_review_agent.db.connection import get_session_factory
        from pr_review_agent.db.repositories import ReviewRepository
        from pr_review_agent.github.comment_poster import GitHubCommentPoster
        from pr_review_agent.models.review import ReviewStatus

        if body.decision not in ("approved", "rejected", "edited"):
            raise HTTPException(
                status_code=400,
                detail="decision must be one of: approved, rejected, edited",
            )

        session_factory = get_session_factory()
        async with session_factory() as session:
            repo = ReviewRepository(session)

            review = await repo.get_review(review_id)
            if not review:
                raise HTTPException(status_code=404, detail="Review not found")

            if review.status != ReviewStatus.AWAITING_APPROVAL.value:
                raise HTTPException(
                    status_code=400,
                    detail=f"Review status is '{review.status}', expected 'awaiting_approval'",
                )

            findings = _findings_for_approval(review.findings, body.edited_findings_json)

            github_review_id: int | None = None
            if body.decision in ("approved", "edited"):
                poster = GitHubCommentPoster()
                try:
                    github_review_id = await poster.post_review(
                        repository_full_name=review.repository_full_name,
                        pr_number=review.pr_number,
                        head_sha=review.head_sha,
                        findings=findings,
                        summary=review.summary or "",
                    )
                finally:
                    await poster.close()

                if not github_review_id:
                    hint = (
                        "GITHUB_TOKEN is not configured"
                        if not settings.github_token
                        else "GitHub API rejected the review"
                    )
                    # Leave the review awaiting approval so it can be retried.
                    raise HTTPException(
                        status_code=502,
                        detail=f"Failed to post review to GitHub ({hint}). "
                        "Review remains awaiting_approval.",
                    )

            # Record the approval
            await repo.create_approval(
                review_id=review_id,
                approver=body.approver,
                decision=body.decision,
                comment=body.comment,
                edited_findings_json=body.edited_findings_json,
            )

            if body.decision == "rejected":
                await repo.update_status(review_id, ReviewStatus.SKIPPED)
            else:
                await repo.update_status(review_id, ReviewStatus.COMPLETED)
                if github_review_id:
                    await repo.mark_posted(review_id, github_review_id)

            await session.commit()

        logger.info(
            "review_approval_processed",
            review_id=review_id,
            decision=body.decision,
            approver=body.approver,
            posted=github_review_id is not None,
        )

        return {
            "status": "ok",
            "review_id": review_id,
            "decision": body.decision,
            "github_pr_review_id": github_review_id,
        }

    # ── Phase 16: Feedback ────────────────────────────────────────────

    @app.post("/findings/{finding_id}/feedback")
    async def submit_feedback(finding_id: int, body: FeedbackRequest) -> dict:
        """Submit developer feedback on a specific finding.

        Phase 16 - Thumbs up/down on AI-generated findings.
        """
        from pr_review_agent.db.connection import get_session_factory
        from pr_review_agent.db.repositories import ReviewRepository

        session_factory = get_session_factory()
        async with session_factory() as session:
            repo = ReviewRepository(session)

            await repo.save_feedback(
                finding_id=finding_id,
                reviewer=body.reviewer,
                is_positive=body.is_positive,
                comment=body.comment,
            )

            # Update the finding's accepted status
            await repo.update_finding_accepted(
                finding_id=finding_id,
                is_accepted=body.is_positive,
            )

            await session.commit()

        return {
            "status": "ok",
            "finding_id": finding_id,
            "is_positive": body.is_positive,
        }

    @app.get("/repos/{repo_name}/feedback")
    async def get_feedback_summary(repo_name: str) -> dict:
        """Get aggregated feedback stats for a repository."""
        from pr_review_agent.db.connection import get_session_factory
        from pr_review_agent.db.repositories import ReviewRepository

        session_factory = get_session_factory()
        async with session_factory() as session:
            repo = ReviewRepository(session)
            summary = await repo.get_feedback_summary(repo_name)

        return summary

    # ── Phase 18: Metrics & Monitoring ─────────────────────────────────

    @app.get("/metrics")
    async def get_metrics() -> dict:
        """Global metrics dashboard endpoint.

        Phase 18 - Observability.
        """
        from pr_review_agent.db.connection import get_session_factory
        from pr_review_agent.db.repositories import ReviewRepository

        metrics: dict[str, Any] = {}

        # Database metrics
        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                repo = ReviewRepository(session)
                db_metrics = await repo.get_metrics_summary()
                metrics["database"] = db_metrics
        except Exception as e:
            metrics["database"] = {"error": str(e)}

        # Queue metrics
        try:
            metrics["queue"] = {
                "pending": await event_queue.queue_length(),
            }
        except Exception as e:
            metrics["queue"] = {"error": str(e)}

        # Rate limiter metrics
        try:
            import redis.asyncio as redis_lib

            from pr_review_agent.rate_limiter import RateLimiter

            rl_client = redis_lib.from_url(settings.redis_url, decode_responses=True)
            limiter = RateLimiter(rl_client)
            metrics["rate_limits"] = await limiter.get_usage_stats()
            await rl_client.aclose()
        except Exception as e:
            metrics["rate_limits"] = {"error": str(e)}

        # System info
        import platform
        import sys

        metrics["system"] = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "version": __version__,
        }

        return metrics

    @app.get("/repos/{repo_name}/metrics")
    async def get_repo_metrics(repo_name: str) -> dict:
        """Get metrics for a specific repository."""
        from pr_review_agent.db.connection import get_session_factory
        from pr_review_agent.db.repositories import ReviewRepository

        session_factory = get_session_factory()
        async with session_factory() as session:
            repo = ReviewRepository(session)
            usage = await repo.get_token_usage_summary(repo_name)
            feedback = await repo.get_feedback_summary(repo_name)

        return {
            "repository": repo_name,
            "usage": usage,
            "feedback": feedback,
        }

    # ── Reviews listing ───────────────────────────────────────────────

    @app.get("/reviews")
    async def list_reviews(
        status: str | None = None,
        repo: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List reviews with optional filtering."""
        from pr_review_agent.db.connection import get_session_factory
        from pr_review_agent.db.repositories import ReviewRepository

        session_factory = get_session_factory()
        async with session_factory() as session:
            repository = ReviewRepository(session)
            reviews = await repository.list_reviews(
                status=status,
                repository_full_name=repo,
                limit=limit,
                offset=offset,
            )

            return [
                {
                    "id": r.id,
                    "pr_number": r.pr_number,
                    "repository": r.repository_full_name,
                    "status": r.status,
                    "title": r.title,
                    "author": r.author,
                    "summary": r.summary,
                    "total_comments": r.total_comments,
                    "critical_count": r.critical_count,
                    "high_count": r.high_count,
                    "medium_count": r.medium_count,
                    "low_count": r.low_count,
                    "total_tokens": r.total_tokens,
                    "estimated_cost_usd": r.estimated_cost_usd,
                    "findings_count": len(r.findings),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "posted_at": r.posted_at.isoformat() if r.posted_at else None,
                }
                for r in reviews
            ]

    @app.get("/reviews/{review_id}")
    async def get_review(review_id: int) -> dict:
        """Get a review by ID with all findings."""
        from pr_review_agent.db.connection import get_session_factory
        from pr_review_agent.db.repositories import ReviewRepository

        session_factory = get_session_factory()
        async with session_factory() as session:
            repo = ReviewRepository(session)
            review = await repo.get_review(review_id)

        if not review:
            raise HTTPException(status_code=404, detail="Review not found")

        return {
            "id": review.id,
            "pr_number": review.pr_number,
            "repository": review.repository_full_name,
            "status": review.status,
            "title": review.title,
            "summary": review.summary,
            "total_comments": review.total_comments,
            "critical_count": review.critical_count,
            "high_count": review.high_count,
            "medium_count": review.medium_count,
            "low_count": review.low_count,
            "total_tokens": review.total_tokens,
            "estimated_cost_usd": review.estimated_cost_usd,
            "github_pr_review_id": review.github_pr_review_id,
            "posted_at": review.posted_at.isoformat() if review.posted_at else None,
            "findings": [
                {
                    "id": f.id,
                    "file": f.file_path,
                    "line": f.line,
                    "severity": f.severity,
                    "category": f.category,
                    "title": f.title,
                    "description": f.description,
                    "suggestion": f.suggestion,
                    "confidence": f.confidence,
                    "source_agent": f.source_agent,
                }
                for f in review.findings
            ],
        }

    return app
