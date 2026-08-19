-- Tiger Cloud initialization script for AI PR Review Agent
-- This script sets up the database schema with all three lanes: memory, truth, time

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS vectorscale;
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Lane 1: Memory - code_chunks table with vector search
CREATE TABLE IF NOT EXISTS code_chunks (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    repo         TEXT         NOT NULL,
    path         TEXT         NOT NULL,
    symbol       TEXT,                       -- function/class name (nullable)
    chunk_index  INT          NOT NULL,      -- order within file
    content      TEXT         NOT NULL,
    embedding    VECTOR(384)  NOT NULL,      -- all-MiniLM-L6-v2, 384 dims
    token_count  INT,
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS code_chunks_repo_idx ON code_chunks (repo);
CREATE INDEX IF NOT EXISTS code_chunks_emb_idx
    ON code_chunks USING diskann (embedding vector_cosine_ops);

ALTER TABLE code_chunks
    ADD COLUMN IF NOT EXISTS content_tsv TSVECTOR
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX IF NOT EXISTS code_chunks_fts_idx
    ON code_chunks USING GIN (content_tsv);

CREATE UNIQUE INDEX IF NOT EXISTS code_chunks_unique_idx
    ON code_chunks (repo, path, chunk_index);

-- Lane 1b: Repo file index for freshness tracking
CREATE TABLE IF NOT EXISTS repo_file_index (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    repo            TEXT        NOT NULL,
    path            TEXT        NOT NULL,
    sha             TEXT        NOT NULL,
    last_indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    chunk_count     INT         DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS repo_file_index_repo_path_idx
    ON repo_file_index (repo, path);

-- Lane 2: Truth - PR review records
CREATE TABLE IF NOT EXISTS pr_review_records (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    repo                TEXT        NOT NULL,
    pr_number           INT         NOT NULL,
    pr_title            TEXT        NOT NULL,
    pr_body             TEXT,
    diff                TEXT        NOT NULL,
    base_sha            TEXT        NOT NULL,
    head_sha            TEXT        NOT NULL,
    overall_confidence  NUMERIC(4,3) DEFAULT 0.0,
    outcome             TEXT,
    hitl_required       BOOLEAN     DEFAULT FALSE,
    github_review_id    INT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS pr_review_records_repo_pr_idx
    ON pr_review_records (repo, pr_number);

CREATE INDEX IF NOT EXISTS pr_review_records_repo_idx ON pr_review_records (repo);
CREATE INDEX IF NOT EXISTS pr_review_records_created_idx ON pr_review_records (created_at DESC);

-- Lane 2b: Finding records
CREATE TABLE IF NOT EXISTS finding_records (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id     UUID        NOT NULL REFERENCES pr_review_records(id) ON DELETE CASCADE,
    agent_type    TEXT        NOT NULL,
    severity      TEXT        NOT NULL,
    category      TEXT        NOT NULL,
    summary       TEXT        NOT NULL,
    file_path     TEXT        NOT NULL,
    line_start    INT         NOT NULL,
    line_end      INT,
    suggestion    TEXT        NOT NULL,
    confidence    NUMERIC(4,3) NOT NULL,
    rationale     TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS finding_records_review_idx ON finding_records (review_id);
CREATE INDEX IF NOT EXISTS finding_records_agent_idx ON finding_records (agent_type);

-- Lane 2c: HITL reviews
CREATE TABLE IF NOT EXISTS hitl_reviews (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id   UUID        NOT NULL REFERENCES pr_review_records(id) ON DELETE CASCADE,
    status      TEXT        DEFAULT 'pending',
    reviewer_id TEXT,
    decision    TEXT,
    feedback    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS hitl_reviews_review_idx ON hitl_reviews (review_id);
CREATE INDEX IF NOT EXISTS hitl_reviews_status_idx ON hitl_reviews (status);

-- Lane 2d: HITL feedback
CREATE TABLE IF NOT EXISTS hitl_feedback (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id     UUID        NOT NULL REFERENCES pr_review_records(id) ON DELETE CASCADE,
    finding_id    UUID        NOT NULL REFERENCES finding_records(id) ON DELETE CASCADE,
    developer_id  TEXT        NOT NULL,
    is_valid      BOOLEAN     NOT NULL,
    comment       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS hitl_feedback_review_idx ON hitl_feedback (review_id);
CREATE INDEX IF NOT EXISTS hitl_feedback_finding_idx ON hitl_feedback (finding_id);

-- Lane 2e: Idempotency keys
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key         TEXT        PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lane 3: Time - Agent events hypertable
CREATE TABLE IF NOT EXISTS agent_events (
    ts            TIMESTAMPTZ NOT NULL,
    review_id     UUID        NOT NULL,
    agent         TEXT        NOT NULL,
    span_id       UUID        NOT NULL DEFAULT gen_random_uuid(),
    parent_span   UUID,
    event_type    TEXT        NOT NULL,
    model         TEXT,
    tokens_in     INT,
    tokens_out    INT,
    cost_usd      NUMERIC(10,6),
    latency_ms    INT,
    outcome       TEXT,
    confidence    NUMERIC(4,3),
    payload       JSONB,
    PRIMARY KEY (ts, review_id, agent, span_id)
);

-- Convert to hypertable partitioned by 1 day
SELECT create_hypertable(
    'agent_events',
    by_range('ts', INTERVAL '1 day'),
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS agent_events_review_ts_idx ON agent_events (review_id, ts);
CREATE INDEX IF NOT EXISTS agent_events_agent_ts_idx ON agent_events (agent, ts);
CREATE INDEX IF NOT EXISTS agent_events_event_type_idx ON agent_events (event_type);

-- Lane 3b: Continuous aggregate - agent health per minute
CREATE MATERIALIZED VIEW IF NOT EXISTS agent_health_1m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', ts) AS bucket,
    agent,
    count(*) FILTER (WHERE event_type = 'llm.call') AS llm_calls,
    sum(cost_usd) AS cost_usd,
    approx_percentile(0.95, percentile_agg(latency_ms)) AS p95_ms,
    count(*) FILTER (WHERE outcome = 'rejected')::float
        / NULLIF(count(*) FILTER (WHERE outcome IS NOT NULL), 0) AS rejection_rate
FROM agent_events
GROUP BY bucket, agent
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'agent_health_1m',
    start_offset      => INTERVAL '2 hours',
    end_offset        => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists     => TRUE
);

-- Lane 3c: Continuous aggregate - PR cost per hour
CREATE MATERIALIZED VIEW IF NOT EXISTS pr_cost_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', ts) AS bucket,
    review_id,
    sum(cost_usd) AS total_cost_usd,
    count(DISTINCT agent) AS agents_used,
    max(confidence) AS max_confidence
FROM agent_events
GROUP BY bucket, review_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'pr_cost_hourly',
    start_offset      => INTERVAL '3 hours',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists     => TRUE
);

-- Compression policy for older data
ALTER TABLE agent_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'review_id, agent'
);

SELECT add_compression_policy('agent_events', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention policy (optional - keep 90 days)
-- SELECT add_retention_policy('agent_events', INTERVAL '90 days', if_not_exists => TRUE);