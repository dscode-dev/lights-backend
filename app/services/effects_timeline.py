from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TimelineEntry:
    at_ms: int
    preset: str


class EffectsTimeline:
    """
    Resolve qual preset de efeitos está ativo com base no elapsedMs.
    Atua como o 'maestro' dos LEDs.

    NÃO calcula efeitos.
    NÃO anima.
    Apenas decide QUAL preset está ativo agora.
    """

    def __init__(self, timeline: List[dict], presets: Dict[str, dict]) -> None:
        """
        timeline: [
          { "atMs": 0, "preset": "intro" },
          { "atMs": 45000, "preset": "drop" }
        ]

        presets: {
          "intro": {...},
          "drop": {...}
        }
        """
        self.presets = presets

        # normaliza e ordena
        self._entries: List[TimelineEntry] = sorted(
            (
                TimelineEntry(
                    at_ms=int(item["atMs"]),
                    preset=item["preset"],
                )
                for item in timeline
                if "atMs" in item and "preset" in item
            ),
            key=lambda e: e.at_ms,
        )

        # lista auxiliar para busca binária
        self._times = [e.at_ms for e in self._entries]

    def get_active_preset(self, elapsed_ms: int) -> Optional[dict]:
        """
        Retorna o preset ativo para o tempo atual.
        Usa busca binária (rápido e determinístico).
        """
        if not self._entries:
            return None

        # índice do último evento <= elapsed_ms
        idx = bisect.bisect_right(self._times, elapsed_ms) - 1

        if idx < 0:
            return None

        entry = self._entries[idx]
        return self.presets.get(entry.preset)

    def debug_snapshot(self, elapsed_ms: int) -> dict:
        """
        Útil para logs e debug.
        """
        preset = self.get_active_preset(elapsed_ms)
        return {
            "elapsedMs": elapsed_ms,
            "activePreset": preset,
            "timelineSize": len(self._entries),
        }