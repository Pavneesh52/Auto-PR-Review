"""Tests for synthesis: HITL threshold, cached findings, and real cost."""

from __future__ import annotations

from pr_review_agent.config.settings import settings
from pr_review_agent.models.review import (
    AgentResult,
    FindingSeverity,
    ReviewFinding,
)
from pr_review_agent.orchestrator.nodes import synthesize


def _finding(confidence: float, severity: FindingSeverity = FindingSeverity.HIGH) -> ReviewFinding:
    return ReviewFinding(
        file="app.py",
        line=1,
        severity=severity,
        category="security",
        title="Issue",
        description="desc",
        confidence=confidence,
    )


class TestHitlThreshold:
    def test_confident_findings_do_not_escalate(self):
        """Regression: a 0.7 default confidence used to escalate everything,
        which meant nothing was ever auto-posted to GitHub."""
        result = synthesize(
            {"security": AgentResult(agent_type="security", findings=[_finding(0.9)])}
        )
        assert result["should_escalate_to_hitl"] is False

    def test_confidence_exactly_at_threshold_does_not_escalate(self):
        result = synthesize(
            {
                "security": AgentResult(
                    agent_type="security",
                    findings=[_finding(settings.hitl_confidence_threshold)],
                )
            }
        )
        assert result["should_escalate_to_hitl"] is False

    def test_low_confidence_escalates(self):
        result = synthesize(
            {"security": AgentResult(agent_type="security", findings=[_finding(0.4)])}
        )
        assert result["should_escalate_to_hitl"] is True

    def test_no_findings_never_escalates(self):
        result = synthesize({"security": AgentResult(agent_type="security")})
        assert result["should_escalate_to_hitl"] is False


class TestCachedFindings:
    def test_cached_findings_are_merged(self):
        cached = _finding(0.9)
        result = synthesize({}, [cached])
        assert result["total_comments"] == 1
        assert cached in result["sorted_findings"]

    def test_cached_and_live_findings_are_deduplicated(self):
        duplicate = _finding(0.9)
        result = synthesize(
            {"security": AgentResult(agent_type="security", findings=[duplicate])},
            [duplicate],
        )
        assert result["total_comments"] == 1


class TestCostAccounting:
    def test_cost_derived_from_real_token_counts(self):
        result = synthesize(
            {
                "security": AgentResult(
                    agent_type="security",
                    tokens_used=1500,
                    prompt_tokens=1000,
                    completion_tokens=500,
                )
            }
        )
        assert result["total_tokens"] == 1500
        assert result["total_prompt_tokens"] == 1000
        assert result["total_completion_tokens"] == 500
        # 1000 input + 500 output tokens must cost strictly more than zero
        assert result["estimated_cost_usd"] > 0

    def test_no_tokens_costs_nothing(self):
        result = synthesize({"security": AgentResult(agent_type="security")})
        assert result["estimated_cost_usd"] == 0.0
