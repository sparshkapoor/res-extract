from pathlib import Path

from app.models import Ingredient
from app.pipeline.vlm import _select_hero, _split_generic_ingredient


def test_select_hero_picks_highest_confidence_true_result():
    candidates = [Path("hero_0.jpg"), Path("hero_1.jpg"), Path("hero_2.jpg")]
    results = {
        "hero:0": {"is_hero_shot": True, "confidence": "low"},
        "hero:1": {"is_hero_shot": True, "confidence": "high"},
        "hero:2": {"is_hero_shot": False, "confidence": "high"},
    }
    assert _select_hero(candidates, results) == Path("hero_1.jpg")


def test_select_hero_ignores_non_hero_results_regardless_of_confidence():
    candidates = [Path("hero_0.jpg"), Path("hero_1.jpg")]
    results = {
        "hero:0": {"is_hero_shot": False, "confidence": "high"},
        "hero:1": {"is_hero_shot": True, "confidence": "low"},
    }
    # is_hero_shot=True wins over a "high" confidence False result — the
    # boolean gate matters more than confidence, which only breaks ties
    # among candidates the VLM actually marked as hero shots.
    assert _select_hero(candidates, results) == Path("hero_1.jpg")


def test_select_hero_returns_none_when_no_results():
    assert _select_hero([Path("hero_0.jpg")], {}) is None


def test_split_generic_ingredient_preserves_quantity_shape():
    generic = Ingredient(name="spices", quantity=None, unit=None, name_is_generic=True)
    split = _split_generic_ingredient(generic, ["paprika", "cumin"])
    assert [i.name for i in split] == ["paprika", "cumin"]
    assert all(i.is_estimated and not i.name_is_generic for i in split)
    assert all(i.quantity is None and i.unit is None for i in split)
