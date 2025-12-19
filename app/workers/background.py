from __future__ import annotations

import asyncio
from fastapi import BackgroundTasks
from typing import Coroutine, Any


def run_coro(background: BackgroundTasks, coro: Coroutine[Any, Any, Any]) -> None:
    """
    FastAPI BackgroundTasks expects a sync callable.
    We schedule the async coro on the running event loop.
    """
    def _kick() -> None:
        asyncio.create_task(coro)

    background.add_task(_kick)
