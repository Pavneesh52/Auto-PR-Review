"""Event processor.

Phases 2-18 — Consumes events from the queue, assembles context,
runs the LangGraph review pipeline, and posts results to GitHub.

Integrates:
- Phase 2:  Queue consumption
- Phase 3:  Context assembly
- Phase 4:  Database persistence
- Phase 5:  LangGraph review pipeline
- Phase 10: Semantic search enrichment (see context/embeddings.py + CLI)
- Phase 12: HITL gate (low-confidence findings → await approval)
- Phase 13: GitHub comment posting
- Phase 14: File-level caching / incremental review
- Phase 16: Feedback loop (past feedback guides the agents)
- Phase 17: Rate limiting & real cost/token budgets
- Phase 18: Event traces for observability
"""

from __future__ import annotations

import hashlib

import structlog

from pr_review_agent.config.settings import settings
from pr_review_agent.context.assembly import ContextAssembler, ContextAssemblyError
from pr_review_agent.db.connection import get_session_factory
from pr_review_agent.db.repositories import ReviewRepository
from pr_review_agent.github.comment_poster import GitHubCommentPoster
from pr_review_agent.models.events import PRAction, WebhookEvent
from pr_review_agent.models.review import ChangedFile, ReviewFinding, ReviewStatus
from pr_review_agent.orchestrator.graph import run_review
from pr_review_agent.queue.event_queue import EventQueue
from pr_review_agent.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)

# Actions we process
PROCESSABLE_ACTIONS = {
    PRAction.OPENED,
    PRAction.SYNCHRONIZE,
    PRAction.REOPENED,
    PRAction.READY_FOR_REVIEW,
}

# Cache findings per file with a single logical "agent" key so a file is
# either fully cached (no LLM calls) or fully re-analyzed. Agents see the
# whole diff, so partial per-agent caching isn't meaningful.
CACHE_AGENT_TYPE = "combined"


def _content_hash(changed_file: ChangedFile) -> str:
    """Hash a changed file's patch to detect whether it changed since last review."""
    material = (changed_file.patch or changed_file.path).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


