"""Tests for the LLM client's token/cost plumbing."""

from __future__ import annotations

from pr_review_agent.config.settings import settings
from pr_review_agent.context.llm_client import (
    LLMCallResult,
    call_llm,
    estimate_cost_usd,
)


class TestEstimateCost:
    def test_zero_tokens_is_free(self):
        assert estimate_cost_usd(0, 0) == 0.0

    def test_output_costs_more_than_input(self):
        input_cost = estimate_cost_usd(1_000_000, 0)
        output_cost = estimate_cost_usd(0, 1_000_000)
        assert output_cost > input_cost

    def test_matches_configured_pricing(self):
        expected = settings.llm_price_per_1m_input_tokens
        assert estimate_cost_usd(1_000_000, 0) == expected


class TestCallLlmWithoutCredentials:
    async def test_returns_result_not_exception(self):
        """A missing API key must degrade to an empty result, not crash the review."""
        result = await call_llm(system_prompt="sys", user_message="hello")
        assert isinstance(result, LLMCallResult)
        assert result.data is None
        assert result.error is not None
        assert result.total_tokens == 0


class TestLLMCallResult:
    def test_total_tokens_sums_both_directions(self):
        result = LLMCallResult(prompt_tokens=10, completion_tokens=5)
        assert result.total_tokens == 15

    def test_defaults_are_empty(self):
        result = LLMCallResult()
        assert result.findings == []
        assert result.total_tokens == 0
