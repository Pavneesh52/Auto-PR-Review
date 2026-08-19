import hmac
import hashlib
from typing import Optional
from backend.config import settings
from backend.core.exceptions import WebhookValidationError
from backend.observability import get_logger

logger = get_logger(__name__)


def verify_github_signature(payload: bytes, signature: str) -> bool:
    if not signature.startswith("sha256="):
        return False
    
    expected_sig = signature[7:]
    computed_sig = hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(computed_sig, expected_sig)


async def validate_webhook(payload: bytes, signature: str, delivery_id: str) -> bool:
    if not verify_github_signature(payload, signature):
        logger.warning("webhook_signature_invalid", delivery_id=delivery_id)
        raise WebhookValidationError(
            "Invalid GitHub webhook signature",
            {"delivery_id": delivery_id},
        )
    
    return True