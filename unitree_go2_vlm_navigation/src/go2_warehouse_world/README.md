# Go2 warehouse world

This package adds the AWS RoboMaker Small Warehouse scene to the Go2 Gazebo
workspace. Its models are installed locally, so the world does not need to
fetch warehouse assets from Gazebo Fuel at runtime.

The scene is adapted from the no-roof warehouse world in
[homerquan/ros2-amr-blueprint](https://github.com/homerquan/ros2-amr-blueprint),
which credits the AWS RoboMaker Small Warehouse assets and the Gazebo Harmonic
port in
[aws-robotics/aws-robomaker-small-warehouse-world](https://github.com/aws-robotics/aws-robomaker-small-warehouse-world).
The source project is MIT licensed; its original LICENSE and attribution are
preserved in this package. The world removes the xacro-only headless switch,
uses the Gazebo Harmonic Bullet Featherstone physics engine, and keeps a
warehouse overview camera and GUI view.

Start it from the repository root with:

```bash
bash scripts/go2_sim.sh start cpu warehouse
# Or start the container separately, then launch Gazebo:
bash scripts/go2_container.sh start cpu warehouse
bash scripts/go2_container.sh gazebo
```
