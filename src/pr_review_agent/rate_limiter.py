"""Rate limiting and cost control.

Phase 17 - Redis-based sliding window rate limiter.
Controls both request rate and LLM token/cost budgets.
"""

from __future__ import annotations

import time
from datetime import date

import redis.asyncio as redis
import structlog

from pr_review_agent.config.settings import settings

logger = structlog.get_logger(__name__)


class RateLimiter:
    """Redis-based sliding window rate limiter.

    Checks two limits:
    1. Global request rate (reviews per minute)
    2. Per-repo rate (reviews per repo per hour)
    """

    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client

    async def check_rate_limit(self, repository_full_name: str) -> tuple[bool, str]:
        """Check if a new review is allowed under rate limits.

        Returns:
            (allowed, reason) — reason is empty if allowed.
        """
        # 1. Check global rate
        global_key = f"pr-review:ratelimit:global:{int(time.time() // 60)}"
        global_count = await self._redis.incr(global_key)
        await self._redis.expire(global_key, 120)  # 2 min TTL

        if global_count > settings.rate_limit_per_minute:
            logger.warning(
                "global_rate_limit_exceeded",
                count=global_count,
                limit=settings.rate_limit_per_minute,
            )
            return False, f"Global rate limit exceeded ({settings.rate_limit_per_minute}/min)"

        # 2. Check per-repo rate
        repo_key = f"pr-review:ratelimit:repo:{repository_full_name}:{int(time.time() // 3600)}"
        repo_count = await self._redis.incr(repo_key)
        await self._redis.expire(repo_key, 7200)  # 2 hour TTL

        if repo_count > settings.rate_limit_per_repo_per_hour:
            logger.warning(
                "repo_rate_limit_exceeded",
                repo=repository_full_name,
                count=repo_count,
                limit=settings.rate_limit_per_repo_per_hour,
            )
            return False, (
                f"Rate limit for {repository_full_name} exceeded "
                f"({settings.rate_limit_per_repo_per_hour}/hour)"
            )

        return True, ""

    async def check_cost_budget(
        self,
        tokens_used: int,
        estimated_cost_usd: float,
    ) -> tuple[bool, str]:
        """Check if the token/cost budget is within limits.

        Returns:
            (allowed, reason) — reason is empty if allowed.
        """
        if tokens_used > settings.max_tokens_per_review:
            return (
                False,
                f"Token limit exceeded ({tokens_used}/{settings.max_tokens_per_review})",
            )

        if estimated_cost_usd > settings.max_cost_per_review_usd:
            return (
                False,
                f"Cost limit exceeded "
                f"(${estimated_cost_usd:.4f}/${settings.max_cost_per_review_usd:.2f})",
            )

        return True, ""

    # ── Daily token budget (pre-flight) ───────────────────────────────

    @staticmethod
    def _budget_key(repository_full_name: str) -> str:
        """Redis key for today's token spend for a repository."""
        return f"pr-review:budget:tokens:{repository_full_name}:{date.today().isoformat()}"

    async def get_daily_token_usage(self, repository_full_name: str) -> int:
        """Return tokens spent on this repository today."""
        raw = await self._redis.get(self._budget_key(repository_full_name))
        return int(raw) if raw else 0

    async def check_daily_budget(self, repository_full_name: str) -> tuple[bool, str]:
        """Pre-flight budget check, run *before* spending on LLM calls.

        This is what makes the Phase 17 cost cap real: a post-hoc check
        after the tokens are already burned cannot prevent overspend.
        """
        used = await self.get_daily_token_usage(repository_full_name)
        if used >= settings.max_tokens_per_repo_per_day:
            return (
                False,
                f"Daily token budget exceeded for {repository_full_name} "
                f"({used}/{settings.max_tokens_per_repo_per_day})",
            )
        return True, ""

    async def record_token_spend(self, repository_full_name: str, tokens: int) -> int:
        """Add to today's token spend for a repository. Returns the new total."""
        if tokens <= 0:
            return await self.get_daily_token_usage(repository_full_name)

        key = self._budget_key(repository_full_name)
        total = await self._redis.incrby(key, tokens)
        await self._redis.expire(key, 172800)  # 2 days, so yesterday's key expires
        return int(total)

    async def get_usage_stats(self) -> dict:
        """Get current rate limit usage statistics."""
        now = int(time.time())
        minute_key = f"pr-review:ratelimit:global:{now // 60}"

        global_count = await self._redis.get(minute_key)
        global_count = int(global_count) if global_count else 0

        return {
            "global_requests_this_minute": global_count,
            "global_limit": settings.rate_limit_per_minute,
            "global_remaining": max(0, settings.rate_limit_per_minute - global_count),
            "daily_token_budget_limit": settings.max_tokens_per_repo_per_day,
        }
