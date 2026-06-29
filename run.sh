#!/bin/bash

set -e

echo "===== Activate micromamba ====="

export MAMBA_ROOT_PREFIX=/workspace/micromamba
eval "$(/workspace/bin/micromamba shell hook -s bash)"
micromamba activate musetalk

echo "===== Kill old services ====="

pkill -f jupyter || true
pkill -f "python app/main.py" || true

echo "===== Start AI Teacher Avatar Web ====="

cd /workspace/ai-teacher-avatar-web

python app/main.py
