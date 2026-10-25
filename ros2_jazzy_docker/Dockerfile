# Basic ROS 2 Jazzy desktop image (RViz, rqt, demo nodes) with colcon for building ./src.
FROM osrf/ros:jazzy-desktop

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3-colcon-common-extensions python3-rosdep ros-jazzy-rmw-fastrtps-cpp \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ros2_ws
RUN echo 'source /opt/ros/jazzy/setup.bash' >> /root/.bashrc \
 && echo '[ -f /ros2_ws/install/setup.bash ] && source /ros2_ws/install/setup.bash' >> /root/.bashrc
CMD ["bash"]
