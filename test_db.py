from backend.database.postgres import engine
from sqlalchemy import text
import asyncio

async def test():
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text('SELECT version()'))
            version = result.scalar()
            print(f'Connected to: {version}')
            
            # Check extensions
            result = await conn.execute(text(
                "SELECT extname FROM pg_extension WHERE extname IN ('vector', 'timescaledb', 'vectorscale', 'pg_trgm')"
            ))
            ext = [row[0] for row in result.all()]
            print(f'Extensions: {ext}')
            
            # Check tables
            result = await conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            ))
            tables = [row[0] for row in result.all()]
            print(f'Tables: {tables}')
            
    except Exception as e:
        print(f'Connection failed: {e}')

asyncio.run(test())