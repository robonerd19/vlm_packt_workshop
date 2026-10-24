#!/usr/bin/env bash
# Select inference backend without resetting an existing simulation/localization.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
device=cpu
usage() {
  cat <<'HELP'
Usage: bash scripts/run_demo.sh [--device cpu|gpu]
  --device cpu  CPU-only inference (default).
  --device gpu  NVIDIA CUDA inference; requires driver and Docker GPU access.
The ROS image and the Ollama model must already be prepared with
bash scripts/workshop.sh setup. Existing ROS services retain
their current image and robot pose. Stop all demo modes before switching from mock.
HELP
}
while (($#)); do
  case "$1" in
    --device) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; device="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ "$device" == cpu || "$device" == gpu ]] || { echo '--device must be cpu or gpu.' >&2; exit 2; }
compose=(docker compose -f "$root/compose.yaml")
if [[ "$device" == gpu ]]; then
  command -v nvidia-smi >/dev/null || { echo 'GPU mode requires NVIDIA drivers (nvidia-smi not found).' >&2; exit 1; }
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
  compose+=(-f "$root/compose.gpu.yaml")
fi
# Refuse another ROS/model owner before mutating the selected services.
for service in mock external; do
  if [[ -n "$(docker compose -f "$root/compose.yaml" --profile "$service" ps --status running -q "$service")" ]]; then
    echo "Stop the running $service mode before starting simulation." >&2
    exit 1
  fi
done
# A backend switch must not interrupt a running navigation/inference request.
# Obtain WEB_PORT through Compose rather than sourcing .env as shell code.
port="$("${compose[@]}" --profile simulation config --format json | python3 -c 'import json,sys; c=json.load(sys.stdin); print(next(v.split(":=",1)[1] for v in c["services"]["application"]["command"] if v.startswith("web_port:=")))')"
if [[ -n "$(docker compose -f "$root/compose.yaml" --profile simulation ps --status running -q application)" ]]; then
  state="$(curl -fsS --max-time 5 "http://127.0.0.1:$port/status")" || { echo 'Cannot confirm application idle; backend switch aborted.' >&2; exit 1; }
  if ! python3 -c 'import json,sys; s=json.load(sys.stdin); sys.exit(0 if not s.get("busy",True) and s.get("stationary",False) else 1)' <<< "$state"; then
    echo 'A demo operation is active or the robot is moving. Cancel it and wait for confirmation, then retry.' >&2
    exit 1
  fi
fi
"${compose[@]}" --profile simulation up -d --no-deps inference
"${compose[@]}" --profile simulation up -d --no-recreate simulation application
echo "Started $device inference. Open http://127.0.0.1:$port and wait for ready status."
