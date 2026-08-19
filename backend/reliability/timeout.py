import asyncio
from typing import Callable, Any
from backend.core.exceptions import ReviewAgentError


class TimeoutError(ReviewAgentError):
    def __init__(self, operation: str, timeout: float):
        super().__init__(
            f"Operation '{operation}' timed out after {timeout}s",
            "TIMEOUT_ERROR",
            {"operation": operation, "timeout": timeout},
        )


async def with_timeout(
    coro: Callable,
    timeout: float,
    operation: str = "operation",
) -> Any:
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(operation, timeout)


class TimeoutConfig:
    LLM_CALL = 60.0
    GITHUB_API = 30.0
    DATABASE = 10.0
    RETRIEVAL = 15.0
    REVIEW_TOTAL = 300.0