from app.models import Ingredient, Platform, Recipe, Step, TranscriptSegment
from app.pipeline.validate import build_corrective_note, expected_min_steps, validate_recipe


def _ing(name: str) -> Ingredient:
    return Ingredient(name=name)


def _step(index: int, instruction: str, citation: str) -> Step:
    return Step(index=index, instruction=instruction, verbatim_transcript_citation=citation)


def _recipe(ingredients: list[Ingredient], steps: list[Step]) -> Recipe:
    return Recipe(
        title="Test Recipe",
        source_url="https://example.com/x",
        platform=Platform.youtube,
        ingredients=ingredients,
        steps=steps,
    )


# --- expected_min_steps ------------------------------------------------------


def test_expected_min_steps_floors_at_three_for_short_video():
    assert expected_min_steps(duration_seconds=10.0, segment_count=1) == 3


def test_expected_min_steps_caps_at_eight_for_long_video():
    assert expected_min_steps(duration_seconds=600.0, segment_count=1) == 8


def test_expected_min_steps_scales_with_duration():
    assert expected_min_steps(duration_seconds=125.0, segment_count=1) == 5  # ceil(125/25)


def test_expected_min_steps_scales_with_transcript_density():
    # 40 meaningful segments -> ceil(40/4)=10, clamped up past the duration floor.
    assert expected_min_steps(duration_seconds=10.0, segment_count=40) == 10


# --- terse / step-count collapse detection ----------------------------------


def test_collapsed_single_step_on_complex_recipe_flags():
    # The reported bug: a 5-ingredient sauce collapsed into one terse step.
    segments = [
        TranscriptSegment(text="melt the butter in a pan", start=0.0, end=3.0),
        TranscriptSegment(text="add the garlic and cook until fragrant", start=3.0, end=6.0),
        TranscriptSegment(text="squeeze in the lemon juice and white wine", start=6.0, end=9.0),
        TranscriptSegment(text="simmer for two minutes then remove from heat", start=9.0, end=12.0),
        TranscriptSegment(text="stir in the parsley and salt to finish", start=12.0, end=15.0),
    ]
    recipe = _recipe(
        ingredients=[_ing("butter"), _ing("garlic"), _ing("lemon"), _ing("wine"), _ing("parsley")],
        steps=[_step(0, "Mix all the ingredients together.", "melt the butter in a pan")],
    )
    result = validate_recipe(recipe, segments, duration_seconds=60.0)
    assert result.step_count_ok is False
    assert result.terse_step_indexes == [0]
    assert result.needs_retry is True


def test_simple_recipe_on_short_clip_does_not_flag():
    # A legitimately simple recipe (few ingredients, short clip) should not
    # be penalized for having few, short-ish steps.
    segments = [
        TranscriptSegment(text="toast the bread first", start=0.0, end=3.0),
        TranscriptSegment(text="spread butter on top", start=3.0, end=6.0),
        TranscriptSegment(text="sprinkle some cinnamon sugar and serve", start=6.0, end=9.0),
    ]
    recipe = _recipe(
        ingredients=[_ing("bread"), _ing("butter")],
        steps=[
            _step(0, "Toast the bread.", "toast the bread first"),
            _step(1, "Spread butter on top.", "spread butter on top"),
            _step(2, "Sprinkle cinnamon sugar and serve.", "sprinkle some cinnamon sugar and serve"),
        ],
    )
    result = validate_recipe(recipe, segments, duration_seconds=20.0)
    assert result.step_count_ok is True
    assert result.terse_step_indexes == []
    assert result.needs_retry is False


def test_terseness_ignored_below_ingredient_threshold():
    # Same short instruction, but too few ingredients for terseness to be a
    # meaningful signal of a collapsed multi-action recipe.
    segments = [TranscriptSegment(text="melt the butter in a pan", start=0.0, end=3.0)]
    recipe = _recipe(ingredients=[_ing("butter")], steps=[_step(0, "Melt butter.", "melt the butter in a pan")])
    result = validate_recipe(recipe, segments, duration_seconds=10.0)
    assert result.terse_step_indexes == []


def test_collapse_phrase_flags_even_at_moderate_length():
    segments = [TranscriptSegment(text="combine everything in a bowl and whisk", start=0.0, end=3.0)]
    recipe = _recipe(
        ingredients=[_ing("flour"), _ing("sugar"), _ing("salt"), _ing("egg")],
        steps=[_step(0, "Combine all the ingredients in a large bowl.", "combine everything in a bowl and whisk")],
    )
    result = validate_recipe(recipe, segments, duration_seconds=10.0)
    assert result.terse_step_indexes == [0]


