"""Tests for Redis event queue with idempotency."""

from __future__ import annotations

import pytest

from pr_review_agent.queue.event_queue import EventQueue


@pytest.fixture
async def event_queue(redis_client):
    """Create an EventQueue connected to the test Redis."""
    queue = EventQueue(redis_url="redis://localhost:6379/1")
    queue._redis = redis_client  # Use the test Redis client directly
    yield queue


class TestEventQueue:
    async def test_enqueue_and_dequeue(self, event_queue):
        payload = {"pr_number": 42, "action": "opened"}

        enqueued = await event_queue.enqueue(
            event_type="pr_opened",
            payload=payload,
            delivery_id="delivery-001",
        )
        assert enqueued is True

        event = await event_queue.dequeue_non_blocking()
        assert event is not None
        assert event["type"] == "pr_opened"
        assert event["payload"]["pr_number"] == 42

    async def test_duplicate_delivery_id_is_rejected(self, event_queue):
        payload = {"pr_number": 42}

        # First enqueue succeeds
        result1 = await event_queue.enqueue(
            event_type="pr_opened",
            payload=payload,
            delivery_id="delivery-002",
        )
        assert result1 is True

        # Duplicate is rejected
        result2 = await event_queue.enqueue(
            event_type="pr_opened",
            payload=payload,
            delivery_id="delivery-002",
        )
        assert result2 is False

        # Only one event in queue
        assert await event_queue.queue_length() == 1

    async def test_queue_length(self, event_queue):
        assert await event_queue.queue_length() == 0

        await event_queue.enqueue("pr_opened", {}, "d1")
        await event_queue.enqueue("pr_synchronize", {}, "d2")

        assert await event_queue.queue_length() == 2

    async def test_fifo_ordering(self, event_queue):
        await event_queue.enqueue("pr_opened", {"seq": 1}, "d1")
        await event_queue.enqueue("pr_synchronize", {"seq": 2}, "d2")
        await event_queue.enqueue("pr_opened", {"seq": 3}, "d3")

        e1 = await event_queue.dequeue_non_blocking()
        e2 = await event_queue.dequeue_non_blocking()
        e3 = await event_queue.dequeue_non_blocking()

        assert e1["payload"]["seq"] == 1
        assert e2["payload"]["seq"] == 2
        assert e3["payload"]["seq"] == 3

    async def test_dequeue_empty_returns_none(self, event_queue):
        result = await event_queue.dequeue_non_blocking()
        assert result is None

    async def test_mark_processing_and_completed(self, event_queue):
        await event_queue.mark_processing("evt-001")
        # Processing marker should exist
        key = "pr-review:processing:evt-001"
        assert await event_queue._redis.exists(key)

        await event_queue.mark_completed("evt-001")
        assert not await event_queue._redis.exists(key)
