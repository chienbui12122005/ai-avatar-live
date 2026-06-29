"""In-memory job registry + single-worker background queue for MuseTalk renders.

Status lives in RAM (lost on restart), but the per-job log file and the output
video survive on disk. A single worker thread runs renders serially so the GPU
is never asked to do two jobs at once.
"""

import glob
import os
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Callable, Optional

from app.services.musetalk import run_musetalk
from app.services import musetalk_realtime as rt
from app.services import musetalk_worker_client as worker

# pending -> running -> done | failed
PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


@dataclass
class Job:
    id: str
    musetalk_dir: str
    config_path: str
    output_dir: str
    log_path: str
    version: str = "v15"

    # input metadata (for display)
    teacher_name: str = ""
    audio_name: str = ""
    bbox_shift: int = 0
    profile: str = ""
    behavior: str = ""

    # render path: kind="render" (default) or "prepare" (build avatar cache);
    # realtime=True uses the cached scripts.realtime_inference path.
    kind: str = "render"
    realtime: bool = False
    chunked: bool = False
    chunk_seconds: float = 3.0
    avatar_id: str = ""
    video_path: str = ""
    audio_path: str = ""
    on_success: Optional[Callable[["Job"], None]] = None

    status: str = PENDING
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    video_path: Optional[str] = None

    @property
    def render_seconds(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "error": self.error,
            "version": self.version,
            "kind": self.kind,
            "realtime": self.realtime,
            "chunked": self.chunked,
            "teacher_name": self.teacher_name,
            "audio_name": self.audio_name,
            "bbox_shift": self.bbox_shift,
            "profile": self.profile,
            "behavior": self.behavior,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "render_seconds": self.render_seconds,
            "has_video": self.video_path is not None,
        }


class JobRegistry:
    def __init__(self, max_workers: int = 1):
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        # single worker => renders run serially (one GPU job at a time)
        self._pool = ThreadPoolExecutor(max_workers=max_workers)

    def create(self, **kwargs) -> Job:
        job_id = kwargs.pop("id", None) or str(uuid.uuid4())[:8]
        job = Job(id=job_id, **kwargs)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def submit(self, job: Job) -> None:
        self._pool.submit(self._run, job)

    def _run(self, job: Job) -> None:
        job.status = RUNNING
        job.started_at = time.time()
        log = Path(job.log_path)
        log.parent.mkdir(parents=True, exist_ok=True)

        try:
            with log.open("w", encoding="utf-8") as lf:
                lf.write(
                    f"[job {job.id}] kind={job.kind} realtime={job.realtime} "
                    f"version={job.version} avatar={job.avatar_id}\n"
                )
                lf.flush()

                if job.kind == "prepare":
                    rt.prepare_avatar(
                        musetalk_dir=job.musetalk_dir, config_path=job.config_path,
                        result_dir=job.output_dir, version=job.version,
                        avatar_id=job.avatar_id, video_path=job.video_path,
                        bbox_shift=job.bbox_shift, log_file=lf,
                    )
                elif job.realtime and job.chunked and worker.worker_enabled():
                    # Lowest latency: stream segments (player starts on segment 0
                    # while the rest render). Segments land in job.output_dir.
                    job.video_path = worker.render_chunked_via_worker(
                        avatar_id=job.avatar_id, audio_path=job.audio_path,
                        audio_id=job.id, out_dir=job.output_dir,
                        chunk_seconds=job.chunk_seconds, log_file=lf,
                    )
                elif job.realtime and worker.worker_enabled():
                    # Fast path: warm worker (models already loaded, materials in RAM)
                    job.video_path = worker.render_via_worker(
                        avatar_id=job.avatar_id, audio_path=job.audio_path,
                        audio_id=job.id, log_file=lf,
                    )
                elif job.realtime:
                    job.video_path = rt.render_realtime(
                        musetalk_dir=job.musetalk_dir, config_path=job.config_path,
                        result_dir=job.output_dir, version=job.version,
                        avatar_id=job.avatar_id, video_path=job.video_path,
                        audio_path=job.audio_path, audio_id=job.id,
                        bbox_shift=job.bbox_shift, log_file=lf,
                    )
                else:
                    run_musetalk(
                        musetalk_dir=job.musetalk_dir, config_path=job.config_path,
                        output_dir=job.output_dir, version=job.version, log_file=lf,
                    )

            if job.kind == "prepare":
                # success = subprocess exit 0; no video expected
                job.status = DONE
            else:
                # realtime sets video_path optimistically; verify / fall back to a glob
                if not (job.video_path and os.path.exists(job.video_path)):
                    job.video_path = self._find_video(job)
                if not job.video_path:
                    job.status = FAILED
                    job.error = "Render finished but no .mp4 was produced (check the log)."
                else:
                    job.status = DONE

            if job.status == DONE and job.on_success:
                try:
                    job.on_success(job)
                except Exception:  # noqa: BLE001 - hook must not fail the job
                    pass
        except Exception as e:  # noqa: BLE001 - we want to record any failure
            job.status = FAILED
            job.error = str(e)
            try:
                with log.open("a", encoding="utf-8") as lf:
                    lf.write("\n[job failed]\n")
                    lf.write(traceback.format_exc())
            except OSError:
                pass
        finally:
            job.finished_at = time.time()

    @staticmethod
    def _find_video(job: "Job") -> Optional[str]:
        roots = [job.output_dir]
        if job.realtime:
            # realtime writes under the MuseTalk results dir, not our output_dir
            roots.append(str(Path(job.musetalk_dir) / "results"))
        files: list[str] = []
        for root in roots:
            files += glob.glob(f"{root}/**/{job.id}.mp4", recursive=True)
            files += glob.glob(f"{root}/**/*.mp4", recursive=True)
        if not files:
            return None
        return sorted(set(files), key=os.path.getmtime)[-1]


def read_log(log_path: str, max_bytes: int = 200_000) -> str:
    """Return the tail of a job log (bounded so the page stays light)."""
    p = Path(log_path)
    if not p.exists():
        return ""
    size = p.stat().st_size
    with p.open("r", encoding="utf-8", errors="replace") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
            return "...(truncated)...\n" + f.read()
        return f.read()
