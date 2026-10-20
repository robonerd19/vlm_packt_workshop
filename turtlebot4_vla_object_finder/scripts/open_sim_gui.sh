#!/usr/bin/env bash
# Run a GUI-only container with the same baked assets as the simulation server.
set -eo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ -z "${DISPLAY:-}" ]]; then
    echo 'Run this script from a terminal in your Linux desktop session (DISPLAY is unset).' >&2
    exit 1
fi
task_xauthority="${XAUTHORITY:-$HOME/.Xauthority}"
if [[ ! -f "$task_xauthority" ]]; then
    echo 'Set XAUTHORITY to the readable X11 authorization file for this desktop session.' >&2
    exit 1
fi
task_partition="$(docker compose --profile simulation exec -T simulation sh -c \
    'printf "%s" "${GZ_PARTITION:-$(hostname):$(id -un)}"')"
task_image="$(docker compose --profile simulation images -q simulation)"
if [[ -z "$task_image" ]]; then
    echo 'Start the Docker simulation first.' >&2
    exit 1
fi
echo "Connecting Gazebo GUI to partition: $task_partition"
# A GUI-only container sees the exact same mesh/texture paths as the server.
# X11 authorization is mounted read-only; no xhost access relaxation is needed.
exec docker run --rm --init --network host --name packt-vlm-workshop-gui \
    --memory 768m --memory-swap 768m \
    --env DISPLAY --env XAUTHORITY=/tmp/workshop.xauthority \
    --env "GZ_PARTITION=$task_partition" \
    --env LIBGL_ALWAYS_SOFTWARE=1 --env GALLIUM_DRIVER=llvmpipe \
    --env QT_QPA_PLATFORM=xcb --env QT_XCB_GL_INTEGRATION=xcb_glx \
    --env __GLX_VENDOR_LIBRARY_NAME=mesa \
    --mount "type=bind,src=$PWD/src/vlm_nav_sim/config/warehouse_gui.config,dst=/tmp/workshop-gui.config,readonly" \
    --mount type=bind,src=/tmp/.X11-unix,dst=/tmp/.X11-unix,readonly \
    --mount "type=bind,src=$task_xauthority,dst=/tmp/workshop.xauthority,readonly" \
    "$task_image" gz sim -g --render-engine-gui ogre --gui-config /tmp/workshop-gui.config "$@"
