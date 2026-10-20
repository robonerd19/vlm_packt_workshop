from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    arg = LaunchConfiguration
    return LaunchDescription([
        DeclareLaunchArgument('inference_url', default_value='http://127.0.0.1:8081'),
        DeclareLaunchArgument('report_dir', default_value='/tmp/spot_inspection'),
        Node(package='spot_inspection', executable='inspector', output='screen', emulate_tty=True,
             parameters=[{'use_sim_time': True, 'inference_url': arg('inference_url'),
                          'report_dir': arg('report_dir')}]),
    ])
