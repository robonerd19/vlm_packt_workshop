"""Launch the required Nav2 servers with complete child-costmap YAML scopes."""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def launch_navigation(context):
    share = Path(get_package_share_directory('vlm_nav_bringup'))
    sim = Path(get_package_share_directory('vlm_nav_sim'))
    warehouse = LaunchConfiguration('scene').perform(context) == 'warehouse'
    params = str(share/'config/nav2.yaml')
    nodes = []
    names = []
    # Separate processes preserve the params-file for the costmap nodes created
    # internally by planner/controller. ComposableNode extracts only parent params.
    for name, package, executable, remap in [
        ('map_server', 'nav2_map_server', 'map_server', []),
        ('amcl', 'nav2_amcl', 'amcl', []),
        ('controller_server', 'nav2_controller', 'controller_server', [('cmd_vel','cmd_vel_nav')]),
        ('planner_server', 'nav2_planner', 'planner_server', []),
        ('behavior_server', 'nav2_behaviors', 'behavior_server', [('cmd_vel','cmd_vel_nav')]),
        ('bt_navigator', 'nav2_bt_navigator', 'bt_navigator', []),
        ('velocity_smoother', 'nav2_velocity_smoother', 'velocity_smoother', [('cmd_vel','cmd_vel_nav')]),
        ('collision_monitor', 'nav2_collision_monitor', 'collision_monitor', [])]:
        extra = {'use_sim_time': True}
        if name == 'map_server':
            extra['yaml_filename'] = str(sim/'maps'/('warehouse.yaml' if warehouse else 'room.yaml'))
        if name == 'amcl' and warehouse:
            extra.update({'initial_pose.x': -3.0, 'initial_pose.y': -1.0})
        nodes.append(Node(package=package, executable=executable, name=name,
                          parameters=[params, extra], remappings=remap, output='screen'))
        names.append(name)
    nodes.append(Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
                      name='lifecycle_manager_navigation', output='screen',
                      parameters=[{'use_sim_time': True,'autostart': True,'node_names': names}]))
    return nodes + [IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(share/'launch/app.launch.py')),
        launch_arguments={'params_file': str(share/'config'/('warehouse.yaml' if warehouse else 'low_memory.yaml'))}.items())]


def generate_launch_description():
    return LaunchDescription([DeclareLaunchArgument('scene', default_value='warehouse',
        choices=['warehouse', 'workshop']), OpaqueFunction(function=launch_navigation)])
