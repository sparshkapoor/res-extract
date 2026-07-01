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


def test_job_status_values_match_pipeline_stage_names():
    # These string values are persisted in SQLite and sent over SSE, so
    # renaming the enum members would silently break stored/streamed state.
    assert JobStatus.queued.value == "queued"
    assert JobStatus.done.value == "done"
    assert JobStatus.failed.value == "failed"
