from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.repository import IdempotencyRepository
from backend.core.exceptions import IdempotencyError


class IdempotencyManager:
    def __init__(self, session: AsyncSession):
        self.repository = IdempotencyRepository(session)

    async def check_and_store(self, key: str) -> bool:
        success = await self.repository.check_and_set(key)
        if not success:
            raise IdempotencyError(f"Duplicate request detected", key)
        return True

    async def is_processed(self, key: str) -> bool:
        existing = await self.repository.session.get(
            self.repository.session.bind.sync_engine.dialect, key
        )
        return existing is not None


async def create_idempotency_manager(session: AsyncSession) -> IdempotencyManager:
    return IdempotencyManager(session)