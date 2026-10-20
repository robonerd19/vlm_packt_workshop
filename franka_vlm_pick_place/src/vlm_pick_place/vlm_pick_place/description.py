"""Make the MoveIt Panda URDF simulatable in Gazebo: inertials, ros2_control, grasp attachments."""
import xml.etree.ElementTree as ET

ARM = [f'panda_joint{i}' for i in range(1, 8)]
FINGERS = ['panda_finger_joint1', 'panda_finger_joint2']
READY = [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785]
MASSES = {'panda_link0': 3.0, 'panda_link1': 2.5, 'panda_link2': 2.5, 'panda_link3': 2.0,
          'panda_link4': 2.0, 'panda_link5': 2.0, 'panda_link6': 1.5, 'panda_link7': 0.5,
          'panda_hand': 0.7, 'panda_leftfinger': 0.05, 'panda_rightfinger': 0.05}


def attach_topic(model):
    return f'/grasp/{model}/attach'


def detach_topic(model):
    return f'/grasp/{model}/detach'


def gazebo_urdf(panda_urdf, mesh_dir, controllers_file, base_z, graspable):
    robot = ET.fromstring(panda_urdf.replace('package://moveit_resources_panda_description', 'file://'+mesh_dir))
    for link in robot.iter('link'):
        mass = MASSES.get(link.get('name'))
        if mass:
            # shortcut: uniform approximate inertia; the arm is position-controlled so it is not dynamics-critical.
            inertia = str(max(1e-4, 0.004*mass))
            inertial = ET.SubElement(link, 'inertial')
            ET.SubElement(inertial, 'mass', value=str(mass))
            ET.SubElement(inertial, 'inertia', ixx=inertia, iyy=inertia, izz=inertia, ixy='0', ixz='0', iyz='0')
    for joint in robot.iter('joint'):
        mimic = joint.find('mimic')
        if mimic is not None:
            joint.remove(mimic)  # both fingers are commanded explicitly.
    ET.SubElement(robot, 'link', name='world')
    fix = ET.SubElement(robot, 'joint', name='world_joint', type='fixed')
    ET.SubElement(fix, 'parent', link='world')
    ET.SubElement(fix, 'child', link='panda_link0')
    ET.SubElement(fix, 'origin', xyz=f'0 0 {base_z}', rpy='0 0 0')

    control = ET.SubElement(robot, 'ros2_control', name='GazeboSystem', type='system')
    hardware = ET.SubElement(control, 'hardware')
    ET.SubElement(hardware, 'plugin').text = 'gz_ros2_control/GazeboSimSystem'
    for name, initial in list(zip(ARM, READY)) + [(f, 0.04) for f in FINGERS]:
        joint = ET.SubElement(control, 'joint', name=name)
        ET.SubElement(joint, 'command_interface', name='position')
        state = ET.SubElement(joint, 'state_interface', name='position')
        ET.SubElement(state, 'param', name='initial_value').text = str(initial)
        ET.SubElement(joint, 'state_interface', name='velocity')

    gazebo = ET.SubElement(robot, 'gazebo')
    plugin = ET.SubElement(gazebo, 'plugin', filename='gz_ros2_control-system',
                           name='gz_ros2_control::GazeboSimROS2ControlPlugin')
    ET.SubElement(plugin, 'parameters').text = controllers_file
    for model in graspable:
        # Grasps are rigid attachments: reliable in a workshop, unlike friction grasps in Gazebo.
        # The hand is lumped into panda_link7 because its joints are fixed.
        plugin = ET.SubElement(gazebo, 'plugin', filename='gz-sim-detachable-joint-system',
                               name='gz::sim::systems::DetachableJoint')
        for tag, text in (('parent_link', 'panda_link7'), ('child_model', model), ('child_link', 'link'),
                          ('attach_topic', attach_topic(model)), ('detach_topic', detach_topic(model)),
                          ('suppress_child_warning', 'true')):
            ET.SubElement(plugin, tag).text = text
    return ET.tostring(robot, encoding='unicode')


# Must match worlds/tabletop.sdf (checked by tests/test_world.py).
GRASPABLE = ['red_cube', 'green_cube', 'blue_cube']
TABLE_Z = 0.4
CAMERA_XYZ = (0.5, 0.0, 1.5)
CAMERA_RPY = (0.0, 1.5708, 0.0)
