import sys
import threading
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('rclpy')  # needs the ROS image: run inside franka-vlm-ros:local
sys.path.insert(0, str(Path(__file__).parents[1]/'src/vlm_pick_place'))
from vlm_pick_place.pick_place_node import PickPlace  # noqa: E402


class Publisher:
    def __init__(self):
        self.count = 0

    def publish(self, _):
        self.count += 1


class FakeVlm:
    def describe(self, bgr):
        return ['red cube', 'yellow tray']

    def plan(self, instruction):
        return 'red cube', 'yellow tray'


def test_failed_place_releases_the_attached_cube():
    node = PickPlace.__new__(PickPlace)  # skip ROS setup; only run() is exercised
    node.lock = threading.Lock()
    node.state = {'busy': True, 'log': [], 'objects': [], 'plan': None}
    node.log = lambda text: None
    node.move_joints = node.grip = lambda *_: None
    node.fresh_frames = lambda: (np.zeros((8, 8, 3), np.uint8), np.zeros((8, 8), np.float32))
    node.vlm = FakeVlm()
    node.locate = lambda bgr, depth, phrase, *_: np.array([0.5, 0.0 if phrase == 'red cube' else 0.3, 0.45])
    node.held_model = lambda tcp: 'red_cube'
    node.attach, node.detach = {'red_cube': Publisher()}, {'red_cube': Publisher()}
    moves = []

    def move_tcp(xyz, steps=1, seed=None):
        moves.append(xyz)
        if len(moves) == 4:  # above-grasp, descend, lift, then the move to the place point fails
            raise ValueError('IK did not converge')
    node.move_tcp = move_tcp

    node.run('put the red cube on the yellow tray')

    assert node.attach['red_cube'].count == 1
    assert node.detach['red_cube'].count == 1
    assert node.state['busy'] is False
