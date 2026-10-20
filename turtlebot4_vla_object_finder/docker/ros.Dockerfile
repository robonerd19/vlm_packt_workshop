FROM ros:jazzy-ros-base
SHELL ["/bin/bash", "-c"]
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions python3-flask python3-numpy python3-opencv \
    python3-pytest curl xvfb xauth libgl1-mesa-dri mesa-utils \
    ros-jazzy-cv-bridge ros-jazzy-message-filters ros-jazzy-tf2-geometry-msgs \
    ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-ros-gz \
    ros-jazzy-robot-state-publisher && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-jazzy-turtlebot4-simulator ros-jazzy-irobot-create-nodes && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /ws
COPY scripts/prepare_tb4_assets.py scripts/warehouse_assets.lock.json /ws/scripts/
RUN --mount=type=cache,target=/root/.gz/fuel source /opt/ros/jazzy/setup.bash && \
    python3 /ws/scripts/prepare_tb4_assets.py /opt/vlm-tb4-assets
COPY src/ src/
RUN cp -r /opt/vlm-tb4-assets/worlds /opt/vlm-tb4-assets/urdf /opt/vlm-tb4-assets/maps /ws/src/vlm_nav_sim/
RUN source /opt/ros/jazzy/setup.bash && \
    colcon build --executor sequential --cmake-args -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3
COPY docker/entrypoint.sh /entrypoint.sh
COPY scripts/verify_demo.py scripts/measure_resources.py /ws/scripts/
COPY tests/ /ws/tests/
COPY LICENSE NOTICE /ws/
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "vlm_nav_bringup", "mock.launch.py"]
