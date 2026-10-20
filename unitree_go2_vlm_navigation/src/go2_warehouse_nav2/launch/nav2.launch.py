import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory("go2_warehouse_nav2")
    nav2_share = get_package_share_directory("nav2_bringup")
    map_file = LaunchConfiguration("map")
    params_file = LaunchConfiguration("params_file")
    use_sim_time = LaunchConfiguration("use_sim_time", default="true")
    autostart = LaunchConfiguration("autostart", default="true")
    rviz = LaunchConfiguration("rviz", default="false")

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

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(nav2_share, "launch", "bringup_launch.py")),
        launch_arguments={
            "map": map_file,
            "params_file": params_file,
            "use_sim_time": use_sim_time,
            "autostart": autostart,
            "slam": "False",
            "use_composition": "False",
        }.items(),
    )
    # bringup_launch.py has no RViz argument, so include Nav2's RViz launch directly
    rviz_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(nav2_share, "launch", "rviz_launch.py")),
        launch_arguments={"use_sim_time": use_sim_time}.items(),
        condition=IfCondition(rviz),
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "map", default_value=os.path.join(package_share, "maps", "warehouse", "warehouse.yaml")
            ),
            DeclareLaunchArgument(
                "params_file", default_value=os.path.join(package_share, "config", "nav2_params.yaml")
            ),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("autostart", default_value="true"),
            DeclareLaunchArgument("rviz", default_value="false"),
            scan_converter,
            nav2,
            rviz_launch,
        ]
    )
