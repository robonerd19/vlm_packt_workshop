import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]/'src/vlm_pick_place'))
from vlm_pick_place.kinematics import PandaKinematics, top_down  # noqa: E402

READY = [0, -0.785, 0, -2.356, 0, 1.571, 0.785]
kin = PandaKinematics((Path(__file__).parent/'panda.urdf').read_text())


def test_ready_pose_points_down_in_front():
    t = kin.forward(READY)
    assert t[0, 3] == pytest.approx(0.307, abs=0.01)
    assert t[2, 3] == pytest.approx(0.48, abs=0.02)
    assert np.allclose(t[:3, :3], top_down(), atol=1e-2)


@pytest.mark.parametrize('xyz,yaw', [((0.5, 0.0, 0.05), 0.0), ((0.45, -0.25, 0.15), 0.6),
                                     ((0.6, 0.2, 0.02), -0.4)])
def test_ik_round_trip(xyz, yaw):
    q = kin.inverse(xyz, top_down(yaw), READY)
    t = kin.forward(q)
    assert np.allclose(t[:3, 3], xyz, atol=1e-3)
    assert np.allclose(t[:3, :3], top_down(yaw), atol=1e-2)
    assert np.all(q >= kin.lower) and np.all(q <= kin.upper)


def test_unreachable_raises():
    with pytest.raises(ValueError):
        kin.inverse((1.5, 0, 0.0), top_down(), READY)
