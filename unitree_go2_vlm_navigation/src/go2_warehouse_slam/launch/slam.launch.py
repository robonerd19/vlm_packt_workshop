import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    slam_share = get_package_share_directory("go2_warehouse_slam")
    nav2_share = get_package_share_directory("nav2_bringup")
    params_file = LaunchConfiguration("params_file")
    nav2_params = LaunchConfiguration("nav2_params")
    use_sim_time = LaunchConfiguration("use_sim_time", default="true")
    autostart = LaunchConfiguration("autostart", default="true")

    scan_converter = Node(
        package="pointcloud_to_laserscan",
        executable="pointcloud_to_laserscan_node",
        name="velodyne_to_scan",
        output="screen",
        parameters=[
            {
                "use_sim_time": use_sim_time,
                "target_frame": "base_footprint",  # gravity-aligned, so gait pitch does not tilt the slice into the floor
                "transform_tolerance": 0.1,
                "min_height": 0.15,
                "max_height": 0.90,
                "angle_min": -3.14159265,
                "angle_max": 3.14159265,
                "angle_increment": 0.00872665,
                "scan_time": 0.1,
                "range_min": 0.5,
                "range_max": 20.0,
                "use_inf": True,
                "inf_epsilon": 1.0,
            }
        ],
        remappings=[("cloud_in", "/velodyne_points/points"), ("scan", "/scan")],
    )
    slam_bringup_share = get_package_share_directory("slam_toolbox")
    mapper = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(slam_bringup_share, "launch", "online_sync_launch.py")
        ),
        launch_arguments={
            "slam_params_file": params_file,
            "use_sim_time": use_sim_time,
            "autostart": autostart,
            "use_lifecycle_manager": "false",
        }.items(),
    )
    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(nav2_share, "launch", "navigation_launch.py")),
        launch_arguments={
            "params_file": nav2_params,
            "use_sim_time": use_sim_time,
            "autostart": autostart,
            "use_composition": "False",
        }.items(),
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "params_file", default_value=os.path.join(slam_share, "config", "mapper_params_online_sync.yaml")
            ),
            DeclareLaunchArgument(
                "nav2_params",
                default_value=os.path.join(
                    get_package_share_directory("go2_warehouse_nav2"), "config", "nav2_params.yaml"
                ),
            ),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("autostart", default_value="true"),
            scan_converter,
            mapper,
            navigation,
        ]
    )
