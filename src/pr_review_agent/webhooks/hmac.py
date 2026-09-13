"""HMAC signature verification for GitHub webhooks.

Verifies the X-Hub-Signature-256 header to ensure the payload
originated from GitHub and hasn't been tampered with.
"""

from __future__ import annotations

import hashlib
import hmac

from pr_review_agent.config.settings import settings


class HMACVerificationError(Exception):
    """Raised when HMAC signature verification fails."""


def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    """Verify the GitHub webhook HMAC-SHA256 signature.

    Args:
        payload_body: Raw request body bytes.
        signature_header: Value of X-Hub-Signature-256 header.

    Returns:
        True if signature is valid.

    Raises:
        HMACVerificationError: If signature is missing or invalid.
    """
    if not settings.github_webhook_secret:
        # No secret configured — skip verification (dev mode only)
        return True

    if not signature_header:
        raise HMACVerificationError("Missing X-Hub-Signature-256 header")

    if not signature_header.startswith("sha256="):
        raise HMACVerificationError("Invalid signature format (expected sha256=...)")

    expected_signature = (
        "sha256="
        + hmac.new(
            key=settings.github_webhook_secret.encode("utf-8"),
            msg=payload_body,
            digestmod=hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(expected_signature, signature_header):
        raise HMACVerificationError("HMAC signature mismatch")

    return True
