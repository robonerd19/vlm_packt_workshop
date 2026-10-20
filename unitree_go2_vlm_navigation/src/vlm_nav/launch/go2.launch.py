from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    args = [DeclareLaunchArgument('inference_url', default_value='http://127.0.0.1:8081'),
            DeclareLaunchArgument('web_port', default_value='8000'),
            DeclareLaunchArgument('params_file', default_value=str(Path(
                get_package_share_directory('vlm_nav'))/'config/go2_warehouse.yaml'))]
    params = LaunchConfiguration('params_file')
    return LaunchDescription(args + [
        Node(package='vlm_nav', executable='navigator', name='vlm_navigator', output='screen',
             parameters=[params, {'use_sim_time': True,
                                  'inference_url': LaunchConfiguration('inference_url')}]),
        Node(package='vlm_nav_web', executable='web_bridge', name='vlm_web', output='screen',
             parameters=[params, {'use_sim_time': True,
                                  'port': ParameterValue(LaunchConfiguration('web_port'), value_type=int)}])])
