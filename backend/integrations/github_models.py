from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime


class GitHubUser(BaseModel):
    login: str
    id: int
    avatar_url: str
    html_url: str


class GitHubRepository(BaseModel):
    id: int
    name: str
    full_name: str
    owner: GitHubUser
    private: bool
    html_url: str
    default_branch: str


class GitHubPullRequest(BaseModel):
    number: int
    title: str
    body: Optional[str] = None
    state: str
    html_url: str
    base: Dict[str, Any]
    head: Dict[str, Any]
    user: GitHubUser
    created_at: datetime
    updated_at: datetime


class GitHubWebhookPayload(BaseModel):
    action: str
    number: int
    pull_request: GitHubPullRequest
    repository: GitHubRepository
    sender: GitHubUser
    installation: Optional[Dict[str, Any]] = None


class GitHubReviewComment(BaseModel):
    path: str
    line: int
    side: str = "RIGHT"
    body: str


class GitHubReviewRequest(BaseModel):
    body: str
    event: str = "COMMENT"
    comments: List[GitHubReviewComment] = []


class GitHubReviewResponse(BaseModel):
    id: int
    state: str
    html_url: str