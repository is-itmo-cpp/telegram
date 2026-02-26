import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class TTLCache:
    ttl_seconds: float
    value: Any = None
    loaded_at: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def is_alive(self) -> bool:
        return (
            self.loaded_at > 0.0
            and time.monotonic() - self.loaded_at < self.ttl_seconds
        )

    def set(self, value: Any) -> None:
        self.value = value
        self.loaded_at = time.monotonic()

    def invalidate(self) -> None:
        self.loaded_at = 0.0

    async def get_or_load(self, loader: Callable[[], Awaitable[Any]]) -> Any:
        if self.is_alive():
            return self.value

        async with self.lock:
            if self.is_alive():
                return self.value

            value = await loader()
            self.set(value)
            return value
