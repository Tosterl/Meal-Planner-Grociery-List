import pytest

from mealplanner import CATEGORY_EMOJI, GROCERY_CATEGORIES, categorize


@pytest.mark.parametrize(
    "item, category",
    [
        ("boneless chicken thighs", "Meat & Protein"),
        ("yellow onion", "Produce"),
        ("shredded cheddar cheese", "Dairy"),
        ("flour tortillas", "Bread & Bakery"),
        ("jasmine rice", "Pantry"),
        ("ground cumin", "Spices & Seasonings"),
        ("mystery ingredient", "Other"),
    ],
)
def test_categorize(item, category):
    assert categorize(item) == category


def test_longest_keyword_wins():
    # "tomato paste" must not fall into Produce via the "tomato" keyword
    assert categorize("tomato paste") == "Pantry"
    assert categorize("tomato sauce") == "Pantry"
    assert categorize("roma tomato") == "Produce"
    # "garlic powder" is a spice, plain "garlic" is produce
    assert categorize("garlic powder") == "Spices & Seasonings"
    assert categorize("garlic") == "Produce"


def test_every_category_has_an_emoji():
    for cat in list(GROCERY_CATEGORIES) + ["Other"]:
        assert cat in CATEGORY_EMOJI
