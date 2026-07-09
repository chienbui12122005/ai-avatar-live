"""Warm MuseTalk worker — keeps the models loaded and avatar materials in RAM.

Why: scripts.realtime_inference (and our subprocess realtime path) reloads VAE +
UNet + Whisper on every invocation — tens of seconds of cold start per render.
This process loads them ONCE and stays up, then renders cached avatars on demand
over a tiny HTTP API. Per-render cost drops to roughly the audio->frames work.

It is intentionally dependency-light: only Python's stdlib http.server plus what
MuseTalk itself already needs (torch, transformers, the `musetalk` package). It
must run with the MuseTalk repo as the working dir so `from musetalk...` imports
resolve and the `./results/{version}/avatars/...` cache paths line up with what
the prepare step wrote.

The render loop mirrors scripts.realtime_inference.Avatar.inference() so the
output is identical; only the model/material lifetime differs and the avatar
"pose" index can continue across calls (needed for seamless chunk streaming).

Endpoints:
  GET  /health   -> {"status","device","version","loaded":[...]}

  POST /render          {avatar_id, audio_path, audio_id, fps?}
       -> {"video_path"}                    # whole clip, one mp4

  POST /render_chunked  {avatar_id, audio_path, audio_id, out_dir,
                         chunk_seconds?, fps?}
       -> {"video_path", "segments":[...]}  # low latency: splits the audio,
          renders each segment, and writes/updates out_dir/segments.json as each
          segment lands so a player can start on segment 0 while the rest render.
          The avatar pose index continues across segments (no jump at seams).

Run (inside the MuseTalk env, e.g. via run_worker.sh):
  python worker/musetalk_worker.py \
      --musetalk-dir /workspace/MuseTalk --version v15 \
      --unet-model-path models/musetalkV15/unet.pth \
      --unet-config models/musetalkV15/musetalk.json \
      --whisper-dir models/whisper --port 8899
"""

import argparse
import copy
import glob
import json
import os
import pickle
import queue
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# Filled in by main() after model load. Module globals so the inference code reads
# like the original script.
ARGS = None
device = None
vae = unet = pe = None
timesteps = None
audio_processor = None
whisper = None
weight_dtype = None
read_imgs = datagen = get_image_blending = None

_render_lock = threading.Lock()   # one GPU render at a time
_avatars = {}                     # avatar_id -> WorkerAvatar (materials in RAM)


def _avatar_base(avatar_id: str) -> str:
    if ARGS.version == "v15":
        return f"./results/{ARGS.version}/avatars/{avatar_id}"
    return f"./results/avatars/{avatar_id}"


def _atomic_write_json(path: str, obj: dict):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


