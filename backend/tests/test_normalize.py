from app.models import Ingredient, Platform, Recipe, Step
from app.pipeline.normalize import normalize_ingredient, normalize_ingredients, normalize_recipe


def _ing(**kwargs) -> Ingredient:
    kwargs.setdefault("name", "test ingredient")
    return Ingredient(**kwargs)


# --- Rule A: unit casing/abbreviation ------------------------------------


def test_canonicalizes_casing_variant():
    # The reported bug: "TSp" vs "tsp".
    ing = normalize_ingredient(_ing(quantity="1", unit="TSp"))
    assert ing.unit == "tsp"


def test_canonicalizes_full_word_unit():
    ing = normalize_ingredient(_ing(quantity="2", unit="Tablespoons"))
    assert ing.unit == "tbsp"


def test_unknown_single_word_unit_is_lowercased_and_kept():
    ing = normalize_ingredient(_ing(quantity="1", unit="Knob"))
    assert ing.unit == "knob"


# --- Rule B: quantity misplaced into unit --------------------------------


def test_splits_quantity_misplaced_in_unit():
    # Observed in the Rye Pitas cached recipe: qty=None unit='2 tbsp'.
    ing = normalize_ingredient(_ing(name="tomato paste", quantity=None, unit="2 tbsp"))
    assert ing.quantity == "2"
    assert ing.unit == "tbsp"


def test_splits_fractional_quantity_misplaced_in_unit():
    ing = normalize_ingredient(_ing(name="greek yogurt", quantity=None, unit="1/2 cup"))
    assert ing.quantity == "1/2"
    assert ing.unit == "cup"


# --- Rule C: free-text unit relocated to note -----------------------------


def test_moves_prepositional_free_text_unit_to_note():
    ing = normalize_ingredient(_ing(name="oil", quantity=None, unit="for heating up the pan"))
    assert ing.unit is None
    assert ing.note == "for heating up the pan"


def test_moves_parenthetical_unit_to_note():
    ing = normalize_ingredient(_ing(name="chili flakes", quantity="1", unit="(optional)"))
    assert ing.unit is None
    assert ing.note == "(optional)"


def test_moves_long_free_text_unit_to_note():
    ing = normalize_ingredient(_ing(name="garlic", quantity="2", unit="to add in with onions"))
    assert ing.unit is None
    assert ing.note == "to add in with onions"


# --- Rule D: cross-unit conflict between quantity and unit ----------------


def test_resolves_cross_unit_conflict_trusting_quantity_pair():
    # Observed: qty='1 tsp' unit='tbsp' rendered as "1 tsp tbsp black pepper".
    ing = normalize_ingredient(_ing(name="black pepper", quantity="1 tsp", unit="tbsp"))
    assert ing.quantity == "1"
    assert ing.unit == "tsp"


def test_cross_unit_conflict_does_not_pollute_note_with_stray_unit():
    # The overwritten "tbsp" is a genuine (if conflicting) unit, not a note
    # — it should be discarded cleanly, not stuffed into `note`.
    ing = normalize_ingredient(_ing(name="black pepper", quantity="1 tsp", unit="tbsp"))
    assert ing.note is None


def test_preserves_prep_note_discarded_by_cross_unit_resolution():
    # Regression: the Rye Pitas cached recipe has quantity="1/3 cup",
    # unit="chopped" — rule D correctly resolves unit to "cup" from the
    # embedded quantity, but was silently discarding "chopped" instead of
    # relocating it to `note`.
    ing = normalize_ingredient(_ing(name="parsley", quantity="1/3 cup", unit="chopped"))
    assert ing.quantity == "1/3"
    assert ing.unit == "cup"
    assert ing.note == "chopped"


def test_preserves_prep_note_with_parenthetical_discarded_by_cross_unit_resolution():
    ing = normalize_ingredient(_ing(name="cilantro", quantity="1/3 cup", unit="chopped (optional)"))
    assert ing.quantity == "1/3"
    assert ing.unit == "cup"
    assert ing.note == "chopped (optional)"


def test_drops_restated_ingredient_name_used_as_unit():
    # Regression: models sometimes echo the ingredient name into `unit`
    # (e.g. unit="onions" for an ingredient named "onions") — that's noise,
    # not a note, and should be dropped rather than preserved.
    ing = normalize_ingredient(_ing(name="onions", quantity="2 lbs", unit="onions"))
    assert ing.quantity == "2"
    assert ing.unit == "lb"
    assert ing.note is None


