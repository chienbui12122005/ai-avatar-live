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
from typing import Optional

from app.services.musetalk import run_musetalk

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
                lf.write(f"[job {job.id}] starting render (version={job.version})\n")
                lf.flush()
                run_musetalk(
                    musetalk_dir=job.musetalk_dir,
                    config_path=job.config_path,
                    output_dir=job.output_dir,
                    version=job.version,
                    log_file=lf,
                )

            job.video_path = self._find_video(job.output_dir)
            if not job.video_path:
                job.status = FAILED
                job.error = "Render finished but no .mp4 was produced (check the log)."
            else:
                job.status = DONE
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
    def _find_video(output_dir: str) -> Optional[str]:
        files = glob.glob(f"{output_dir}/**/*.mp4", recursive=True)
        if not files:
            return None
        return sorted(files, key=os.path.getmtime)[-1]


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
