#!/usr/bin/env bash
# Start the Go2 container without Gazebo, then launch Gazebo on demand.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
project=unitree-go2-vlm-navigation
action="${1:-}"
mode="${2:-cpu}"
world="${3:-default}"
compose=(docker compose -p "$project" -f compose.yaml -f compose.idle.yaml)

usage() {
  cat <<'HELP'
Usage:
  bash scripts/go2_container.sh start [cpu|gpu] [default|industrial|warehouse]  # start idle container
  bash scripts/go2_container.sh gazebo           # launch Gazebo in the container
  bash scripts/go2_container.sh status           # show container status
  bash scripts/go2_container.sh stop             # stop and remove container

Start the container first, then run the gazebo command. The CPU/GPU setting
and sensor configuration are selected when the container starts.
HELP
}

if [[ "$action" == -h || "$action" == --help || -z "$action" ]]; then
  usage
  exit 0
fi

case "$action" in
  start)
    [[ "$mode" == cpu || "$mode" == gpu ]] || { echo 'Mode must be cpu or gpu.' >&2; exit 2; }
    [[ $# -le 3 ]] || { echo 'Too many arguments for start.' >&2; exit 2; }
    [[ "$world" == default || "$world" == industrial || "$world" == warehouse ]] || { echo 'World must be default, industrial, or warehouse.' >&2; exit 2; }
    command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
    docker compose version >/dev/null
    [[ -n "${DISPLAY:-}" ]] || { echo 'Start this command from an X11 desktop session (DISPLAY is unset).' >&2; exit 1; }
    xauthority="${XAUTHORITY:-$HOME/.Xauthority}"
    [[ -r "$xauthority" ]] || { echo "X11 authorization file is unreadable: $xauthority" >&2; exit 1; }
    [[ -d /tmp/.X11-unix ]] || { echo 'The X11 socket directory /tmp/.X11-unix is unavailable.' >&2; exit 1; }
    running_id="$("${compose[@]}" ps -q go2-simulation)"
    if [[ -n "$running_id" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$running_id")" == true ]]; then
      echo 'The Go2 container is already running. Stop it before changing to the idle-container workflow.' >&2
      exit 1
    fi
    export HOST_XAUTHORITY="$xauthority"
    if [[ "$world" == industrial ]]; then
      export GO2_WORLD=/go2_ws/install/electrical_substation_world/share/electrical_substation_world/worlds/electrical_substation.world
      unset GO2_SPAWN_Z
      unset GO2_PUBLISH_MAP_TO_ODOM
    elif [[ "$world" == warehouse ]]; then
      export GO2_WORLD=/go2_ws/install/go2_warehouse_world/share/go2_warehouse_world/worlds/warehouse.sdf
      export GO2_SPAWN_Z=0.40
    else
      unset GO2_WORLD GO2_SPAWN_Z GO2_PUBLISH_MAP_TO_ODOM
    fi
    if [[ "$mode" == gpu ]]; then
      command -v nvidia-smi >/dev/null || { echo 'GPU mode requires NVIDIA drivers (nvidia-smi not found).' >&2; exit 1; }
      nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader
      export LIBGL_ALWAYS_SOFTWARE=0 GALLIUM_DRIVER=''
      export GO2_DISABLE_D455=false GO2_DISABLE_LIDAR_L1=false GO2_DISABLE_VELODYNE=false
      compose+=(-f compose.gpu.yaml)
    else
      export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe
      export GO2_DISABLE_D455=true GO2_DISABLE_LIDAR_L1=true
      export GO2_DISABLE_VELODYNE="${GO2_DISABLE_VELODYNE:-true}"
    fi
    "${compose[@]}" up -d --build go2-simulation
    "${compose[@]}" ps
    echo "Go2 container started idle in $mode mode with the $world world. Start Gazebo with: bash scripts/go2_container.sh gazebo"
    ;;
  gazebo)
    running_id="$("${compose[@]}" ps -q go2-simulation)"
    if [[ -z "$running_id" ]] || [[ "$(docker inspect -f '{{.State.Running}}' "$running_id")" != true ]]; then
      echo 'Go2 container is not running. Start it with scripts/go2_container.sh start [cpu|gpu].' >&2
      exit 1
    fi
    exec "${compose[@]}" exec go2-simulation bash -lc \
      'set -e; source /go2_ws/install/setup.bash; launch_args=(rviz:=false disable_d455:=${GO2_DISABLE_D455:-true} disable_lidar_l1:=${GO2_DISABLE_LIDAR_L1:-true} disable_velodyne_lidar:=${GO2_DISABLE_VELODYNE:-true} world_init_z:=${GO2_SPAWN_Z:-0.375} publish_map_to_odom:=${GO2_PUBLISH_MAP_TO_ODOM:-true}); if [[ -n "${GO2_WORLD:-}" ]]; then launch_args+=("world:=${GO2_WORLD}"); fi; exec ros2 launch unitree_go2_sim unitree_go2_launch.py "${launch_args[@]}"'
    ;;
  status)
    "${compose[@]}" ps
    ;;
  stop)
    exec "${compose[@]}" down --remove-orphans
    ;;
  *)
    echo "Unknown action: $action" >&2
    usage >&2
    exit 2
    ;;
esac
