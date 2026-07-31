import pytest

import scraper


@pytest.mark.parametrize(
    "iso, minutes",
    [
        ("PT1H30M", 90),
        ("P0DT1H30M", 90),  # WordPress-style date part
        ("PT45M", 45),
        ("PT2H", 120),
        ("P1DT2H", 1560),
        ("45", 45),
        (None, None),
        ("", None),
    ],
)
def test_parse_duration(iso, minutes):
    assert scraper.parse_duration(iso) == minutes


def test_parse_schema_recipe_unescapes_entities():
    recipe = scraper.parse_schema_recipe({
        "name": "Quick &amp; Easy Garlic Noodles",
        "description": "A &quot;fast&quot; dish",
        "recipeIngredient": ["1 1/2 cups flour"],
        "recipeInstructions": "Mix &amp; serve.",
    })
    assert recipe["name"] == "Quick & Easy Garlic Noodles"
    assert recipe["notes"] == 'A "fast" dish'
    assert recipe["steps"] == ["Mix & serve."]
    ing = recipe["ingredients"][0]
    assert (ing["qty"], ing["unit"], ing["item"]) == (1.5, "cup", "flour")


def test_parse_schema_recipe_servings_and_times():
    recipe = scraper.parse_schema_recipe({
        "name": "T",
        "recipeYield": ["6 servings"],
        "prepTime": "PT10M",
        "cookTime": "PT20M",
    })
    assert recipe["servings"] == 6
    assert recipe["prep_time"] == 10
    assert recipe["cook_time"] == 20
