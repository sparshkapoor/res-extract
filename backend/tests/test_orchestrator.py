from app.pipeline.orchestrator import _nudge_forward


def test_nudge_forward_passes_through_when_already_ahead():
    assert _nudge_forward(10.0, last_ts=5.0) == 10.0


def test_nudge_forward_pushes_past_collision():
    # Two steps whose citations both clamp to the same transcript moment
    # would otherwise request the identical frame-extraction timestamp.
    assert _nudge_forward(5.0, last_ts=5.0) == 6.5


def test_nudge_forward_pushes_past_backward_jump():
    assert _nudge_forward(3.0, last_ts=5.0) == 6.5


def test_nudge_forward_respects_custom_gap():
    assert _nudge_forward(5.0, last_ts=5.0, min_gap=2.0) == 7.0
