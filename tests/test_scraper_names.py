import scraper


def test_redundant_recipe_suffix_stripped():
    r = scraper.parse_schema_recipe({"name": "Crockpot Beef Stew Recipe"})
    assert r["name"] == "Crockpot Beef Stew"


def test_name_that_is_only_recipe_kept():
    r = scraper.parse_schema_recipe({"name": "Recipe"})
    assert r["name"] == "Recipe"
