# Franka VLM pick and place — ROS 2 Jazzy + Gazebo

Type an instruction such as *"put the red cube on the yellow tray"* in a local
browser. A Franka Panda in Gazebo uses Qwen2-VL-2B (llama.cpp) to understand the
table scene, finds both objects in an overhead RGB-D camera, turns the boxes into
3D points with depth, and does a top-down pick and place.

Same stack as the TurtleBot 4 and Go2 workshops in this repo: Docker, ROS 2 Jazzy,
Gazebo Harmonic, and the same VLM files and inference images.

## Pipeline

1. **Scene understanding** — the VLM lists the objects on the table (shown in the UI).
2. **Instruction parsing** — the VLM extracts the object to pick and the destination.
3. **Grounding** — the VLM returns a 0..1000 box for each phrase. A box whose pixels
   do not have the colour the phrase names is rejected: the 2B model tends to box the
   nearest object instead of saying "not visible".
4. **3D** — the nearest coherent depth surface in each box is back-projected and
   transformed with the known camera pose (`description.py`, matching the world SDF).
5. **Motion** — damped least-squares IK on the URDF's own kinematics (no MoveIt);
   straight-line descents and lifts via `joint_trajectory_controller`.
6. **Grasp** — the fingers close, then a Gazebo `DetachableJoint` attaches the cube,
   but only if a cube is actually within 2.5 cm of the fingertips. Friction grasps in
   Gazebo are too flaky for a workshop. Placing on an occupied tray stacks on top,
   because the nearest surface in the tray's box is then the cube.

## Run

```bash
cd /home/robot/vlm_packt_workshop/franka_vlm_pick_place
bash scripts/workshop.sh setup cpu   # or: setup gpu  (downloads 2.3 GB model, builds images)
bash scripts/workshop.sh start cpu   # or: start gpu
```

Open http://127.0.0.1:8000, wait for **Ready**, then run an instruction.
`bash scripts/workshop.sh gui` opens the Gazebo GUI (X11), `logs` follows output,
`stop` shuts everything down. Port 8081 (VLM) and 8000 (web) must be free: stop
the other workshops first. ROS domain defaults to 78.

## Scene

Red, green and blue 4 cm cubes; yellow and purple trays. Edit
`src/vlm_pick_place/worlds/tabletop.sdf`; cubes the robot can grasp must also be
listed in `GRASPABLE` in `description.py` (checked by `tests/test_scene.py`).

## Tests

```bash
python3 -m pytest -q tests   # kinematics, reachability, projection, VLM output parsing
```

## Known limits

- Cubes are grasped at yaw 0; rotated cubes are not handled.
- No collision checking; the motions assume an open tabletop.
- Colourless phrases ("the bin") are not colour-verified.
- The UI is unauthenticated and binds to 127.0.0.1 only.
