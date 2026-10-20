from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('web_port', default_value='8000'),
        DeclareLaunchArgument('inference_url', default_value='http://127.0.0.1:8081'),
        Node(package='vlm_pick_place', executable='pick_place', output='screen',
             parameters=[{'use_sim_time': True,
                          'web_port': LaunchConfiguration('web_port'),
                          'inference_url': LaunchConfiguration('inference_url')}]),
    ])
