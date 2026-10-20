FROM ros:jazzy-ros-base

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3-colcon-common-extensions python3-opencv python3-yaml \
      ros-jazzy-ros-gz ros-jazzy-gz-ros2-control ros-jazzy-ros2-controllers \
      ros-jazzy-robot-localization ros-jazzy-robot-state-publisher ros-jazzy-xacro \
      ros-jazzy-urdf ros-jazzy-teleop-twist-keyboard \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /spot_ws
COPY upstream/ /spot_ws/src/upstream/
COPY src/ /spot_ws/src/
RUN source /opt/ros/jazzy/setup.bash \
    && colcon build --cmake-args -DBUILD_TESTING=OFF

ENV ROS_DOMAIN_ID=91 \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    FASTDDS_BUILTIN_TRANSPORTS=UDPv4 \
    QT_X11_NO_MITSHM=1

CMD ["bash", "-lc", "source /spot_ws/install/setup.bash && ros2 launch spot_inspection_sim sim.launch.py"]
