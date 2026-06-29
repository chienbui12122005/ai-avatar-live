import glob
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
import uvicorn

from app import templates as T
from app.jobs import JobRegistry, read_log
from app.profiles import ProfileStore, avatar_id as make_avatar_id
from app.services import musetalk_worker_client as worker

load_dotenv()

MUSETALK_DIR = os.getenv("MUSETALK_DIR", "/workspace/MuseTalk")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/workspace/avatars")
RESULT_DIR = os.getenv("RESULT_DIR", "/workspace/outputs")
PROFILE_DIR = os.getenv("PROFILE_DIR", "/workspace/profiles")
LOG_DIR = os.getenv("LOG_DIR", "/workspace/logs")
DEFAULT_AUDIO = os.getenv("DEFAULT_AUDIO", f"{MUSETALK_DIR}/data/audio/eng.wav")
APP_PORT = int(os.getenv("APP_PORT", "8888"))
# >0 enables streaming chunk rendering (lower time-to-first-frame) via the worker.
CHUNK_SECONDS = float(os.getenv("MUSETALK_CHUNK_SECONDS", "0") or "0")


def _chunked_for(realtime: bool) -> bool:
    return bool(realtime and CHUNK_SECONDS > 0 and worker.worker_enabled())

for d in (UPLOAD_DIR, RESULT_DIR, PROFILE_DIR, LOG_DIR):
    Path(d).mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Teacher Avatar Web")
registry = JobRegistry(max_workers=1)
profiles = ProfileStore(PROFILE_DIR)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "musetalk_dir": MUSETALK_DIR,
        "upload_dir": UPLOAD_DIR,
        "result_dir": RESULT_DIR,
        "profile_dir": PROFILE_DIR,
        "log_dir": LOG_DIR,
        "default_audio": DEFAULT_AUDIO,
        "jobs": len(registry.all()),
        "worker_url": worker.worker_url() or None,
        "worker": worker.health(),  # None if disabled/unreachable
    }


# --------------------------------------------------------------------------- #
# Generate
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def home():
    return T.home(profiles.all())


@app.post("/generate")
async def generate(
    teacher_file: Optional[UploadFile] = File(None),
    audio_file: Optional[UploadFile] = File(None),
    bbox_shift: int = Form(0),
    version: str = Form("v15"),
    profile: str = Form(""),
    behavior: str = Form("idle"),
):
    job_id = os.urandom(4).hex()
    job_dir = Path(UPLOAD_DIR) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Resolve the teacher source: an uploaded clip overrides the profile.
    teacher_name = ""
    used_profile = ""
    used_behavior = ""
    if teacher_file and teacher_file.filename:
        ext = Path(teacher_file.filename).suffix or ".mp4"
        teacher_path = job_dir / f"teacher{ext}"
        with teacher_path.open("wb") as f:
            shutil.copyfileobj(teacher_file.file, f)
        teacher_name = teacher_file.filename
    elif profile:
        clip = profiles.clip_path(profile, behavior)
        if not clip:
            return _error_page(
                f'Profile "{profile}" has no clip for behavior "{behavior}". '
                'Upload one on the Profiles page.'
            )
        teacher_path = Path(clip)
        used_profile, used_behavior = profile, behavior
        teacher_name = Path(clip).name
    else:
        return _error_page("Pick a profile + behavior, or upload a teacher clip.")

    # Audio: uploaded or default.
    if audio_file and audio_file.filename:
        ext = Path(audio_file.filename).suffix or ".wav"
        audio_path = job_dir / f"audio{ext}"
        with audio_path.open("wb") as f:
            shutil.copyfileobj(audio_file.file, f)
        audio_name = audio_file.filename
    else:
        audio_path = Path(DEFAULT_AUDIO)
        audio_name = ""

    # Use the cached realtime path when this profile+behavior has been prepared.
    realtime = bool(used_profile and profiles.is_prepared(used_profile, used_behavior))
    av_id = make_avatar_id(used_profile, used_behavior) if realtime else ""

    job = _start_job(
        job_id, job_dir, teacher_path, teacher_name, audio_path, audio_name,
        version, bbox_shift, used_profile, used_behavior, realtime, av_id,
        _chunked_for(realtime),
    )
    return RedirectResponse(f"/job/{job.id}", status_code=303)


