#!/usr/bin/env bash
# Start Qwen2-VL inference and the VLM object finder (browser UI on port 8000).
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
project=unitree-go2-vlm-navigation
mode="${1:-gpu}"
sim=(docker compose -p "$project" -f compose.yaml)
vlm=(docker compose -p "$project-vlm" -f compose.vlm.yaml)
cleanup_vlm() {
  "${sim[@]}" exec -T go2-simulation bash -lc \
    "pkill -INT -f '[r]os2 launch vlm_nav go2.launch.py' || true" >/dev/null 2>&1 || true
}

usage() {
  cat <<'HELP'
Usage:
  bash scripts/start_vlm.sh [gpu|cpu]   # start inference + VLM navigator and web UI
  bash scripts/start_vlm.sh stop        # stop the navigator and inference server

Needs the warehouse simulation with the D455 enabled and Nav2 running:
  GO2_PUBLISH_MAP_TO_ODOM=false bash scripts/go2_sim.sh start gpu warehouse
  bash scripts/start_nav2.sh nav2
Then open http://127.0.0.1:8000 and type e.g. "go to the green dumpster".
HELP
}

case "$mode" in
  -h|--help) usage; exit 0 ;;
  stop) cleanup_vlm; "${vlm[@]}" down --remove-orphans; exit 0 ;;
  gpu) vlm+=(-f compose.vlm.gpu.yaml) ;;
  cpu) ;;
  *) echo 'Mode must be gpu, cpu, or stop.' >&2; usage >&2; exit 2 ;;
esac
models="${MODEL_DIR:-../turtlebot4_vla_object_finder/models}"
[[ -f "$models/Qwen2-VL-2B-Instruct-Q4_K_M.gguf" && -f "$models/mmproj-Qwen2-VL-2B-Instruct-f16.gguf" ]] || {
  echo "Model files missing in $models. Download them with: bash ../turtlebot4_vla_object_finder/scripts/download_model.sh" >&2; exit 1; }

container_id="$("${sim[@]}" ps -q go2-simulation)"
if [[ -z "$container_id" ]] || [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" != true ]]; then
  echo 'Go2 simulation container is not running. Start the warehouse world first.' >&2
  exit 1
fi
"${vlm[@]}" up -d --wait inference

trap cleanup_vlm EXIT INT TERM
"${sim[@]}" exec -T go2-simulation bash -lc \
  'set -e; source /go2_ws/install/setup.bash; \
   if ! timeout 8 ros2 topic echo --once --field encoding /d455/depth_image >/dev/null 2>&1; then \
     echo "No D455 depth image is arriving. Start GPU mode, or CPU mode with GO2_DISABLE_D455=false." >&2; exit 3; \
   fi; \
   exec ros2 launch vlm_nav go2.launch.py'
