import os
import shutil
import subprocess
import uuid
import glob
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import uvicorn

MUSETALK_DIR = "/workspace/MuseTalk"
BASE = MUSETALK_DIR
UPLOAD_DIR = "/workspace/avatar_uploads"
RESULT_DIR = "/workspace/outputs/avatar_web"
DEFAULT_AUDIO = f"{MUSETALK_DIR}/data/audio/eng.wav"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

app = FastAPI(title="MuseTalk Avatar Web")

HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>MuseTalk Avatar Web</title>
<style>
body{
    font-family:Arial;
    max-width:900px;
    margin:40px auto;
}
input,select{
    font-size:18px;
}
button{
    padding:10px 20px;
    font-size:18px;
}
</style>
</head>
<body>

<h1>MuseTalk Avatar Web App</h1>\n<p><a href="/videos">View generated videos</a></p>

<form action="/generate" method="post" enctype="multipart/form-data">

<p>
Teacher image/video:<br>
<input type="file" name="teacher_file" required>
</p>

<p>
Audio wav (optional):<br>
<input type="file" name="audio_file"><br>
<small>
Nếu bỏ trống sẽ dùng:
<code>data/audio/eng.wav</code>
</small>
</p>

<p>
bbox_shift:<br>
<input type="number" name="bbox_shift" value="0">
</p>

<p>
Version:<br>
<select name="version">
<option value="v15">v1.5</option>
<option value="v1">v1.0</option>
</select>
</p>

<button type="submit">
Generate Avatar Video
</button>

</form>

</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


@app.get("/video/{job_id}")
def get_video(job_id:str):
    files = glob.glob(
        f"{RESULT_DIR}/{job_id}/**/*.mp4",
        recursive=True
    )

    if not files:
        return JSONResponse(
            {"error":"video not found"},
            status_code=404
        )

    video = sorted(
        files,
        key=os.path.getmtime
    )[-1]

    return FileResponse(
        video,
        media_type="video/mp4"
    )


@app.get("/result/{job_id}",
         response_class=HTMLResponse)
def result(job_id:str):

    return f"""
    <html>
    <body style="
        font-family:Arial;
        max-width:900px;
        margin:40px auto;
    ">

    <h2>Generated Video</h2>

    <video
        width="720"
        controls
        autoplay>
        <source
          src="/video/{job_id}"
          type="video/mp4">
    </video>

    <br><br>

    <a href="/video/{job_id}"
       download>
       Download MP4
    </a>

    <br><br>

    <a href="/">Back</a>

    </body>
    </html>
    """



@app.get("/videos", response_class=HTMLResponse)
def list_videos():
    mp4_files = glob.glob(f"{RESULT_DIR}/**/*.mp4", recursive=True)
    mp4_files = sorted(mp4_files, key=os.path.getmtime, reverse=True)

    rows = []
    for f in mp4_files:
        rel = os.path.relpath(f, RESULT_DIR)
        parts = rel.split(os.sep)
        job_id = parts[0]
        size_mb = os.path.getsize(f) / 1024 / 1024
        mtime = os.path.getmtime(f)

        rows.append(f"""
        <tr>
          <td>{job_id}</td>
          <td>{rel}</td>
          <td>{size_mb:.1f} MB</td>
          <td>
            <a href="/result/{job_id}">View</a> |
            <a href="/video/{job_id}" download>Download</a>
          </td>
        </tr>
        """)

    body = "\\n".join(rows) if rows else "<tr><td colspan='4'>No videos yet</td></tr>"

    return f"""
    <html>
    <body style="font-family:Arial; max-width:1100px; margin:40px auto;">
      <h2>Generated Videos</h2>
      <p><a href="/">Generate new video</a></p>
      <table border="1" cellpadding="8" cellspacing="0">
        <tr>
          <th>Job ID</th>
          <th>File</th>
          <th>Size</th>
          <th>Action</th>
        </tr>
        {body}
      </table>
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

    job_dir = os.path.join(
        UPLOAD_DIR,
        job_id
    )

    os.makedirs(
        job_dir,
        exist_ok=True
    )

    teacher_ext = (
        os.path.splitext(
            teacher_file.filename
        )[1]
        or ".png"
    )

    teacher_path = os.path.join(
        job_dir,
        "teacher"+teacher_ext
    )

    with open(
        teacher_path,
        "wb"
    ) as f:
        shutil.copyfileobj(
            teacher_file.file,
            f
        )

    if audio_file and audio_file.filename:

        audio_ext = (
            os.path.splitext(
                audio_file.filename
            )[1]
            or ".wav"
        )

        audio_path = os.path.join(
            job_dir,
            "audio"+audio_ext
        )

        with open(
            audio_path,
            "wb"
        ) as f:
            shutil.copyfileobj(
                audio_file.file,
                f
            )
    else:
        audio_path = DEFAULT_AUDIO

    config_path = os.path.join(
        job_dir,
        "config.yaml"
    )

    with open(
        config_path,
        "w"
    ) as f:

        f.write(
f"""task_0:
  video_path: {teacher_path}
  audio_path: {audio_path}
  bbox_shift: {bbox_shift}
"""
        )

    output_dir = os.path.join(
        RESULT_DIR,
        job_id
    )

    if version=="v15":

        unet_model="models/musetalkV15/unet.pth"
        unet_config="models/musetalkV15/musetalk.json"
        version_arg="v15"

    else:

        unet_model="models/musetalk/pytorch_model.bin"
        unet_config="models/musetalk/musetalk.json"
        version_arg="v1"

    cmd = [
        "python",
        "-m",
        "scripts.inference",

        "--inference_config",
        config_path,

        "--result_dir",
        output_dir,

        "--unet_model_path",
        unet_model,

        "--unet_config",
        unet_config,

        "--version",
        version_arg,

        "--ffmpeg_path",
        "/usr/bin",
    ]

    try:

        subprocess.run(
            cmd,
            cwd=MUSETALK_DIR,
            check=True
        )

    except subprocess.CalledProcessError as e:

        return JSONResponse(
            {
                "error":"MuseTalk failed",
                "returncode":e.returncode
            },
            status_code=500
        )

    return HTMLResponse(
f"""
<html>
<head>
<meta http-equiv="refresh"
      content="0; url=/result/{job_id}">
</head>
<body>
Redirecting...
</body>
</html>
"""
    )


if __name__=="__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8888
    )
