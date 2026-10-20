#!/usr/bin/env bash
# Select inference backend without resetting an existing simulation/localization.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
device=cpu
build=0
usage() {
  cat <<'HELP'
Usage: bash scripts/run_demo.sh [--device cpu|gpu] [--build]
  --device cpu  CPU-only inference (default).
  --device gpu  NVIDIA CUDA inference; requires driver and Docker GPU access.
  --build       Rebuild the selected inference image before starting.
Missing/outdated inference images are built automatically. ROS images and models
must already be prepared as described in README. Existing ROS services retain
their current image and robot pose. Stop all demo modes before switching from mock.
HELP
}
while (($#)); do
  case "$1" in
    --device) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; device="$2"; shift 2 ;;
    --build) build=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ "$device" == cpu || "$device" == gpu ]] || { echo '--device must be cpu or gpu.' >&2; exit 2; }
compose=(docker compose -f "$root/compose.yaml")
image=vlm-workshop-inference:local
if [[ "$device" == gpu ]]; then
  command -v nvidia-smi >/dev/null || { echo 'GPU mode requires NVIDIA drivers (nvidia-smi not found).' >&2; exit 1; }
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
  if [[ -z "${CUDA_ARCHITECTURES:-}" ]]; then
    CUDA_ARCHITECTURES="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | tr -d '. ' | sort -u | paste -sd ';' -)"
  fi
  [[ "$CUDA_ARCHITECTURES" =~ ^[0-9]+(\;[0-9]+)*$ ]] || { echo 'CUDA_ARCHITECTURES must contain numeric architectures separated by semicolons.' >&2; exit 2; }
  export CUDA_ARCHITECTURES
  compose+=(-f "$root/compose.gpu.yaml")
  image=vlm-workshop-inference-cuda:local
  echo "CUDA architectures: $CUDA_ARCHITECTURES"
fi
# Refuse another ROS/model owner before mutating the selected services.
for service in mock external; do
  if [[ -n "$(docker compose -f "$root/compose.yaml" --profile "$service" ps --status running -q "$service")" ]]; then
    echo "Stop the running $service mode before starting simulation." >&2
    exit 1
  fi
done
label="$(docker image inspect "$image" --format '{{index .Config.Labels "org.vlm-workshop.inference.device"}}' 2>/dev/null || true)"
if [[ "$label" != "$device" ]]; then build=1; fi
if [[ "$device" == gpu ]]; then
  arch="$(docker image inspect "$image" --format '{{index .Config.Labels "org.vlm-workshop.cuda.architectures"}}' 2>/dev/null || true)"
  [[ "$arch" == "$CUDA_ARCHITECTURES" ]] || build=1
fi
if ((build)); then "${compose[@]}" --profile simulation build inference; fi
if [[ "$device" == gpu ]]; then
  docker run --rm --gpus all --entrypoint nvidia-smi "$image" --query-gpu=name,memory.total --format=csv,noheader
fi
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
