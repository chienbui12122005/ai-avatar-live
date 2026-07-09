#!/usr/bin/env python3
"""Mock MuseTalk worker for local testing without GPU.

This script simulates the API of `musetalk_worker.py` by generating dummy video
files using ffmpeg (color panels with the input audio track).
It is extremely useful for testing the full live stage web flow, segment chunking,
logs, and player transitions on a local development machine (like macOS).

Usage:
  python worker/mock_worker.py --port 8899

Then run the web app pointing to this mock worker:
  export MUSETALK_WORKER_URL=http://127.0.0.1:8899
  export MUSETALK_CHUNK_SECONDS=3
  python -m app.main
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8899
_render_lock = threading.Lock()


def _atomic_write_json(path: str, obj: dict):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def generate_mock_video(audio_path: str, out_video_path: str, color: str = "blue"):
    """Generate a mock video using ffmpeg's color source and the input audio."""
    os.makedirs(os.path.dirname(out_video_path), exist_ok=True)
    # Generates a solid color video with the input audio, auto-terminating when audio ends
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=640x480:r=25",
        "-i", audio_path,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        out_video_path
    ]
    subprocess.run(cmd, check=True)


def _split_audio(audio_path, out_dir, chunk_seconds):
    prefix = os.path.join(out_dir, "_seg_aud_")
    for old in glob.glob(prefix + "*.wav"):
        os.remove(old)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", audio_path,
        "-f", "segment", "-segment_time", str(chunk_seconds),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        f"{prefix}%03d.wav"
    ]
    subprocess.run(cmd, check=True)
    return sorted(glob.glob(prefix + "*.wav"))


def mock_render_chunked(audio_path, audio_id, out_dir, chunk_seconds):
    """Slice audio and generate color-alternating segments to simulate chunked render."""
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "segments.json")
    
    seg_audios = _split_audio(audio_path, out_dir, chunk_seconds)
    if not seg_audios:
        seg_audios = [audio_path]

    manifest = {"audio_id": audio_id, "fps": 25, "segments": [], "done": False}
    _atomic_write_json(manifest_path, manifest)

    colors = ["blue", "darkgreen", "purple", "darkred", "orange", "teal"]
    seg_files = []

    for i, seg_audio in enumerate(seg_audios):
        seg_name = f"{audio_id}_{i:03d}.mp4"
        seg_path = os.path.join(out_dir, seg_name)
        
        # Simulate GPU render delay (e.g. 1.0 seconds per segment)
        time.sleep(1.0)
        
        color = colors[i % len(colors)]
        generate_mock_video(seg_audio, seg_path, color=color)
        seg_files.append(seg_path)
        
        manifest["segments"].append({"index": i, "file": seg_name})
        _atomic_write_json(manifest_path, manifest)

    # Concat segments into one full clip
    full_path = os.path.join(out_dir, f"{audio_id}.mp4")
    list_path = os.path.join(out_dir, "_concat.txt")
    with open(list_path, "w") as f:
        for p in seg_files:
            f.write(f"file '{os.path.abspath(p)}'\n")
            
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", list_path,
        "-c", "copy", full_path
    ]
    subprocess.run(cmd, check=True)
    
    if os.path.exists(list_path):
        os.remove(list_path)
    for seg_audio in seg_audios:
        if seg_audio != audio_path and os.path.exists(seg_audio):
            os.remove(seg_audio)

    manifest["done"] = True
    manifest["video"] = f"{audio_id}.mp4"
    _atomic_write_json(manifest_path, manifest)
    return manifest, os.path.abspath(full_path)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            self._json(200, {
                "status": "ok", "device": "cpu (MOCK)",
                "version": "v15", "loaded": ["mock_avatar"],
            })
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        route = self.path.rstrip("/")
        try:
            req = self._read_json()
        except Exception as e:
            return self._json(400, {"error": f"bad request: {e}"})

        if route == "/render":
            return self._do_render(req)
        if route == "/render_chunked":
            return self._do_render_chunked(req)
        return self._json(404, {"error": "not found"})

    def _do_render(self, req):
        avatar_id = req.get("avatar_id")
        audio_path = req.get("audio_path")
        audio_id = req.get("audio_id") or "out"
        start_idx = int(req.get("start_idx") or 0)
        if not avatar_id or not audio_path:
            return self._json(400, {"error": "avatar_id and audio_path are required"})
        
        try:
            t0 = time.time()
            # Simple mock render: output video directly to profiles/results or tmp directory
            # For simplicity, we write it under results/mock_output/
            out = f"/tmp/mock_musetalk_out_{audio_id}.mp4"
            with _render_lock:
                generate_mock_video(audio_path, out, color="blue")
            
            self._json(200, {
                "video_path": os.path.abspath(out),
                "render_seconds": round(time.time() - t0, 2),
                "avatar_id": avatar_id,
                "next_idx": start_idx + 75,
            })
        except Exception as e:
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def _do_render_chunked(self, req):
        avatar_id = req.get("avatar_id")
        audio_path = req.get("audio_path")
        audio_id = req.get("audio_id") or "out"
        out_dir = req.get("out_dir")
        chunk_seconds = float(req.get("chunk_seconds") or 3)
        if not avatar_id or not audio_path or not out_dir:
            return self._json(400, {"error": "avatar_id, audio_path, out_dir required"})

        try:
            t0 = time.time()
            with _render_lock:
                manifest, full = mock_render_chunked(
                    audio_path, audio_id, out_dir, chunk_seconds
                )
            self._json(200, {
                "video_path": full,
                "segments": manifest["segments"],
                "render_seconds": round(time.time() - t0, 2),
                "avatar_id": avatar_id,
            })
        except Exception as e:
            self._json(500, {"error": f"{type(e).__name__}: {e}"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    # Quick check for ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        print("[MOCK WORKER ERROR] 'ffmpeg' command not found. Please install ffmpeg to run the mock worker locally.")
        sys.exit(1)

    print(f"[MOCK WORKER] starting on {args.host}:{args.port} ...")
    print("[MOCK WORKER] This mock worker does not use GPU and generates dummy color panels with your input audio.")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.serve_forever()


if __name__ == "__main__":
    main()
