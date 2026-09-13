"""Regression tests for the Phase 12 HITL approval flow.

The bug these cover: approving a review used to mark it "completed" without
ever posting the findings to GitHub, so the documented flow was a no-op.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from pr_review_agent.models.review import FindingSeverity, ReviewStatus
from pr_review_agent.webhooks.receiver import (
    _findings_for_approval,
    create_app,
)

REVIEW_ID = 1
GITHUB_REVIEW_ID = 999


def _fake_finding_row() -> SimpleNamespace:
    return SimpleNamespace(
        file_path="app.py",
        line=3,
        end_line=None,
        severity=FindingSeverity.HIGH,
        category="security",
        title="SQL injection",
        description="Interpolated query",
        suggestion="Use parameters",
        confidence=0.9,
        source_agent="security",
    )


def _fake_review() -> SimpleNamespace:
    return SimpleNamespace(
        status=ReviewStatus.AWAITING_APPROVAL.value,
        findings=[_fake_finding_row()],
        repository_full_name="org/repo",
        pr_number=7,
        head_sha="abc123",
        summary="1 issue",
    )


class FakeQueue:
    """Minimal stand-in for EventQueue."""


def _make_client(monkeypatch, *, poster_returns=GITHUB_REVIEW_ID):
    """Build a test client with the DB and GitHub poster faked out."""
    calls: dict = {"poster_returns": poster_returns}

    class FakeRepo:
        def __init__(self, session) -> None:
            pass

        async def get_review(self, review_id: int):
            return _fake_review()

        async def create_approval(self, **kwargs):
            calls["approval"] = kwargs
            return SimpleNamespace(id=1)

        async def update_status(self, review_id: int, status) -> None:
            calls["status"] = status

        async def mark_posted(self, review_id: int, github_review_id: int) -> None:
            calls["posted"] = github_review_id

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def commit(self) -> None:
            calls["committed"] = True

    class FakePoster:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def post_review(self, **kwargs):
            calls["post_kwargs"] = kwargs
            return calls["poster_returns"]

        async def close(self) -> None:
            calls["poster_closed"] = True

    monkeypatch.setattr("pr_review_agent.db.connection.get_session_factory", lambda: FakeSession)
    monkeypatch.setattr("pr_review_agent.db.repositories.ReviewRepository", FakeRepo)
    monkeypatch.setattr("pr_review_agent.github.comment_poster.GitHubCommentPoster", FakePoster)

    app = create_app(FakeQueue())
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return client, calls


class TestApprovalPostsToGitHub:
    async def test_approved_review_is_posted(self, monkeypatch):
        client, calls = _make_client(monkeypatch)

        resp = await client.post(
            f"/reviews/{REVIEW_ID}/approve",
            json={"approver": "dev", "decision": "approved"},
        )

        assert resp.status_code == 200
        assert resp.json()["github_pr_review_id"] == GITHUB_REVIEW_ID
        # Posted to GitHub and marked in the DB
        assert calls["posted"] == GITHUB_REVIEW_ID
        assert calls["status"] == ReviewStatus.COMPLETED
        assert calls["approval"]["decision"] == "approved"
        assert calls["post_kwargs"]["repository_full_name"] == "org/repo"
        assert calls["post_kwargs"]["pr_number"] == 7
        assert len(calls["post_kwargs"]["findings"]) == 1

    async def test_rejected_review_is_not_posted(self, monkeypatch):
        client, calls = _make_client(monkeypatch)

        resp = await client.post(
            f"/reviews/{REVIEW_ID}/approve",
            json={"approver": "dev", "decision": "rejected"},
        )

        assert resp.status_code == 200
        assert resp.json()["github_pr_review_id"] is None
        assert calls["status"] == ReviewStatus.SKIPPED
        assert "posted" not in calls
        assert "post_kwargs" not in calls

    async def test_edited_decision_posts_edited_findings(self, monkeypatch):
        client, calls = _make_client(monkeypatch)

        edited = (
            '[{"file": "app.py", "line": 3, "severity": "LOW", '
            '"category": "quality", "title": "Tidy up", "description": "d", '
            '"suggestion": "", "confidence": 0.95}]'
        )
        resp = await client.post(
            f"/reviews/{REVIEW_ID}/approve",
            json={
                "approver": "dev",
                "decision": "edited",
                "edited_findings_json": edited,
            },
        )

        assert resp.status_code == 200
        posted = calls["post_kwargs"]["findings"]
        assert len(posted) == 1
        assert posted[0].title == "Tidy up"
        assert posted[0].severity == FindingSeverity.LOW

    async def test_posting_failure_leaves_review_awaiting_approval(self, monkeypatch):
        client, calls = _make_client(monkeypatch, poster_returns=None)

        resp = await client.post(
            f"/reviews/{REVIEW_ID}/approve",
            json={"approver": "dev", "decision": "approved"},
        )

        assert resp.status_code == 502
        # Review must stay pending so the decision can be retried
        assert "status" not in calls
        assert calls["poster_closed"] is True

    async def test_invalid_decision_is_rejected(self, monkeypatch):
        client, _ = _make_client(monkeypatch)

        resp = await client.post(
            f"/reviews/{REVIEW_ID}/approve",
            json={"approver": "dev", "decision": "maybe"},
        )

        assert resp.status_code == 400


class TestFindingsForApproval:
    def test_uses_stored_findings_by_default(self):
        findings = _findings_for_approval([_fake_finding_row()], None)
        assert len(findings) == 1
        assert findings[0].file == "app.py"
        assert findings[0].severity == FindingSeverity.HIGH

    def test_parses_edited_findings_json(self):
        payload = (
            '[{"file": "x.py", "line": 1, "severity": "CRITICAL", '
            '"category": "security", "title": "t", "description": "d"}]'
        )
        findings = _findings_for_approval([], payload)
        assert findings[0].severity == FindingSeverity.CRITICAL

    def test_malformed_json_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _findings_for_approval([], "{not json")
        assert exc.value.status_code == 400

    def test_non_array_json_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _findings_for_approval([], '{"findings": []}')
        assert exc.value.status_code == 400

    def test_invalid_finding_shape_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _findings_for_approval([], '[{"title": "missing required fields"}]')
        assert exc.value.status_code == 400
