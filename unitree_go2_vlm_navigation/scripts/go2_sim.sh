#!/usr/bin/env bash
# Build, run, inspect, and stop the Unitree Go2 Gazebo simulation.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
project=unitree-go2-vlm-navigation
action="${1:-}"
mode="${2:-cpu}"
world="${3:-default}"

usage() {
  cat <<'HELP'
Usage:
  bash scripts/go2_sim.sh build [cpu|gpu]
  bash scripts/go2_sim.sh start [cpu|gpu] [default|industrial|warehouse]
  bash scripts/go2_sim.sh stop
  bash scripts/go2_sim.sh status
  bash scripts/go2_sim.sh logs
  bash scripts/go2_sim.sh rviz

CPU mode uses Mesa software rendering and disables the heavy depth and lidar
sensors. GPU mode uses NVIDIA rendering and enables the full sensor set.
The Gazebo window requires an active X11 desktop session.
HELP
}

if [[ "$action" == -h || "$action" == --help || -z "$action" ]]; then
  usage
  exit 0
fi
case "$action" in
  build|start)
    [[ "$mode" == cpu || "$mode" == gpu ]] || { echo 'Mode must be cpu or gpu.' >&2; exit 2; }
    if [[ "$action" == build && $# -gt 2 ]] || [[ "$action" == start && $# -gt 3 ]]; then
      echo "Too many arguments for $action." >&2
      exit 2
    fi
    if [[ "$action" == start && "$world" != default && "$world" != industrial && "$world" != warehouse ]]; then
      echo 'World must be default, industrial, or warehouse.' >&2
      exit 2
    fi
    ;;
  stop|status|logs|rviz) [[ $# -le 1 ]] || { echo "$action does not take a mode." >&2; exit 2; } ;;
  *) echo "Unknown action: $action" >&2; usage >&2; exit 2 ;;
esac

compose=(docker compose -p "$project" -f compose.yaml)
if [[ "$mode" == gpu && ( "$action" == build || "$action" == start ) ]]; then
  compose+=(-f compose.gpu.yaml)
fi

case "$action" in
  build)
    command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
    docker compose version >/dev/null
    "${compose[@]}" build go2-simulation
    ;;
  start)
    command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
    docker compose version >/dev/null
    [[ -n "${DISPLAY:-}" ]] || { echo 'Start this command from an X11 desktop session (DISPLAY is unset).' >&2; exit 1; }
    xauthority="${XAUTHORITY:-$HOME/.Xauthority}"
    [[ -r "$xauthority" ]] || { echo "X11 authorization file is unreadable: $xauthority" >&2; exit 1; }
    [[ -d /tmp/.X11-unix ]] || { echo 'The X11 socket directory /tmp/.X11-unix is unavailable.' >&2; exit 1; }
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
    else
      export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe
      export GO2_DISABLE_D455="${GO2_DISABLE_D455:-true}" GO2_DISABLE_LIDAR_L1=true
      export GO2_DISABLE_VELODYNE="${GO2_DISABLE_VELODYNE:-true}"
    fi
    "${compose[@]}" up -d --build go2-simulation
    "${compose[@]}" ps
    echo "Go2 simulation started in $mode mode with the $world world. Follow output with: bash scripts/go2_sim.sh logs"
    ;;
  stop)
    docker compose -p "$project" -f compose.yaml down --remove-orphans
    docker compose -p "$project-vlm" -f compose.vlm.yaml down --remove-orphans
    echo 'Go2 simulation stopped.'
    ;;
  status)
    docker compose -p "$project" -f compose.yaml ps
    ;;
  logs)
    docker compose -p "$project" -f compose.yaml logs -f --tail 100 go2-simulation
    ;;
  rviz)
    docker compose -p "$project" -f compose.yaml exec go2-simulation \
      bash -lc 'source /go2_ws/install/setup.bash && rviz2 -d /go2_ws/install/unitree_go2_sim/share/unitree_go2_sim/rviz/rviz.rviz'
    ;;
esac
