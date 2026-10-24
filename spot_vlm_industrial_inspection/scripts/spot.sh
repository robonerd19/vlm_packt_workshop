#!/usr/bin/env bash
# Build, start, inspect and stop the Spot VLM industrial inspection demo.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
action="${1:-}"
mode="${2:-gpu}"

usage() {
  cat <<'HELP'
Usage:
  bash scripts/spot.sh build   [gpu|cpu]   Build the ROS/Gazebo image
  bash scripts/spot.sh start   [gpu|cpu]   Start Gazebo (window opens) and the VLM server
  bash scripts/spot.sh inspect [gpu|cpu]   Run the inspection route; report lands in ./reports
  bash scripts/spot.sh teleop              Drive Spot with the keyboard (/cmd_vel)
  bash scripts/spot.sh logs | status | stop
HELP
}

[[ "$mode" == gpu || "$mode" == cpu ]] || { echo 'Mode must be gpu or cpu.' >&2; exit 2; }
compose=(docker compose -p spot-vlm-inspection -f compose.yaml)
[[ "$mode" == gpu ]] && compose+=(-f compose.gpu.yaml)

case "$action" in
  build)
    "${compose[@]}" build simulation
    ;;
  start)
    [[ -n "${DISPLAY:-}" ]] || { echo 'Run from an X11 desktop session (DISPLAY is unset).' >&2; exit 1; }
    xauthority="${XAUTHORITY:-$HOME/.Xauthority}"
    [[ -r "$xauthority" ]] || { echo "X11 authorization file is unreadable: $xauthority" >&2; exit 1; }
    export HOST_XAUTHORITY="$xauthority"
    echo 'Starting Ollama; the first run downloads qwen2.5vl:3b (3.2 GB). Progress: bash scripts/spot.sh logs'
    "${compose[@]}" up -d simulation inference
    echo 'Gazebo is starting. Wait for Spot to stand, then: bash scripts/spot.sh inspect'
    ;;
  inspect)
    mkdir -p reports
    export HOST_UID="$(id -u)" HOST_GID="$(id -g)"
    "${compose[@]}" --profile inspect run --rm inspector
    echo "Reports: $root/reports/<timestamp>/report.md"
    ;;
  teleop)
    "${compose[@]}" exec simulation bash -lc \
      'source /spot_ws/install/setup.bash && ros2 run teleop_twist_keyboard teleop_twist_keyboard'
    ;;
  logs) "${compose[@]}" logs -f ;;
  status) "${compose[@]}" ps ;;
  stop) "${compose[@]}" --profile inspect down ;;
  -h|--help|'') usage ;;
  *) echo "Unknown action: $action" >&2; usage >&2; exit 2 ;;
esac
