"""GitHub PR review comment poster.

Phase 13 - Formats review findings and posts them as GitHub PR review comments.
Supports summary mode, inline mode, and both.
"""

from __future__ import annotations

import httpx
import structlog

from pr_review_agent.config.settings import settings
from pr_review_agent.models.review import FindingSeverity, ReviewFinding

logger = structlog.get_logger(__name__)

# GitHub API base
GITHUB_API = "https://api.github.com"

# Severity to emoji mapping
SEVERITY_EMOJI = {
    FindingSeverity.CRITICAL: "🔴",
    FindingSeverity.HIGH: "🟠",
    FindingSeverity.MEDIUM: "🟡",
    FindingSeverity.LOW: "🔵",
    FindingSeverity.INFO: "⚪",
}


class GitHubCommentPoster:
    """Posts review findings to GitHub as PR review comments."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or settings.github_token
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=GITHUB_API,
                headers={
                    "Authorization": f"token {self.token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def post_review(
        self,
        repository_full_name: str,
        pr_number: int,
        head_sha: str,
        findings: list[ReviewFinding],
        summary: str,
        *,
        mode: str | None = None,
    ) -> int | None:
        """Post a PR review with inline comments and a summary.

        Args:
            repository_full_name: "owner/repo" format.
            pr_number: Pull request number.
            head_sha: HEAD commit SHA for the review.
            findings: List of review findings.
            summary: Overall review summary.
            mode: "summary", "inline", or "both". Defaults to settings.

        Returns:
            GitHub PR review ID, or None on failure.
        """
        if not self.token:
            logger.warning("github_token_not_configured")
            return None

        mode = mode or settings.github_comment_mode

        # Build the review body (summary)
        body = self._format_summary_body(findings, summary)

        # Determine review event
        has_critical = any(
            f.severity in (FindingSeverity.CRITICAL, FindingSeverity.HIGH) for f in findings
        )
        event = "REQUEST_CHANGES" if has_critical else "COMMENT"
        if not findings:
            event = "APPROVE"

        # Build inline comments
        comments = []
        if mode in ("inline", "both"):
            comments = self._build_inline_comments(findings)

        # Post the review
        payload: dict = {
            "commit_id": head_sha,
            "body": body,
            "event": event,
            "comments": comments,
        }

        try:
            response = await self.client.post(
                f"/repos/{repository_full_name}/pulls/{pr_number}/reviews",
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            review_id: int | None = data.get("id")
            logger.info(
                "github_review_posted",
                repo=repository_full_name,
                pr_number=pr_number,
                review_id=review_id,
                findings_count=len(findings),
                event=event,
            )
            return review_id

        except httpx.HTTPStatusError as e:
            logger.error(
                "github_review_post_failed",
                status=e.response.status_code,
                body=e.response.text[:500],
            )
            return None
        except Exception as e:
            logger.error("github_review_post_error", error=str(e))
            return None

    def _format_summary_body(self, findings: list[ReviewFinding], summary: str) -> str:
        """Format the review summary body with findings table."""
        parts = [f"## 🔍 AI Code Review\n\n{summary}\n"]

        if not findings:
            return "\n".join(parts)

        # Group findings by severity
        by_severity: dict[str, list[ReviewFinding]] = {}
        for f in findings:
            sev = f.severity.value
            by_severity.setdefault(sev, []).append(f)

        # Build findings table
        parts.append("\n### Findings\n")
        parts.append("| # | Severity | File | Title |")
        parts.append("|---|----------|------|-------|")

        for i, f in enumerate(findings, 1):
            emoji = SEVERITY_EMOJI.get(f.severity, "")
            parts.append(f"| {i} | {emoji} {f.severity.value} | `{f.file}` | {f.title} |")

        # Add detailed findings
        parts.append("\n### Details\n")

        for i, f in enumerate(findings, 1):
            emoji = SEVERITY_EMOJI.get(f.severity, "")
            line_ref = f" (line {f.line})" if f.line else ""
            parts.append(
                f"#### {i}. {emoji} {f.title}\n"
                f"**{f.severity.value}** in `{f.file}`{line_ref}\n\n"
                f"{f.description}\n"
            )
            if f.suggestion:
                parts.append(f"**Suggestion:** {f.suggestion}\n")
            parts.append(f"*Confidence: {f.confidence:.0%} | Agent: {f.source_agent}*\n")

        # Footer
        parts.append(
            "\n---\n"
            "*🤖 Automated review by [PR Review Agent](https://github.com) "
            f"({len(findings)} finding{'s' if len(findings) != 1 else ''})*"
        )

        return "\n".join(parts)

    def _build_inline_comments(self, findings: list[ReviewFinding]) -> list[dict]:
        """Build inline review comments for findings with line numbers."""
        comments = []
        for f in findings:
            if f.line is None or not f.file:
                continue

            body = (
                f"**{SEVERITY_EMOJI.get(f.severity, '')} {f.severity.value}**: "
                f"{f.title}\n\n"
                f"{f.description}\n"
            )
            if f.suggestion:
                body += f"\n> 💡 **Suggestion:** {f.suggestion}"

            comments.append(
                {
                    "path": f.file,
                    "line": f.line,
                    "body": body,
                }
            )

        return comments
