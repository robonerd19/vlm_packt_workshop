#!/usr/bin/env bash
# Stop the Go2 simulation or teleoperate it from the attached ROS container.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
project=unitree-go2-vlm-navigation
compose=(docker compose -p "$project" -f compose.yaml)
action="${1:-}"

usage() {
  cat <<'HELP'
Usage:
  bash scripts/go2_control.sh keyboard  # keyboard teleoperation
  bash scripts/go2_control.sh rqt       # rqt_robot_steering GUI
  bash scripts/go2_control.sh stop      # stop and remove the simulation

Start the simulation first with: bash scripts/go2_sim.sh start [cpu|gpu]
Both teleoperation options publish geometry_msgs/Twist on /cmd_vel.
HELP
}

if [[ "$action" == -h || "$action" == --help || -z "$action" ]]; then
  usage
  exit 0
fi

case "$action" in
  stop)
    exec bash scripts/go2_sim.sh stop
    ;;
  keyboard|rqt)
    command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
    docker compose version >/dev/null
    container_id="$("${compose[@]}" ps -q go2-simulation)"
    if [[ -z "$container_id" ]] || [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" != true ]]; then
      echo 'Go2 simulation is not running. Start it with scripts/go2_sim.sh first.' >&2
      exit 1
    fi
    ;;
  *)
    echo "Unknown action: $action" >&2
    usage >&2
    exit 2
    ;;
esac

case "$action" in
  keyboard)
    echo 'Keyboard teleoperation active. Use the teleop_twist_keyboard keys; press Ctrl+C to exit.'
    exec "${compose[@]}" exec -it go2-simulation bash -lc \
      'source /go2_ws/install/setup.bash && ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/cmd_vel'
    ;;
  rqt)
    echo 'Starting rqt_robot_steering. Use the GUI controls to command /cmd_vel; close the window to exit.'
    exec "${compose[@]}" exec -it go2-simulation bash -lc \
      'source /go2_ws/install/setup.bash && ros2 run rqt_robot_steering rqt_robot_steering --ros-args -p default_vx_min:=-0.6 -p default_vx_max:=0.6'
    ;;
esac
