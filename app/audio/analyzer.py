from __future__ import annotations

import logging
from dataclasses import dataclass

import librosa
import numpy as np

log = logging.getLogger("audio.analyzer")


@dataclass
class AudioAnalysisResult:
    duration_ms: int
    bpm: int


def analyze_audio_file(path: str) -> AudioAnalysisResult:
    """
    Analisa um arquivo WAV local e retorna:
    - duração em ms
    - BPM estimado
    """

    log.info("audio_load_start", extra={"path": path})

    # y = waveform, sr = sample rate
    y, sr = librosa.load(path, sr=None, mono=True)

    log.info("audio_load_ok")

    duration_s = librosa.get_duration(y=y, sr=sr)
    duration_ms = int(duration_s * 1000)

    # BPM (tempo global)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = int(round(float(tempo)))

    log.info(
        "audio_analysis_ok",
        extra={
            "duration_ms": duration_ms,
            "bpm": bpm,
        },
    )

    return AudioAnalysisResult(
        duration_ms=duration_ms,
        bpm=bpm,
    )