from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class WebhookEvent(BaseModel):
    event_type: str
    delivery_id: str
    payload: Dict[str, Any]
    signature: str


class PullRequestPayload(BaseModel):
    action: str
    number: int
    pull_request: Dict[str, Any]
    repository: Dict[str, Any]
    sender: Dict[str, Any]


class ReviewJob(BaseModel):
    review_id: str
    repo: str
    pr_number: int
    pr_title: str
    pr_body: Optional[str]
    diff: str
    base_sha: str
    head_sha: str
    delivery_id: str