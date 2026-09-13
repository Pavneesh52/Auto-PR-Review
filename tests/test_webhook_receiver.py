"""Tests for the FastAPI webhook receiver."""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json

import pytest
from httpx import ASGITransport, AsyncClient

from pr_review_agent.config.settings import settings
from pr_review_agent.queue.event_queue import EventQueue
from pr_review_agent.webhooks.receiver import create_app

TEST_SECRET = "test-secret"


@pytest.fixture
def mock_queue():
    """A mock EventQueue that records enqueue calls."""
    from unittest.mock import AsyncMock

    queue = AsyncMock(spec=EventQueue)
    queue.enqueue = AsyncMock(return_value=True)
    return queue


@pytest.fixture
def app(mock_queue):
    """FastAPI app with mock queue."""
    return create_app(mock_queue)


@pytest.fixture
def client(app):
    """Async HTTP client for testing."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def webhook_secret(monkeypatch):
    """Configure a webhook secret so signatures are actually enforced."""
    monkeypatch.setattr(settings, "github_webhook_secret", TEST_SECRET, raising=False)
    return TEST_SECRET


@pytest.fixture
def sign_payload():
    """Helper to sign a payload with a test secret."""

    def _sign(payload_bytes: bytes, secret: str = TEST_SECRET) -> str:
        return (
            "sha256="
            + hmac_mod.new(
                key=secret.encode("utf-8"),
                msg=payload_bytes,
                digestmod=hashlib.sha256,
            ).hexdigest()
        )

    return _sign


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestWebhookEndpoint:
    async def test_ignores_non_pr_events(self, client, webhook_secret, sign_payload):
        body = b"{}"
        resp = await client.post(
            "/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "delivery-001",
                "X-Hub-Signature-256": sign_payload(body),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    async def test_rejects_invalid_hmac(self, client, webhook_secret):
        payload = json.dumps({"action": "opened"}).encode()

        resp = await client.post(
            "/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-002",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )
        assert resp.status_code == 401

    async def test_rejects_missing_signature(self, client, webhook_secret):
        resp = await client.post(
            "/webhook",
            content=b"{}",
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-006",
            },
        )
        assert resp.status_code == 401

    async def test_skips_verification_when_no_secret(self, client):
        """Dev mode: with no secret configured, unsigned payloads are accepted."""
        payload = json.dumps({"action": "closed", "pull_request": {}}).encode()
        resp = await client.post(
            "/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-007",
            },
        )
        assert resp.status_code == 200

    async def test_enqueues_pr_opened_event(self, client, mock_queue, webhook_secret, sign_payload):
        payload = json.dumps(
            {
                "action": "opened",
                "pull_request": {
                    "number": 42,
                    "title": "Add auth",
                    "body": "Adds JWT auth.",
                    "head": {"sha": "abc123"},
                    "base": {"ref": "main"},
                    "user": {"login": "sarah"},
                    "html_url": "https://github.com/org/repo/pull/42",
                },
                "repository": {"full_name": "org/repo"},
            }
        ).encode()

        resp = await client.post(
            "/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-003",
                "X-Hub-Signature-256": sign_payload(payload),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["pr_number"] == 42

        # Verify enqueue was called
        mock_queue.enqueue.assert_called_once()

    async def test_duplicate_delivery_is_reported(
        self, client, mock_queue, webhook_secret, sign_payload
    ):
        payload = json.dumps(
            {
                "action": "opened",
                "pull_request": {
                    "number": 42,
                    "title": "Add auth",
                    "head": {"sha": "abc123"},
                    "base": {"ref": "main"},
                    "user": {"login": "sarah"},
                },
                "repository": {"full_name": "org/repo"},
            }
        ).encode()
        mock_queue.enqueue.return_value = False

        resp = await client.post(
            "/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-004",
                "X-Hub-Signature-256": sign_payload(payload),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "duplicate"

    async def test_skips_unhandled_action(self, client, webhook_secret, sign_payload):
        payload = json.dumps(
            {
                "action": "closed",
                "pull_request": {"number": 1},
                "repository": {"full_name": "org/repo"},
            }
        ).encode()

        resp = await client.post(
            "/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-004",
                "X-Hub-Signature-256": sign_payload(payload),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "skipped"

    async def test_handles_invalid_json(self, client, webhook_secret, sign_payload):
        body = b"not json"
        resp = await client.post(
            "/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-005",
                "X-Hub-Signature-256": sign_payload(body),
            },
        )
        assert resp.status_code == 400


class TestReviewsEndpoint:
    async def test_list_reviews(self, client, monkeypatch):
        from contextlib import asynccontextmanager
        from types import SimpleNamespace

        fake_review = SimpleNamespace(
            id=1,
            pr_number=10,
            repository_full_name="org/repo",
            status="awaiting_approval",
            title="Test PR",
            author="tester",
            summary="Review summary",
            total_comments=1,
            critical_count=0,
            high_count=1,
            medium_count=0,
            low_count=0,
            total_tokens=150,
            estimated_cost_usd=0.002,
            findings=[],
            created_at=None,
            posted_at=None,
        )

        class FakeRepo:
            def __init__(self, session):
                pass

            async def list_reviews(self, **kwargs):
                return [fake_review]

        @asynccontextmanager
        async def fake_session():
            yield object()

        monkeypatch.setattr(
            "pr_review_agent.db.connection.get_session_factory",
            lambda: fake_session,
        )
        monkeypatch.setattr(
            "pr_review_agent.db.repositories.ReviewRepository",
            FakeRepo,
        )

        resp = await client.get("/reviews")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert data[0]["repository"] == "org/repo"
        assert data[0]["status"] == "awaiting_approval"

