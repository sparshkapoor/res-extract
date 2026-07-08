from app.models import Ingredient, Platform
from app.pipeline.orchestrator import _nudge_forward, _should_mine_comments


def _ing(is_estimated: bool) -> Ingredient:
    return Ingredient(name="test", is_estimated=is_estimated)


def test_should_mine_comments_requires_youtube():
    assert not _should_mine_comments(Platform.instagram, [_ing(True)], enabled=True)


def test_should_mine_comments_requires_an_estimated_ingredient():
    assert not _should_mine_comments(Platform.youtube, [_ing(False), _ing(False)], enabled=True)


def test_should_mine_comments_respects_feature_flag():
    assert not _should_mine_comments(Platform.youtube, [_ing(True)], enabled=False)


def test_should_mine_comments_true_when_all_conditions_met():
    assert _should_mine_comments(Platform.youtube, [_ing(False), _ing(True)], enabled=True)


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
