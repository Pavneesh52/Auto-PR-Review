import redis.asyncio as redis
from typing import Optional, Any
import json
from backend.config import settings


class RedisClient:
    def __init__(self):
        self.client = redis.from_url(settings.redis_url, decode_responses=True)

    async def get(self, key: str) -> Optional[str]:
        return await self.client.get(key)

    async def set(self, key: str, value: str, expire: int = 3600) -> bool:
        return await self.client.set(key, value, ex=expire)

    async def set_json(self, key: str, value: Any, expire: int = 3600) -> bool:
        return await self.client.set(key, json.dumps(value), ex=expire)

    async def get_json(self, key: str) -> Optional[Any]:
        data = await self.client.get(key)
        if data:
            return json.loads(data)
        return None

    async def delete(self, key: str) -> int:
        return await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        return await self.client.exists(key) > 0

    async def close(self):
        await self.client.close()


redis_client = RedisClient()