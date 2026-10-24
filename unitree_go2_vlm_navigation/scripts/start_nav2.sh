#!/usr/bin/env bash
# Start Nav2 on the generated warehouse map, or online SLAM with Nav2.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
project=unitree-go2-vlm-navigation
mode="${1:-nav2}"
rviz="${2:-false}"
compose=(docker compose -p "$project" -f compose.yaml)
cleanup_nav() {
  "${compose[@]}" exec -T go2-simulation bash -lc \
    "pkill -INT -f '[r]os2 launch go2_warehouse_(nav2|slam)' || true" >/dev/null 2>&1 || true
}

usage() {
  cat <<'HELP'
Usage:
  bash scripts/start_nav2.sh [nav2|slam] [true|false]

The Go2 warehouse simulation must already be running with its Velodyne sensor
enabled. Restart it with map->odom TF disabled before starting Nav2 or SLAM:
  GO2_PUBLISH_MAP_TO_ODOM=false bash scripts/go2_sim.sh start gpu warehouse

For CPU mode, enable the Velodyne point cloud explicitly:
  GO2_PUBLISH_MAP_TO_ODOM=false GO2_DISABLE_VELODYNE=false \
    bash scripts/go2_sim.sh start cpu warehouse

Press Ctrl+C in this terminal to stop the selected navigation launch. If it
does not exit, use: bash scripts/stop_nav2.sh
HELP
}

if [[ "$mode" == -h || "$mode" == --help ]]; then
  usage
  exit 0
fi
[[ "$mode" == nav2 || "$mode" == slam ]] || { echo 'Mode must be nav2 or slam.' >&2; usage >&2; exit 2; }
[[ "$rviz" == true || "$rviz" == false ]] || { echo 'RViz option must be true or false.' >&2; exit 2; }

container_id="$("${compose[@]}" ps -q go2-simulation)"
if [[ -z "$container_id" ]] || [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" != true ]]; then
  echo 'Go2 simulation container is not running. Start the warehouse world first.' >&2
  exit 1
fi

trap cleanup_nav EXIT INT TERM
# Nav2 gives up for good if its costmap cannot find odom -> base_footprint at activation,
# so the launch below waits for that transform as well as for the Velodyne cloud.
"${compose[@]}" exec -T go2-simulation bash -lc \
  'set -e; source /go2_ws/install/setup.bash; \
   if [[ "${GO2_PUBLISH_MAP_TO_ODOM:-true}" != false ]]; then \
     echo "Disable the simulator static map->odom transform first: GO2_PUBLISH_MAP_TO_ODOM=false bash scripts/go2_sim.sh start [cpu|gpu] warehouse" >&2; exit 2; \
   fi; \
   if ! timeout 8 ros2 topic echo --once /velodyne_points/points >/dev/null 2>&1; then \
     echo "No Velodyne point cloud is arriving. Start GPU mode, or CPU mode with GO2_DISABLE_VELODYNE=false." >&2; exit 3; \
   fi; \
   if ! timeout 60 bash -c "until timeout 5 ros2 run tf2_ros tf2_echo odom base_footprint 2>/dev/null | grep -q -m1 Translation; do sleep 1; done"; then \
     echo "No odom -> base_footprint transform yet. Wait for the Go2 to stand, then retry." >&2; exit 4; \
   fi; \
   if [[ "'"$mode"'" == slam ]]; then \
     exec ros2 launch go2_warehouse_slam slam.launch.py; \
   else \
     exec ros2 launch go2_warehouse_nav2 nav2.launch.py rviz:="'"$rviz"'"; \
   fi'
