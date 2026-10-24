import json
import math
from types import SimpleNamespace

import numpy as np

from spot_inspection.inspector import Inspector, drive_command, judge

GAUGE = {'max_value': 6.0}
LEAK = {'anomaly_if': 'yes'}


def test_judge_gauge_reading():
    assert judge('9', GAUGE) == (True, 9.0)
    assert judge('The needle points at 3.8 bar.', GAUGE) == (False, 3.8)
    assert judge('I cannot tell', GAUGE) == (None, None)


def test_judge_yes_no():
    assert judge('Yes.', LEAK) == (True, 'yes')
    assert judge('no', LEAK) == (False, 'no')
    assert judge('No', {'anomaly_if': 'no'}) == (True, 'no')
    assert judge('Maybe', LEAK) == (None, None)
    assert judge('', LEAK) == (None, None)


def test_drive_command_turns_then_walks_then_arrives():
    vx, wz, done = drive_command(0, 0, 0, 0, 3)  # goal 90 deg left: turn in place
    assert vx == 0 and wz > 0 and not done
    vx, wz, done = drive_command(0, 0, math.pi / 2, 0, 3)  # facing it: walk
    assert vx > 0 and abs(wz) < 1e-6 and not done
    assert drive_command(0, 2.95, 0, 0, 3)[2]


def test_zoom_crops_centre():
    import numpy as np
    from spot_inspection.inspector import zoom
    img = np.arange(16).reshape(4, 4)
    assert zoom(img, 2).tolist() == [[5, 6], [9, 10]]
    assert zoom(img, 1) is img


def test_unreached_station_is_unknown_not_ok(tmp_path):
    node = Inspector.__new__(Inspector)  # skip ROS setup; only run() is exercised
    node.stations = [{'name': 'S3 flange', 'x': 5.0, 'y': 0.0, 'yaw': 0,
                      'question': 'Is water leaking?', 'anomaly_if': 'yes'}]
    node.report_dir, node.return_home, node.pose = tmp_path, False, (0.0, 0.0, 0.0)
    node.walk_to = lambda *_: False  # stuck on the way
    node.capture = lambda: np.zeros((8, 8, 3), np.uint8)
    node.ask_vlm = lambda *_: 'No'  # a wall shows no leak: would read as OK
    node.report = SimpleNamespace(publish=lambda _: None)
    node.get_logger = lambda: SimpleNamespace(info=lambda *_, **__: None)

    node.run()

    result = json.loads(next(tmp_path.glob('*/results.json')).read_text())[0]
    assert result['anomaly'] is None
