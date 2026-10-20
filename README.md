# VLM robotics workshop (Packt)

Four ROS 2 Jazzy + Gazebo projects that put vision-language models on robots.
Each folder is self-contained with its own README and Docker setup.

| Project | Robot | What it does |
|---|---|---|
| [turtlebot4_vla_object_finder](turtlebot4_vla_object_finder/) | TurtleBot 4 | Finds an object named in a text instruction with Qwen2-VL and navigates to it with Nav2 |
| [unitree_go2_vlm_navigation](unitree_go2_vlm_navigation/) | Unitree Go2 | CHAMP-gait quadruped that patrols a warehouse with Nav2, marks the objects Qwen2-VL sees as map waypoints, and walks to one when asked; also SLAM and a substation world |
| [franka_vlm_pick_place](franka_vlm_pick_place/) | Franka Panda | VLM scene understanding for pick and place (work in progress) |
| [spot_vlm_industrial_inspection](spot_vlm_industrial_inspection/) | Boston Dynamics Spot | Walks an inspection route in an industrial plant and flags faults with a VLM |

Model weights (`*.gguf`) are not stored in the repo; each project's setup script
downloads them. The Spot project reuses the TurtleBot 4 model files and
inference image.
