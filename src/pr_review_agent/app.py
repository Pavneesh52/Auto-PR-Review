"""Application entry point.

Wires together all components and starts the FastAPI server.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from pr_review_agent.config.settings import settings
from pr_review_agent.context.assembly import ContextAssembler
from pr_review_agent.context.embeddings import EmbeddingService
from pr_review_agent.context.github_client import GitHubClient
from pr_review_agent.db.connection import close_db, init_db
from pr_review_agent.processor import EventProcessor
from pr_review_agent.queue.event_queue import EventQueue
from pr_review_agent.webhooks.receiver import create_app

logger = structlog.get_logger(__name__)


def configure_logging() -> None:
    """Configure structlog for the application.

    structlog writes straight to stdout with its own PrintLogger rather than
    going through the stdlib logging root logger. The stdlib route is fragile
    here: uvicorn installs its own logging config after ours, and any
    interaction that leaves the root logger without a handler or above the
    configured level silently swallows every application log while uvicorn's
    own output keeps working.

    Uvicorn keeps its stdlib logging for its own loggers; the two do not
    interfere because structlog no longer shares that pipeline.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Third-party libraries (including uvicorn) still log through stdlib.
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stdout, force=True)
    for noisy in ("httpx", "httpcore", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        context_class=dict,
        cache_logger_on_first_use=True,
    )


def build_app() -> FastAPI:
    """Build the FastAPI app with all dependencies wired up.

    Separated from main() so tests and tooling can construct the app
    without starting uvicorn.
    """
    event_queue = EventQueue()
    # Context assembly talks to GitHub on behalf of private repos, so the
    # token matters: without it we're limited to 60 unauthenticated requests
    # per hour and can't see private repositories.
    github_client = GitHubClient(token=settings.github_token)
    embedding_service = EmbeddingService()
    context_assembler = ContextAssembler(github_client, embedding_service)
    event_processor = EventProcessor(event_queue, context_assembler)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Connect dependencies, start the processor, clean up on exit."""
        # Phase 4: Initialize database tables (dev convenience; Alembic in prod)
        try:
            await init_db()
            logger.info("database_initialized")
        except Exception as e:
            logger.warning("database_init_failed", error=str(e))

        # Phase 2: Connect to Redis
        try:
            await event_queue.connect()
            logger.info("connected_to_redis", redis_url=settings.redis_url)
        except Exception as e:
            logger.warning("redis_connection_failed", error=str(e))

        # Start event processor in background. The processor logs its own
        # startup (or its own refusal to start when Redis is unavailable), so
        # no log here — announcing success unconditionally was misleading.
        processor_task = asyncio.create_task(event_processor.start())

        try:
            yield
        finally:
            await event_processor.stop()
            processor_task.cancel()
            try:
                await processor_task
            except (asyncio.CancelledError, Exception):
                pass
            await embedding_service.close()
            await event_queue.close()
            await close_db()
            logger.info("shutdown_complete")

    app = create_app(event_queue, lifespan=lifespan)
    app.state.event_queue = event_queue
    app.state.event_processor = event_processor
    return app


def main() -> None:
    """Main entry point."""
    configure_logging()

    app = build_app()

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
