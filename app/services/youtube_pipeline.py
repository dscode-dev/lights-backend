from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.models.playlist import PlaylistStep, EspCommand
from app.state.redis_state import RedisState
from app.state.redis_keys import EVENTS_CHANNEL, processing_key
from app.state.playlist_state import get_playlist, save_playlist
from app.services.audio_analysis import analyze_audio

log = logging.getLogger("pipeline.youtube")


def _safe_filename(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[^\w\s\-\.]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s)
    return s[:120] if s else "track"


async def _run_cmd(*cmd: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    out = (out_b or b"").decode("utf-8", errors="replace")
    err = (err_b or b"").decode("utf-8", errors="replace")
    return proc.returncode or 0, out, err


@dataclass
class AddFromYouTubeJob:
    step_id: str
    youtube_url: str
    use_ai: bool


class YouTubePipeline:
    def __init__(self, state: RedisState):
        self.state = state

    async def _publish_progress(self, step_id: str, progress: float) -> None:
        if progress < 0:
            progress = 0.0
        if progress > 1:
            progress = 1.0

        await self.state.set_json(processing_key(step_id), {"stepId": step_id, "progress": progress})
        await self.state.publish_event(
            EVENTS_CHANNEL,
            {"type": "playlist_progress", "data": {"stepId": step_id, "progress": progress}},
        )

    async def _publish_error(self, step_id: str, message: str) -> None:
        await self.state.publish_event(
            EVENTS_CHANNEL,
            {"type": "playlist_error", "data": {"stepId": step_id, "error": message}},
        )

    async def _publish_ready(self, step: PlaylistStep) -> None:
        await self.state.publish_event(
            EVENTS_CHANNEL,
            {"type": "playlist_ready", "data": {"step": step.model_dump()}},
        )

    async def _update_step(self, step_id: str, mutator) -> Optional[PlaylistStep]:
        steps = await get_playlist(self.state)
        changed: Optional[PlaylistStep] = None
        for i, s in enumerate(steps):
            if s.id == step_id:
                s2 = mutator(s)
                steps[i] = s2
                changed = s2
                break
        await save_playlist(self.state, steps)
        return changed

    async def _fetch_metadata_title(self, url: str) -> str:
        # yt-dlp -J url (JSON metadata)
        code, out, err = await _run_cmd(settings.ytdlp_bin, "-J", url)
        if code != 0:
            raise RuntimeError(f"yt-dlp metadata failed: {err.strip() or out.strip()}")
        data = json.loads(out)
        title = data.get("title") or "YouTube Track"
        return str(title)

    async def _download_mp3(self, url: str, out_mp3_path: str) -> None:
        """
        Uses yt-dlp to extract audio and convert to mp3.
        Requires ffmpeg installed on machine.
        """
        out_dir = os.path.dirname(out_mp3_path)
        os.makedirs(out_dir, exist_ok=True)

        # yt-dlp will create .mp3 based on -o template and --audio-format
        # We'll provide template WITHOUT extension; yt-dlp will append .mp3
        template_no_ext = os.path.splitext(out_mp3_path)[0]

        cmd = (
            settings.ytdlp_bin,
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "-o",
            template_no_ext + ".%(ext)s",
            url,
        )
        code, out, err = await _run_cmd(*cmd)
        if code != 0:
            raise RuntimeError(f"yt-dlp download failed: {err.strip() or out.strip()}")

        # yt-dlp will output something like template_no_ext.mp3
        if not os.path.exists(out_mp3_path):
            # sometimes ext handling can differ; try to locate any mp3 in dir with prefix
            base = os.path.basename(template_no_ext)
            candidates = [
                os.path.join(out_dir, f)
                for f in os.listdir(out_dir)
                if f.startswith(base) and f.lower().endswith(".mp3")
            ]
            if candidates:
                os.replace(candidates[0], out_mp3_path)
            else:
                raise RuntimeError("mp3 not found after yt-dlp download")

    def _base_show_fields(self, step: PlaylistStep) -> PlaylistStep:
        """
        Fill base show values & initial ESP commands. (Simple baseline)
        """
        # baseline patterns (strings for now; you can evolve to structured later)
        step.leds = "base_vu_pulse"
        step.portal = "portal_soft"
        step.hologram = "hologram_float"

        step.esp = [
            EspCommand(
                target="broadcast",
                type="set_palette",
                payload={"palette": step.palette},
            ),
            EspCommand(
                target="broadcast",
                type="set_mode",
                payload={"mode": "VU"},
            ),
        ]
        return step

    async def run(self, job: AddFromYouTubeJob) -> None:
        step_id = job.step_id
        url = job.youtube_url

        try:
            await self._publish_progress(step_id, 0.05)

            title = await self._fetch_metadata_title(url)
            await self._publish_progress(step_id, 0.15)

            safe = _safe_filename(title)
            out_mp3 = os.path.join(settings.media_dir, f"{step_id}_{safe}.mp3")

            await self._download_mp3(url, out_mp3)
            await self._publish_progress(step_id, 0.45)

            duration_ms, bpm = analyze_audio(out_mp3)
            await self._publish_progress(step_id, 0.75)

            # Update step: fill computed fields
            def apply_ready(s: PlaylistStep) -> PlaylistStep:
                s.trackTitle = title
                s.audioFile = out_mp3
                s.durationMs = duration_ms
                s.bpm = bpm
                s.progress = 1.0
                s.status = "ready"
                return self._base_show_fields(s)

            updated = await self._update_step(step_id, apply_ready)
            if not updated:
                raise RuntimeError("Step not found in playlist (was it deleted?)")

            # Emit ready
            await self._publish_progress(step_id, 1.0)
            await self._publish_ready(updated)

            log.info(
                "youtube_pipeline_ready",
                extra={"stepId": step_id, "bpm": bpm, "durationMs": duration_ms, "audioFile": out_mp3},
            )

        except Exception as e:
            msg = str(e)
            log.exception("youtube_pipeline_error", extra={"stepId": step_id})

            # mark step as error
            def apply_error(s: PlaylistStep) -> PlaylistStep:
                s.status = "error"
                s.progress = 0.0
                return s

            await self._update_step(step_id, apply_error)
            await self._publish_error(step_id, msg)
