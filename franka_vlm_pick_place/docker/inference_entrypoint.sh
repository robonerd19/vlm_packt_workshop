#!/usr/bin/env bash
set -euo pipefail
mode="${1:-cpu}"
case "$mode" in
  cpu|gpu) if (($#)); then shift; fi ;;
  *) exec llama-server "$@" ;;
esac
port="${INFERENCE_PORT:-8081}"
[[ "$port" =~ ^[0-9]+$ ]] && ((port >= 1 && port <= 65535)) || { echo 'INFERENCE_PORT must be 1..65535.' >&2; exit 2; }
threads="${CPU_THREADS:-4}"
layers="${GPU_LAYERS:-999}"
[[ "$threads" =~ ^[1-9][0-9]*$ ]] || { echo 'CPU_THREADS must be a positive integer.' >&2; exit 2; }
args=(
  -m /models/Qwen2-VL-2B-Instruct-Q4_K_M.gguf
  --mmproj /models/mmproj-Qwen2-VL-2B-Instruct-f16.gguf
  --alias vlm --host 127.0.0.1 --port "$port"
  --ctx-size 2048 --parallel 1 --threads "$threads" --threads-batch "$threads"
  --batch-size 128 --ubatch-size 128 --image-min-tokens 1024 --image-max-tokens 1024 --temp 0
)
if [[ "$mode" == gpu ]]; then
  devices="$(llama-server --list-devices 2>&1)" || { echo "$devices" >&2; exit 1; }
  [[ "$devices" =~ CUDA[0-9]+: ]] || { echo 'GPU mode requires an available CUDA device; refusing CPU fallback.' >&2; echo "$devices" >&2; exit 1; }
  [[ "$layers" =~ ^[1-9][0-9]*$ ]] || { echo 'GPU_LAYERS must be a positive integer.' >&2; exit 2; }
  args+=(--n-gpu-layers "$layers")
else
  args+=(--n-gpu-layers 0 --no-mmproj-offload)
fi
echo "Starting $mode inference (CPU threads: $threads)." >&2
exec llama-server "${args[@]}" "$@"
