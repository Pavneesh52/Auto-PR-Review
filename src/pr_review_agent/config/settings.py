"""Application settings.

Loaded from .env file via pydantic-settings.
Each phase adds its own section as the system grows.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # ── Phase 1: Data Models ───────────────────────────────────────────

    # ── Phase 2: Webhook Ingestion ─────────────────────────────────────
    github_webhook_secret: str = ""
    github_app_id: int = 0
    github_private_key_path: str = ""

    # ── Phase 2: Redis ─────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Phase 4: Database ──────────────────────────────────────────────
    # Port 5433 matches docker-compose: 5432 is commonly taken by a native
    # Postgres install. Override with DATABASE_URL / DATABASE_URL_SYNC.
    database_url: str = (
        "postgresql+asyncpg://pr_agent:pr_agent_secret@localhost:5433/pr_review_agent"
    )
    database_url_sync: str = "postgresql://pr_agent:pr_agent_secret@localhost:5433/pr_review_agent"

    # ── Phase 6-9: LLM Agents ─────────────────────────────────────────
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    # ── Phase 10: Semantic Search ──────────────────────────────────────
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    semantic_search_enabled: bool = True
    semantic_search_limit: int = 5

    # ── Phase 13: GitHub Comment Posting ───────────────────────────────
    github_token: str = ""  # PAT or App installation token
    github_comment_mode: str = "summary"  # "summary" | "inline" | "both"

    # ── Phase 14: Caching ──────────────────────────────────────────────
    cache_enabled: bool = True
    cache_ttl_seconds: int = 86400  # 24 hours

    # ── Phase 17: Rate Limiting & Cost Control ─────────────────────────
    rate_limit_per_minute: int = 30  # reviews per minute (global)
    rate_limit_per_repo_per_hour: int = 10  # reviews per repo per hour
    max_cost_per_review_usd: float = 0.50  # hard cap per review
    max_tokens_per_review: int = 50000  # hard cap per review
    max_tokens_per_repo_per_day: int = 500000  # rolling daily budget per repo

    # ── Phase 12: HITL Gate ────────────────────────────────────────────
    # Findings with confidence below this pause the review for approval.
    hitl_confidence_threshold: float = 0.7

    # ── Phase 17: LLM pricing (USD per 1M tokens) ──────────────────────
    # Defaults are gpt-4o-mini list prices; used for real cost tracking.
    llm_price_per_1m_input_tokens: float = 0.15
    llm_price_per_1m_output_tokens: float = 0.60

    # ── Phase 18: Monitoring ───────────────────────────────────────────
    metrics_enabled: bool = True

    # ── App ────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # ── Review Limits ──────────────────────────────────────────────────
    max_comments_per_pr: int = 10
    context_file_limit: int = 20
    large_pr_threshold: int = 500  # lines changed


settings = Settings()
