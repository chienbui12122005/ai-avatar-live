import os
import shutil
import subprocess
import uuid
import glob
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import uvicorn

from app.services.musetalk import run_musetalk

load_dotenv()

MUSETALK_DIR = os.getenv("MUSETALK_DIR", "/workspace/MuseTalk")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/workspace/avatars")
RESULT_DIR = os.getenv("RESULT_DIR", "/workspace/outputs")
DEFAULT_AUDIO = os.getenv("DEFAULT_AUDIO", f"{MUSETALK_DIR}/data/audio/eng.wav")
APP_PORT = int(os.getenv("APP_PORT", "8888"))

Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(RESULT_DIR).mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Teacher Avatar Web")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "musetalk_dir": MUSETALK_DIR,
        "upload_dir": UPLOAD_DIR,
        "result_dir": RESULT_DIR,
        "default_audio": DEFAULT_AUDIO,
    }


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <body style="font-family:Arial;max-width:900px;margin:40px auto;">
      <h1>AI Teacher Avatar Web</h1>
      <p><a href="/videos">View generated videos</a></p>

      <form action="/generate" method="post" enctype="multipart/form-data">
        <p>Teacher image/video:<br><input type="file" name="teacher_file" required></p>
        <p>Audio wav/mp3 optional:<br><input type="file" name="audio_file"><br>
        <small>If blank, default audio will be used.</small></p>

        <p>bbox_shift:<br><input type="number" name="bbox_shift" value="0"></p>

        <p>Version:<br>
          <select name="version">
            <option value="v15">v1.5</option>
            <option value="v1">v1.0</option>
          </select>
        </p>

        <button type="submit" style="font-size:18px;padding:10px 20px;">
          Generate Avatar Video
        </button>
      </form>
    </body>
    </html>
    """


@app.post("/generate")
async def generate(
    teacher_file: UploadFile = File(...),
    audio_file: Optional[UploadFile] = File(None),
    bbox_shift: int = Form(0),
    version: str = Form("v15"),
):
    job_id = str(uuid.uuid4())[:8]
    job_dir = Path(UPLOAD_DIR) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    teacher_ext = Path(teacher_file.filename).suffix or ".mp4"
    teacher_path = job_dir / f"teacher{teacher_ext}"

    with teacher_path.open("wb") as f:
        shutil.copyfileobj(teacher_file.file, f)

    if audio_file and audio_file.filename:
        audio_ext = Path(audio_file.filename).suffix or ".wav"
        audio_path = job_dir / f"audio{audio_ext}"
        with audio_path.open("wb") as f:
            shutil.copyfileobj(audio_file.file, f)
    else:
        audio_path = Path(DEFAULT_AUDIO)

    config_path = job_dir / "config.yaml"
    config_path.write_text(
        f"""task_0:
  video_path: {teacher_path}
  audio_path: {audio_path}
  bbox_shift: {bbox_shift}
"""
    )

    output_dir = Path(RESULT_DIR) / job_id

    try:
        run_musetalk(
            musetalk_dir=MUSETALK_DIR,
            config_path=str(config_path),
            output_dir=str(output_dir),
            version=version,
        )
    except subprocess.CalledProcessError as e:
        return JSONResponse(
            {"error": "MuseTalk failed", "returncode": e.returncode},
            status_code=500,
        )

    return HTMLResponse(f'<meta http-equiv="refresh" content="0; url=/result/{job_id}">')


@app.get("/video/{job_id}")
def video(job_id: str):
    files = glob.glob(f"{RESULT_DIR}/{job_id}/**/*.mp4", recursive=True)
    if not files:
        return JSONResponse({"error": "video not found"}, status_code=404)

    video_path = sorted(files, key=os.path.getmtime)[-1]
    return FileResponse(video_path, media_type="video/mp4")


@app.get("/result/{job_id}", response_class=HTMLResponse)
def result(job_id: str):
    return f"""
    <html>
    <body style="font-family:Arial;max-width:900px;margin:40px auto;">
      <h2>Generated Video</h2>
      <video width="720" controls autoplay>
        <source src="/video/{job_id}" type="video/mp4">
      </video>
      <p><a href="/video/{job_id}" download>Download MP4</a></p>
      <p><a href="/videos">All videos</a> | <a href="/">Generate another</a></p>
    </body>
    </html>
    """


@app.get("/videos", response_class=HTMLResponse)
def videos():
    files = glob.glob(f"{RESULT_DIR}/**/*.mp4", recursive=True)
    files = sorted(files, key=os.path.getmtime, reverse=True)

    rows = []
    for f in files:
        rel = os.path.relpath(f, RESULT_DIR)
        job_id = rel.split(os.sep)[0]
        size_mb = os.path.getsize(f) / 1024 / 1024
        rows.append(
            f"""
            <tr>
              <td>{job_id}</td>
              <td>{rel}</td>
              <td>{size_mb:.1f} MB</td>
              <td>
                <a href="/result/{job_id}">View</a> |
                <a href="/video/{job_id}" download>Download</a>
              </td>
            </tr>
            """
        )

    body = "\n".join(rows) if rows else '<tr><td colspan="4">No videos yet</td></tr>'

    return f"""
    <html>
    <body style="font-family:Arial;max-width:1100px;margin:40px auto;">
      <h2>Generated Videos</h2>
      <p><a href="/">Generate new video</a></p>
      <table border="1" cellpadding="8" cellspacing="0">
        <tr><th>Job ID</th><th>File</th><th>Size</th><th>Action</th></tr>
        {body}
      </table>
    </body>
    </html>
    """


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=APP_PORT)
