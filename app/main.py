import glob
import os
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
from app.profiles import ProfileStore

load_dotenv()

MUSETALK_DIR = os.getenv("MUSETALK_DIR", "/workspace/MuseTalk")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/workspace/avatars")
RESULT_DIR = os.getenv("RESULT_DIR", "/workspace/outputs")
PROFILE_DIR = os.getenv("PROFILE_DIR", "/workspace/profiles")
LOG_DIR = os.getenv("LOG_DIR", "/workspace/logs")
DEFAULT_AUDIO = os.getenv("DEFAULT_AUDIO", f"{MUSETALK_DIR}/data/audio/eng.wav")
APP_PORT = int(os.getenv("APP_PORT", "8888"))

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
        profile=used_profile,
        behavior=used_behavior,
    )
    registry.submit(job)
    return RedirectResponse(f"/job/{job_id}", status_code=303)


def _error_page(msg: str) -> HTMLResponse:
    return HTMLResponse(
        T.page("Error", f'<h1>Cannot start render</h1><div class="card">{T.esc(msg)}'
        '<p style="margin-top:12px;"><a href="/">← Back</a></p></div>'),
        status_code=400,
    )


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
# Video management
# --------------------------------------------------------------------------- #
@app.get("/videos", response_class=HTMLResponse)
def videos():
    files = glob.glob(f"{RESULT_DIR}/**/*.mp4", recursive=True)
    files = sorted(files, key=os.path.getmtime, reverse=True)
    rows = []
    for f in files:
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


@app.post("/profiles/{slug}/delete")
def profiles_delete(slug: str):
    profiles.delete(os.path.basename(slug))
    return RedirectResponse("/profiles", status_code=303)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=APP_PORT)
