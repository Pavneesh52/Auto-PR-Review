"""Tests for webhook event models."""

from __future__ import annotations

import pytest

from pr_review_agent.models.events import PRAction, WebhookEvent


class TestPRAction:
    def test_known_actions_are_valid(self):
        assert PRAction.OPENED.value == "opened"
        assert PRAction.SYNCHRONIZE.value == "synchronize"
        assert PRAction.REOPENED.value == "reopened"

    def test_all_members_are_strings(self):
        for action in PRAction:
            assert isinstance(action.value, str)


class TestWebhookEvent:
    def test_parse_opened_event(self, sample_github_payload):
        event = WebhookEvent.from_github_payload(sample_github_payload, delivery_id="abc")

        assert event.action == PRAction.OPENED
        assert event.pr_number == 42
        assert event.repository_full_name == "acme/app"
        assert event.pull_request.title == "Add user authentication endpoint"
        assert event.pull_request.author == "dev-sarah"
        assert event.pull_request.head_sha == "abc123def456"
        assert event.pull_request.base_branch == "main"
        assert event.delivery_id == "abc"

    def test_parse_synchronize_event(self):
        payload = {
            "action": "synchronize",
            "number": 10,
            "pull_request": {
                "number": 10,
                "title": "Fix bug",
                "body": "",
                "head": {"sha": "def789"},
                "base": {"ref": "develop"},
                "user": {"login": "dev-bob"},
                "html_url": "https://github.com/org/repo/pull/10",
            },
            "repository": {"full_name": "org/repo"},
        }
        event = WebhookEvent.from_github_payload(payload)

        assert event.action == PRAction.SYNCHRONIZE
        assert event.pr_number == 10
        assert event.pull_request.base_branch == "develop"

    def test_unhandled_action_raises_value_error(self):
        payload = {
            "action": "closed",
            "number": 5,
            "pull_request": {"number": 5},
            "repository": {"full_name": "org/repo"},
        }
        with pytest.raises(ValueError, match="Unhandled PR action"):
            WebhookEvent.from_github_payload(payload)

    def test_missing_pr_field_handled(self):
        payload = {
            "action": "opened",
            "pull_request": {},
            "repository": {},
        }
        event = WebhookEvent.from_github_payload(payload)
        assert event.pr_number == 0
        assert event.repository_full_name == ""

    def test_empty_head_and_base_handled(self):
        payload = {
            "action": "opened",
            "number": 1,
            "pull_request": {
                "number": 1,
                "title": "Test",
                "head": "not-a-dict",
                "base": "also-not-a-dict",
                "user": "also-not-a-dict",
            },
            "repository": {"full_name": "org/repo"},
        }
        event = WebhookEvent.from_github_payload(payload)
        assert event.pull_request.head_sha == ""
        assert event.pull_request.base_branch == ""
