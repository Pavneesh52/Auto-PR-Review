import json
from typing import Dict, Any, Optional
from backend.integrations.github_models import GitHubWebhookPayload
from backend.models.webhook import ReviewJob
from backend.integrations.github_client import github_client
from backend.observability import get_logger

logger = get_logger(__name__)


def parse_webhook_payload(payload: Dict[str, Any]) -> GitHubWebhookPayload:
    return GitHubWebhookPayload(**payload)


async def extract_review_job(webhook: GitHubWebhookPayload) -> Optional[ReviewJob]:
    if webhook.action not in ("opened", "synchronize", "reopened"):
        logger.info("webhook_action_ignored", action=webhook.action)
        return None
    
    installation_id = None
    if webhook.installation:
        installation_id = webhook.installation.get("id")
    
    if not installation_id:
        logger.warning("webhook_missing_installation", repo=webhook.repository.full_name)
        return None
    
    pr = webhook.pull_request
    
    diff = await github_client.get_pr_diff(
        installation_id,
        webhook.repository.full_name,
        webhook.number,
    )
    
    if not diff:
        logger.warning("webhook_empty_diff", repo=webhook.repository.full_name, pr=webhook.number)
        return None
    
    return ReviewJob(
        review_id="",
        repo=webhook.repository.full_name,
        pr_number=webhook.number,
        pr_title=pr.title,
        pr_body=pr.body,
        diff=diff,
        base_sha=pr.base.get("sha", ""),
        head_sha=pr.head.get("sha", ""),
        delivery_id="",
    )