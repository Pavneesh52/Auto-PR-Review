from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, JSON, Numeric, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID as PGUUID, TSVECTOR
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import uuid
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class PRReviewRecord(Base):
    __tablename__ = "pr_review_records"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo = Column(String(255), nullable=False, index=True)
    pr_number = Column(Integer, nullable=False, index=True)
    pr_title = Column(String(500), nullable=False)
    pr_body = Column(Text, nullable=True)
    diff = Column(Text, nullable=False)
    base_sha = Column(String(64), nullable=False)
    head_sha = Column(String(64), nullable=False)
    overall_confidence = Column(Numeric(4, 3), default=0.0)
    outcome = Column(String(50), nullable=True)
    hitl_required = Column(Boolean, default=False)
    github_review_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    findings = relationship("FindingRecord", back_populates="review", cascade="all, delete-orphan")
    hitl_reviews = relationship("HITLReviewRecord", back_populates="review", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_pr_review_records_repo_pr", "repo", "pr_number", unique=True),
    )


class FindingRecord(Base):
    __tablename__ = "finding_records"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(PGUUID(as_uuid=True), ForeignKey("pr_review_records.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    category = Column(String(50), nullable=False)
    summary = Column(Text, nullable=False)
    file_path = Column(String(500), nullable=False)
    line_start = Column(Integer, nullable=False)
    line_end = Column(Integer, nullable=True)
    suggestion = Column(Text, nullable=False)
    confidence = Column(Numeric(4, 3), nullable=False)
    rationale = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    review = relationship("PRReviewRecord", back_populates="findings")


class HITLReviewRecord(Base):
    __tablename__ = "hitl_reviews"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(PGUUID(as_uuid=True), ForeignKey("pr_review_records.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), default="pending")
    reviewer_id = Column(String(255), nullable=True)
    decision = Column(String(50), nullable=True)
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    review = relationship("PRReviewRecord", back_populates="hitl_reviews")


class HITLFeedbackRecord(Base):
    __tablename__ = "hitl_feedback"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(PGUUID(as_uuid=True), ForeignKey("pr_review_records.id", ondelete="CASCADE"), nullable=False, index=True)
    finding_id = Column(PGUUID(as_uuid=True), ForeignKey("finding_records.id", ondelete="CASCADE"), nullable=False, index=True)
    developer_id = Column(String(255), nullable=False)
    is_valid = Column(Boolean, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CodeChunk(Base):
    __tablename__ = "code_chunks"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo = Column(String(255), nullable=False, index=True)
    path = Column(String(500), nullable=False)
    symbol = Column(String(255), nullable=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(384), nullable=False)
    token_count = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    content_tsv = Column(TSVECTOR, nullable=True)

    __table_args__ = (
        Index("code_chunks_unique_idx", "repo", "path", "chunk_index", unique=True),
    )


class AgentEvent(Base):
    __tablename__ = "agent_events"

    ts = Column(DateTime(timezone=True), nullable=False, primary_key=True)
    review_id = Column(PGUUID(as_uuid=True), nullable=False, primary_key=True)
    agent = Column(String(50), nullable=False, primary_key=True)
    span_id = Column(PGUUID(as_uuid=True), nullable=False, default=uuid.uuid4, primary_key=True)
    parent_span = Column(PGUUID(as_uuid=True), nullable=True)
    event_type = Column(String(50), nullable=False)
    model = Column(String(100), nullable=True)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    cost_usd = Column(Numeric(10, 6), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    outcome = Column(String(50), nullable=True)
    confidence = Column(Numeric(4, 3), nullable=True)
    payload = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_agent_events_review_ts", "review_id", "ts"),
        Index("ix_agent_events_agent_ts", "agent", "ts"),
    )


class RepoFileIndex(Base):
    __tablename__ = "repo_file_index"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo = Column(String(255), nullable=False, index=True)
    path = Column(String(500), nullable=False)
    sha = Column(String(64), nullable=False)
    last_indexed_at = Column(DateTime(timezone=True), server_default=func.now())
    chunk_count = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_repo_file_index_repo_path", "repo", "path", unique=True),
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key = Column(String(255), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())