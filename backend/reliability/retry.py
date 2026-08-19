from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging
from typing import Callable, Any, Type
from backend.config import settings

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=base_delay, max=max_delay),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


async def async_retry(
    func: Callable,
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
    **kwargs,
) -> Any:
    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            if attempt == max_attempts - 1:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(f"Retry attempt {attempt + 1}/{max_attempts} after {delay}s: {e}")
            import asyncio
            await asyncio.sleep(delay)