def _start_job(
    job_id, job_dir, teacher_path, teacher_name, audio_path, audio_name,
    version, bbox_shift, profile, behavior, realtime=False, av_id="", chunked=False,
):
    """Enqueue a render. Returns the Job.

    Batch path writes the scripts.inference config here; the realtime path lets
    the realtime service write its own per-run YAML (config_path points at it).
    """
    if realtime:
        config_path = job_dir / "realtime.yaml"
    else:
        config_path = job_dir / "config.yaml"
        config_path.write_text(
            f"task_0:\n"
            f"  video_path: {teacher_path}\n"
            f"  audio_path: {audio_path}\n"
            f"  bbox_shift: {bbox_shift}\n"
        )
    job = registry.create(
        id=job_id,
        musetalk_dir=MUSETALK_DIR,
        config_path=str(config_path),
        output_dir=str(Path(RESULT_DIR) / job_id),
        log_path=str(Path(LOG_DIR) / f"{job_id}.log"),
        version=version,
        teacher_name=teacher_name,
        audio_name=audio_name,
        bbox_shift=bbox_shift,
        profile=profile,
        behavior=behavior,
        realtime=realtime,
        chunked=chunked,
        chunk_seconds=CHUNK_SECONDS or 3.0,
        avatar_id=av_id,
        video_path=str(teacher_path),
        audio_path=str(audio_path),
    )
    registry.submit(job)
    return job


# Map an AI "intent" to one of the avatar behaviors (profile clip).
INTENT_TO_BEHAVIOR = {
    "explain": "explain", "teach": "explain", "answer": "explain", "lecture": "explain",
    "question": "question", "ask": "question", "quiz": "question",
    "greet": "smile", "greeting": "smile", "welcome": "smile", "happy": "smile",
    "praise": "smile", "smile": "smile",
    "idle": "idle", "wait": "idle", "listen": "idle",
}


def intent_to_behavior(intent: str) -> str:
    return INTENT_TO_BEHAVIOR.get((intent or "").strip().lower(), "explain")


def _error_page(msg: str) -> HTMLResponse:
    return HTMLResponse(
        T.page("Error", f'<h1>Cannot start render</h1><div class="card">{T.esc(msg)}'
        '<p style="margin-top:12px;"><a href="/">← Back</a></p></div>'),
        status_code=400,
    )


# --------------------------------------------------------------------------- #
# Programmatic API (for the AI assistant: TTS audio + intent -> video)
# --------------------------------------------------------------------------- #
@app.post("/api/generate")
async def api_generate(
    audio: UploadFile = File(...),
    profile: str = Form(...),
    intent: str = Form(""),
    behavior: str = Form(""),
    version: str = Form("v15"),
    bbox_shift: int = Form(0),
):
    """Accept a TTS audio clip + a teacher profile and return job info as JSON.

    `behavior` wins if given; otherwise it is derived from `intent`. The teacher
    source is the profile's clip for that behavior (uploaded once, reused).
    """
    if not profiles.exists(profile):
        return JSONResponse({"error": f"unknown profile: {profile}"}, status_code=404)

    chosen = behavior.strip() or intent_to_behavior(intent)
    clip = profiles.clip_path(profile, chosen)
    if not clip:
        return JSONResponse(
            {"error": f'profile "{profile}" has no clip for behavior "{chosen}"',
             "behavior": chosen},
            status_code=400,
        )

    job_id = os.urandom(4).hex()
    job_dir = Path(UPLOAD_DIR) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(audio.filename or "audio.wav").suffix or ".wav"
    audio_path = job_dir / f"audio{ext}"
    with audio_path.open("wb") as f:
        shutil.copyfileobj(audio.file, f)

    realtime = profiles.is_prepared(profile, chosen)
    av_id = make_avatar_id(profile, chosen) if realtime else ""
    chunked = _chunked_for(realtime)
    job = _start_job(
        job_id, job_dir, Path(clip), Path(clip).name, audio_path,
        audio.filename or "", version, bbox_shift, profile, chosen, realtime, av_id, chunked,
    )
    return {
        "job_id": job.id,
        "status": job.status,
        "profile": profile,
        "behavior": chosen,
        "realtime": realtime,
        "chunked": chunked,
        "status_url": f"/job/{job.id}/status",
        "job_url": f"/job/{job.id}",
        "segments_url": f"/job/{job.id}/segments",
        "video_url": f"/video/{job.id}",
    }


