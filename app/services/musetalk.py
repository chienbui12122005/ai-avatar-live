import subprocess
from pathlib import Path


def run_musetalk(
    musetalk_dir: str,
    config_path: str,
    output_dir: str,
    version: str = "v15",
):
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

    subprocess.run(
        cmd,
        cwd=musetalk_dir,
        check=True,
    )
