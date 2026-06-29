"""Cached / realtime MuseTalk path (scripts.realtime_inference).

Phase 5 latency work. The realtime script supports an "avatar" cache:

  - preparation: True  -> extract landmarks/bbox/VAE latents/masks from the clip
                          once and persist them under the MuseTalk results dir.
  - preparation: False -> load that cache and run only the audio->frames step,
                          skipping the expensive face/latent preprocessing.

Models are still loaded per process (the script has no server mode), so this
removes the per-render preprocessing cost but not the model-load cost. The
persistent warm worker (worker/musetalk_worker.py) removes the model-load cost
too and keeps avatar materials in RAM.

Avatar cache location (relative to the MuseTalk cwd):
  v15: ./results/v15/avatars/{avatar_id}/
  v1 : ./results/avatars/{avatar_id}/
Output video: {avatar_dir}/vid_output/{audio_id}.mp4
"""

from pathlib import Path
from typing import IO, Optional

from app.services.musetalk import model_paths, stream_command


def write_config(
    config_path: str,
    avatar_id: str,
    video_path: str,
    bbox_shift: int,
    preparation: bool,
    audio_clips: Optional[dict] = None,
):
    """Write a realtime_inference YAML for a single avatar."""
    lines = [
        f"{avatar_id}:",
        f"  preparation: {'True' if preparation else 'False'}",
        f"  bbox_shift: {bbox_shift}",
        f"  video_path: {video_path}",
    ]
    if audio_clips:
        lines.append("  audio_clips:")
        for audio_id, path in audio_clips.items():
            lines.append(f"    {audio_id}: {path}")
    else:
        # Empty mapping: preparation still builds the cache; no clip is rendered.
        lines.append("  audio_clips: {}")
    Path(config_path).write_text("\n".join(lines) + "\n")


def _cmd(config_path: str, result_dir: str, version: str):
    unet_model, unet_config, version_arg = model_paths(version)
    # NOTE: do NOT pass --skip_save_images. In scripts.realtime_inference that flag
    # skips writing the combined frames, which also skips the ffmpeg mux step, so
    # no output .mp4 is produced. We need the frames written to get a video.
    return [
        "python", "-m", "scripts.realtime_inference",
        "--inference_config", str(config_path),
        "--result_dir", str(result_dir),
        "--unet_model_path", unet_model,
        "--unet_config", unet_config,
        "--version", version_arg,
        "--fps", "25",
        "--batch_size", "20",
        "--ffmpeg_path", "/usr/bin",
    ]


def avatar_dir(musetalk_dir: str, version: str, avatar_id: str) -> Path:
    base = Path(musetalk_dir) / "results"
    if version == "v15":
        base = base / "v15"
    return base / "avatars" / avatar_id


def expected_output(musetalk_dir: str, version: str, avatar_id: str, audio_id: str) -> Path:
    return avatar_dir(musetalk_dir, version, avatar_id) / "vid_output" / f"{audio_id}.mp4"


def is_prepared_on_disk(musetalk_dir: str, version: str, avatar_id: str) -> bool:
    """True if the avatar cache already exists (latents extracted)."""
    return (avatar_dir(musetalk_dir, version, avatar_id) / "latents.pt").exists()


def clear_avatar(musetalk_dir: str, version: str, avatar_id: str):
    """Remove any existing avatar cache so preparation rebuilds without prompting.

    scripts.realtime_inference calls input() ("re-create? y/n") if the avatar dir
    already exists during preparation — which would hang/EOF in a subprocess.
    """
    import shutil
    d = avatar_dir(musetalk_dir, version, avatar_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def prepare_avatar(
    musetalk_dir: str,
    config_path: str,
    result_dir: str,
    version: str,
    avatar_id: str,
    video_path: str,
    bbox_shift: int = 0,
    log_file: Optional[IO[str]] = None,
):
    """Build & cache the avatar from a clip (no clip rendered)."""
    clear_avatar(musetalk_dir, version, avatar_id)
    write_config(config_path, avatar_id, video_path, bbox_shift, preparation=True, audio_clips=None)
    stream_command(_cmd(config_path, result_dir, version), musetalk_dir, log_file)


def render_realtime(
    musetalk_dir: str,
    config_path: str,
    result_dir: str,
    version: str,
    avatar_id: str,
    video_path: str,
    audio_path: str,
    audio_id: str,
    bbox_shift: int = 0,
    log_file: Optional[IO[str]] = None,
):
    """Render one audio clip against a (cached) avatar. Returns expected mp4 path."""
    write_config(
        config_path, avatar_id, video_path, bbox_shift,
        preparation=False, audio_clips={audio_id: audio_path},
    )
    stream_command(_cmd(config_path, result_dir, version), musetalk_dir, log_file)
    return str(expected_output(musetalk_dir, version, avatar_id, audio_id))
