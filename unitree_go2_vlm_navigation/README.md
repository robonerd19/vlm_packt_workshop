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

The legs use position commands (`command_interface:=position`, matching
`config/ros_control/ros_control.yaml`). Walking straight at a 0.5 m/s command in
the warehouse, body roll/pitch rate RMS was about 12/15 deg/s with position
commands versus 48-55/39-44 deg/s with the original effort PID (p 100, d 1), and
roll stayed within about ±0.7° instead of ±2.8°. The trade-off: the robot reaches
only about 0.3 m/s for a 0.5 m/s command, and Nav2 needed recovery behaviours
near some goals (three test goals took 37-294 s versus 31-48 s with effort
control). Launch with `command_interface:=effort` and set `command_interfaces`
back to `effort` in that file to compare.

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

See [UPSTREAM.md](UPSTREAM.md) for the robot source revision and its licensing notes.

## VLM object finding

Type an instruction such as `go to the green dumpster` in a browser and the Go2
finds it from patrol memory (below) or looks for the object with Qwen2-VL-2B in its D455 RGB-D camera, projects the
detection into the map with depth and TF, and walks there with the Nav2 stack
above. If the object is not in view it turns in place and then visits a few
free-space viewpoints on the map; an object it cannot find is refused without
moving to a goal.

The pipeline is the TurtleBot 4 object finder from
[`../turtlebot4_vla_object_finder`](../turtlebot4_vla_object_finder/), copied
into `src/vlm_nav`, `src/vlm_nav_msgs`, and `src/vlm_nav_web`. Go2-specific
settings are in `src/vlm_nav/config/go2_warehouse.yaml`: D455 topics
(`/d455/image`, `/d455/depth_image`, `/d455/camera_info`), `map` and
`base_footprint` frames, and `camera_frame: d455_camera_depth_optical_frame`.
Gazebo stamps the D455 images with `d455_camera_link` (x forward), while the
pixels follow the optical convention (z forward), so the navigator relabels
them with the optical frame at the same origin. The model server reuses the
TurtleBot project's llama.cpp images (`vlm-workshop-inference[-cuda]:local`,
built from that project if missing) and its model files in
`../turtlebot4_vla_object_finder/models` (download them there with
`bash scripts/download_model.sh`, or set `MODEL_DIR`).

Run each command in its own terminal, from this folder:

```bash
GO2_PUBLISH_MAP_TO_ODOM=false bash scripts/go2_sim.sh start gpu warehouse
bash scripts/start_nav2.sh nav2
bash scripts/start_vlm.sh gpu      # Qwen2-VL server on 8081, web UI on 8000
```

Open <http://127.0.0.1:8000>, wait for the status to show ready, and send an
instruction. `go home` returns to the start pose. Ctrl+C in the `start_vlm.sh`
terminal stops the navigator; `bash scripts/start_vlm.sh stop` also stops the
model server, and `bash scripts/go2_sim.sh stop` stops everything. Ports 8000
and 8081 are shared with the other workshop projects, so stop those first.

### Patrol and object waypoints

Send `patrol` to have the Go2 walk the `patrol_points` in
`src/vlm_nav/config/go2_warehouse.yaml` with Nav2, turning through
`patrol_headings` views at each point. For every view Qwen2-VL lists the objects
it sees with boxes; depth and TF place each one in the map, and it is remembered
as a labelled waypoint: the object position plus a viewing pose 1.2 m in front of
it, which the robot reached on patrol. Waypoints appear under "Remembered
objects" in the web UI (click one to fill in `go to the …`) and as
`visualization_msgs/MarkerArray` on `/vlm_nav/objects` for RViz.

After a patrol, `go to the <object>` first matches the instruction against the
remembered labels and sends Nav2 straight to that waypoint's pose, with no
searching. When nothing matches (a named color must appear in the remembered
label), it falls back to the live search described above. Memory lasts until the
navigator restarts. Boxes clipped by the image edge, floor markings, and walls
are not stored.

Measured in GPU mode (RTX 4060 Laptop GPU), four patrol points with six views each:

| Instruction | Result | Time |
|---|---|---|
| `patrol` | 24 views, 12 objects remembered; the dumpster stored as "green bin" at (-1.05, 7.5), about 0.5 m from its model origin | 562 s |
| `go to the green dumpster` | matched "green bin" from memory, walked to its waypoint, ended facing the dumpster | 58 s |
| `go to the yellow metal rack` (earlier 4-view patrol) | matched "yellow metal racks", arrived 0.26 m from the stored pose | 27 s |
| `go to the pallet truck` | wrong object: "pallet" matched the remembered "pallets" stack, not the pallet jack (stored as "forklift") | 29 s |
| `go to the blue sofa` (earlier patrol) | no remembered match, live search refused it after 30 views | 536 s |

Limits seen while testing: the 2B model sometimes names the same object
differently ("green bin", "green truck") or invents labels for a box stack
("forklift", "pallets"), so check the remembered list before demoing an object.
With four views per point, the dumpster was clipped at the image edge and
stored 2.9 m away inside a wall, which is why patrol now skips clipped boxes
and uses six views. At temperature 0 the model can repeat one entry until its
token limit; complete entries are still read from the truncated reply. AMCL
drifted about 2 m in the long south aisle, so the patrol points stay in the
north half.

**CPU mode** has no depth camera by default. Enable the D455 and the Velodyne
explicitly, and use CPU inference (each VLM answer then takes 45–60 s instead
of about 1 s, and software rendering of the depth camera slows Gazebo further):

```bash
GO2_PUBLISH_MAP_TO_ODOM=false GO2_DISABLE_VELODYNE=false GO2_DISABLE_D455=false \
  bash scripts/go2_sim.sh start cpu warehouse
bash scripts/start_nav2.sh nav2
bash scripts/start_vlm.sh cpu
```

The plain `/rgb_image` camera has no depth and is not used for object finding.
CPU mode was not tested end to end; the GPU results below were.

Measured in the warehouse world, GPU mode (RTX 4060 Laptop GPU), robot starting
at the origin:

| Instruction | Result | Time | Views | Robot end (Gazebo x, y) |
|---|---|---|---|---|
| `go to the green dumpster` (run 1) | arrived, dumpster in view | 128 s | 4 | (-0.44, 6.47) |
| `go to the green dumpster` (run 2) | arrived | 54 s | 4 | (0.31, 7.31) |
| `go to the blue sofa` | refused: not found in search time limit | 545 s | 30 (3 viewpoints) | no goal sent |

The dumpster model origin is at (-1.59, 7.72); the robot stops `approach_distance`
(1.2 m) short of the detected surface. Each VLM call takes about 1 s on the GPU;
most of the time is the Go2 turning and walking between views (Gazebo runs below
real time). Limits seen in testing: the 2B model's text-only identity check once
accepted `blue sofa` for a green bin, so a named color that the candidate's
label visibly lacks now rejects it before that check (`identity_matches` in
`src/vlm_nav/vlm_nav/perception.py`, the one change to the TurtleBot logic
besides `camera_frame`). AMCL can drift: after one `go home` the robot was
about 1.6 m from the true origin. When the robot starts wedged next to a rack,
the search can skip viewpoints it cannot reach and miss the target.

# unitree_go2_vlm_navigation-
