# Upstream source

The Go2-specific ROS packages are in the top-level `src/` workspace directory.
The CHAMP gait and message packages remain under `upstream/unitree_go2_ros2/`.
All six packages originate from:

<https://github.com/khaledgabr77/unitree_go2_ros2>

The checkout used here is commit `55ff151632a0220bf3ae0c0772392615d86da7a8`.
The source README describes ROS 2 Jazzy and Gazebo Harmonic support. The
simulation launches with `ros2 launch unitree_go2_sim unitree_go2_launch.py`.

Local patch: the launch file's delayed controller-status check calls the
`/controller_manager/list_controllers` ROS service directly. The upstream check
uses `ros2 control list_controllers`, but its documented dependency list does
not install that CLI extension.

The upstream README marks Gazebo Nav2 integration as not yet implemented and
the description/simulation package licenses as TODO. This project packages
the upstream simulation; it does not add Nav2 or VLM object navigation.
