"""Database connection and session management.

Phase 4 - Async SQLAlchemy engine + session factory.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from pr_review_agent.config.settings import settings
from pr_review_agent.db.models import Base

logger = structlog.get_logger(__name__)

# Async engine (for the app)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# Sync engine (for migrations / testing)
_sync_engine = None
_sync_session_factory = None


def get_engine() -> AsyncEngine:
    """Get or create the async engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async session, auto-closes."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Verify the database is reachable and has been migrated.

    Schema creation is owned by Alembic (`alembic upgrade head`). We
    deliberately do not call create_all here: doing so would let the ORM
    metadata and the migration history drift apart, and would leave a DB
    with tables but no `alembic_version` row that later migrations reject.
    """
    engine = get_engine()
    async with engine.connect() as conn:
        has_tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).has_table("reviews"))

    if has_tables:
        logger.info("database_ready")
    else:
        logger.error(
            "database_schema_missing",
            hint="run 'alembic upgrade head' to create the schema",
        )


async def close_db() -> None:
    """Dispose of the engine."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
    logger.info("database_connections_closed")


# Sync helpers (for CLI / migrations)
def get_sync_session() -> Session:
    """Synchronous session for scripts and testing."""
    global _sync_engine, _sync_session_factory
    if _sync_engine is None:
        _sync_engine = create_engine(settings.database_url_sync, echo=False)
        _sync_session_factory = sessionmaker(bind=_sync_engine)
    return _sync_session_factory()


def create_tables_sync() -> None:
    """Create tables synchronously (for CLI bootstrap)."""
    engine = create_engine(settings.database_url_sync, echo=False)
    Base.metadata.create_all(engine)
    engine.dispose()
