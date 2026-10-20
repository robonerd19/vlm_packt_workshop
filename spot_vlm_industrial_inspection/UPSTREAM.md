# Upstream sources

| Path | Source | License |
|---|---|---|
| `src/spot_description/` | <https://github.com/rai-opensource/spot_description> at `156d1802bfb117f219dbfce7597d283d5fabc968` | MIT (see its `LICENSE`) |
| `upstream/champ*` | CHAMP, copied from `../unitree_go2_vlm_navigation/upstream/unitree_go2_ros2` (khaledgabr77/unitree_go2_ros2 at `55ff151632a0220bf3ae0c0772392615d86da7a8`) | BSD-3-Clause |
| VLM inference image | `../turtlebot4_vla_object_finder/docker/inference*.Dockerfile` (llama.cpp, pinned commit there) | MIT |

## Local patches

- `src/spot_description/urdf/spot_macro.xacro`: joint effort limits raised
  from 45/115 Nm (hips/knee) to 200/250 Nm. The URDF totals about 50 kg
  (real Spot: ~32 kg), and with the real limits the CHAMP stance sagged to the
  ground in Gazebo. Simulation only; do not reuse these limits on hardware.
- CHAMP EKF configs are copied into `src/spot_inspection_sim/config/` with the
  base frame changed from `base_link` to Spot's root link `body`.
