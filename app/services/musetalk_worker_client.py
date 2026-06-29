"""Client for the warm MuseTalk worker (worker/musetalk_worker.py).

The worker runs on the same pod as the web app, so audio/video are passed by
absolute filesystem path, not bytes. Enabled only when MUSETALK_WORKER_URL is set.
Uses stdlib urllib so the web app needs no extra dependency.
"""

import json
import os
import urllib.error
import urllib.request
from typing import IO, Optional


def worker_url() -> str:
    return (os.getenv("MUSETALK_WORKER_URL", "") or "").rstrip("/")


def worker_enabled() -> bool:
    return bool(worker_url())


def health(timeout: float = 2.0) -> Optional[dict]:
    """Return the worker's /health JSON, or None if it is unreachable."""
    if not worker_enabled():
        return None
    try:
        with urllib.request.urlopen(worker_url() + "/health", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def render_via_worker(
    avatar_id: str,
    audio_path: str,
    audio_id: str,
    fps: int = 25,
    timeout: float = 1200.0,
    log_file: Optional[IO[str]] = None,
) -> str:
    """Render one clip on the warm worker. Returns the output video path.

    Raises on transport/worker error so the job is marked failed with the reason.
    """
    url = worker_url() + "/render"
    payload = json.dumps({
        "avatar_id": avatar_id, "audio_path": audio_path,
        "audio_id": audio_id, "fps": fps,
    }).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    if log_file:
        log_file.write(f"[worker] POST {url} avatar={avatar_id} audio={audio_path}\n")
        log_file.flush()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"worker HTTP {e.code}: {body}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"worker unreachable: {e.reason}") from None

    if log_file:
        log_file.write(
            f"[worker] done in {data.get('render_seconds')}s -> {data.get('video_path')}\n"
        )
        log_file.flush()
    return data["video_path"]


def render_chunked_via_worker(
    avatar_id: str,
    audio_path: str,
    audio_id: str,
    out_dir: str,
    chunk_seconds: float = 3.0,
    fps: int = 25,
    timeout: float = 1800.0,
    log_file: Optional[IO[str]] = None,
) -> str:
    """Streaming render: worker splits the audio and writes ordered segment mp4s
    + out_dir/segments.json as each lands (player can start on segment 0). Returns
    the concatenated full video path. Raises on transport/worker error."""
    url = worker_url() + "/render_chunked"
    payload = json.dumps({
        "avatar_id": avatar_id, "audio_path": audio_path, "audio_id": audio_id,
        "out_dir": out_dir, "chunk_seconds": chunk_seconds, "fps": fps,
    }).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    if log_file:
        log_file.write(
            f"[worker] POST {url} avatar={avatar_id} chunked={chunk_seconds}s -> {out_dir}\n"
        )
        log_file.flush()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"worker HTTP {e.code}: {body}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"worker unreachable: {e.reason}") from None

    if log_file:
        log_file.write(
            f"[worker] chunked done in {data.get('render_seconds')}s, "
            f"{len(data.get('segments', []))} segments\n"
        )
        log_file.flush()
    return data["video_path"]
