import redis.asyncio as redis
from backend.config import settings
import asyncio

async def test():
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        info = await client.info()
        print(f'Redis connected: {info["redis_version"]}')
        print(f'Connected clients: {info["connected_clients"]}')
        print(f'Used memory: {info["used_memory_human"]}')
        await client.close()
    except Exception as e:
        print(f'Redis connection failed: {e}')

asyncio.run(test())