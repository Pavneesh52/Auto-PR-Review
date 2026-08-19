from backend.database.postgres import engine
from backend.database.models import Base
from sqlalchemy import text
import asyncio

async def run():
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print('Tables created')
        
        # Create extensions
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS vectorscale'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS timescaledb'))
        print('Extensions created')
        
        # Create hypertable
        await conn.execute(text("""
            SELECT create_hypertable(
                'agent_events',
                by_range('ts', INTERVAL '1 day'),
                if_not_exists => TRUE
            )
        """))
        print('Hypertable created')
        
        # Create continuous aggregates
        await conn.execute(text("""
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
            WITH NO DATA
        """))
        print('agent_health_1m created')
        
        await conn.execute(text("""
            SELECT add_continuous_aggregate_policy(
                'agent_health_1m',
                start_offset => INTERVAL '2 hours',
                end_offset => INTERVAL '1 minute',
                schedule_interval => INTERVAL '1 minute',
                if_not_exists => TRUE
            )
        """))
        print('agent_health_1m policy added')
        
        await conn.execute(text("""
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
            WITH NO DATA
        """))
        print('pr_cost_hourly created')
        
        await conn.execute(text("""
            SELECT add_continuous_aggregate_policy(
                'pr_cost_hourly',
                start_offset => INTERVAL '3 hours',
                end_offset => INTERVAL '1 hour',
                schedule_interval => INTERVAL '1 hour',
                if_not_exists => TRUE
            )
        """))
        print('pr_cost_hourly policy added')
        
        print('All migrations completed!')

asyncio.run(run())