"""Official TurtleBot 4 warehouse assets with a CPU navigation sensor preset."""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def launch_scene(context):
    share = Path(get_package_share_directory('vlm_nav_sim'))
    scene = LaunchConfiguration('scene').perform(context)
    warehouse = scene == 'warehouse'
    world = share/'worlds'/('warehouse.sdf' if warehouse else 'workshop.sdf')
    robot = share/'urdf'/('turtlebot4.urdf' if warehouse else 'robot.urdf')
    if not world.exists() or not robot.exists():
        raise RuntimeError('Warehouse assets are generated during the Docker image build. Rebuild the ROS image.')
    actions = [ExecuteProcess(cmd=['gz', 'sim', '-s', '-r', str(world)], output='screen'),
        Node(package='ros_gz_bridge', executable='parameter_bridge',
             parameters=[{'config_file': str(share/'config/bridge.yaml'), 'use_sim_time': True}], output='screen'),
        Node(package='robot_state_publisher', executable='robot_state_publisher',
             parameters=[{'robot_description': robot.read_text(), 'use_sim_time': True}], output='screen')]
    if warehouse:
        actions.append(Node(package='ros_gz_sim', executable='create',
                            arguments=['-world', 'warehouse', '-name', 'turtlebot4',
                                       '-file', str(robot), '-x', '-3.0', '-y', '-1.0', '-z', '0.02'],
                            output='screen'))
        # Lightweight local objects for VLM selection from the home camera view.
        # Each includes collision geometry for the existing lidar/costmap pipeline.
        for target, x, y, yaw in (('red_chair', -0.2, 0.45, 0.6),
                                  ('blue_barrel', 0.4, -1.85, 0.0),
                                  ('cardboard_box', 0.5, 0.0, 0.0),
                                  # Remote targets exercise the existing bounded map search.
                                  ('green_crate', -5.0, -0.75, 0.0),
                                  ('orange_cone', 3.0, -1.0, 0.0),
                                  ('yellow_box', 6.0, -1.0, 0.0)):
            actions.append(Node(package='ros_gz_sim', executable='create',
                                arguments=['-world', 'warehouse', '-file',
                                           str(share/'worlds'/'targets'/f'{target}.sdf'),
                                           '-x', str(x), '-y', str(y), '-z', '0.0',
                                           '-Y', str(yaw)], output='screen'))
    return actions


def generate_launch_description():
    return LaunchDescription([DeclareLaunchArgument('scene', default_value='warehouse',
        choices=['warehouse', 'workshop']), OpaqueFunction(function=launch_scene)])
