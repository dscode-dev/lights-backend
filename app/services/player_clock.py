from __future__ import annotations
import asyncio
from typing import Optional

class PlayerClock:
    def __init__(self):
        self.current_time_s: float = 0.0
        self.state: str = "paused"
        self.step_index: Optional[int] = None
        self._lock = asyncio.Lock()

    async def update(self, *, time_s: float, state: str, step_index: int):
        async with self._lock:
            self.current_time_s = time_s
            self.state = state
            self.step_index = step_index

    async def snapshot(self):
        async with self._lock:
            return {
                "time_s": self.current_time_s,
                "state": self.state,
                "step_index": self.step_index,
            }