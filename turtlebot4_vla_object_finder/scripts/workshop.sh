#!/usr/bin/env bash
# One-command setup, start, and stop for the Docker workshop demo.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

usage() {
  cat <<'HELP'
Usage:
  bash scripts/workshop.sh setup [cpu|gpu]
  bash scripts/workshop.sh start [cpu|gpu]
  bash scripts/workshop.sh stop

setup downloads/checks the VLM files and builds the ROS and selected inference images.
start launches the real warehouse demo with the selected inference device (CPU default).
stop shuts down workshop modes and the optional Gazebo GUI container.
GPU mode requires NVIDIA drivers and Docker GPU support.
HELP
}

command_name="${1:-}"
device="${2:-cpu}"
if [[ "$command_name" == -h || "$command_name" == --help || -z "$command_name" ]]; then
  usage
  exit 0
fi
if [[ "$command_name" != setup && "$command_name" != start && "$command_name" != stop ]]; then
  echo "Unknown command: $command_name" >&2
  usage >&2
  exit 2
fi
if [[ "$command_name" == stop ]]; then
  [[ $# -le 1 ]] || { echo 'stop takes no device argument.' >&2; exit 2; }
  docker compose -f compose.yaml --profile mock --profile simulation --profile external down
  if docker container inspect packt-vlm-workshop-gui >/dev/null 2>&1; then
    docker stop packt-vlm-workshop-gui >/dev/null
  fi
  echo 'Workshop demo stopped.'
  exit 0
fi
[[ $# -le 2 ]] || { echo 'Too many arguments.' >&2; usage >&2; exit 2; }
[[ "$device" == cpu || "$device" == gpu ]] || { echo 'Device must be cpu or gpu.' >&2; exit 2; }

if [[ "$command_name" == start ]]; then
  exec bash scripts/run_demo.sh --device "$device"
fi

for prerequisite in docker curl python3 sha256sum; do
  command -v "$prerequisite" >/dev/null || { echo "Missing prerequisite: $prerequisite" >&2; exit 1; }
done
docker compose version >/dev/null
if [[ "$device" == gpu ]]; then
  command -v nvidia-smi >/dev/null || { echo 'GPU setup requires NVIDIA drivers (nvidia-smi not found).' >&2; exit 1; }
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo 'Created .env from .env.example.'
fi
docker compose --profile simulation config -q
bash scripts/download_model.sh

compose=(docker compose -f compose.yaml)
if [[ "$device" == gpu ]]; then
  compose+=(-f compose.gpu.yaml)
  if [[ -z "${CUDA_ARCHITECTURES:-}" ]]; then
    CUDA_ARCHITECTURES="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | tr -d '. ' | sort -u | paste -sd ';' -)"
  fi
  [[ "$CUDA_ARCHITECTURES" =~ ^[0-9]+(\;[0-9]+)*$ ]] || {
    echo 'CUDA_ARCHITECTURES must contain numeric architectures separated by semicolons.' >&2
    exit 2
  }
  export CUDA_ARCHITECTURES
  echo "CUDA architectures: $CUDA_ARCHITECTURES"
fi

# Build sequentially to keep peak build memory down.
"${compose[@]}" --profile simulation build simulation
"${compose[@]}" --profile simulation build inference
echo "Setup complete for $device mode. Start it with: bash scripts/workshop.sh start $device"
