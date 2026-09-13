"""Shared test fixtures."""

from __future__ import annotations

import pytest
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from pr_review_agent.config.settings import settings
from pr_review_agent.db.models import Base
from pr_review_agent.models.events import PRAction, PRInfo, WebhookEvent
from pr_review_agent.models.review import ChangedFile


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch):
    """Keep tests independent of the developer's local .env file.

    Without this, a real GITHUB_WEBHOOK_SECRET (or OPENAI_API_KEY) in
    .env leaks into the test run and makes results machine-dependent.
    """
    monkeypatch.setattr(settings, "github_webhook_secret", "", raising=False)
    monkeypatch.setattr(settings, "github_token", "", raising=False)
    monkeypatch.setattr(settings, "openai_api_key", "", raising=False)
    yield


@pytest.fixture
def sample_github_payload() -> dict:
    """A realistic GitHub pull_request webhook payload."""
    return {
        "action": "opened",
        "number": 42,
        "pull_request": {
            "number": 42,
            "title": "Add user authentication endpoint",
            "body": "Adds JWT-based auth with login/signup endpoints.",
            "head": {"sha": "abc123def456"},
            "base": {"ref": "main"},
            "user": {"login": "dev-sarah"},
            "html_url": "https://github.com/acme/app/pull/42",
        },
        "repository": {
            "full_name": "acme/app",
        },
    }


@pytest.fixture
def sample_webhook_event() -> WebhookEvent:
    """A parsed WebhookEvent."""
    return WebhookEvent(
        action=PRAction.OPENED,
        pr_number=42,
        repository_full_name="acme/app",
        pull_request=PRInfo(
            number=42,
            title="Add user authentication endpoint",
            body="Adds JWT-based auth.",
            head="abc123def456",
            base="main",
            user="dev-sarah",
            html_url="https://github.com/acme/app/pull/42",
        ),
        delivery_id="test-delivery-001",
    )


@pytest.fixture
def sample_changed_files() -> list[ChangedFile]:
    """Changed files from a typical PR."""
    return [
        ChangedFile(
            path="src/auth/login.py",
            status="added",
            additions=45,
            deletions=0,
            patch="""@@ -0,0 +1,45 @@
+import hashlib
+from pr_review_agent.models import User
+
+def login(username: str, password: str) -> bool:
+    user = User.find(username)
+    if not user:
+        return False
+    return user.verify_password(password)
""",
            language="python",
        ),
        ChangedFile(
            path="src/auth/__init__.py",
            status="modified",
            additions=2,
            deletions=0,
            patch="@@ -1 +1,3 @@\n+from .login import login\n",
            language="python",
        ),
        ChangedFile(
            path="tests/test_login.py",
            status="added",
            additions=20,
            deletions=0,
            patch="@@ -0,0 +1,20 @@\n+import pytest\n+from src.auth import login\n",
            language="python",
        ),
    ]


@pytest.fixture
def sample_pr_files_api_response() -> list[dict]:
    """GitHub API response for PR files."""
    return [
        {
            "filename": "src/auth/login.py",
            "status": "added",
            "additions": 45,
            "deletions": 0,
            "patch": "@@ -0,0 +1,45 @@\n+import hashlib",
        },
        {
            "filename": "src/auth/__init__.py",
            "status": "modified",
            "additions": 2,
            "deletions": 0,
            "patch": "@@ -1 +1,3 @@\n+from .login import login",
        },
    ]


@pytest.fixture
async def redis_client():
    """Async Redis client for testing, using a separate DB.

    Skips the test when Redis isn't reachable so the suite still passes
    on a machine without Docker running.
    """
    client = aioredis.from_url("redis://localhost:6379/1", decode_responses=True)
    try:
        await client.ping()
    except Exception:  # pragma: no cover - environment dependent
        await client.aclose()
        pytest.skip("Redis not available on localhost:6379")
    try:
        yield client
    finally:
        try:
            await client.flushdb()
        finally:
            await client.aclose()


@pytest.fixture
async def db_engine():
    """Async SQLAlchemy engine for testing.

    Skips the test when Postgres isn't reachable so the suite still
    passes on a machine without Docker running.
    """
    engine = create_async_engine(settings.database_url, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip("Postgres not available")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Async SQLAlchemy session for testing."""
    session_factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
