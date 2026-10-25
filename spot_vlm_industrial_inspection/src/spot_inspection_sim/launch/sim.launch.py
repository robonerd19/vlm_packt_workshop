"""Gazebo industrial plant + Spot (official RAI model) walking with the CHAMP gait.

Adapted from the Unitree Go2 CHAMP launch in ../unitree_go2_vlm_navigation.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (AppendEnvironmentVariable, DeclareLaunchArgument, ExecuteProcess,
                            IncludeLaunchDescription, SetEnvironmentVariable)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node, SetParameter
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    sim = get_package_share_directory('spot_inspection_sim')
    cfg = lambda name: os.path.join(sim, 'config', name)  # noqa: E731
    urdf = ParameterValue(Command(['xacro ', os.path.join(sim, 'urdf', 'spot_gazebo.urdf.xacro'),
                    ' robot_controllers:=', cfg('ros_control.yaml')]), value_type=str)
    champ_cfg = [cfg('joints.yaml'), cfg('links.yaml'), cfg('gait.yaml')]
    arg = LaunchConfiguration

    return LaunchDescription([
        DeclareLaunchArgument('world', default_value=os.path.join(sim, 'worlds', 'industrial_plant.sdf')),
        DeclareLaunchArgument('spawn_z', default_value='0.55'),
        SetParameter(name='use_sim_time', value=True),
        # Without a fixed gz-transport interface the server hung before world load (black GUI,
        # `create` waiting for world names) on a laptop with Wi-Fi plus Docker bridges.
        SetEnvironmentVariable('GZ_IP', EnvironmentVariable('GZ_IP', default_value='127.0.0.1')),
        # package:// mesh URIs and the world's relative texture paths resolve through this path
        AppendEnvironmentVariable('GZ_SIM_RESOURCE_PATH',
                                  os.path.dirname(get_package_share_directory('spot_description'))),
        AppendEnvironmentVariable('GZ_SIM_RESOURCE_PATH', os.path.join(sim, 'worlds')),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(
                get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')),
            launch_arguments={'gz_args': [arg('world'), ' -s -r'], 'on_exit_shutdown': 'true'}.items()),
        # Separate GUI process: a combined `gz sim` (server+GUI fork) hung its server before world load.
        ExecuteProcess(cmd=['gz', 'sim', '-g'], output='screen'),
        Node(package='robot_state_publisher', executable='robot_state_publisher', output='screen',
             parameters=[{'robot_description': urdf}]),
        Node(package='ros_gz_sim', executable='create', output='screen',
             arguments=['-name', 'spot', '-topic', 'robot_description', '-z', arg('spawn_z')]),
        Node(package='ros_gz_bridge', executable='parameter_bridge', output='screen', arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/imu/data@sensor_msgs/msg/Imu[gz.msgs.IMU',
            '/odom/ground_truth@nav_msgs/msg/Odometry[gz.msgs.Odometry',
            '/inspection_camera/image@sensor_msgs/msg/Image[gz.msgs.Image',
        ]),

        # CHAMP gait: /cmd_vel -> joint trajectories; publishes planned foot contacts itself
        Node(package='champ_base', executable='quadruped_controller_node', output='screen',
             parameters=[{'gazebo': True, 'publish_joint_states': True, 'publish_joint_control': True,
                          'publish_foot_contacts': True,
                          'joint_controller_topic': 'joint_group_position_controller/joint_trajectory',
                          'urdf': urdf, 'hardware_connected': False, 'close_loop_odom': True},
                         *champ_cfg],
             remappings=[('/cmd_vel/smooth', '/cmd_vel')]),
        Node(package='champ_base', executable='state_estimation_node', output='screen',
             parameters=[{'orientation_from_imu': True, 'urdf': urdf}, *champ_cfg]),
        Node(package='robot_localization', executable='ekf_node', name='base_to_footprint_ekf',
             parameters=[cfg('ekf_base_to_footprint.yaml')], remappings=[('odometry/filtered', 'odom/local')]),
        Node(package='robot_localization', executable='ekf_node', name='footprint_to_odom_ekf',
             parameters=[cfg('ekf_footprint_to_odom.yaml')], remappings=[('odometry/filtered', 'odom')]),

        # One spawner for both: two spawners started together race for the same lock file
        Node(package='controller_manager', executable='spawner', output='screen',
             arguments=['--controller-manager-timeout', '120',
                        'joint_states_controller', 'joint_group_position_controller']),
    ])
