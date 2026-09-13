"""Redis-backed event queue with idempotency deduplication.

Phase 2 - Decouples webhook receipt from processing.
Each event is deduplicated by delivery_id to prevent duplicate processing.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import redis.asyncio as redis

from pr_review_agent.config.settings import settings

# Queue and dedup key prefixes
QUEUE_KEY = "pr-review:pending"
DEDUP_PREFIX = "pr-review:dedup:"
DEDUP_TTL_SECONDS = 3600  # 1 hour — delivery IDs are unique per run


class EventQueue:
    """Redis-backed queue with idempotency guarantees.

    Guarantees:
    - At-most-once delivery per delivery_id
    - FIFO ordering within a single Redis instance
    - Automatic dedup key expiry (no memory leaks)
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or settings.redis_url
        self._redis: redis.Redis | None = None

    async def connect(self) -> None:
        """Establish Redis connection.

        Only stores the client once the connection is proven live, so
        `is_connected` never reports a dead connection as usable.
        """
        client = redis.from_url(self._redis_url, decode_responses=True)
        try:
            await client.ping()
        except Exception:
            await client.aclose()
            self._redis = None
            raise
        self._redis = client

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    @property
    def is_connected(self) -> bool:
        """Whether the Redis connection has been established."""
        return self._redis is not None

    @property
    def _client(self) -> redis.Redis:
        if self._redis is None:
            raise RuntimeError("EventQueue not connected. Call connect() first.")
        return self._redis

    @property
    def client(self) -> redis.Redis:
        """Public access to the Redis client for reuse by other components."""
        return self._client

    async def enqueue(
        self,
        event_type: str,
        payload: dict,
        delivery_id: str = "",
    ) -> bool:
        """Enqueue an event with idempotency check.

        Args:
            event_type: Event category (e.g., "pr_opened", "pr_synchronized").
            payload: The parsed webhook event data.
            delivery_id: GitHub delivery ID for deduplication.

        Returns:
            True if enqueued, False if duplicate (already processed or queued).
        """
        dedup_key = f"{DEDUP_PREFIX}{delivery_id or uuid.uuid4().hex}"

        # Atomic: check-and-set dedup key.
        # redis-py's async command signatures resolve to `Awaitable[T] | T`,
        # which mypy can't narrow, so we go through an Any-typed local.
        client: Any = self._client
        is_new = await client.set(dedup_key, "1", nx=True, ex=DEDUP_TTL_SECONDS)
        if not is_new:
            return False  # Duplicate — skip

        event = {
            "id": delivery_id or uuid.uuid4().hex,
            "type": event_type,
            "payload": payload,
        }
        await client.rpush(QUEUE_KEY, json.dumps(event))
        return True

    async def dequeue(self, timeout: int = 5) -> dict | None:
        """Blocking dequeue from the pending queue.

        Uses BLPOP for efficient blocking without polling.

        Returns:
            Parsed event dict, or None on timeout or invalid JSON.
        """
        client: Any = self._client
        result = await client.blpop([QUEUE_KEY], timeout=timeout)
        if result is None:
            return None
        _, raw = result
        try:
            event: dict = json.loads(raw)
            return event
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    async def dequeue_non_blocking(self) -> dict | None:
        """Non-blocking dequeue.

        Returns:
            Parsed event dict, or None if queue is empty or payload is invalid.
        """
        client: Any = self._client
        raw = await client.lpop(QUEUE_KEY)
        if raw is None:
            return None
        try:
            event: dict = json.loads(raw)
            return event
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    async def queue_length(self) -> int:
        """Return current queue depth."""
        client: Any = self._client
        return int(await client.llen(QUEUE_KEY))

    async def mark_processing(self, event_id: str) -> None:
        """Mark an event as currently being processed."""
        key = f"pr-review:processing:{event_id}"
        await self._client.set(key, "1", ex=600)  # 10 min TTL

    async def mark_completed(self, event_id: str) -> None:
        """Mark an event as completed and remove processing marker."""
        key = f"pr-review:processing:{event_id}"
        await self._client.delete(key)
