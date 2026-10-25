import numpy as np

from spot_vlm_teleop import vlm


def test_model_size_matches_ollama_upscale_of_640x480():
    assert vlm.model_size(640, 480) == (1036, 784)


def test_parse_objects_scales_to_frame_and_skips_bad_entries():
    # A reply cut off at the token limit, with one invalid and one duplicate entry.
    text = ('{"objects":[{"label":"green dumpster","bbox_2d":[518,196,777,588]},'
            '{"label":"bad","bbox_2d":[1,2]},{"label":"green dumpster","bbox_2d":[518,196,777,588]},'
            '{"label":"red barrel","bbox_2d":[0,0,2000,900]},{"label":"blue cr')
    objects = vlm.parse_objects(text, 960, 720)
    assert [label for label, _ in objects] == ['green dumpster', 'red barrel']
    assert objects[0][1] == (480.0, 180.0, 720.0, 540.0)  # 1036x784 model pixels -> 960x720 frame
    assert objects[1][1] == (0.0, 0.0, 960.0, 720.0)      # clipped to the frame


def test_draw_objects_leaves_the_input_frame_untouched():
    frame = np.zeros((720, 960, 3), np.uint8)
    out = vlm.draw_objects(frame, [('red barrel', (100.0, 100.0, 300.0, 400.0))])
    assert not frame.any() and out.any()
