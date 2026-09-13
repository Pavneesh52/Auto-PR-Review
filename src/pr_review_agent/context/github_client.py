"""GitHub API client for fetching PR data.

Phase 3 - Context Assembly Engine.
Fetches diffs, file lists, and related files from the GitHub API.
"""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GitHubClient:
    """Async GitHub API client.

    Uses a personal access token or GitHub App installation token
    for authentication.
    """

    def __init__(self, token: str = "") -> None:
        self._token = token
        self._headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self._headers["Authorization"] = f"token {token}"

    async def get_pr_files(self, repo_full_name: str, pr_number: int) -> list[dict]:
        """Get the list of files changed in a PR."""
        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}/files"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers, params={"per_page": 100})
            resp.raise_for_status()
            data: list[dict] = resp.json()
            return data

    async def get_pr_diff(self, repo_full_name: str, pr_number: int) -> str:
        """Get the raw diff for a PR."""
        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={**self._headers, "Accept": "application/vnd.github.v3.diff"},
            )
            resp.raise_for_status()
            return resp.text

    async def get_file_content(
        self, repo_full_name: str, file_path: str, ref: str = "main"
    ) -> str | None:
        """Fetch the content of a single file at a specific ref."""
        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/contents/{file_path}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers, params={"ref": ref})
            if resp.status_code == 404:
                logger.warning("file_not_found", file=file_path, ref=ref)
                return None
            resp.raise_for_status()
            data = resp.json()
            # Content is base64 encoded
            import base64

            content = data.get("content", "")
            encoding = data.get("encoding", "")
            if encoding == "base64" and content:
                return base64.b64decode(content).decode("utf-8", errors="replace")
            return None

    async def get_tree_files(self, repo_full_name: str, ref: str = "main") -> list[str]:
        """Get all file paths in the repo tree at a given ref.

        Used for smart context selection — finding related files.
        """
        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/git/trees/{ref}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers, params={"recursive": "1"})
            if resp.status_code != 200:
                logger.warning("tree_fetch_failed", status=resp.status_code)
                return []
            data = resp.json()
            return [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]

    async def get_repo_info(self, repo_full_name: str) -> dict:
        """Get repository metadata."""
        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers)
            resp.raise_for_status()
            data: dict = resp.json()
            return data

    async def get_recent_commits(
        self, repo_full_name: str, ref: str = "main", count: int = 10
    ) -> list[dict]:
        """Get recent commits for a branch."""
        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/commits"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers=self._headers,
                params={"sha": ref, "per_page": count},
            )
            resp.raise_for_status()
            data: list[dict] = resp.json()
            return data
