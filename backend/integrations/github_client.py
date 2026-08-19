from typing import List, Dict, Any, Optional
from github import Github, GithubIntegration
from github.GithubException import GithubException
from backend.config import settings
from backend.reliability import with_timeout, TimeoutConfig, retry_with_backoff
from backend.observability import get_logger

logger = get_logger(__name__)


class GitHubClient:
    def __init__(self):
        self.app_id = settings.github_app_id
        self.private_key_path = settings.github_private_key_path
        self._integration = None
        self._installation_clients = {}

    def get_integration(self) -> GithubIntegration:
        if self._integration is None:
            with open(self.private_key_path, "r") as f:
                private_key = f.read()
            self._integration = GithubIntegration(self.app_id, private_key)
        return self._integration

    def get_installation_client(self, installation_id: int) -> Github:
        if installation_id not in self._installation_clients:
            integration = self.get_integration()
            token = integration.get_access_token(installation_id).token
            self._installation_clients[installation_id] = Github(token)
        return self._installation_clients[installation_id]

    @retry_with_backoff(max_attempts=3, exceptions=(GithubException,))
    async def post_review(
        self,
        installation_id: int,
        repo_full_name: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
        comments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        client = self.get_installation_client(installation_id)
        repo = client.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        
        review = await with_timeout(
            lambda: pr.create_review(body=body, event=event, comments=comments or []),
            timeout=TimeoutConfig.GITHUB_API,
            operation="github_post_review",
        )
        
        return {
            "id": review.id,
            "state": review.state,
            "html_url": review.html_url,
        }

    @retry_with_backoff(max_attempts=3, exceptions=(GithubException,))
    async def get_pr_diff(
        self,
        installation_id: int,
        repo_full_name: str,
        pr_number: int,
    ) -> str:
        client = self.get_installation_client(installation_id)
        repo = client.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        
        files = await with_timeout(
            lambda: list(pr.get_files()),
            timeout=TimeoutConfig.GITHUB_API,
            operation="github_get_pr_files",
        )
        
        diff_parts = []
        for file in files:
            if file.patch:
                diff_parts.append(f"--- a/{file.filename}\n+++ b/{file.filename}\n{file.patch}")
        
        return "\n".join(diff_parts)

    @retry_with_backoff(max_attempts=3, exceptions=(GithubException,))
    async def get_pr_info(
        self,
        installation_id: int,
        repo_full_name: str,
        pr_number: int,
    ) -> Dict[str, Any]:
        client = self.get_installation_client(installation_id)
        repo = client.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        
        return {
            "title": pr.title,
            "body": pr.body,
            "base_sha": pr.base.sha,
            "head_sha": pr.head.sha,
            "repo": repo_full_name,
            "pr_number": pr_number,
        }

    @retry_with_backoff(max_attempts=3, exceptions=(GithubException,))
    async def get_file_content(
        self,
        installation_id: int,
        repo_full_name: str,
        file_path: str,
        ref: str,
    ) -> Optional[str]:
        client = self.get_installation_client(installation_id)
        repo = client.get_repo(repo_full_name)
        
        try:
            content = await with_timeout(
                lambda: repo.get_contents(file_path, ref=ref),
                timeout=TimeoutConfig.GITHUB_API,
                operation="github_get_file_content",
            )
            return content.decoded_content.decode("utf-8")
        except GithubException:
            return None


github_client = GitHubClient()