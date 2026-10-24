#!/usr/bin/env bash
# One-command setup, start, and stop for the Docker workshop demo.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

usage() {
  cat <<'HELP'
Usage:
  bash scripts/workshop.sh setup [cpu|gpu]
  bash scripts/workshop.sh start [cpu|gpu]
  bash scripts/workshop.sh stop

setup builds the ROS image and pulls the VLM (qwen2.5vl:3b) into the Ollama server.
start launches the real warehouse demo with the selected inference device (CPU default).
stop shuts down workshop modes and the optional Gazebo GUI container.
GPU mode requires NVIDIA drivers and Docker GPU support.
HELP
}

command_name="${1:-}"
device="${2:-cpu}"
if [[ "$command_name" == -h || "$command_name" == --help || -z "$command_name" ]]; then
  usage
  exit 0
fi
if [[ "$command_name" != setup && "$command_name" != start && "$command_name" != stop ]]; then
  echo "Unknown command: $command_name" >&2
  usage >&2
  exit 2
fi
if [[ "$command_name" == stop ]]; then
  [[ $# -le 1 ]] || { echo 'stop takes no device argument.' >&2; exit 2; }
  docker compose -f compose.yaml --profile mock --profile simulation --profile external down
  if docker container inspect packt-vlm-workshop-gui >/dev/null 2>&1; then
    docker stop packt-vlm-workshop-gui >/dev/null
  fi
  echo 'Workshop demo stopped.'
  exit 0
fi
[[ $# -le 2 ]] || { echo 'Too many arguments.' >&2; usage >&2; exit 2; }
[[ "$device" == cpu || "$device" == gpu ]] || { echo 'Device must be cpu or gpu.' >&2; exit 2; }

if [[ "$command_name" == start ]]; then
  exec bash scripts/run_demo.sh --device "$device"
fi

for prerequisite in docker curl python3; do
  command -v "$prerequisite" >/dev/null || { echo "Missing prerequisite: $prerequisite" >&2; exit 1; }
done
docker compose version >/dev/null
compose=(docker compose -f compose.yaml)
if [[ "$device" == gpu ]]; then
  command -v nvidia-smi >/dev/null || { echo 'GPU setup requires NVIDIA drivers (nvidia-smi not found).' >&2; exit 1; }
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
  compose+=(-f compose.gpu.yaml)
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo 'Created .env from .env.example.'
fi
docker compose --profile simulation config -q

"${compose[@]}" --profile simulation build simulation
# Ollama keeps the model in the "ollama" volume; the application asks for it as "vlm".
model=qwen2.5vl:3b
"${compose[@]}" --profile simulation up -d --no-deps inference
for _ in {1..30}; do
  "${compose[@]}" exec -T inference ollama list >/dev/null 2>&1 && break
  sleep 1
done
"${compose[@]}" exec -T inference ollama pull "$model"
"${compose[@]}" exec -T inference ollama cp "$model" vlm
echo "Setup complete for $device mode. Start it with: bash scripts/workshop.sh start $device"
