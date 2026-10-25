"""Spot in the teleop room: the Spot inspection simulation with this package's world."""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import AppendEnvironmentVariable, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    share = get_package_share_directory('spot_vlm_teleop')
    spot_sim = get_package_share_directory('spot_inspection_sim')
    return LaunchDescription([
        AppendEnvironmentVariable('GZ_SIM_RESOURCE_PATH', os.path.join(share, 'worlds', 'models')),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(spot_sim, 'launch', 'sim.launch.py')),
            launch_arguments={'world': os.path.join(share, 'worlds', 'room.sdf')}.items()),
    ])
