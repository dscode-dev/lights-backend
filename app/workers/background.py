from __future__ import annotations

import asyncio
import logging
from typing import Awaitable

from fastapi import BackgroundTasks

log = logging.getLogger("workers.background")


def run_coro(background: BackgroundTasks, coro: Awaitable[object]) -> None:
    """
    Agenda um coroutine para rodar via FastAPI BackgroundTasks.
    BackgroundTasks executa em threadpool (sem event loop).
    Então a forma segura é executar o coro com asyncio.run dentro da task.
    """

    def _kick(c: Awaitable[object]) -> None:
        try:
            asyncio.run(c)
        except Exception:
            log.exception("background_coro_failed")

    background.add_task(_kick, coro)