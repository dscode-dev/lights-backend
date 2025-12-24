from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

log = logging.getLogger("openai.client")


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class OpenAIClient:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            log.warning("openai_api_key_missing")
        self._headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    async def led_plan(
        self,
        *,
        title: str,
        genre: str,
        palette: str,
        duration_ms: int,
        bpm: int,
        beat_map_preview: list[int],
        topology: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Retorna JSON puro com o plano.
        """
        system = (
            "Você é um gerador de planos de show de LEDs. "
            "RETORNE APENAS JSON válido (sem markdown, sem texto extra)."
        )

        user = {
            "title": title,
            "genre": genre,
            "palette": palette,
            "durationMs": duration_ms,
            "bpm": bpm,
            "beatMapPreview": beat_map_preview[:64],
            "ledTopology": topology,
            "requirements": {
                "minBpm": 128,
                "firmwareCommands": {
                    "vu": "VU:<LEVEL>",
                    "contour": "CT:SOLID:<HUE> | CT:OFF",
                },
                "notes": [
                    "O backend controla LEDs, o frontend toca o YouTube.",
                    "Plano deve ser sincronizável por tempo (ms) + BPM + beatMap.",
                ],
            },
            "outputSchema": {
                "ledPlan": "object",
            },
        }

        payload = {
            "model": settings.openai_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "temperature": 0.2,
        }

        log.info(
            "openai_request_start",
            extra={"model": settings.openai_model, "title": title},
        )

        async with httpx.AsyncClient(timeout=settings.openai_timeout_s) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=self._headers,
                json=payload,
            )
            r.raise_for_status()
            data = r.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        preview = content[:300].replace("\n", "\\n")
        log.info("openai_response_raw", extra={"preview": preview})

        parsed = self._parse_json(content)
        log.info("openai_response_ok", extra={"keys": list(parsed.keys())[:10]})
        return parsed

    def _parse_json(self, content: str) -> Dict[str, Any]:
        content = (content or "").strip()
        if not content:
            raise ValueError("OpenAI returned empty content")

        # se já é JSON puro
        try:
            return json.loads(content)
        except Exception:
            pass

        # tenta extrair um {...}
        m = _JSON_RE.search(content)
        if not m:
            raise ValueError("Could not find JSON object in OpenAI response")

        return json.loads(m.group(0))

    async def generate_show_plan(
        self, *, title: str, genre: str, duration_ms: int, bpm: int
    ) -> dict:
        prompt = f"""
        Você é um diretor de show de LEDs profissional.
    
        Crie:
        1) presets de efeitos
        2) timeline com mudanças ao longo da música
    
        Formato JSON:
    
        {{
          "presets": {{
            "intro": {{ "vu": {{...}}, "contour": {{...}} }},
            "drop": {{ "vu": {{...}}, "contour": {{...}} }},
            "final": {{ "vu": {{...}}, "contour": {{...}} }}
          }},
          "timeline": [
            {{ "atMs": 0, "presetName": "intro" }},
            {{ "atMs": {duration_ms * 0.3:.0f}, "presetName": "drop" }},
            {{ "atMs": {duration_ms * 0.8:.0f}, "presetName": "final" }}
          ]
        }}
        """
        return await self._call_openai(prompt)
