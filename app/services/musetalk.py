import subprocess
import sys
from typing import IO, Optional


def model_paths(version: str):
    """Return (unet_model_path, unet_config, version_arg) for a MuseTalk version."""
    if version == "v15":
        return "models/musetalkV15/unet.pth", "models/musetalkV15/musetalk.json", "v15"
    return "models/musetalk/pytorch_model.bin", "models/musetalk/musetalk.json", "v1"


def stream_command(cmd: list, cwd: str, log_file: Optional[IO[str]] = None):
    """Run a subprocess, streaming its combined output line-by-line to ``log_file``
    (or stdout) so progress is visible while it runs.

    Raises ``subprocess.CalledProcessError`` on a non-zero exit code.
    """
    sink = log_file or sys.stdout
    sink.write("$ " + " ".join(cmd) + "\n")
    sink.flush()

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,  # never block on an interactive input() prompt
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sink.write(line)
        sink.flush()

    returncode = proc.wait()
    if returncode != 0:
        sink.write(f"\n[exit code {returncode}]\n")
        sink.flush()
        raise subprocess.CalledProcessError(returncode, cmd)


def run_musetalk(
    musetalk_dir: str,
    config_path: str,
    output_dir: str,
    version: str = "v15",
    log_file: Optional[IO[str]] = None,
):
    """Run a batch MuseTalk inference render (scripts.inference).

    This path loads the models and re-preprocesses the avatar every run. For a
    cached/faster path see app/services/musetalk_realtime.py.
    """
    unet_model, unet_config, version_arg = model_paths(version)
    cmd = [
        "python", "-m", "scripts.inference",
        "--inference_config", str(config_path),
        "--result_dir", str(output_dir),
        "--unet_model_path", unet_model,
        "--unet_config", unet_config,
        "--version", version_arg,
        "--ffmpeg_path", "/usr/bin",
    ]
    stream_command(cmd, musetalk_dir, log_file)
