import math
import numpy as np
import pytest
from vlm_nav.search import viewpoints
from vlm_nav.perception import ObjectNotFound, PerceptionError, UnusableDetection, require_complete_box, parse_box


def test_absence_is_distinct_from_invalid_response():
    with pytest.raises(ObjectNotFound):
        parse_box('{"found":false}', 320, 240)
    with pytest.raises(PerceptionError) as error:
        parse_box('{"found":true,"bbox":[1,2,1,3]}', 320, 240)
    assert not isinstance(error.value, ObjectNotFound)


def test_viewpoints_reject_unknown_and_disconnected_room():
    grid = np.zeros((120, 120), np.int8)
    grid[:, 60] = 100
    grid[:30, :] = -1
    points = viewpoints(grid, 0.1, (-6, -6, 0), (-3, 0), spacing=2, limit=5)
    assert points
    assert len(points) <= 5
    for x, y in points:
        assert x < -0.4
        assert y > -2.6
        assert math.hypot(x+3, y) >= 2
    for i, point in enumerate(points):
        assert all(np.linalg.norm(np.asarray(point)-other) >= 2 for other in points[:i])


def test_rotated_map_and_blocked_start():
    grid = np.zeros((100, 100), np.int8)
    points = viewpoints(grid, 0.1, (10, 20, math.pi/2), (5, 25), limit=2)
    assert len(points) == 2
    assert all(0 < x < 10 and 20 < y < 30 for x, y in points)
    grid[50, 50] = 100
    assert viewpoints(grid, 0.1, (0, 0, 0), (5, 5)) == []


def test_clipped_detection_needs_another_view():
    for box in [(160, 0, 320, 140), (0, 40, 70, 190), (40, 40, 70, 240)]:
        with pytest.raises(UnusableDetection):
            require_complete_box(box, 320, 240)
    require_complete_box((100, 40, 130, 190), 320, 240)


@pytest.mark.parametrize('response, error', [
    ('{"found":true}', None),
    ('{"found":false}', ObjectNotFound),
    ('{"found":"true"}', PerceptionError),
    ('{}', PerceptionError),
])
def test_candidate_identity_confirmation(response, error):
    from vlm_nav.perception import InferenceClient
    client = InferenceClient('http://unused')
    seen = []
    def complete(jpeg, prompt, tokens, timeout=None):
        seen.append((jpeg, prompt, tokens))
        return response if jpeg is None else '{"label":"sculpture"}'
    client.complete = complete
    image = np.zeros((240, 320, 3), np.uint8)
    if error:
        with pytest.raises(error):
            client.confirm(image, (110, 70, 210, 170), 'go to the sculpture')
    else:
        client.confirm(image, (110, 70, 210, 170), 'go to the sculpture')
    import cv2
    crop = cv2.imdecode(seen[0][0], cv2.IMREAD_COLOR)
    assert crop.shape[:2] == (120, 120)
    assert 'go to the sculpture' not in seen[0][1]
    assert 'go to the sculpture' in seen[1][1]


def test_identity_synonyms_and_requested_attributes():
    from vlm_nav.perception import identity_matches
    assert identity_matches('man in purple shirt and khaki shorts', 'go to the standing person') is True
    assert identity_matches('yellow pen', 'go to the standing person') is False
    assert identity_matches('black and yellow floor markings', 'find the person') is False
    assert identity_matches('blue chair', 'go to the red chair') is False
    assert identity_matches('gray crate', 'go to the grey box') is True
    assert identity_matches('seated woman', 'go to the standing person') is False
    assert identity_matches('sculpture', 'go to the sculpture') is None
