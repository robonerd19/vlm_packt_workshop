#!/usr/bin/env bash
# Setup, start, and stop for the Franka VLM pick-and-place workshop.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
usage() { echo 'Usage: bash scripts/workshop.sh setup|start [cpu|gpu] | stop | logs | gui'; }
command_name="${1:-}"
device="${2:-cpu}"
[[ "$device" == cpu || "$device" == gpu ]] || { echo 'Device must be cpu or gpu.' >&2; exit 2; }
compose=(docker compose -f compose.yaml)
if [[ "$device" == gpu ]]; then
  command -v nvidia-smi >/dev/null || { echo 'GPU mode requires NVIDIA drivers (nvidia-smi not found).' >&2; exit 1; }
  CUDA_ARCHITECTURES="${CUDA_ARCHITECTURES:-$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | tr -d '. ' | sort -u | paste -sd ';' -)}"
  [[ "$CUDA_ARCHITECTURES" =~ ^[0-9]+(\;[0-9]+)*$ ]] || { echo 'Invalid CUDA_ARCHITECTURES.' >&2; exit 2; }
  export CUDA_ARCHITECTURES
  compose+=(-f compose.gpu.yaml)
fi
case "$command_name" in
  setup)
    bash scripts/download_model.sh models
    "${compose[@]}" build simulation
    "${compose[@]}" build inference ;;
  start)
    # Recreate inference so a cpu/gpu switch takes effect; keep a running simulation.
    "${compose[@]}" up -d --force-recreate --no-deps inference
    "${compose[@]}" up -d simulation application
    echo "Open http://127.0.0.1:${WEB_PORT:-8000} and wait for the Ready status." ;;
  stop) docker compose -f compose.yaml down ;;
  logs) docker compose -f compose.yaml logs -f --tail 50 ;;
  gui)
    # Gazebo GUI client joining the headless server; needs an X11 desktop.
    # X11 authorization is mounted read-only; no xhost access relaxation is needed.
    xauthority="${XAUTHORITY:-$HOME/.Xauthority}"
    [[ -r "$xauthority" ]] || { echo "X11 authorization file is unreadable: $xauthority" >&2; exit 1; }
    docker run --rm -it --network host -e DISPLAY -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-78}" \
      -e XAUTHORITY=/tmp/.Xauthority -v "$xauthority:/tmp/.Xauthority:ro" \
      -v /tmp/.X11-unix:/tmp/.X11-unix franka-vlm-ros:local gz sim -g ;;
  *) usage; [[ -z "$command_name" || "$command_name" == -h ]] && exit 0 || exit 2 ;;
esac
