import json
from pathlib import Path

from app.pipeline.comments import Comment, _unit_token_density, shortlist_recipe_like_comments

# Real comment thread scraped from the sparse-short-1 golden case's video
# (https://www.youtube.com/shorts/050xIwsfpuo, a "Simple Sauces" gochujang-mayo
# recipe) — the actual case that motivated WS4d: this video has no written
# description and near-zero actionable narration, but multiple viewers posted
# a specific recreation in the comments ("½ cup mayonnaise / 1–2 tbsp
# gochujang / 1 clove garlic, grated / 1 tsp soy sauce / 1 tsp rice vinegar /
# Salt & pepper, to taste") alongside ~70 comments of banter, reaction, and
# off-topic questions. A genuine regression fixture, not synthetic data.
_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sparse_short_1_comments.json"

_RECIPE_TEXT = (
    "½ cup mayonnaise\n1–2 tbsp gochujang\n1 clove garlic, grated\n1 tsp soy sauce\n"
    "1 tsp rice vinegar\nSalt & pepper, to taste"
)

# Matches evals/golden/sparse-short-1.json's expected.ingredients.
_INGREDIENT_NAMES = ["mayonnaise", "gochujang", "soy sauce", "rice vinegar", "garlic", "salt", "pepper"]


def _load_real_comments() -> list[Comment]:
    raw = json.loads(_FIXTURE_PATH.read_text())
    return [Comment(id=c["id"], text=c["text"], author="", like_count=c["like_count"]) for c in raw]


# --- _unit_token_density ---------------------------------------------------


def test_unit_token_density_scores_recipe_comment_highly():
    assert _unit_token_density(_RECIPE_TEXT) >= 4  # cup, tbsp, clove, tsp, tsp


def test_unit_token_density_zero_for_banter():
    assert _unit_token_density("Bro my sose have got a seme test of md sose") == 0
    assert _unit_token_density("who heared gojo gang sauce 😂😂") == 0


def test_unit_token_density_counts_each_occurrence():
    assert _unit_token_density("1 tsp salt, 1 tsp pepper, 2 tsp sugar") == 3


# --- shortlist_recipe_like_comments (real fixture data) --------------------


def test_shortlist_picks_the_real_recreation_over_banter():
    comments = _load_real_comments()
    shortlisted = shortlist_recipe_like_comments(comments, _INGREDIENT_NAMES, top_n=2)
    assert shortlisted
    assert any(c.text.strip() == _RECIPE_TEXT for c in shortlisted)


def test_shortlist_excludes_pure_banter():
    comments = _load_real_comments()
    banter_texts = {
        "Bro my sose have got a seme test of md sose",
        "who heared gojo gang sauce 😂😂",
        "ranch and buffalo sauce",
        "Mayochupppppp",
    }
    shortlisted = shortlist_recipe_like_comments(comments, _INGREDIENT_NAMES, top_n=2)
    assert not any(c.text in banter_texts for c in shortlisted)


def test_shortlist_respects_top_n():
    comments = _load_real_comments()
    assert len(shortlist_recipe_like_comments(comments, _INGREDIENT_NAMES, top_n=1)) <= 1
    assert len(shortlist_recipe_like_comments(comments, _INGREDIENT_NAMES, top_n=5)) <= 5


def test_shortlist_empty_when_no_comments_mention_ingredients_or_units():
    comments = [
        Comment(id="1", text="great video!", author="", like_count=0),
        Comment(id="2", text="first!", author="", like_count=0),
    ]
    assert shortlist_recipe_like_comments(comments, _INGREDIENT_NAMES, top_n=2) == []


def test_shortlist_prefers_higher_scoring_comment():
    # Both mention units, but only one also names several real ingredients.
    low = Comment(id="1", text="maybe 1 tsp of something", author="", like_count=0)
    high = Comment(
        id="2", text="1 tsp soy sauce, 1 tsp rice vinegar, salt and pepper to taste", author="", like_count=0
    )
    result = shortlist_recipe_like_comments([low, high], _INGREDIENT_NAMES, top_n=1)
    assert result == [high]
