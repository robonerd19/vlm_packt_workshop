#!/usr/bin/env bash
# Stop the warehouse Nav2 or SLAM launch without stopping Gazebo.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
compose=(docker compose -p unitree-go2-vlm-navigation -f compose.yaml)
container_id="$("${compose[@]}" ps -q go2-simulation)"

if [[ -z "$container_id" ]] || [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" != true ]]; then
  echo 'Go2 simulation container is not running; there is no navigation launch to stop.'
  exit 0
fi

"${compose[@]}" exec -T go2-simulation bash -lc \
  "pkill -INT -f '[r]os2 launch go2_warehouse_(nav2|slam)' || true"

for _ in {1..10}; do
  if ! docker exec "$container_id" bash -lc \
    "pgrep -f '[r]os2 launch go2_warehouse_(nav2|slam)' >/dev/null"; then
    echo 'Warehouse Nav2/SLAM stopped; Gazebo remains running.'
    exit 0
  fi
  sleep 0.5
done

echo 'Navigation launch received SIGINT but is still shutting down; check the launch terminal.' >&2
exit 1
