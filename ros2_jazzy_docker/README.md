# ros2_jazzy_docker

A basic ROS 2 Jazzy development container: `osrf/ros:jazzy-desktop` (RViz, rqt, demo nodes) plus colcon and rosdep.
No robot and no VLM, just a clean place to build and run your own ROS 2 packages.

Needs Docker and Compose v2 (and the NVIDIA Container Toolkit for GPU mode): `bash scripts/install_prereqs.sh` from the repo root.

## Files

| File | What it is |
|---|---|
| `Dockerfile` | Jazzy desktop image; every shell sources ROS and `/ros2_ws/install` when it exists |
| `compose.yaml` | One `ros2` service: host network, X11 for GUI tools, `./src` mounted as `/ros2_ws/src` |
| `compose.gpu.yaml` | NVIDIA overlay: GPU rendering for RViz/Gazebo |
| `scripts/ros2.sh` | Build, start, shell, logs, status, stop |
| `src/` | Put your ROS packages here; edit them on the host |

Build output (`build/`, `install/`) lives in Docker volumes, so it survives `stop`/`start`.

## Use it

```bash
cd ~/vlm_packt_workshop/ros2_jazzy_docker
bash scripts/ros2.sh build        # builds ros2-jazzy:local
bash scripts/ros2.sh start        # starts the container in the background
bash scripts/ros2.sh shell        # bash inside it, ROS already sourced
```

Inside the container:

```bash
ros2 run demo_nodes_cpp talker &  # quick check
ros2 topic echo --once /chatter
colcon build                      # builds /ros2_ws/src
rviz2                             # needs an X11 desktop session
```

Add `cpu` to `build`/`start` on a machine without an NVIDIA GPU. Stop with `bash scripts/ros2.sh stop`.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `ROS_DOMAIN_ID` | `0` | ROS 2 domain; the workshop projects use 77–92, so 0 does not collide |
| `LIBGL_ALWAYS_SOFTWARE` | `1` (cpu), `0` (gpu) | Software or GPU OpenGL |

Example: `ROS_DOMAIN_ID=5 bash scripts/ros2.sh start`.

## Tested

Ubuntu 24.04, Docker 29.6, Compose v5.3, RTX 4060 Laptop GPU: build, `start gpu`, `nvidia-smi` inside the container, talker → `/chatter` echo.
RViz over X11 not yet checked.