class WorkerAvatar:
    """Holds one prepared avatar's materials in memory and renders audio clips.

    Loads only the cached (preparation=False) materials — preparation/build is
    still done by the prepare step (scripts.realtime_inference, one-time).
    """

    def __init__(self, avatar_id: str):
        self.avatar_id = avatar_id
        self.avatar_path = _avatar_base(avatar_id)
        self.full_imgs_path = f"{self.avatar_path}/full_imgs"
        self.coords_path = f"{self.avatar_path}/coords.pkl"
        self.latents_out_path = f"{self.avatar_path}/latents.pt"
        self.video_out_path = f"{self.avatar_path}/vid_output/"
        self.mask_out_path = f"{self.avatar_path}/mask"
        self.mask_coords_path = f"{self.avatar_path}/mask_coords.pkl"
        if not os.path.exists(self.avatar_path):
            raise FileNotFoundError(
                f"avatar '{avatar_id}' not prepared (missing {self.avatar_path})"
            )
        os.makedirs(self.video_out_path, exist_ok=True)
        self._load_materials()

    def _load_materials(self):
        import torch
        self.input_latent_list_cycle = torch.load(self.latents_out_path)
        with open(self.coords_path, "rb") as f:
            self.coord_list_cycle = pickle.load(f)
        imgs = glob.glob(os.path.join(self.full_imgs_path, "*.[jpJP][pnPN]*[gG]"))
        imgs = sorted(imgs, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
        self.frame_list_cycle = read_imgs(imgs)
        with open(self.mask_coords_path, "rb") as f:
            self.mask_coords_list_cycle = pickle.load(f)
        masks = glob.glob(os.path.join(self.mask_out_path, "*.[jpJP][pnPN]*[gG]"))
        masks = sorted(masks, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
        self.mask_list_cycle = read_imgs(masks)
        self.cycle_len = len(self.coord_list_cycle)

    def _process_frames(self, res_frame_queue, video_len, start_idx, tmp_dir):
        """Consume generated mouth frames, blend onto the cyclic body frames, and
        write per-segment PNGs numbered 0..video_len-1 for ffmpeg. The body pose
        index continues from start_idx so segments don't jump back to frame 0."""
        import cv2
        import numpy as np
        produced = 0
        while produced < video_len:
            try:
                res_frame = res_frame_queue.get(block=True, timeout=1)
            except queue.Empty:
                continue
            pose = (start_idx + produced) % self.cycle_len
            bbox = self.coord_list_cycle[pose]
            ori_frame = copy.deepcopy(self.frame_list_cycle[pose])
            x1, y1, x2, y2 = bbox
            try:
                res_frame = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
            except Exception:
                produced += 1
                continue
            mask = self.mask_list_cycle[pose]
            mask_crop_box = self.mask_coords_list_cycle[pose]
            combine_frame = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop_box)
            cv2.imwrite(f"{tmp_dir}/{str(produced).zfill(8)}.bmp", combine_frame)
            produced += 1

    def render(self, audio_path, out_vid_path, fps, start_idx=0):
        """Render one audio file to out_vid_path. Returns the next pose index so a
        caller can chain segments seamlessly."""
        import numpy as np
        import torch
        tmp_dir = f"{self.avatar_path}/tmp_{os.getpid()}_{threading.get_ident()}"
        os.makedirs(tmp_dir, exist_ok=True)
        try:
            # torch.no_grad is ESSENTIAL: without it autograd retains activations
            # across every UNet/VAE forward and the warm process balloons to OOM
            # (the original Avatar.inference is decorated @torch.no_grad()).
            with torch.no_grad():
                whisper_input_features, librosa_length = audio_processor.get_audio_feature(
                    audio_path, weight_dtype=weight_dtype
                )
                whisper_chunks = audio_processor.get_whisper_chunk(
                    whisper_input_features, device, weight_dtype, whisper, librosa_length,
                    fps=fps,
                    audio_padding_length_left=ARGS.audio_padding_length_left,
                    audio_padding_length_right=ARGS.audio_padding_length_right,
                )
                video_num = len(whisper_chunks)
                res_frame_queue = queue.Queue()
                t = threading.Thread(
                    target=self._process_frames,
                    args=(res_frame_queue, video_num, start_idx, tmp_dir),
                )
                t.start()

                gen = datagen(whisper_chunks, self.input_latent_list_cycle, ARGS.batch_size)
                for whisper_batch, latent_batch in gen:
                    audio_feature_batch = pe(whisper_batch.to(device))
                    latent_batch = latent_batch.to(device=device, dtype=unet.model.dtype)
                    pred_latents = unet.model(
                        latent_batch, timesteps, encoder_hidden_states=audio_feature_batch
                    ).sample
                    pred_latents = pred_latents.to(device=device, dtype=vae.vae.dtype)
                    recon = vae.decode_latents(pred_latents)
                    for res_frame in recon:
                        res_frame_queue.put(res_frame)
            t.join()

            tmp_video = f"{tmp_dir}/temp.mp4"
            os.system(
                f"ffmpeg -y -v warning -r {fps} -f image2 -i {tmp_dir}/%08d.bmp "
                f"-vcodec libx264 -preset superfast -vf format=yuv420p -crf 18 {tmp_video}"
            )
            os.makedirs(os.path.dirname(out_vid_path), exist_ok=True)
            os.system(
                f"ffmpeg -y -v warning -i {tmp_video} -i {audio_path} "
                f"-c:v copy -c:a aac -shortest {out_vid_path}"
            )
            return start_idx + video_num
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def get_avatar(avatar_id: str) -> WorkerAvatar:
    av = _avatars.get(avatar_id)
    if av is None:
        av = WorkerAvatar(avatar_id)   # raises FileNotFoundError if not prepared
        _avatars[avatar_id] = av
    return av


def _split_audio(audio_path, out_dir, chunk_seconds):
    """Split the wav into ~chunk_seconds pieces; return the ordered list."""
    prefix = os.path.join(out_dir, "_seg_aud_")
    for old in glob.glob(prefix + "*.wav"):
        os.remove(old)
    os.system(
        f"ffmpeg -y -v warning -i {audio_path} -f segment "
        f"-segment_time {chunk_seconds} -c copy {prefix}%03d.wav"
    )
    return sorted(glob.glob(prefix + "*.wav"))


def render_chunked(avatar_id, audio_path, audio_id, out_dir, chunk_seconds, fps):
    """Render the audio as ordered segment mp4s, updating out_dir/segments.json as
    each segment completes, then concat a full {audio_id}.mp4. Returns the manifest."""
    av = get_avatar(avatar_id)
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "segments.json")
    seg_audios = _split_audio(audio_path, out_dir, chunk_seconds)
    if not seg_audios:
        seg_audios = [audio_path]  # fall back to a single segment

    manifest = {"audio_id": audio_id, "fps": fps, "segments": [], "done": False}
    _atomic_write_json(manifest_path, manifest)

    start_idx = 0
    seg_files = []
    for i, seg_audio in enumerate(seg_audios):
        seg_name = f"{audio_id}_{i:03d}.mp4"
        seg_path = os.path.join(out_dir, seg_name)
        start_idx = av.render(seg_audio, seg_path, fps, start_idx=start_idx)
        seg_files.append(seg_path)
        manifest["segments"].append({"index": i, "file": seg_name})
        _atomic_write_json(manifest_path, manifest)  # publish progress immediately

    # Concat segments into one full clip so /video and downloads still work.
    full_path = os.path.join(out_dir, f"{audio_id}.mp4")
    list_path = os.path.join(out_dir, "_concat.txt")
    with open(list_path, "w") as f:
        for p in seg_files:
            f.write(f"file '{os.path.abspath(p)}'\n")
    os.system(f"ffmpeg -y -v warning -f concat -safe 0 -i {list_path} -c copy {full_path}")
    os.remove(list_path)
    for seg_audio in seg_audios:
        if seg_audio != audio_path and os.path.exists(seg_audio):
            os.remove(seg_audio)

    manifest["done"] = True
    manifest["video"] = f"{audio_id}.mp4"
    _atomic_write_json(manifest_path, manifest)
    return manifest, os.path.abspath(full_path)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quieter logs
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
                "status": "ok", "device": str(device),
                "version": ARGS.version, "loaded": list(_avatars.keys()),
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
        fps = int(req.get("fps") or ARGS.fps)
        if not avatar_id or not audio_path:
            return self._json(400, {"error": "avatar_id and audio_path are required"})
        if not os.path.exists(audio_path):
            return self._json(400, {"error": f"audio not found: {audio_path}"})
        try:
            t0 = time.time()
            with _render_lock:
                av = get_avatar(avatar_id)
                out = os.path.join(av.video_out_path, audio_id + ".mp4")
                av.render(audio_path, out, fps, start_idx=0)
            if not os.path.exists(out):
                return self._json(500, {"error": "render produced no video"})
            self._json(200, {
                "video_path": os.path.abspath(out),
                "render_seconds": round(time.time() - t0, 2),
                "avatar_id": avatar_id,
            })
        except FileNotFoundError as e:
            self._json(404, {"error": str(e)})
        except Exception as e:
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def _do_render_chunked(self, req):
        avatar_id = req.get("avatar_id")
        audio_path = req.get("audio_path")
        audio_id = req.get("audio_id") or "out"
        out_dir = req.get("out_dir")
        fps = int(req.get("fps") or ARGS.fps)
        chunk_seconds = float(req.get("chunk_seconds") or 3)
        if not avatar_id or not audio_path or not out_dir:
            return self._json(400, {"error": "avatar_id, audio_path, out_dir required"})
        if not os.path.exists(audio_path):
            return self._json(400, {"error": f"audio not found: {audio_path}"})
        try:
            t0 = time.time()
            with _render_lock:
                manifest, full = render_chunked(
                    avatar_id, audio_path, audio_id, out_dir, chunk_seconds, fps
                )
            self._json(200, {
                "video_path": full,
                "segments": manifest["segments"],
                "render_seconds": round(time.time() - t0, 2),
                "avatar_id": avatar_id,
            })
        except FileNotFoundError as e:
            self._json(404, {"error": str(e)})
        except Exception as e:
            self._json(500, {"error": f"{type(e).__name__}: {e}"})


