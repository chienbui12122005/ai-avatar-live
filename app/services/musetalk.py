import subprocess
import sys
from typing import IO, Optional


def run_musetalk(
    musetalk_dir: str,
    config_path: str,
    output_dir: str,
    version: str = "v15",
    log_file: Optional[IO[str]] = None,
):
    """Run a MuseTalk inference render.

    Streams the subprocess output line-by-line so progress is visible while the
    render is still running. If ``log_file`` is given, output is written there
    (and flushed per line); otherwise it goes to stdout.

    Raises ``subprocess.CalledProcessError`` on a non-zero exit code.
    """
    if version == "v15":
        unet_model = "models/musetalkV15/unet.pth"
        unet_config = "models/musetalkV15/musetalk.json"
        version_arg = "v15"
    else:
        unet_model = "models/musetalk/pytorch_model.bin"
        unet_config = "models/musetalk/musetalk.json"
        version_arg = "v1"

    cmd = [
        "python", "-m", "scripts.inference",
        "--inference_config", str(config_path),
        "--result_dir", str(output_dir),
        "--unet_model_path", unet_model,
        "--unet_config", unet_config,
        "--version", version_arg,
        "--ffmpeg_path", "/usr/bin",
    ]

    sink = log_file or sys.stdout
    sink.write("$ " + " ".join(cmd) + "\n")
    sink.flush()

    proc = subprocess.Popen(
        cmd,
        cwd=musetalk_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
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
