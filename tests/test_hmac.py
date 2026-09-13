"""Tests for HMAC signature verification."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pr_review_agent.webhooks.hmac import HMACVerificationError, verify_github_signature


class TestHMACVerification:
    def test_valid_signature_passes(self):
        payload = b'{"action": "opened"}'
        secret = "test-secret"

        import hashlib
        import hmac as hmac_mod

        sig = (
            "sha256="
            + hmac_mod.new(
                key=secret.encode("utf-8"),
                msg=payload,
                digestmod=hashlib.sha256,
            ).hexdigest()
        )

        with patch("pr_review_agent.webhooks.hmac.settings") as mock_settings:
            mock_settings.github_webhook_secret = secret
            assert verify_github_signature(payload, sig) is True

    def test_invalid_signature_raises(self):
        payload = b'{"action": "opened"}'
        with patch("pr_review_agent.webhooks.hmac.settings") as mock_settings:
            mock_settings.github_webhook_secret = "test-secret"
            with pytest.raises(HMACVerificationError, match="mismatch"):
                verify_github_signature(payload, "sha256=wrong_signature_here")

    def test_missing_signature_header_raises(self):
        with patch("pr_review_agent.webhooks.hmac.settings") as mock_settings:
            mock_settings.github_webhook_secret = "test-secret"
            with pytest.raises(HMACVerificationError, match="Missing"):
                verify_github_signature(b"body", "")

    def test_invalid_format_raises(self):
        with patch("pr_review_agent.webhooks.hmac.settings") as mock_settings:
            mock_settings.github_webhook_secret = "test-secret"
            with pytest.raises(HMACVerificationError, match="format"):
                verify_github_signature(b"body", "not-a-signature")

    def test_no_secret_skips_verification(self):
        with patch("pr_review_agent.webhooks.hmac.settings") as mock_settings:
            mock_settings.github_webhook_secret = ""
            assert verify_github_signature(b"anything", "sha256=fake") is True
