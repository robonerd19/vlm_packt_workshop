#!/usr/bin/env bash
# Build, start, enter and stop the ROS 2 Jazzy container.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
action="${1:-}"
mode="${2:-gpu}"

usage() {
  cat <<'HELP'
Usage:
  bash scripts/ros2.sh build [gpu|cpu]   Build the ros2-jazzy:local image
  bash scripts/ros2.sh start [gpu|cpu]   Start the container in the background
  bash scripts/ros2.sh shell             Open a bash shell inside it (ROS sourced)
  bash scripts/ros2.sh logs | status | stop
HELP
}

[[ "$mode" == gpu || "$mode" == cpu ]] || { echo 'Mode must be gpu or cpu.' >&2; exit 2; }
compose=(docker compose -p ros2-jazzy -f compose.yaml)
[[ "$mode" == gpu ]] && compose+=(-f compose.gpu.yaml)

case "$action" in
  build) "${compose[@]}" build ;;
  start)
    # X11 is optional here: without it the container runs, only GUI tools fail.
    xauthority="${XAUTHORITY:-$HOME/.Xauthority}"
    [[ -n "${DISPLAY:-}" && -r "$xauthority" ]] && export HOST_XAUTHORITY="$xauthority" \
      || echo 'No X11 session found; RViz and other GUI tools will not open.' >&2
    docker image inspect ros2-jazzy:local >/dev/null 2>&1 || "${compose[@]}" build
    "${compose[@]}" up -d
    echo 'Started. Enter it with: bash scripts/ros2.sh shell'
    ;;
  shell) "${compose[@]}" exec ros2 bash ;;
  logs) "${compose[@]}" logs -f ;;
  status) "${compose[@]}" ps ;;
  stop) "${compose[@]}" down ;;
  -h|--help|'') usage ;;
  *) echo "Unknown action: $action" >&2; usage >&2; exit 2 ;;
esac
