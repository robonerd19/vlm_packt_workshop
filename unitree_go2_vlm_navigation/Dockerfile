FROM osrf/ros:jazzy-desktop

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      git python3-colcon-common-extensions python3-rosdep python3-vcstool \
      ros-jazzy-gz-ros2-control ros-jazzy-ros-gz \
      ros-jazzy-robot-localization ros-jazzy-ros2-controllers \
      ros-jazzy-velodyne ros-jazzy-velodyne-description \
      ros-jazzy-realsense2-description ros-jazzy-xacro \
      ros-jazzy-joint-state-publisher-gui \
      ros-jazzy-teleop-twist-keyboard ros-jazzy-rqt-robot-steering \
      ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-slam-toolbox \
      ros-jazzy-pointcloud-to-laserscan python3-flask \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /go2_ws
COPY src/ /go2_ws/src/
COPY upstream/unitree_go2_ros2/champ/ /go2_ws/src/upstream/champ/
COPY upstream/unitree_go2_ros2/champ_base/ /go2_ws/src/upstream/champ_base/
COPY upstream/unitree_go2_ros2/champ_msgs/ /go2_ws/src/upstream/champ_msgs/

# The upstream manifest has a plural typo for unitree_application. The
# ament_python build tool is provided by ROS Jazzy but is not a rosdep key.
RUN source /opt/ros/jazzy/setup.bash \
    && rosdep update \
    && rosdep install --rosdistro jazzy --from-paths src --ignore-src \
         --skip-keys=ament_python -r -y \
    && colcon build --executor sequential --symlink-install

ENV ROS_DOMAIN_ID=89 \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    FASTDDS_BUILTIN_TRANSPORTS=UDPv4 \
    QT_X11_NO_MITSHM=1

CMD ["bash", "-lc", "source /go2_ws/install/setup.bash && ros2 launch unitree_go2_sim unitree_go2_launch.py rviz:=false"]
