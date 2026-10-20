#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
if [[ "${SOFTWARE_RENDERING:-0}" == "1" ]]; then
    export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe
    exec xvfb-run -a -s '-screen 0 640x480x24' "$@"
fi
exec "$@"
