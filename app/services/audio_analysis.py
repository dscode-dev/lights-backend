from __future__ import annotations

import librosa


def analyze_audio(path: str) -> tuple[int, int]:
    """
    Returns: (duration_ms, bpm_int)
    """
    y, sr = librosa.load(path, sr=None, mono=True)
    duration_s = float(librosa.get_duration(y=y, sr=sr))

    # beat_track can output float bpm
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = int(round(float(tempo))) if tempo else 120

    # clamp to sane values
    if bpm < 30:
        bpm = 30
    if bpm > 240:
        bpm = 240

    duration_ms = int(round(duration_s * 1000.0))
    if duration_ms < 0:
        duration_ms = 0

    return duration_ms, bpm
