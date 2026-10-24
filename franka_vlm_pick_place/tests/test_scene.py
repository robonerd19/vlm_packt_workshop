import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

root = Path(__file__).parents[1]/'src/vlm_pick_place'
sys.path.insert(0, str(root))
from vlm_pick_place.description import (CAMERA_RPY, CAMERA_XYZ, GRASPABLE, READY, TABLE_Z,  # noqa: E402
                                        gazebo_urdf)
from vlm_pick_place.kinematics import PandaKinematics, top_down  # noqa: E402
from vlm_pick_place.perception import (PerceptionError, model_size, optical_to_world, parse_box,  # noqa: E402
                                       project_box)

world = ET.parse(root/'worlds/tabletop.sdf').getroot()
poses = {m.get('name'): [float(v) for v in m.find('pose').text.split()]
         for m in world.iter('model') if m.find('pose') is not None}
panda = (Path(__file__).parent/'panda.urdf').read_text()


def test_world_matches_constants():
    assert poses['overhead_camera'][:3] == list(CAMERA_XYZ)
    assert poses['overhead_camera'][3:] == list(CAMERA_RPY)
    assert all(m in poses for m in GRASPABLE)


@pytest.mark.parametrize('name', ['red_cube', 'green_cube', 'blue_cube', 'yellow_tray', 'purple_tray'])
def test_objects_reachable_top_down(name):
    kin = PandaKinematics(panda)
    x, y, z = poses[name][:3]
    for height in (0.0, 0.17):
        kin.inverse((x, y, z - TABLE_Z + height + 0.02), top_down(), READY)


def test_camera_centre_ray_hits_table_below_camera():
    point = optical_to_world((0, 0, CAMERA_XYZ[2] - TABLE_Z), CAMERA_XYZ, CAMERA_RPY)
    assert np.allclose(point, (0.5, 0, TABLE_Z), atol=1e-3)
    # Image right is world -y, image down is world -x (towards the robot).
    assert optical_to_world((0.1, 0, 1.1), CAMERA_XYZ, CAMERA_RPY)[1] == pytest.approx(-0.1, abs=1e-3)
    assert optical_to_world((0, 0.1, 1.1), CAMERA_XYZ, CAMERA_RPY)[0] == pytest.approx(0.4, abs=1e-3)


def test_project_box_finds_cube_top_in_loose_box():
    depth = np.full((480, 640), 1.1, np.float32)
    depth[200:230, 300:330] = 1.06  # 4 cm cube top
    point = project_box((280, 180, 360, 250), depth, (577.0, 577.0, 320.0, 240.0))
    assert point[2] == pytest.approx(1.06)
    assert point[0] == pytest.approx((314.5-320)*1.06/577, abs=1e-3)


def test_parse_box_rejects_bad_output():
    assert parse_box('{"found":true,"bbox":[0,0,320,480]}', 640, 480) == (0, 0, 320, 480)
    # Ollama answers in pixels of its 1036x784 resize of a 4:3 frame.
    assert model_size(640, 480) == (1036, 784)
    assert parse_box('{"found":true,"bbox_2d":[518,392,1036,784]}', 640, 480, (1036, 784)) == (320, 240, 640, 480)
    with pytest.raises(PerceptionError):
        parse_box('{"bbox_2d":[0,0,1037,700]}', 640, 480, (1036, 784))
    for text in ('{"found":false}', '{"bbox":[1,2,3]}', 'nonsense', '{"bbox":[5,5,1,1]}'):
        with pytest.raises(PerceptionError):
            parse_box(text, 640, 480)


def test_gazebo_urdf_has_control_and_grasp_plugins():
    robot = ET.fromstring(gazebo_urdf(panda, '/m', '/c.yaml', TABLE_Z, GRASPABLE))
    assert len(robot.findall('ros2_control/joint')) == 9
    assert all(link.find('inertial') is not None for link in robot.iter('link')
               if link.find('visual') is not None)
    assert len(robot.findall("gazebo/plugin[@name='gz::sim::systems::DetachableJoint']")) == 3
    assert 'package://' not in ET.tostring(robot, encoding='unicode')


def test_check_colour_rejects_wrong_object():
    from vlm_pick_place.perception import check_colour
    image = np.full((100, 200, 3), (128, 166, 210), np.uint8)  # beige table
    image[10:40, 10:40] = (40, 40, 220)     # red cube
    image[50:90, 100:150] = (211, 116, 183)  # purple tray
    check_colour(image, (5, 5, 45, 45), 'red cube')
    check_colour(image, (95, 45, 155, 95), 'the purple tray')
    check_colour(image, (5, 5, 45, 45), 'bin')
    with pytest.raises(PerceptionError, match='blue'):
        check_colour(image, (5, 5, 45, 45), 'blue cube')
    with pytest.raises(PerceptionError, match='green'):
        check_colour(image, (60, 60, 90, 90), 'green cube')  # bare table
