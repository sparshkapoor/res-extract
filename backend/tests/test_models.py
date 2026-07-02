import json

from app.models import Ingredient, JobStatus, Platform, Recipe, Step


def test_recipe_round_trips_through_json():
    recipe = Recipe(
        title="Test Recipe",
        source_url="https://www.youtube.com/watch?v=abc123",
        platform=Platform.youtube,
        ingredients=[Ingredient(name="salt", quantity="1", unit="tsp")],
        steps=[
            Step(
                index=1,
                instruction="Add salt.",
                verbatim_transcript_citation="add some salt",
                timestamp_seconds=1.5,
                image_path="/media/jobs/abc/step_1.jpg",
            )
        ],
    )
    dumped = recipe.model_dump_json()
    restored = Recipe.model_validate_json(dumped)
    assert restored == recipe


def test_recipe_hero_image_path_defaults_none_and_is_backward_compatible():
    # Older cached recipe_json blobs (persisted before hero_image_path
    # existed) have no such key at all — must still validate cleanly.
    old_json = json.dumps(
        {
            "title": "Old Recipe",
            "source_url": "https://www.youtube.com/watch?v=old123",
            "platform": "youtube",
            "ingredients": [],
            "steps": [],
        }
    )
    restored = Recipe.model_validate_json(old_json)
    assert restored.hero_image_path is None


def test_recipe_json_schema_has_required_fields_for_ollama_format():
    # This schema is passed directly to Ollama's `format=` for constrained
    # decoding — it must be a plain JSON-schema-compatible dict.
    schema = Recipe.model_json_schema()
    assert schema["type"] == "object"
    assert "title" in schema["properties"]
    assert "steps" in schema["properties"]
    assert "ingredients" in schema["properties"]
    # sanity: must be JSON-serializable (Ollama sends this over HTTP)
    json.dumps(schema)


def test_ingredient_optional_fields_default_none():
    ing = Ingredient(name="flour")
    assert ing.quantity is None
    assert ing.unit is None


def test_ingredient_strips_duplicated_unit_from_quantity():
    # Regression test: observed in production on the M1 Air — every LLM
    # pass that fills these fields (pass 1, OCR refinement, VLM estimation)
    # intermittently embeds the unit word in `quantity` too, e.g.
    # quantity="1.8 kg", unit="kg", which rendered as "1.8 kg kg" in the UI.
    ing = Ingredient(name="chicken breast", quantity="1.8 kg", unit="kg")
    assert ing.quantity == "1.8"
    assert ing.unit == "kg"


def test_ingredient_dedup_fires_on_incremental_assignment():
    # vlm.py sets .quantity then .unit as two separate assignments (not a
    # single constructor call) — the dedup must still fire correctly by
    # the time both are set, regardless of assignment order.
    ing = Ingredient(name="pasta")
    ing.quantity = "215 g"
    ing.unit = "g"
    assert ing.quantity == "215"
    assert ing.unit == "g"


def test_ingredient_dedup_is_noop_when_no_duplication():
    ing = Ingredient(name="salt", quantity="1/2", unit="tsp")
    assert ing.quantity == "1/2"
    assert ing.unit == "tsp"


def test_ingredient_dedup_handles_plural_unit_singular_in_quantity():
    # Regression test: observed in production — quantity="1 cup", unit="cups"
    # (plural unit, singular word embedded in quantity) previously survived
    # as "1 cup cups" because the old regex only matched the exact unit
    # string, never a simple singular/plural variant.
    ing = Ingredient(name="yogurt", quantity="1 cup", unit="cups")
    assert ing.quantity == "1"
    assert ing.unit == "cups"


def test_ingredient_dedup_handles_singular_unit_plural_in_quantity():
    ing = Ingredient(name="garlic", quantity="3 cloves", unit="clove")
    assert ing.quantity == "3"
    assert ing.unit == "clove"


def test_ingredient_name_is_generic_defaults_false():
    ing = Ingredient(name="spices")
    assert ing.name_is_generic is False


def test_job_status_values_match_pipeline_stage_names():
    # These string values are persisted in SQLite and sent over SSE, so
    # renaming the enum members would silently break stored/streamed state.
    assert JobStatus.queued.value == "queued"
    assert JobStatus.done.value == "done"
    assert JobStatus.failed.value == "failed"
