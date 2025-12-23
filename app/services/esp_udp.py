# app/services/esp_udp.py

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Optional

log = logging.getLogger("esp.udp")


class EspUdpClient:
    """
    Cliente UDP simples e stateless.

    - Envia STRING ASCII
    - Não espera resposta
    - Um comando por pacote
    - Totalmente compatível com firmware atual
    """

    def __init__(self, port: int = 7777) -> None:
        self.port = port

    # =========================
    # PUBLIC API
    # =========================

    async def send(self, ip: str, message: str) -> None:
        """
        Envia um comando UDP simples.
        """
        if not message:
            return

        try:
            await asyncio.to_thread(self._send_blocking, ip, message)
        except Exception:
            log.exception(
                "udp_send_failed",
                extra={"ip": ip, "message": message},
            )

    # =========================
    # LOW LEVEL
    # =========================

    def _send_blocking(self, ip: str, message: str) -> None:
        """
        Envio real via socket UDP.
        Executado fora do event loop.
        """
        data = message.encode("utf-8")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(data, (ip, self.port))
        finally:
            sock.close()

    # =========================
    # HELPERS DE COMANDO
    # =========================

    async def vu(self, ip: str, level: int, max_level: int) -> None:
        """
        Envia comando VU com clamp correto.
        """
        level = max(0, min(max_level, level))
        await self.send(ip, f"VU:{level}")

    async def contorno_solid(self, ip: str, hue: int) -> None:
        """
        Liga contorno em cor sólida.
        """
        hue = max(0, min(255, hue))
        await self.send(ip, f"CT:SOLID:{hue}")

    async def contorno_off(self, ip: str) -> None:
        """
        Desliga contorno.
        """
        await self.send(ip, "CT:OFF")