class EventProcessor:
    """Processes queued events through the full review pipeline.

    Pipeline:
        Queue → Parse → Rate limit → Budget check → Context Assembly
        → Cache lookup → LangGraph Review → Persist → HITL check
        → Post to GitHub → Record spend & traces
    """

    def __init__(
        self,
        event_queue: EventQueue,
        context_assembler: ContextAssembler,
    ) -> None:
        self.queue = event_queue
        self.context_assembler = context_assembler
        self.comment_poster = GitHubCommentPoster()
        self._running = False

    async def start(self) -> None:
        """Start processing events from the queue."""
        # Fail loudly-but-cleanly if Redis never connected, rather than
        # crashing the background task on the first dequeue.
        if not self.queue.is_connected:
            logger.error(
                "event_processor_cannot_start",
                reason="redis not connected; no events will be processed",
            )
            return

        self._running = True
        logger.info("event_processor_started")

        while self._running:
            try:
                event = await self.queue.dequeue(timeout=5)
                if event is None:
                    continue

                await self._process_event(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("processor_unexpected_error", error=str(e))
                await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the event processor."""
        self._running = False
        await self.comment_poster.close()
        logger.info("event_processor_stopped")

    # ── Helpers ───────────────────────────────────────────────────────

    def _rate_limiter(self) -> RateLimiter | None:
        """Build a rate limiter, or None when Redis isn't connected."""
        if not self.queue.is_connected:
            logger.warning("rate_limiter_unavailable", reason="redis not connected")
            return None
        return RateLimiter(self.queue.client)

    async def _trace(
        self,
        event_type: str,
        review_id: int | None = None,
        detail: str = "",
        tokens: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        """Record an observability trace (Phase 18), never failing the review."""
        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                repo = ReviewRepository(session)
                await repo.record_trace(
                    event_type=event_type,
                    review_id=review_id,
                    detail=detail,
                    tokens=tokens,
                    duration_ms=duration_ms,
                )
                await session.commit()
        except Exception as e:  # pragma: no cover - observability is best effort
            logger.warning("trace_record_failed", event_type=event_type, error=str(e))

    async def _split_cached_files(
        self, repository_full_name: str, changed_files: list[ChangedFile]
    ) -> tuple[list[ChangedFile], list[ReviewFinding], dict[str, str]]:
        """Split changed files into cache hits and files needing analysis.

        Returns:
            (files_to_analyze, cached_findings, path -> content hash)
        """
        hashes = {f.path: _content_hash(f) for f in changed_files}

        if not settings.cache_enabled:
            return list(changed_files), [], hashes

        to_analyze: list[ChangedFile] = []
        reused: list[ReviewFinding] = []

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                repo = ReviewRepository(session)
                for changed_file in changed_files:
                    cached = await repo.get_cached_findings(
                        repository_full_name=repository_full_name,
                        file_path=changed_file.path,
                        content_hash=hashes[changed_file.path],
                        agent_type=CACHE_AGENT_TYPE,
                    )
                    if cached is None:
                        to_analyze.append(changed_file)
                    else:
                        reused.extend(cached)
                await session.commit()
        except Exception as e:
            logger.warning("cache_lookup_failed", error=str(e))
            return list(changed_files), [], hashes

        logger.info(
            "cache_lookup_complete",
            repo=repository_full_name,
            cached_files=len(changed_files) - len(to_analyze),
            files_to_analyze=len(to_analyze),
            cached_findings=len(reused),
        )
        return to_analyze, reused, hashes

    async def _store_findings_in_cache(
        self,
        repository_full_name: str,
        analyzed_files: list[ChangedFile],
        hashes: dict[str, str],
        findings: list[ReviewFinding],
    ) -> None:
        """Cache the findings produced for each analyzed file (Phase 14)."""
        if not settings.cache_enabled or not analyzed_files:
            return

        by_file: dict[str, list[ReviewFinding]] = {}
        for finding in findings:
            by_file.setdefault(finding.file, []).append(finding)

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                repo = ReviewRepository(session)
                for changed_file in analyzed_files:
                    content_hash = hashes.get(changed_file.path)
                    if not content_hash:
                        continue
                    await repo.cache_findings(
                        repository_full_name=repository_full_name,
                        file_path=changed_file.path,
                        content_hash=content_hash,
                        agent_type=CACHE_AGENT_TYPE,
                        findings=by_file.get(changed_file.path, []),
                    )
                await session.commit()
        except Exception as e:
            logger.warning("cache_store_failed", error=str(e))

    # ── Main pipeline ─────────────────────────────────────────────────

    async def _process_event(self, raw_event: dict) -> None:
        """Process a single event through the full pipeline."""
        event_id = raw_event.get("id", "unknown")
        event_type = raw_event.get("type", "unknown")

        logger.info("processing_event", event_id=event_id, event_type=event_type)

        await self.queue.mark_processing(event_id)
        review_id: int | None = None

        try:
            # ── Phase 2: Parse the event ──────────────────────────────
            payload = raw_event.get("payload", {})
            event = WebhookEvent.from_github_payload(payload, delivery_id=event_id)

            if event.action not in PROCESSABLE_ACTIONS:
                logger.info(
                    "action_not_processable",
                    action=event.action,
                    event_id=event_id,
                )
                await self.queue.mark_completed(event_id)
                return

            repository = event.repository_full_name
            limiter = self._rate_limiter()

            # ── Phase 17: Rate limit + pre-flight budget ──────────────
            if limiter is not None:
                try:
                    allowed, reason = await limiter.check_rate_limit(repository)
                    if not allowed:
                        logger.warning("rate_limited", reason=reason)
                        await self._trace("rate_limited", detail=reason)
                        await self.queue.mark_completed(event_id)
                        return

                    budget_ok, budget_reason = await limiter.check_daily_budget(repository)
                    if not budget_ok:
                        logger.warning("daily_budget_exceeded", reason=budget_reason)
                        await self._trace("budget_exceeded", detail=budget_reason)
                        await self.queue.mark_completed(event_id)
                        return
                except Exception as e:
                    logger.warning("rate_limit_check_failed", error=str(e))

            # ── Phase 3: Assemble context ─────────────────────────────
            context = await self.context_assembler.assemble(event)

            logger.info(
                "context_assembled",
                pr_number=event.pr_number,
                files_changed=len(context.changed_files),
                context_files=len(context.context_files),
                is_large_pr=context.is_large_pr,
            )

            session_factory = get_session_factory()

            # ── Phase 4: Create review record ─────────────────────────
            async with session_factory() as session:
                repo = ReviewRepository(session)
                review_row = await repo.create_review(
                    pr_number=event.pr_number,
                    repository_full_name=repository,
                    title=event.pull_request.title,
                    body=event.pull_request.body,
                    author=event.pull_request.author,
                    base_branch=event.pull_request.base_branch,
                    head_sha=event.pull_request.head_sha,
                )
                await repo.update_status(review_row.id, ReviewStatus.IN_PROGRESS)
                await repo.update_review_diff_stats(
                    review_id=review_row.id,
                    files_changed=len(context.changed_files),
                    total_additions=context.total_additions,
                    total_deletions=context.total_deletions,
                )
                await session.commit()
                review_id = review_row.id

            await self._trace(
                "context_assembled",
                review_id=review_id,
                detail=(
                    f"{len(context.changed_files)} files, "
                    f"+{context.total_additions}/-{context.total_deletions}"
                ),
            )

            # ── Phase 14: Cache lookup ────────────────────────────────
            to_analyze, cached_findings, hashes = await self._split_cached_files(
                repository, context.changed_files
            )

            # ── Phase 16: Feedback guidance ───────────────────────────
            feedback_guidance = ""
            try:
                async with session_factory() as session:
                    repo = ReviewRepository(session)
                    feedback_guidance = await repo.get_feedback_guidance(repository)
            except Exception as e:
                logger.warning("feedback_guidance_failed", error=str(e))

            # ── Phase 5: Run LangGraph review pipeline ────────────────
            final_state = await run_review(
                review_id=review_id,
                pr_number=event.pr_number,
                repository_full_name=repository,
                title=event.pull_request.title,
                body=event.pull_request.body,
                author=event.pull_request.author,
                base_branch=event.pull_request.base_branch,
                head_sha=event.pull_request.head_sha,
                diff=context.diff,
                changed_files=to_analyze,
                context_files=context.context_files,
                cached_findings=cached_findings,
                feedback_guidance=feedback_guidance,
            )

            # ── Phase 17: Cost from real token usage ──────────────────
            total_tokens = final_state.get("total_tokens", 0)
            estimated_cost = float(final_state.get("estimated_cost_usd", 0.0))
            budget_ok, budget_reason = True, ""
            if limiter is not None:
                try:
                    budget_ok, budget_reason = await limiter.check_cost_budget(
                        total_tokens, estimated_cost
                    )
                    if not budget_ok:
                        logger.warning("review_over_budget", reason=budget_reason)
                except Exception as e:
                    logger.warning("cost_budget_check_failed", error=str(e))

            # ── Phase 4: Persist results ──────────────────────────────
            async with session_factory() as session:
                repo = ReviewRepository(session)
                await repo.update_status(review_id, ReviewStatus(final_state["status"]))
                await repo.update_review_totals(
                    review_id=review_id,
                    summary=final_state.get("summary", ""),
                    total_comments=final_state.get("total_comments", 0),
                    critical_count=final_state.get("critical_count", 0),
                    high_count=final_state.get("high_count", 0),
                    medium_count=final_state.get("medium_count", 0),
                    low_count=final_state.get("low_count", 0),
                    total_tokens=total_tokens,
                    estimated_cost_usd=estimated_cost,
                )
                # Save findings
                findings = final_state.get("sorted_findings", [])
                if findings:
                    await repo.save_findings(review_id, findings)

                # Save agent results
                agent_results = final_state.get("agent_results", {})
                for agent_type, ar in agent_results.items():
                    await repo.save_agent_result(
                        review_id=review_id,
                        agent_type=agent_type,
                        confidence=ar.confidence,
                        findings_count=len(ar.findings),
                        tokens_used=ar.tokens_used,
                        duration_seconds=ar.duration_seconds,
                        error=ar.error,
                    )
                await session.commit()

            # ── Phase 14: Populate cache for next push ────────────────
            await self._store_findings_in_cache(
                repository,
                to_analyze,
                hashes,
                final_state.get("all_findings", []),
            )

            # ── Phase 17: Record real spend against the daily budget ──
            if limiter is not None and total_tokens > 0:
                try:
                    await limiter.record_token_spend(repository, total_tokens)
                except Exception as e:
                    logger.warning("token_spend_record_failed", error=str(e))

            await self._trace(
                "review_completed",
                review_id=review_id,
                detail=(
                    f"status={final_state.get('status')} "
                    f"findings={final_state.get('total_comments', 0)}"
                ),
                tokens=total_tokens,
            )

            # ── Phase 12: HITL gate ───────────────────────────────────
            if final_state.get("should_escalate_to_hitl", False):
                async with session_factory() as session:
                    repo = ReviewRepository(session)
                    await repo.update_status(review_id, ReviewStatus.AWAITING_APPROVAL)
                    await session.commit()

                await self._trace(
                    "awaiting_approval",
                    review_id=review_id,
                    detail=f"{final_state.get('total_comments', 0)} findings",
                )
                logger.info(
                    "review_awaiting_approval",
                    review_id=review_id,
                    pr_number=event.pr_number,
                )
                await self.queue.mark_completed(event_id)
                return

            # ── Phase 13: Post to GitHub ──────────────────────────────
            sorted_findings = final_state.get("sorted_findings", [])
            summary = final_state.get("summary", "")

            if sorted_findings:
                try:
                    github_review_id = await self.comment_poster.post_review(
                        repository_full_name=repository,
                        pr_number=event.pr_number,
                        head_sha=event.pull_request.head_sha,
                        findings=sorted_findings,
                        summary=summary,
                    )

                    if github_review_id:
                        async with session_factory() as session:
                            repo = ReviewRepository(session)
                            await repo.mark_posted(review_id, github_review_id)
                            await session.commit()
                        await self._trace(
                            "posted_to_github",
                            review_id=review_id,
                            detail=f"github_review_id={github_review_id}",
                        )
                except Exception as e:
                    logger.error(
                        "github_post_failed",
                        review_id=review_id,
                        error=str(e),
                    )

            await self.queue.mark_completed(event_id)

            logger.info(
                "event_processed_successfully",
                event_id=event_id,
                pr_number=event.pr_number,
                findings=final_state.get("total_comments", 0),
                cached_files=len(context.changed_files) - len(to_analyze),
                posted_to_github=bool(sorted_findings),
                over_budget=not budget_ok,
            )

        except ContextAssemblyError as e:
            logger.error(
                "event_processing_failed",
                event_id=event_id,
                error=str(e),
            )
            await self._mark_failed(review_id, str(e))
            await self.queue.mark_completed(event_id)

        except Exception as e:
            logger.error(
                "event_processing_error",
                event_id=event_id,
                error=str(e),
            )
            await self._mark_failed(review_id, str(e))
            await self.queue.mark_completed(event_id)

    async def _mark_failed(self, review_id: int | None, error: str) -> None:
        """Record a failed review so it doesn't sit in 'in_progress' forever."""
        if review_id is None:
            return
        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                repo = ReviewRepository(session)
                await repo.update_status(review_id, ReviewStatus.FAILED)
                await session.commit()
        except Exception as e:  # pragma: no cover - best effort
            logger.warning("mark_failed_write_error", review_id=review_id, error=str(e))
        await self._trace("review_failed", review_id=review_id, detail=error[:500])
