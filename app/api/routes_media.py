from __future__ import annotations

import os
import mimetypes
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from starlette.responses import StreamingResponse, Response

from app.core.config import settings

router = APIRouter(tags=["media"])


def _file_iterator(path: str, start: int, end: int, chunk_size: int = 1024 * 256):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = f.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _parse_range(range_header: str, file_size: int) -> Optional[tuple[int, int]]:
    # Range: bytes=START-END
    try:
        if not range_header.startswith("bytes="):
            return None

        part = range_header.replace("bytes=", "").strip()
        if "," in part:
            # não suportamos multi-range
            return None

        start_s, end_s = part.split("-")
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else (file_size - 1)

        if start < 0 or end < 0 or start > end:
            return None
        if start >= file_size:
            return None

        end = min(end, file_size - 1)
        return (start, end)
    except Exception:
        return None


@router.get("/media/{filename}")
async def stream_media(filename: str, request: Request):
    # segurança básica: não permitir path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    path = os.path.join(settings.media_dir, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="media not found")

    file_size = os.path.getsize(path)
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"

    range_header = request.headers.get("range")
    if not range_header:
        # full content
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        }
        return StreamingResponse(open(path, "rb"), media_type=content_type, headers=headers)

    r = _parse_range(range_header, file_size)
    if not r:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    start, end = r
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
    }
    return StreamingResponse(
        _file_iterator(path, start, end),
        status_code=206,
        media_type=content_type,
        headers=headers,
    )