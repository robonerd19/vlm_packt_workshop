# Builds on the Spot inspection image (Spot model, CHAMP gait, Gazebo, cv_bridge):
#   bash scripts/teleop.sh build  builds that image first when it is missing.
FROM spot-inspection-ros:local

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends python3-flask \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /teleop_ws
COPY src/ /teleop_ws/src/
RUN source /spot_ws/install/setup.bash && colcon build

ENV ROS_DOMAIN_ID=92
CMD ["bash", "-lc", "source /teleop_ws/install/setup.bash && ros2 launch spot_vlm_teleop sim.launch.py"]
