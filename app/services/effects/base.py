from __future__ import annotations
from abc import ABC, abstractmethod

from app.services.effects.beat_tracker import BeatTracker


class EffectContext:
    def __init__(
        self,
        *,
        elapsed_ms: int,
        bpm: int,
        palette: str,
        beat_tracker: BeatTracker,
    ):
        self.elapsed_ms = elapsed_ms
        self.bpm = bpm
        self.palette = palette
        self.beat = beat_tracker


class BaseEffect(ABC):
    @abstractmethod
    def apply(self, ctx: EffectContext):
        pass