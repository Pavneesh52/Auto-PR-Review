"""Tests for review domain models."""

from __future__ import annotations

from pr_review_agent.models.review import (
    FindingSeverity,
    ReviewContext,
    ReviewFinding,
    ReviewResult,
    ReviewStatus,
)


class TestReviewContext:
    def test_is_large_pr(self):
        ctx = ReviewContext(
            pr_number=1,
            repository_full_name="org/repo",
            total_additions=300,
            total_deletions=250,
        )
        assert ctx.is_large_pr is True

    def test_small_pr(self):
        ctx = ReviewContext(
            pr_number=1,
            repository_full_name="org/repo",
            total_additions=10,
            total_deletions=5,
        )
        assert ctx.is_large_pr is False


class TestReviewFinding:
    def test_severity_levels(self):
        assert FindingSeverity.CRITICAL.value == "CRITICAL"
        assert FindingSeverity.HIGH.value == "HIGH"
        assert FindingSeverity.MEDIUM.value == "MEDIUM"
        assert FindingSeverity.LOW.value == "LOW"

    def test_finding_creation(self):
        finding = ReviewFinding(
            file="src/auth.py",
            line=42,
            severity=FindingSeverity.HIGH,
            category="security",
            title="SQL Injection vulnerability",
            description="User input is directly interpolated into SQL query.",
            suggestion="Use parameterized queries.",
            confidence=0.95,
            source_agent="security",
        )
        assert finding.severity == FindingSeverity.HIGH
        assert finding.confidence == 0.95


class TestReviewResult:
    def test_default_status_is_pending(self):
        result = ReviewResult(
            pr_number=1,
            repository_full_name="org/repo",
        )
        assert result.status == ReviewStatus.PENDING

    def test_counts(self):
        result = ReviewResult(
            pr_number=1,
            repository_full_name="org/repo",
            critical_count=1,
            high_count=3,
            medium_count=5,
            low_count=2,
        )
        total = result.critical_count + result.high_count + result.medium_count + result.low_count
        assert total == 11
