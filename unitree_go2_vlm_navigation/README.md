# Unitree Go2 Gazebo simulation

This project packages the [Unitree Go2 ROS 2 repository](https://github.com/khaledgabr77/unitree_go2_ros2)
with Docker setup and run/stop commands for ROS 2 Jazzy and Gazebo Harmonic.
The Go2-specific packages are in `src/`; the CHAMP packages are retained under
`upstream/unitree_go2_ros2/`.
The upstream launch starts Gazebo, spawns the Go2, starts the CHAMP gait and
state-estimation nodes, and bridges the simulated sensors.

## Requirements

- Ubuntu 24.04, Docker Engine, and Docker Compose v2.
- An active X11 desktop session for the Gazebo window (`DISPLAY` and a readable
  `XAUTHORITY` file).
- Internet access and disk space for the first Docker image build.
- For GPU mode: a compatible NVIDIA driver and working Docker GPU support via
  NVIDIA Container Toolkit.

ROS, Gazebo, CHAMP, and simulation dependencies are installed inside the image;
the host does not need a ROS installation. The upstream checkout is pinned in
[UPSTREAM.md](UPSTREAM.md).

## Build and run

Run from this folder. The first build installs ROS dependencies and compiles the
upstream workspace; it can take a while. Build once, then start either mode:

```bash
# Build the shared ROS/Gazebo image
bash scripts/go2_sim.sh build cpu

# Start with CPU rendering (lighter sensor configuration)
bash scripts/go2_sim.sh start cpu

# Or start with NVIDIA GPU rendering and all configured sensors
bash scripts/go2_sim.sh start gpu

# Start in the downloaded electrical substation world
bash scripts/go2_sim.sh start cpu industrial

# Start in the AWS RoboMaker warehouse world
bash scripts/go2_sim.sh start cpu warehouse

# Follow simulator output
bash scripts/go2_sim.sh logs

# Keyboard teleoperation (run in its own terminal; press Ctrl+C to exit)
bash scripts/go2_control.sh keyboard

# Or open the rqt steering GUI
bash scripts/go2_control.sh rqt

# Open RViz2 with the Go2 model and RGB camera image
bash scripts/go2_sim.sh rviz

# Stop and remove the simulation container
bash scripts/go2_control.sh stop
```

Both teleoperation options send `geometry_msgs/Twist` commands on `/cmd_vel`.
Keyboard control uses the standard `u/i/o`, `j/k/l`, `m/,/.` key layout; `q/z`
adjust linear speed and `w/x` adjust angular speed. The stop command removes the
simulation container. Build or rebuild the image with
`bash scripts/go2_sim.sh build cpu` after changing the Dockerfile so the
teleoperation tools are installed. Keyboard
teleoperation needs an interactive terminal; rqt needs the same active X11
desktop used for Gazebo.

The CHAMP forward command limit and rqt slider are set to 0.6 m/s, and Nav2
drives at up to 0.5 m/s. In a sim-time sweep the gait tracked commands up to
0.7 m/s, but body tilt rises above 0.6 m/s. Unitree's Go2 EDU speed rating is a
hardware specification, not a validated target for this fixed-cadence CHAMP
simulation gait. Gazebo runs at roughly 0.55x real time on a laptop-class CPU,
so on-screen motion looks about half as fast as the sim-time speed.

`start` also builds the image if it is missing or needs rebuilding. CPU mode uses
Mesa software rendering and disables the D455 depth camera and two 3D lidars to
reduce load; it keeps the robot and RGB camera in Gazebo. GPU mode requires
NVIDIA container GPU access and enables those sensors. Gazebo physics and the
CHAMP robot controller run on the CPU in both modes; GPU mode accelerates
rendering and GPU-based sensors.

To start the container without launching Gazebo, then launch the simulator
separately, use these commands in order:

```bash
bash scripts/go2_container.sh start cpu   # or: start gpu
bash scripts/go2_container.sh gazebo
bash scripts/go2_container.sh status
bash scripts/go2_container.sh stop
```

Choose `industrial` when starting the idle container to use the downloaded
substation scene:

```bash
bash scripts/go2_container.sh start cpu industrial
bash scripts/go2_container.sh gazebo
```

The industrial scene is the [Robotnik Automation electrical substation
world](https://github.com/RobotnikAutomation/robotnik_gazebo_worlds), adapted
for this workspace's Gazebo Harmonic physics and packaged with its local models.
The original simple scene remains available as `default` and is still the
default when no world is specified. Source and licensing details are in
[`src/electrical_substation_world/README.md`](src/electrical_substation_world/README.md).

Choose `warehouse` with either launcher to run the AWS RoboMaker Small
Warehouse scene. It includes warehouse racks, pallets, clutter, and a wide
open aisle layout; its locally packaged models do not need Fuel downloads.
The scene is adapted for Gazebo Harmonic and includes a warehouse overview
camera. Source, attribution, and license details are in
[`src/go2_warehouse_world/README.md`](src/go2_warehouse_world/README.md).
The warehouse launch places the robot at `z=0.40 m` to give its legs a small
amount of extra clearance at spawn; the default and industrial worlds keep
`z=0.375 m`.

The `gazebo` command stays attached to the launch output; press Ctrl+C to end
the Gazebo launch while leaving the container up. Use `stop` to remove the
container.

The launcher uses the host X11 authorization file read-only. It does not open
global X server access with `xhost`. If your desktop uses a non-default auth
file, export its path before starting, for example:

```bash
export XAUTHORITY=/run/user/1000/gdm/Xauthority
bash scripts/go2_sim.sh start cpu
```

Check container state with `bash scripts/go2_sim.sh status`. Ctrl+C in the
terminal that started the script does not stop the background container; use
`bash scripts/go2_sim.sh stop` to stop it.

## Available interfaces

The upstream project includes a mono RGB camera (`/rgb_image`), optional D455
RGB/depth topics, IMU, GPS, foot-contact data, and optional 3D lidar topics.
Use `ros2 topic list` inside the container to inspect active interfaces. The
Go2 receives velocity commands through `/cmd_vel`; the upstream README shows
keyboard teleoperation with `teleop_twist_keyboard`.

The upstream RViz preset opens with the robot and TF displays. To see camera
images, add an `Image` display and select `/rgb_image`. In GPU mode, you can
also select `/d455/image` or `/d455/depth_image`, and add `PointCloud2`
displays for `/d455/points`, `/unitree_lidar/points`, or
`/velodyne_points/points`. The optional D455 and lidar sensors are disabled by
default in CPU mode, so those topics are only available in GPU mode unless
explicitly enabled.

## Warehouse Nav2 and SLAM

The warehouse scene has a generated 2D occupancy map based on the SDF collision
geometry, plus separate `go2_warehouse_nav2` and `go2_warehouse_slam` ROS 2
packages. Both convert the Go2 Velodyne point cloud to `/scan` and use `/odom`
with `base_footprint`. Nav2 uses AMCL with the generated static map; SLAM mode
builds a map online with slam_toolbox and starts Nav2 against that live map.

AMCL and slam_toolbox publish the `map -> odom` transform, so disable the
simulation's fixed transform and enable the Velodyne before starting the
warehouse world:

```bash
# GPU sensors enabled (recommended)
GO2_PUBLISH_MAP_TO_ODOM=false bash scripts/go2_sim.sh start gpu warehouse

# Or CPU rendering with Velodyne enabled
GO2_PUBLISH_MAP_TO_ODOM=false GO2_DISABLE_VELODYNE=false \
  bash scripts/go2_sim.sh start cpu warehouse
```

Start Nav2 on the generated map, or start online SLAM with Nav2:

```bash
bash scripts/start_nav2.sh nav2
bash scripts/start_nav2.sh slam
```

Press Ctrl+C in the navigation terminal to stop those nodes; if the launch was
started from a non-interactive terminal, use `bash scripts/stop_nav2.sh`.
This stops Nav2/SLAM while leaving Gazebo running. To open RViz with the Nav2 map and costmaps, run `bash scripts/start_nav2.sh nav2 true`. The map
is `src/go2_warehouse_nav2/maps/warehouse/warehouse.yaml`; regenerate it after
changing the world with:

```bash
python3 src/go2_warehouse_nav2/scripts/generate_warehouse_map.py
```

Save a map produced by online SLAM with:

```bash
docker compose -p unitree-go2-vlm-navigation exec go2-simulation \
  bash -lc 'source /go2_ws/install/setup.bash && ros2 run nav2_map_server map_saver_cli -f /go2_ws/warehouse_slam_map'
```

The packages provide baseline autonomous navigation and mapping; VLM-based
object finding and goal selection are not included. See [UPSTREAM.md](UPSTREAM.md)
for the robot source revision and its licensing notes.
# unitree_go2_vlm_navigation-
