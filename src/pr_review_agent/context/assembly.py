"""Context Assembly Engine.

Phase 3 - Orchestrates the gathering of all context needed for a review.
Fetches PR metadata, diff, related files, and repo metadata, then
packages everything into a ReviewContext object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from pr_review_agent.config.settings import settings
from pr_review_agent.context.github_client import GitHubClient
from pr_review_agent.context.smart_context import detect_language, find_related_files
from pr_review_agent.models.events import WebhookEvent
from pr_review_agent.models.review import ChangedFile, RepoMetadata, ReviewContext

if TYPE_CHECKING:
    from pr_review_agent.context.embeddings import EmbeddingService

logger = structlog.get_logger(__name__)

# Cap the semantic query size so embedding requests stay cheap.
MAX_SEMANTIC_QUERY_CHARS = 4000


class ContextAssemblyError(Exception):
    """Raised when context assembly fails."""


class ContextAssembler:
    """Assembles review context from GitHub.

    This is the "brain" of Phase 3 — it knows what context
    a reviewer agent needs and efficiently gathers it.
    """

    def __init__(
        self,
        github_client: GitHubClient,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.github = github_client
        self.embeddings = embedding_service

    async def assemble(self, event: WebhookEvent) -> ReviewContext:
        """Assemble full review context for a PR.

        Steps:
        1. Fetch PR diff
        2. Parse changed files from the PR
        3. Get repo file tree for smart context selection
        4. Find related files via smart context selection
        5. Fetch context file contents
        6. Gather repo metadata
        7. Package into ReviewContext
        """
        repo = event.repository_full_name
        pr_number = event.pr_number

        logger.info("context_assembly_started", repo=repo, pr_number=pr_number)

        try:
            # Step 1: Fetch diff
            diff = await self.github.get_pr_diff(repo, pr_number)

            # Step 2: Parse changed files
            pr_files = await self.github.get_pr_files(repo, pr_number)
            changed_files = self._parse_changed_files(pr_files)

            # Step 3: Get repo file tree (for smart context)
            all_repo_files = await self.github.get_tree_files(
                repo, ref=event.pull_request.head_sha or "main"
            )

            # Step 4: Find related files
            context_file_paths = find_related_files(
                changed_files,
                all_repo_files,
                max_context_files=settings.context_file_limit,
            )

            # Step 4b: Augment with semantically similar files (Phase 10)
            semantic_paths = await self._semantic_context_paths(repo, changed_files)
            for path in semantic_paths:
                if path not in context_file_paths:
                    context_file_paths.append(path)
            context_file_paths = context_file_paths[: settings.context_file_limit]

            # Step 5: Fetch context file contents
            context_files: dict[str, str] = {}
            for path in context_file_paths:
                content = await self.github.get_file_content(
                    repo, path, ref=event.pull_request.head_sha or "main"
                )
                if content:
                    context_files[path] = content

            logger.info(
                "context_files_fetched",
                count=len(context_files),
                paths=list(context_files.keys())[:10],
            )

            # Step 6: Gather repo metadata
            repo_metadata = await self._gather_repo_metadata(repo)

            # Step 7: Package into ReviewContext
            ctx = ReviewContext(
                pr_number=pr_number,
                repository_full_name=repo,
                title=event.pull_request.title,
                body=event.pull_request.body,
                author=event.pull_request.author,
                base_branch=event.pull_request.base_branch,
                head_sha=event.pull_request.head_sha,
                diff=diff,
                changed_files=changed_files,
                total_additions=sum(f.additions for f in changed_files),
                total_deletions=sum(f.deletions for f in changed_files),
                context_files=context_files,
                repo_metadata=repo_metadata,
            )

            logger.info(
                "context_assembly_completed",
                repo=repo,
                pr_number=pr_number,
                files_changed=len(changed_files),
                context_files=len(context_files),
                is_large_pr=ctx.is_large_pr,
            )

            return ctx

        except Exception as e:
            logger.error(
                "context_assembly_failed",
                repo=repo,
                pr_number=pr_number,
                error=str(e),
            )
            raise ContextAssemblyError(
                f"Failed to assemble context for {repo}#{pr_number}: {e}"
            ) from e

    async def _semantic_context_paths(
        self, repo: str, changed_files: list[ChangedFile]
    ) -> list[str]:
        """Find related files by meaning, using the Phase 10 embeddings.

        This complements the heuristic import/test/sibling selection: it can
        surface files that are conceptually related without a direct import.
        Any failure (no embeddings indexed, no API key, DB down) degrades to
        an empty list rather than failing the review.
        """
        if not settings.semantic_search_enabled or self.embeddings is None:
            return []

        try:
            from pr_review_agent.db.connection import get_session_factory
            from pr_review_agent.db.repositories import ReviewRepository

            session_factory = get_session_factory()
            async with session_factory() as session:
                repository = ReviewRepository(session)
                if await repository.count_embeddings(repo) == 0:
                    logger.info("semantic_search_skipped", repo=repo, reason="not_indexed")
                    return []

                query = self._build_semantic_query(changed_files)
                if not query:
                    return []

                embedding = await self.embeddings.generate_embedding(query)
                if not embedding:
                    return []

                matches = await repository.semantic_search(
                    repository_full_name=repo,
                    query_embedding=embedding,
                    limit=settings.semantic_search_limit,
                )

            changed_paths = {f.path for f in changed_files}
            return [path for path in matches if path not in changed_paths]

        except Exception as e:
            logger.warning("semantic_search_failed", repo=repo, error=str(e))
            return []

    @staticmethod
    def _build_semantic_query(changed_files: list[ChangedFile]) -> str:
        """Build the text used to look up semantically similar files."""
        parts: list[str] = []
        for changed_file in changed_files:
            parts.append(f"# {changed_file.path}\n{changed_file.patch}")
        return "\n".join(parts)[:MAX_SEMANTIC_QUERY_CHARS]

    def _parse_changed_files(self, pr_files: list[dict]) -> list[ChangedFile]:
        """Parse GitHub API file list into our ChangedFile model."""
        changed = []
        for f in pr_files:
            file = ChangedFile(
                path=f.get("filename", ""),
                status=f.get("status", "modified"),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
                patch=f.get("patch", ""),
                language=detect_language(f.get("filename", "")),
            )
            # Skip binary/lock files
            if file.language in ("json", "yaml") and file.path.endswith(
                (".lock", "package-lock.json", "yarn.lock", "poetry.lock")
            ):
                continue
            changed.append(file)
        return changed

    async def _gather_repo_metadata(self, repo: str) -> RepoMetadata:
        """Gather repository-level metadata."""
        try:
            repo_info = await self.github.get_repo_info(repo)
            recent_commits = await self.github.get_recent_commits(repo)

            return RepoMetadata(
                default_branch=repo_info.get("default_branch", "main"),
                languages=repo_info.get("languages", {}),
                recent_commits=[
                    {
                        "sha": c.get("sha", "")[:8],
                        "message": c.get("commit", {}).get("message", "").split("\n")[0],
                        "author": c.get("commit", {}).get("author", {}).get("name", ""),
                    }
                    for c in recent_commits[:10]
                ],
            )
        except Exception as e:
            logger.warning("repo_metadata_fetch_failed", repo=repo, error=str(e))
            return RepoMetadata()