def test_bare_prep_descriptor_used_as_unit_moves_to_note():
    # Regression: unit="diced"/"chopped" with no quantity conflict to
    # trigger rule D — these are prep notes, not units, even alone.
    ing = normalize_ingredient(_ing(name="onions", quantity=None, unit="diced"))
    assert ing.unit is None
    assert ing.note == "diced"


def test_same_unit_case_left_to_existing_dedupe_validator():
    # quantity="1.8 kg" + unit="kg" is the *same* canonical unit — this is
    # Ingredient's own `_dedupe_unit_from_quantity` validator's job, not
    # rule D's; normalize_ingredient must not fight it.
    ing = normalize_ingredient(_ing(name="chicken breast", quantity="1.8 kg", unit="kg"))
    assert ing.quantity == "1.8"
    assert ing.unit == "kg"


# --- Rule E: parenthetical dual measures ----------------------------------


def test_strips_parenthetical_conversion_into_note():
    ing = normalize_ingredient(_ing(name="almond flour", quantity="300g (10.58 oz)", unit="g"))
    assert ing.quantity == "300"
    assert ing.unit == "g"
    assert ing.note == "(10.58 oz)"


# --- Rule F: unparseable/formula quantities are left untouched -----------


def test_leaves_formula_quantity_untouched():
    ing = normalize_ingredient(_ing(name="granulated sugar", quantity="1.2x weight of egg whites", unit="oz"))
    assert ing.quantity == "1.2x weight of egg whites"
    assert ing.unit == "oz"


def test_folds_unicode_fractions():
    ing = normalize_ingredient(_ing(name="butter", quantity="½", unit="cup"))
    assert ing.quantity == "1/2"


# --- Rule G: name normalization --------------------------------------------


def test_lowercases_title_case_name():
    ing = normalize_ingredient(_ing(name="Egg whites"))
    assert ing.name == "egg whites"


def test_preserves_allowlisted_proper_noun():
    ing = normalize_ingredient(_ing(name="Dijon mustard"))
    assert ing.name == "Dijon mustard"


def test_preserves_acronym():
    ing = normalize_ingredient(_ing(name="BBQ sauce"))
    assert ing.name == "BBQ sauce"


def test_empty_string_quantity_becomes_none():
    ing = normalize_ingredient(_ing(name="egg whites", quantity="", unit="each"))
    assert ing.quantity is None
    assert ing.unit == "each"


# --- Rule H: dedupe --------------------------------------------------------


def test_dedupes_exact_post_normalization_duplicates():
    ingredients = [
        _ing(name="Salt", quantity="1", unit="Tsp"),
        _ing(name="salt", quantity="1", unit="tsp"),
    ]
    result = normalize_ingredients(ingredients)
    assert len(result) == 1


def test_does_not_dedupe_same_name_different_quantity():
    # e.g. garlic used separately in a filling and a sauce — legitimate.
    ingredients = [
        _ing(name="garlic", quantity="7", unit="clove"),
        _ing(name="garlic", quantity="2", unit="clove"),
    ]
    result = normalize_ingredients(ingredients)
    assert len(result) == 2


# --- Idempotence -----------------------------------------------------------


def _make_recipe(ingredients: list[Ingredient]) -> Recipe:
    return Recipe(
        title="Test Recipe",
        source_url="https://www.youtube.com/watch?v=abc123",
        platform=Platform.youtube,
        ingredients=ingredients,
        steps=[
            Step(
                index=1,
                instruction="Do the thing.",
                verbatim_transcript_citation="do the thing",
                timestamp_seconds=1.0,
            )
        ],
    )


def test_normalize_recipe_is_idempotent():
    recipe = _make_recipe(
        [
            _ing(name="Oil", quantity=None, unit="for heating up the pan"),
            _ing(name="tomato paste", quantity=None, unit="2 Tbsp"),
            _ing(name="black pepper", quantity="1 tsp", unit="tbsp"),
            _ing(name="almond flour", quantity="300g (10.58 oz)", unit="g"),
            _ing(name="Granulated sugar", quantity="1.2x weight of egg whites", unit="oz"),
        ]
    )
    once = normalize_recipe(recipe)
    twice = normalize_recipe(once)
    assert once == twice
