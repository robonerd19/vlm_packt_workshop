from vlm_nav.perception import identity_matches


def test_named_color_rejects_any_class_before_text_comparison():
    assert identity_matches('green object with wheels', 'go to the blue sofa') is False
    assert identity_matches('green object with wheels', 'go to the green dumpster') is None
    assert identity_matches('object with wheels', 'go to the blue sofa') is None


def test_object_list_skips_invalid_entries_and_memory_matches_by_color():
    import numpy as np
    from vlm_nav.perception import InferenceClient
    client = InferenceClient('http://unused')
    client.complete = lambda *_args, **_kw: (
        '{"objects":[{"label":"Green container","bbox":[500,100,700,600]},'
        '{"label":"bad","bbox":[9,9,1,1]},{"bbox":[0,0,10,10]}]}')
    found, _ = client.list_objects(np.zeros((480, 640, 3), np.uint8))
    assert found == [('green container', (320.0, 48.0, 448.0, 288.0))]
    client.complete = lambda *_args, **_kw: '{"index":0}'
    assert client.match_memory(['green container', 'yellow shelf'], 'go to the green dumpster') == 0
    assert client.match_memory(['yellow shelf'], 'go to the green dumpster') is None


def test_object_list_salvages_repeated_truncated_output():
    import numpy as np
    from vlm_nav.perception import InferenceClient
    client = InferenceClient('http://unused')
    client.complete = lambda *_a, **_k: (
        '{"objects":[{"label":"yellow box","bbox":[412,367,572,550]},'
        '{"label":"yellow box","bbox":[412,367,572,550]},{"label":"tape","bbox":[0,0,1000,1000]},{"label":"yel')
    found, _ = client.list_objects(np.zeros((480, 640, 3), np.uint8))
    assert [label for label, _ in found] == ['yellow box']


def test_memory_match_requires_the_named_color():
    from vlm_nav.perception import InferenceClient
    client = InferenceClient('http://unused')
    asked = []
    client.complete = lambda _jpeg, prompt, *_a, **_k: asked.append(prompt) or '{"index":2}'
    assert client.match_memory(['boxes', 'yellow boxes', 'green trash bin'], 'go to the green dumpster') == 2
    assert 'boxes;' not in asked[0] and '0: boxes' not in asked[0]