# --------------------------------------------------------------------------- #
# Job status + live log
# --------------------------------------------------------------------------- #
@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_page(job_id: str):
    job = registry.get(job_id)
    if not job:
        return _error_page(f"Unknown job: {job_id}")
    return T.job_page(job)


@app.get("/job/{job_id}/status")
def job_status(job_id: str):
    job = registry.get(job_id)
    if not job:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    data = job.to_dict()
    data["status_badge"] = T.status_badge(job.status)
    data["log"] = read_log(job.log_path)
    return data


# --------------------------------------------------------------------------- #
# Video serving
# --------------------------------------------------------------------------- #
def _resolve_video(job_id: str) -> Optional[str]:
    job = registry.get(job_id)
    if job and job.video_path and os.path.exists(job.video_path):
        return job.video_path
    files = glob.glob(f"{RESULT_DIR}/{job_id}/**/*.mp4", recursive=True)
    if not files:
        return None
    return sorted(files, key=os.path.getmtime)[-1]


@app.get("/video/{job_id}")
def video(job_id: str):
    path = _resolve_video(job_id)
    if not path:
        return JSONResponse({"error": "video not found"}, status_code=404)
    return FileResponse(path, media_type="video/mp4")


@app.get("/result/{job_id}", response_class=HTMLResponse)
def result(job_id: str):
    return T.result_page(job_id)


# --------------------------------------------------------------------------- #
# Live avatar stage (point OBS Browser Source here -> Virtual Camera -> Zoom)
# --------------------------------------------------------------------------- #
@app.get("/profile-clip/{slug}/{behavior}")
def profile_clip(slug: str, behavior: str):
    clip = profiles.clip_path(os.path.basename(slug), os.path.basename(behavior))
    if not clip:
        return JSONResponse({"error": "clip not found"}, status_code=404)
    return FileResponse(clip)


def _manifest(job_id: str) -> Optional[dict]:
    p = Path(RESULT_DIR) / os.path.basename(job_id) / "segments.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


@app.get("/api/latest")
def api_latest(profile: str = "", since: float = 0.0):
    """Most recent playable render for the live page. A normal render is playable
    when done; a chunked render is playable as soon as its first segment lands
    (while still rendering) so the stage can start early. Returns null if nothing
    newer than `since`."""
    for job in registry.all():  # already newest-first
        if profile and job.profile != profile:
            continue

        chunked = False
        ts = 0.0
        if job.chunked:
            man = _manifest(job.id)
            if man and man.get("segments"):
                chunked = True
                ts = job.started_at or 0.0
        if not chunked:
            if job.status != "done" or not job.video_path:
                continue
            ts = job.finished_at or 0.0

        if since and ts <= since:
            return {"job": None}
        return {
            "job": {
                "job_id": job.id,
                "chunked": chunked,
                "video_url": f"/video/{job.id}",
                "segments_url": f"/job/{job.id}/segments",
                "finished_at": ts,
                "behavior": job.behavior,
                "profile": job.profile,
            }
        }
    return {"job": None}


@app.get("/job/{job_id}/segments")
def job_segments(job_id: str):
    """Ordered ready segments for a chunked render (grows while rendering)."""
    man = _manifest(job_id)
    if not man:
        return {"segments": [], "done": False}
    segs = [{"index": s["index"], "url": f"/segment/{job_id}/{s['index']}"}
            for s in man.get("segments", [])]
    return {"segments": segs, "done": bool(man.get("done"))}


