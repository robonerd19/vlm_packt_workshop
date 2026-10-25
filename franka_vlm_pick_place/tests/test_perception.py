import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]/'src/vlm_pick_place'))
from vlm_pick_place.perception import InferenceClient  # noqa: E402


def test_describe_accepts_strings_or_color_type_objects():
    client = InferenceClient('http://unused')
    image = np.zeros((48, 64, 3), np.uint8)
    client.complete = lambda *_a: '{"objects":["red cube"," yellow tray "]}'
    assert client.describe(image) == ['red cube', 'yellow tray']
    # Seen from qwen2.5vl:3b once a cube was stacked on a tray.
    client.complete = lambda *_a: '{"objects":[{"color":"yellow","type":"square"},{"color":"blue","type":"cube"}]}'
    assert client.describe(image) == ['yellow square', 'blue cube']
