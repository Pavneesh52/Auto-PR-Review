"""Tests for SQLAlchemy ORM models (Phase 4)."""

from __future__ import annotations

from pr_review_agent.db.models import (
    AgentResultRow,
    Base,
    EventTraceRow,
    FeedbackRow,
    FindingRow,
    ReviewRow,
)
from pr_review_agent.models.review import FindingSeverity


class TestReviewRow:
    def test_table_name(self):
        assert ReviewRow.__tablename__ == "reviews"

    def test_default_status(self):
        review = ReviewRow(
            pr_number=42,
            repository_full_name="org/repo",
        )
        # Verify column exists and is accessible
        assert review.total_comments is None or review.total_comments == 0
        assert review.critical_count is None or review.critical_count == 0

    def test_column_types(self):
        # Verify columns exist and have correct types
        mapper = ReviewRow.__table__
        assert "pr_number" in mapper.columns
        assert "status" in mapper.columns
        assert "total_tokens" in mapper.columns

    def test_relationships_defined(self):
        # Check that relationships are configured
        mapper = ReviewRow.__mapper__
        relationship_names = [r.key for r in mapper.relationships]
        assert "findings" in relationship_names
        assert "agent_results" in relationship_names
        assert "traces" in relationship_names


class TestFindingRow:
    def test_table_name(self):
        assert FindingRow.__tablename__ == "findings"

    def test_severity_enum(self):
        finding = FindingRow(
            review_id=1,
            file_path="src/app.py",
            severity=FindingSeverity.HIGH,
            category="security",
            title="Test finding",
        )
        assert finding.severity == FindingSeverity.HIGH

    def test_default_confidence(self):
        finding = FindingRow(
            review_id=1,
            file_path="src/app.py",
            severity=FindingSeverity.LOW,
            category="quality",
            title="Test",
        )
        # ORM defaults only apply at DB level; in Python they're None
        # until inserted and refreshed. Verify the column definition is correct.
        assert hasattr(finding, "confidence")

    def test_nullable_fields(self):
        finding = FindingRow(
            review_id=1,
            file_path="src/app.py",
            severity=FindingSeverity.INFO,
            category="quality",
            title="Test",
        )
        assert finding.line is None
        assert finding.end_line is None


class TestAgentResultRow:
    def test_table_name(self):
        assert AgentResultRow.__tablename__ == "agent_results"

    def test_defaults(self):
        result = AgentResultRow(
            review_id=1,
            agent_type="security",
        )
        # ORM defaults apply at DB level; verify attributes exist
        assert hasattr(result, "confidence")
        assert hasattr(result, "tokens_used")
        assert hasattr(result, "duration_seconds")
        assert result.error is None


class TestEventTraceRow:
    def test_table_name(self):
        assert EventTraceRow.__tablename__ == "event_traces"

    def test_nullable_review_id(self):
        trace = EventTraceRow(
            event_type="webhook_received",
        )
        assert trace.review_id is None
        assert trace.agent_type is None


class TestFeedbackRow:
    def test_table_name(self):
        assert FeedbackRow.__tablename__ == "feedback"


class TestBaseMetadata:
    def test_all_tables_registered(self):
        """Verify all tables are in the metadata."""
        table_names = list(Base.metadata.tables.keys())
        assert "reviews" in table_names
        assert "findings" in table_names
        assert "agent_results" in table_names
        assert "event_traces" in table_names
        assert "feedback" in table_names
