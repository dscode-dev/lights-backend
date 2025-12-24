from __future__ import annotations


class BeatTracker:
    def __init__(self, beat_map: list[int]):
        self.beat_map = beat_map
        self.index = 0

    def reset(self):
        self.index = 0

    def energy_at(self, elapsed_ms: int) -> float:
        """
        Retorna energia entre 0.0 e 1.0 baseada
        na proximidade do próximo beat real.
        """
        if not self.beat_map:
            return 0.0

        while (
            self.index + 1 < len(self.beat_map)
            and self.beat_map[self.index + 1] <= elapsed_ms
        ):
            self.index += 1

        beat_time = self.beat_map[self.index]
        delta = abs(elapsed_ms - beat_time)

        # janela de impacto do beat (ms)
        window = 120

        if delta > window:
            return 0.0

        # energia decai linearmente
        return 1.0 - (delta / window)