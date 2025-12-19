from __future__ import annotations

import httpx
from typing import Any, Dict

from app.core.config import settings


async def ping_esp(ip: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=settings.esp_timeout_s) as client:
            r = await client.get(f"{settings.esp_protocol}://{ip}/ping")
            return r.status_code == 200
    except Exception:
        return False


async def blink_esp(ip: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=settings.esp_timeout_s) as client:
            await client.post(
                f"{settings.esp_protocol}://{ip}/cmd",
                json={"cmd": "blink", "payload": {}},
            )
    except Exception:
        pass


async def send_cmd(ip: str, cmd: str, payload: Dict[str, Any] | None = None) -> bool:
    payload = payload or {}
    try:
        async with httpx.AsyncClient(timeout=settings.esp_timeout_s) as client:
            r = await client.post(
                f"{settings.esp_protocol}://{ip}/cmd",
                json={"cmd": cmd, "payload": payload},
            )
            return 200 <= r.status_code < 300
    except Exception:
        return False