# --- verbosity ceiling --------------------------------------------------------


def test_verbose_step_flagged_but_does_not_force_retry():
    segments = [
        TranscriptSegment(text="melt the butter in a pan", start=0.0, end=3.0),
        TranscriptSegment(text="add the garlic and cook briefly", start=3.0, end=6.0),
        TranscriptSegment(text="serve it hot right away", start=6.0, end=9.0),
    ]
    long_instruction = "Melt the butter " + "slowly and carefully " * 12 + "in a large nonstick pan over low heat."
    recipe = _recipe(
        ingredients=[_ing("butter")],
        steps=[
            _step(0, long_instruction, "melt the butter in a pan"),
            _step(1, "Add the garlic and cook briefly.", "add the garlic and cook briefly"),
            _step(2, "Serve it hot right away.", "serve it hot right away"),
        ],
    )
    result = validate_recipe(recipe, segments, duration_seconds=10.0)
    assert result.verbose_step_indexes == [0]
    assert result.needs_retry is False  # verbosity alone never triggers a retry


# --- transcript coverage -----------------------------------------------------


def test_coverage_is_full_when_citations_span_the_whole_timeline():
    segments = [
        TranscriptSegment(text="first melt the butter", start=0.0, end=5.0),
        TranscriptSegment(text="then add the garlic", start=5.0, end=10.0),
    ]
    recipe = _recipe(
        ingredients=[_ing("butter"), _ing("garlic")],
        steps=[
            _step(0, "Melt butter.", "first melt the butter"),
            _step(1, "Add garlic.", "then add the garlic"),
        ],
    )
    result = validate_recipe(recipe, segments, duration_seconds=10.0)
    assert result.transcript_coverage == 1.0


def test_coverage_drops_when_citations_only_hit_part_of_the_timeline():
    segments = [
        TranscriptSegment(text="first melt the butter", start=0.0, end=5.0),
        TranscriptSegment(text="then add the garlic", start=5.0, end=10.0),
        TranscriptSegment(text="finally serve it hot", start=10.0, end=15.0),
        TranscriptSegment(text="garnish with parsley on top", start=15.0, end=20.0),
    ]
    recipe = _recipe(
        ingredients=[_ing("butter")],
        steps=[_step(0, "Melt butter.", "first melt the butter")],
    )
    result = validate_recipe(recipe, segments, duration_seconds=20.0)
    assert result.transcript_coverage == 5.0 / 20.0


def test_coverage_zero_when_no_citations_match():
    segments = [TranscriptSegment(text="first melt the butter", start=0.0, end=5.0)]
    recipe = _recipe(
        ingredients=[_ing("butter")],
        steps=[_step(0, "Do something.", "completely unrelated spaceship text")],
    )
    result = validate_recipe(recipe, segments, duration_seconds=5.0)
    assert result.transcript_coverage == 0.0


# --- ingredient <-> step cross-check (warning only) --------------------------


def test_unreferenced_ingredient_is_reported_but_never_blocks():
    segments = [
        TranscriptSegment(text="melt the butter in a pan", start=0.0, end=3.0),
        TranscriptSegment(text="add the butter again for flavor", start=3.0, end=6.0),
        TranscriptSegment(text="serve the butter dish hot", start=6.0, end=9.0),
    ]
    recipe = _recipe(
        ingredients=[_ing("butter"), _ing("saffron")],
        steps=[
            _step(0, "Melt the butter in a pan.", "melt the butter in a pan"),
            _step(1, "Add more butter for flavor.", "add the butter again for flavor"),
            _step(2, "Serve the butter dish hot.", "serve the butter dish hot"),
        ],
    )
    result = validate_recipe(recipe, segments, duration_seconds=10.0)
    assert result.unreferenced_ingredients == ["saffron"]
    assert result.needs_retry is False


# --- corrective note ----------------------------------------------------------


def test_corrective_note_mentions_step_count_and_terse_indexes():
    segments = [TranscriptSegment(text="melt the butter in a pan", start=0.0, end=3.0)]
    recipe = _recipe(
        ingredients=[_ing("butter"), _ing("garlic"), _ing("salt"), _ing("pepper")],
        steps=[_step(0, "Mix everything.", "melt the butter in a pan")],
    )
    result = validate_recipe(recipe, segments, duration_seconds=30.0)
    note = build_corrective_note(recipe, result, duration_seconds=30.0)
    assert "1 steps" in note
    assert "[0]" in note
