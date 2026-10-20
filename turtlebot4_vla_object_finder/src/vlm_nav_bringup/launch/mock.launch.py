from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory('vlm_nav_bringup'))
    return LaunchDescription([
        Node(package='vlm_nav_demo', executable='mock_inference', output='screen'),
        Node(package='vlm_nav_demo', executable='fixture', output='screen'),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(share/'launch/app.launch.py')),
                                 launch_arguments={'params_file': str(share/'config/mock.yaml')}.items())])
