"""GitHub webhook event models.

Maps GitHub PR webhook payloads to structured Pydantic models.
Phase 2 - Trigger Design & Event Ingestion.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PRAction(StrEnum):
    """PR webhook actions we handle."""

    OPENED = "opened"
    SYNCHRONIZE = "synchronize"
    REOPENED = "reopened"
    READY_FOR_REVIEW = "ready_for_review"
    REVIEW_REQUESTED = "review_requested"


class PRInfo(BaseModel):
    """Key fields from the pull_request object in the webhook."""

    number: int
    title: str
    body: str = ""
    head_sha: str = Field(alias="head")
    base_branch: str = Field(alias="base")
    author: str = Field(alias="user")
    html_url: str = ""


class WebhookEvent(BaseModel):
    """Top-level webhook event wrapper.

    We only extract fields we need, ignoring the rest of the
    massive GitHub payload.
    """

    action: PRAction
    pr_number: int
    repository_full_name: str
    pull_request: PRInfo
    delivery_id: str = ""  # X-GitHub-Delivery header

    @classmethod
    def from_github_payload(cls, payload: dict[str, Any], delivery_id: str = "") -> WebhookEvent:
        """Parse a raw GitHub webhook payload into our model.

        Extracts only the fields we need and discards the rest.
        """
        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})

        action = payload.get("action", "")
        if action not in [a.value for a in PRAction]:
            # We silently ignore actions we don't handle (closed, labeled, etc.)
            raise ValueError(f"Unhandled PR action: {action}")

        pr_info = PRInfo(
            number=pr.get("number", 0),
            title=pr.get("title", ""),
            body=pr.get("body", ""),
            head=pr.get("head", {}).get("sha", "") if isinstance(pr.get("head"), dict) else "",
            base=pr.get("base", {}).get("ref", "") if isinstance(pr.get("base"), dict) else "",
            user=pr.get("user", {}).get("login", "") if isinstance(pr.get("user"), dict) else "",
            html_url=pr.get("html_url", ""),
        )

        return cls(
            action=action,
            pr_number=pr.get("number", 0),
            repository_full_name=repo.get("full_name", ""),
            pull_request=pr_info,
            delivery_id=delivery_id,
        )
