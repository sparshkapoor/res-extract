from app.models import Step
from app.pipeline.spellcheck import clean_text


def test_clean_text_leaves_culinary_terms_untouched():
    text = "Combine ground beef with tahini and gochujang."
    assert clean_text(text) == text


def test_clean_text_fixes_unambiguous_typo():
    assert clean_text("Whisk the eggz until frothy.") == "Whisk the eggs until frothy."
    assert clean_text("Set the oven temprature to 350.") == "Set the oven temperature to 350."


def test_clean_text_leaves_ambiguous_typo_untouched():
    # "heet" is edit-distance-1 from many common words (heat, meet, feet, ...)
    # — too ambiguous to guess confidently, so it must be left as-is rather
    # than risk a confidently wrong correction.
    text = "Cook on medium heet for five minutes."
    assert clean_text(text) == text


def test_clean_text_preserves_short_words():
    # Below the minimum length gate — short words are disproportionately
    # false-positive-prone and are left alone regardless of dictionary match.
    text = "Mix ans stir."
    assert clean_text(text) == text


def test_clean_step_text_mutates_instruction_only():
    steps = [
        Step(
            index=1,
            instruction="Whisk the eggz until frothy.",
            verbatim_transcript_citation="whisk the eggs",
            timestamp_seconds=1.0,
        )
    ]
    from app.pipeline.spellcheck import clean_step_text

    cleaned = clean_step_text(steps)
    assert cleaned[0].instruction == "Whisk the eggs until frothy."
    assert cleaned[0].verbatim_transcript_citation == "whisk the eggs"
