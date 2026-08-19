import asyncio
import time
from enum import Enum
from typing import Callable, Any, Optional
from dataclasses import dataclass, field
from backend.config import settings


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 30.0
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time > self.timeout:
                return CircuitState.HALF_OPEN
        return self._state

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        async with self._lock:
            current_state = self.state
            if current_state == CircuitState.OPEN:
                raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is OPEN")
            
            if current_state == CircuitState.HALF_OPEN:
                self._state = CircuitState.HALF_OPEN
        
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def _on_success(self):
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    async def _on_failure(self):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._success_count = 0
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN

    def reset(self):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0


class CircuitBreakerOpenError(Exception):
    pass


class CircuitBreakerRegistry:
    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(self, name: str, **kwargs) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, **kwargs)
        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        return self._breakers.get(name)

    async def call(self, name: str, func: Callable, *args, **kwargs) -> Any:
        breaker = self.get_or_create(name)
        return await breaker.call(func, *args, **kwargs)

    def get_all_states(self) -> dict[str, CircuitState]:
        return {name: breaker.state for name, breaker in self._breakers.items()}


circuit_breaker_registry = CircuitBreakerRegistry()