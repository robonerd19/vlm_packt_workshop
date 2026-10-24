import json
import numpy as np
import pytest
from vlm_nav.perception import InferenceClient, PerceptionError, approach_goal, description_matches, identity_matches, model_size, parse_box, project_box


def test_box_coordinates_map_back_to_original_image():
    assert parse_box('{"found":true,"bbox":[160,120,480,360]}',640,480)==(160,120,480,360)


def test_ollama_pixel_box_scales_from_sent_size():
    # Real qwen2.5vl:3b answer for the standing person in the 320x240 home view.
    assert model_size(320, 240) == model_size(640, 480) == model_size(1008, 756) == (1036, 784)
    x1, y1, x2, y2 = parse_box('{"found":true,"bbox_2d":[456,129,557,442]}', 320, 240, (1036, 784))
    assert 138 < x1 < 148 and 34 < y1 < 44 and 168 < x2 < 178 and 133 < y2 < 143


@pytest.mark.parametrize('box',[[800,0,200,700],[-1,0,1000,700],[0,0,1009,700],[0,0,500,757],
                               [0,0,0,20],[True,0,1000,700],[0,0,float('nan'),700]])
def test_invalid_coordinates_are_rejected(box):
    with pytest.raises(PerceptionError):parse_box(json.dumps({'bbox_2d':box}),320,240,(1008,756))


def test_missing_object_rejected():
    with pytest.raises(PerceptionError):parse_box('{"found":false}',320,240)


def test_calibrated_projection_and_standoff():
    depth=np.full((240,320),3.,dtype=np.float32)
    point=project_box((112,72,208,168),depth,(280,280,160,120))
    assert np.allclose(point,[0,0,3])
    assert np.allclose(approach_goal((3,0),(0,0),.8),(2.2,0,0))


def test_invalid_depth_and_calibration_rejected():
    with pytest.raises(PerceptionError):project_box((112,72,208,168),np.zeros((240,320)),(280,280,160,120))
    with pytest.raises(PerceptionError):project_box((112,72,208,168),np.ones((240,320)),(0,280,160,120))


def test_hollow_object_uses_foreground_instead_of_background_at_box_centre():
    depth=np.full((240,320),6.)
    depth[72:102,112:208]=2.5
    depth[102:168,112:124]=2.5
    depth[102:168,196:208]=2.5
    point=project_box((112,72,208,168),depth,(280,280,160,120))
    assert point[2] == 2.5


def test_sparse_near_depth_noise_does_not_move_target():
    depth=np.full((240,320),3.)
    depth[115:121,155:166]=1.
    point=project_box((112,72,208,168),depth,(280,280,160,120))
    assert point[2] == 3.


def test_depth_without_a_coherent_surface_is_rejected():
    depth=np.tile(np.linspace(1,7,320),(240,1))
    with pytest.raises(PerceptionError):project_box((0,0,320,240),depth,(280,280,160,120))


def test_frame_description_uses_the_image_without_a_navigation_target():
    client = object.__new__(InferenceClient)
    client.image_width = 320
    captured = {}
    def complete(jpeg, prompt, tokens, timeout=None):
        captured.update(jpeg=jpeg, prompt=prompt, tokens=tokens)
        return '{"scene":"a blue barrel"}'
    client.complete = complete
    assert client.describe(np.zeros((240,320,3), dtype=np.uint8)) == '{"scene":"a blue barrel"}'
    assert captured['jpeg'] is not None
    assert captured['tokens'] == 96
    assert 'Locate the single object requested' not in captured['prompt']


def test_frame_description_can_confirm_a_matching_target_without_using_a_crop():
    assert description_matches('{"scene":"a standing person in a purple shirt"}',
                               'go to the standing person')
    assert not description_matches('{"scene":"yellow safety barrier and shelves"}',
                                   'go to the standing person')


def test_named_color_rejects_any_class_before_text_comparison():
    assert identity_matches('green object with wheels', 'go to the blue sofa') is False
    assert identity_matches('green object with wheels', 'go to the green dumpster') is None
    assert identity_matches('object with wheels', 'go to the blue sofa') is None
