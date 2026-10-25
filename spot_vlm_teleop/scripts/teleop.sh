#!/usr/bin/env bash
# Build, start and stop the Spot web teleop + VLM demo.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
action="${1:-}"
mode="${2:-gpu}"

usage() {
  cat <<'HELP'
Usage:
  bash scripts/teleop.sh build [gpu|cpu]   Build the image (and the Spot inspection image it uses)
  bash scripts/teleop.sh start [gpu|cpu]   Start Gazebo, Ollama and the web page on http://127.0.0.1:8000
  bash scripts/teleop.sh logs | status | stop
HELP
}

[[ "$mode" == gpu || "$mode" == cpu ]] || { echo 'Mode must be gpu or cpu.' >&2; exit 2; }
compose=(docker compose -p spot-vlm-teleop -f compose.yaml)
# FROM a local image: a docker-container buildx builder cannot see it, the docker driver can.
export BUILDX_BUILDER=default
[[ "$mode" == gpu ]] && compose+=(-f compose.gpu.yaml)

build() {
  if ! docker image inspect spot-inspection-ros:local >/dev/null 2>&1; then
    echo 'Building the Spot inspection image this project builds on...'
    bash ../spot_vlm_industrial_inspection/scripts/spot.sh build "$mode"
  fi
  "${compose[@]}" build simulation
}

case "$action" in
  build) build ;;
  start)
    [[ -n "${DISPLAY:-}" ]] || { echo 'Run from an X11 desktop session (DISPLAY is unset).' >&2; exit 1; }
    xauthority="${XAUTHORITY:-$HOME/.Xauthority}"
    [[ -r "$xauthority" ]] || { echo "X11 authorization file is unreadable: $xauthority" >&2; exit 1; }
    export HOST_XAUTHORITY="$xauthority"
    docker image inspect spot-vlm-teleop:local >/dev/null 2>&1 || build
    echo 'Starting Gazebo and Ollama; the first run downloads qwen2.5vl:3b (3.2 GB).'
    "${compose[@]}" up -d simulation inference web
    echo 'Open http://127.0.0.1:8000 once Spot stands (the page waits for the model to load).'
    ;;
  logs) "${compose[@]}" logs -f ;;
  status) "${compose[@]}" ps ;;
  stop) "${compose[@]}" down ;;
  -h|--help|'') usage ;;
  *) echo "Unknown action: $action" >&2; usage >&2; exit 2 ;;
esac
