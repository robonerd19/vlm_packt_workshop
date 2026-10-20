FROM ros:jazzy-ros-base
SHELL ["/bin/bash", "-c"]
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions python3-flask python3-numpy python3-opencv \
    python3-pytest curl xvfb xauth libgl1-mesa-dri mesa-utils \
    ros-jazzy-cv-bridge ros-jazzy-ros-gz ros-jazzy-gz-ros2-control \
    ros-jazzy-ros2-controllers ros-jazzy-robot-state-publisher \
    ros-jazzy-moveit-resources-panda-description && rm -rf /var/lib/apt/lists/*
WORKDIR /ws
COPY src/ src/
RUN source /opt/ros/jazzy/setup.bash && colcon build --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3
COPY docker/entrypoint.sh /entrypoint.sh
COPY tests/ /ws/tests/
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "vlm_pick_place", "sim.launch.py"]
