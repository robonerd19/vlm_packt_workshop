from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    args = [DeclareLaunchArgument('inference_url', default_value='http://127.0.0.1:8081'),
            DeclareLaunchArgument('use_sim_time', default_value='true'),
            DeclareLaunchArgument('web_bind', default_value='127.0.0.1'),
            DeclareLaunchArgument('web_port', default_value='8000'),
            DeclareLaunchArgument('params_file', default_value=str(Path(
                get_package_share_directory('vlm_nav_bringup'))/'config/low_memory.yaml'))]
    common = {'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool)}
    return LaunchDescription(args + [
        Node(package='vlm_nav', executable='navigator', name='vlm_navigator', output='screen',
             parameters=[LaunchConfiguration('params_file'), common,
                         {'inference_url': LaunchConfiguration('inference_url')}]),
        Node(package='vlm_nav_web', executable='web_bridge', name='vlm_web', output='screen',
             parameters=[LaunchConfiguration('params_file'), common,
                         {'bind': LaunchConfiguration('web_bind'),
                          'port': ParameterValue(LaunchConfiguration('web_port'), value_type=int)}])])