def _add_ffmpeg_to_path(ffmpeg_path):
    import subprocess
    def ok():
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return True
        except Exception:
            return False
    if not ok() and ffmpeg_path:
        sep = ";" if sys.platform == "win32" else ":"
        os.environ["PATH"] = f"{ffmpeg_path}{sep}{os.environ.get('PATH', '')}"


def main():
    global ARGS, device, vae, unet, pe, timesteps, audio_processor, whisper, weight_dtype
    global read_imgs, datagen, get_image_blending

    p = argparse.ArgumentParser()
    p.add_argument("--musetalk-dir", required=True)
    p.add_argument("--version", default="v15", choices=["v1", "v15"])
    p.add_argument("--gpu-id", type=int, default=0)
    p.add_argument("--vae-type", default="sd-vae")
    p.add_argument("--unet-config", default="./models/musetalkV15/musetalk.json")
    p.add_argument("--unet-model-path", default="./models/musetalkV15/unet.pth")
    p.add_argument("--whisper-dir", default="./models/whisper")
    p.add_argument("--ffmpeg-path", default="/usr/bin")
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--batch-size", type=int, default=20)
    p.add_argument("--audio-padding-length-left", type=int, default=2)
    p.add_argument("--audio-padding-length-right", type=int, default=2)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8899)
    ARGS = p.parse_args()

    # Run with the MuseTalk repo as cwd so imports + ./results paths resolve.
    os.chdir(ARGS.musetalk_dir)
    sys.path.insert(0, ARGS.musetalk_dir)
    _add_ffmpeg_to_path(ARGS.ffmpeg_path)

    import torch
    from transformers import WhisperModel
    from musetalk.utils.utils import datagen as _datagen, load_all_model
    from musetalk.utils.preprocessing import read_imgs as _read_imgs
    from musetalk.utils.blending import get_image_blending as _blend
    from musetalk.utils.audio_processor import AudioProcessor

    datagen = _datagen
    read_imgs = _read_imgs
    get_image_blending = _blend

    device = torch.device(f"cuda:{ARGS.gpu_id}" if torch.cuda.is_available() else "cpu")
    print(f"[worker] loading models on {device} ...", flush=True)
    vae, unet, pe = load_all_model(
        unet_model_path=ARGS.unet_model_path, vae_type=ARGS.vae_type,
        unet_config=ARGS.unet_config, device=device,
    )
    timesteps = torch.tensor([0], device=device)
    pe = pe.half().to(device)
    vae.vae = vae.vae.half().to(device)
    unet.model = unet.model.half().to(device)
    audio_processor = AudioProcessor(feature_extractor_path=ARGS.whisper_dir)
    weight_dtype = unet.model.dtype
    whisper = WhisperModel.from_pretrained(ARGS.whisper_dir)
    whisper = whisper.to(device=device, dtype=weight_dtype).eval()
    whisper.requires_grad_(False)
    print("[worker] models loaded; ready.", flush=True)

    srv = ThreadingHTTPServer((ARGS.host, ARGS.port), Handler)
    print(f"[worker] listening on {ARGS.host}:{ARGS.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
