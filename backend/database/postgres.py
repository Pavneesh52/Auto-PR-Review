from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from backend.config import settings
from backend.database.models import Base
import asyncpg
from urllib.parse import urlparse, parse_qs


def build_engine_url() -> str:
    """Build SQLAlchemy engine URL with proper SSL handling for asyncpg."""
    parsed = urlparse(settings.tiger_database_url)
    query = parse_qs(parsed.query)
    
    # Remove sslmode from query since asyncpg handles SSL differently
    sslmode = query.pop('sslmode', ['require'])[0]
    
    # Rebuild URL without sslmode
    new_query = '&'.join(f"{k}={v[0]}" for k, v in query.items()) if query else ''
    base_url = f"postgresql+asyncpg://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}{parsed.path}"
    if new_query:
        base_url += f"?{new_query}"
    
    return base_url, sslmode


engine_url, sslmode = build_engine_url()

import ssl
connect_args = {}
if sslmode in ('require', 'verify-ca', 'verify-full'):
    # For Tiger Cloud/TimescaleDB, use SSL without cert verification
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = ssl_ctx

engine = create_async_engine(
    engine_url,
    poolclass=NullPool,
    echo=settings.debug,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_tiger_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        await conn.execute("""
            CREATE EXTENSION IF NOT EXISTS vector;
            CREATE EXTENSION IF NOT EXISTS vectorscale;
            CREATE EXTENSION IF NOT EXISTS timescaledb;
        """)
        
        await conn.execute("""
            ALTER TABLE code_chunks
            ADD COLUMN IF NOT EXISTS content_tsv TSVECTOR
                GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS code_chunks_emb_idx
            ON code_chunks USING diskann (embedding vector_cosine_ops);
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS code_chunks_fts_idx
            ON code_chunks USING GIN (content_tsv);
        """)
        
        await conn.execute("""
            SELECT create_hypertable(
                'agent_events',
                by_range('ts', INTERVAL '1 day'),
                if_not_exists => TRUE
            );
        """)
        
        await conn.execute("""
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
        """)
        
        await conn.execute("""
            SELECT add_continuous_aggregate_policy(
                'agent_health_1m',
                start_offset => INTERVAL '2 hours',
                end_offset => INTERVAL '1 minute',
                schedule_interval => INTERVAL '1 minute',
                if_not_exists => TRUE
            );
        """)
        
        await conn.execute("""
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
        """)
        
        await conn.execute("""
            SELECT add_continuous_aggregate_policy(
                'pr_cost_hourly',
                start_offset => INTERVAL '3 hours',
                end_offset => INTERVAL '1 hour',
                schedule_interval => INTERVAL '1 hour',
                if_not_exists => TRUE
            );
        """)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_asyncpg_pool():
    parsed = urlparse(settings.tiger_database_url)
    query = parse_qs(parsed.query)
    sslmode = query.pop('sslmode', ['require'])[0]
    
    ssl = True if sslmode in ('require', 'verify-ca', 'verify-full') else False
    
    return await asyncpg.create_pool(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/'),
        ssl=ssl,
        min_size=2,
        max_size=10,
    )