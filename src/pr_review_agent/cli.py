"""CLI entry point.

Commands:
    serve                 Run the webhook server (default).
    index owner/repo      Embed a repository's files for semantic search.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from pr_review_agent.config.settings import settings
from pr_review_agent.context.embeddings import EmbeddingService
from pr_review_agent.context.github_client import GitHubClient
from pr_review_agent.context.smart_context import detect_language

logger = structlog.get_logger(__name__)

# Files we never bother embedding: locks, minified bundles, vendored blobs.
SKIP_SUFFIXES = (
    ".lock",
    "-lock.json",
    ".min.js",
    ".min.css",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".zip",
    ".woff",
    ".woff2",
)
SKIP_PATH_PARTS = ("node_modules/", "vendor/", "dist/", "build/", ".min.")


def _should_index(path: str) -> bool:
    """Whether a repo path is worth embedding."""
    if path.endswith(SKIP_SUFFIXES):
        return False
    if any(part in path for part in SKIP_PATH_PARTS):
        return False
    if detect_language(path) == "unknown":
        return False
    return True


async def _index_repo(repo: str, ref: str, max_files: int) -> int:
    """Embed a repository's files into the code_embeddings table.

    Returns the number of files indexed.
    """
    from pr_review_agent.db.connection import get_session_factory
    from pr_review_agent.db.repositories import ReviewRepository

    github = GitHubClient(token=settings.github_token)
    embeddings = EmbeddingService()

    if not settings.openai_api_key:
        logger.error("index_failed", reason="OPENAI_API_KEY is not configured")
        return 1

    try:
        target_ref = ref
        if not target_ref:
            info = await github.get_repo_info(repo)
            target_ref = info.get("default_branch", "main")

        all_files = await github.get_tree_files(repo, ref=target_ref)
        candidates = [p for p in all_files if _should_index(p)][:max_files]
        logger.info(
            "index_candidates",
            repo=repo,
            ref=target_ref,
            total_files=len(all_files),
            to_index=len(candidates),
        )

        session_factory = get_session_factory()
        indexed = 0

        async with session_factory() as session:
            repository = ReviewRepository(session)

            for path in candidates:
                content = await github.get_file_content(repo, path, ref=target_ref)
                if not content:
                    continue

                chunks = embeddings.chunk_code(content, path)
                vectors = await embeddings.generate_embeddings_batch([chunk for chunk, _ in chunks])
                vectors = [v for v in vectors if v]
                if not vectors:
                    continue

                await repository.replace_embeddings(
                    repository_full_name=repo,
                    file_path=path,
                    content_hash=embeddings.content_hash(content),
                    chunks=vectors,
                    language=detect_language(path),
                )
                indexed += 1

            await session.commit()

        logger.info("index_complete", repo=repo, files_indexed=indexed)
        return 0

    except Exception as e:
        logger.error("index_failed", repo=repo, error=str(e))
        return 1
    finally:
        await embeddings.close()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="pr-review-agent",
        description="AI PR review agent",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Run the webhook server (default)")

    index_parser = subparsers.add_parser(
        "index", help="Embed a repository for semantic code search (Phase 10)"
    )
    index_parser.add_argument("repo", help="Repository in owner/name form")
    index_parser.add_argument(
        "--ref", default="", help="Git ref to index (defaults to the default branch)"
    )
    index_parser.add_argument("--max-files", type=int, default=200, help="Maximum files to index")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI dispatch. Returns the process exit code."""
    args = _parse_args(argv)

    if args.command == "index":
        return asyncio.run(_index_repo(args.repo, args.ref, args.max_files))

    # Default: run the server
    from pr_review_agent.app import main as serve_main

    serve_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
