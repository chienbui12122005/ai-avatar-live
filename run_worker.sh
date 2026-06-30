#!/bin/bash
# Start the warm MuseTalk worker: loads the models ONCE and serves renders over
# HTTP so the web app's renders skip the cold-start model load every time.
# Point the web app at it with:  export MUSETALK_WORKER_URL=http://127.0.0.1:8899

set -e

echo "===== Activate micromamba ====="
export MAMBA_ROOT_PREFIX=/workspace/micromamba
eval "$(/workspace/bin/micromamba shell hook -s bash)"
micromamba activate musetalk

echo "===== Kill old worker ====="
pkill -f "musetalk_worker.py" || true

MUSETALK_DIR="${MUSETALK_DIR:-/workspace/MuseTalk}"
VERSION="${MUSETALK_WORKER_VERSION:-v15}"
WORKER_PORT="${MUSETALK_WORKER_PORT:-8899}"
WORKER_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$VERSION" = "v15" ]; then
  UNET_MODEL="models/musetalkV15/unet.pth"
  UNET_CONFIG="models/musetalkV15/musetalk.json"
else
  UNET_MODEL="models/musetalk/pytorch_model.bin"
  UNET_CONFIG="models/musetalk/musetalk.json"
fi

echo "===== Start warm MuseTalk worker (version=$VERSION, port=$WORKER_PORT) ====="
python "$WORKER_DIR/worker/musetalk_worker.py" \
  --musetalk-dir "$MUSETALK_DIR" \
  --version "$VERSION" \
  --unet-model-path "$UNET_MODEL" \
  --unet-config "$UNET_CONFIG" \
  --whisper-dir "models/whisper" \
  --ffmpeg-path "/usr/bin" \
  --batch-size "${MUSETALK_WORKER_BATCH:-8}" \
  --port "$WORKER_PORT"
