import pytest

from app.models import Ingredient
from app.pipeline import extract_recipe


def _ing(name: str, quantity: str | None = None, unit: str | None = None, is_estimated: bool = True) -> Ingredient:
    return Ingredient(name=name, quantity=quantity, unit=unit, is_estimated=is_estimated)


@pytest.mark.asyncio
async def test_refine_ingredients_with_comment_forces_is_estimated_true_when_changed(monkeypatch):
    # Regression: verified live on the sparse-short-1 golden case's video —
    # qwen2.5:7b filled real values from a genuine viewer comment but flipped
    # is_estimated=False on 3 of 4 changed ingredients despite
    # _SYSTEM_COMMENT_REFINE explicitly instructing it to keep is_estimated=true.
    # A comment is an unverified external claim, never something the video
    # itself stated, so this must never be trusted to the model alone.
    originals = [_ing("mayonnaise", is_estimated=True), _ing("salt", is_estimated=True)]

    async def fake_chat_with_retry(prompt, schema, system, is_valid, corrective_note):
        parsed = schema(
            ingredients=[
                # Model filled a real value but (non-compliantly) marked it False.
                _ing("mayonnaise", quantity="0.5", unit="cup", is_estimated=False),
                # Untouched ingredient — no change, so is_estimated must stay as-is.
                _ing("salt", is_estimated=True),
            ]
        )
        return parsed, is_valid(parsed)

    monkeypatch.setattr(extract_recipe, "_chat_with_retry", fake_chat_with_retry)

    result = await extract_recipe.refine_ingredients_with_comment(originals, "½ cup mayonnaise")

    assert result[0].name == "mayonnaise"
    assert result[0].quantity == "0.5"
    assert result[0].is_estimated is True  # forced true despite the model saying False
    assert result[1].name == "salt"
    assert result[1].is_estimated is True


@pytest.mark.asyncio
async def test_refine_ingredients_with_comment_forces_true_when_only_note_changed(monkeypatch):
    # Regression: an ingredient an earlier, unrelated pipeline stage already
    # mis-marked is_estimated=False with a guess (e.g. quantity/unit already
    # happened to match the comment's value) — the model correctly attaches
    # the provenance note without touching quantity/unit, but is_estimated
    # must still flip to True since the value's real source is this comment.
    originals = [_ing("mayonnaise", quantity="0.5", unit="cup", is_estimated=False)]

    async def fake_chat_with_retry(prompt, schema, system, is_valid, corrective_note):
        parsed = schema(
            ingredients=[
                Ingredient(
                    name="mayonnaise", quantity="0.5", unit="cup", is_estimated=False,
                    note="from a viewer's comment",
                ),
            ]
        )
        return parsed, is_valid(parsed)

    monkeypatch.setattr(extract_recipe, "_chat_with_retry", fake_chat_with_retry)

    result = await extract_recipe.refine_ingredients_with_comment(originals, "½ cup mayonnaise")

    assert result[0].is_estimated is True


@pytest.mark.asyncio
async def test_refine_ingredients_with_comment_keeps_originals_on_count_mismatch(monkeypatch):
    originals = [_ing("mayonnaise"), _ing("salt")]

    async def fake_chat_with_retry(prompt, schema, system, is_valid, corrective_note):
        parsed = schema(ingredients=[_ing("mayonnaise", quantity="1", unit="cup", is_estimated=False)])
        return parsed, is_valid(parsed)

    monkeypatch.setattr(extract_recipe, "_chat_with_retry", fake_chat_with_retry)

    result = await extract_recipe.refine_ingredients_with_comment(originals, "some comment")

    assert result == originals
