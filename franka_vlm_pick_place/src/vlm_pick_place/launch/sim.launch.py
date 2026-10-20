"""Gazebo tabletop with a Panda under ros2_control and an overhead RGB-D camera."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch_ros.actions import Node

from vlm_pick_place.description import GRASPABLE, TABLE_Z, attach_topic, detach_topic, gazebo_urdf


def generate_launch_description():
    share = Path(get_package_share_directory('vlm_pick_place'))
    panda = Path(get_package_share_directory('moveit_resources_panda_description'))
    urdf = gazebo_urdf((panda/'urdf/panda.urdf').read_text(), str(panda), str(share/'config/controllers.yaml'),
                       TABLE_Z, GRASPABLE)
    grasp_topics = [f'{t}@std_msgs/msg/Empty]gz.msgs.Empty'
                    for m in GRASPABLE for t in (attach_topic(m), detach_topic(m))]
    spawn = Node(package='ros_gz_sim', executable='create', output='screen',
                 arguments=['-world', 'tabletop', '-name', 'panda', '-topic', 'robot_description'])
    controllers = Node(package='controller_manager', executable='spawner', output='screen',
                       arguments=['joint_state_broadcaster', 'arm_controller', 'gripper_controller',
                                  '--controller-manager-timeout', '120'])
    return LaunchDescription([
        ExecuteProcess(cmd=['gz', 'sim', '-s', '-r', str(share/'worlds/tabletop.sdf')], output='screen'),
        # Two bridges: parameter_bridge ignores config_file when topics are also given as arguments.
        Node(package='ros_gz_bridge', executable='parameter_bridge', output='screen',
             parameters=[{'config_file': str(share/'config/bridge.yaml'), 'use_sim_time': True}]),
        Node(package='ros_gz_bridge', executable='parameter_bridge', name='grasp_bridge', output='screen',
             arguments=grasp_topics),
        Node(package='robot_state_publisher', executable='robot_state_publisher', output='screen',
             parameters=[{'robot_description': urdf, 'use_sim_time': True}]),
        spawn,
        RegisterEventHandler(OnProcessExit(target_action=spawn, on_exit=[controllers])),
    ])