@app.get("/segment/{job_id}/{index}")
def segment(job_id: str, index: int):
    safe = os.path.basename(job_id)
    path = Path(RESULT_DIR) / safe / f"{safe}_{index:03d}.mp4"
    if not path.exists():
        return JSONResponse({"error": "segment not found"}, status_code=404)
    return FileResponse(str(path), media_type="video/mp4")


@app.get("/live", response_class=HTMLResponse)
def live(profile: str = ""):
    slug = profile or (profiles.all()[0]["slug"] if profiles.all() else "")
    if not slug:
        return _error_page("No profiles yet — create one on the Profiles page first.")
    return T.live_page(slug)


# --------------------------------------------------------------------------- #
# Video management
# --------------------------------------------------------------------------- #
@app.get("/videos", response_class=HTMLResponse)
def videos():
    files = glob.glob(f"{RESULT_DIR}/**/*.mp4", recursive=True)
    files = sorted(files, key=os.path.getmtime, reverse=True)
    rows = []
    for f in files:
        # Hide chunked-stream segment parts ({jobid}_000.mp4); show the full clip only.
        if re.match(r".+_\d{3}\.mp4$", os.path.basename(f)):
            continue
        rel = os.path.relpath(f, RESULT_DIR)
        rows.append(
            {
                "job_id": rel.split(os.sep)[0],
                "file": rel,
                "size": f"{os.path.getsize(f) / 1024 / 1024:.1f} MB",
                "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(f))),
            }
        )
    return T.videos_page(rows)


@app.post("/videos/{job_id}/delete")
def delete_video(job_id: str):
    # job_id is a route segment; strip any path tricks before touching disk
    safe = os.path.basename(job_id)
    for base in (RESULT_DIR, UPLOAD_DIR):
        target = Path(base) / safe
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    log = Path(LOG_DIR) / f"{safe}.log"
    if log.exists():
        log.unlink()
    return RedirectResponse("/videos", status_code=303)


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #
@app.get("/profiles", response_class=HTMLResponse)
def profiles_list():
    return T.profiles_page(profiles.all())


@app.post("/profiles")
def profiles_create(name: str = Form(...)):
    profiles.create(name)
    return RedirectResponse("/profiles", status_code=303)


@app.post("/profiles/{slug}/upload")
async def profiles_upload(slug: str, behavior: str = Form(...), clip: UploadFile = File(...)):
    try:
        profiles.save_clip(slug, behavior, clip.file, clip.filename or "clip.mp4")
    except ValueError as e:
        return _error_page(str(e))
    return RedirectResponse("/profiles", status_code=303)


@app.post("/profiles/{slug}/prepare")
def profiles_prepare(slug: str, behavior: str = Form(...)):
    """Build & cache the avatar for one behavior clip so later renders are faster
    (skips face detection + latent extraction). Runs as a background job."""
    clip = profiles.clip_path(slug, behavior)
    if not clip:
        return _error_page(f'Profile "{slug}" has no clip for behavior "{behavior}".')

    job_id = os.urandom(4).hex()
    job_dir = Path(UPLOAD_DIR) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    av_id = make_avatar_id(slug, behavior)

    job = registry.create(
        id=job_id,
        musetalk_dir=MUSETALK_DIR,
        config_path=str(job_dir / "realtime.yaml"),
        output_dir=str(Path(RESULT_DIR) / job_id),
        log_path=str(Path(LOG_DIR) / f"{job_id}.log"),
        version="v15",
        kind="prepare",
        realtime=True,
        avatar_id=av_id,
        video_path=clip,
        profile=slug,
        behavior=behavior,
        teacher_name=Path(clip).name,
        on_success=lambda j: profiles.mark_prepared(slug, behavior, av_id),
    )
    registry.submit(job)
    return RedirectResponse(f"/job/{job_id}", status_code=303)


@app.post("/profiles/{slug}/delete")
def profiles_delete(slug: str):
    profiles.delete(os.path.basename(slug))
    return RedirectResponse("/profiles", status_code=303)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=APP_PORT)
