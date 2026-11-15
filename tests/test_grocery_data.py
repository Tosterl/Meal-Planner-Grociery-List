"""The grocery list as plain data (planner.grocery_sections), used by /api/grocery-list."""
import json

import planner


def _recipe(folder, name, ingredients):
    (folder / f"{planner.slugify(name)}.json").write_text(
        json.dumps({"name": name, "ingredients": ingredients}), encoding="utf-8")


def _plan(*meals):
    return {"created": "2026-11-08T16:55:52", "days": [{"day": "Monday", "meals": dict(meals)}]}


def test_ingredients_are_added_up_across_meals_and_grouped_by_section(tmp_path, monkeypatch):
    monkeypatch.setattr(planner, "load_recipe",
                        lambda name: json.loads((tmp_path / f"{planner.slugify(name)}.json").read_text(encoding="utf-8"))
                        if (tmp_path / f"{planner.slugify(name)}.json").exists() else None)
    _recipe(tmp_path, "Chicken Stir Fry", [
        {"item": "Chicken Breast", "qty": 1.5, "unit": "lb"},
        {"item": "Soy Sauce", "qty": 2, "unit": "tbsp"},
    ])
    _recipe(tmp_path, "Chicken Tacos", [
        {"item": "chicken breast", "qty": 1, "unit": "lb"},
        {"item": "Small Flour Tortillas", "qty": 8, "unit": ""},
    ])
    plan = _plan(("lunch", {"name": "Chicken Stir Fry", "servings": 4}),
                 ("dinner", {"name": "Chicken Tacos", "servings": 4}),
                 # A leftover names no recipe of its own, so it must not double the shopping.
                 ("breakfast", {"name": "Chicken Stir Fry (leftover)", "servings": 1, "is_leftover": True}))

    sections = planner.grocery_sections(plan)

    everything = {item["name"]: item["amount"] for section in sections for item in section["items"]}
    assert everything["Chicken Breast"] == "2½ lb", "the same item from two recipes is one line, added up"
    assert everything["Small Flour Tortillas"] == "8"
    assert set(everything) == {"Chicken Breast", "Soy Sauce", "Small Flour Tortillas"}
    names = [section["section"] for section in sections]
    assert names == sorted(names), "sections come in a stable order"
    assert all(name[0].isalnum() for name in names), "section names are plain text, with no emoji in front"
    for section in sections:
        assert [i["name"] for i in section["items"]] == sorted(i["name"] for i in section["items"])


def test_scaling_and_an_empty_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(planner, "load_recipe", lambda name: {"name": name, "ingredients": [{"item": "rice", "qty": 1, "unit": "cup"}]})
    doubled = planner.grocery_sections(_plan(("dinner", "Rice Bowl")), scale=2)
    assert doubled[0]["items"] == [{"name": "Rice", "amount": "2 cup"}]
    assert planner.grocery_sections({"days": []}) == []


def test_printing_and_the_markdown_file_still_use_the_same_amounts(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(planner, "load_recipe", lambda name: {"name": name, "ingredients": [
        {"item": "butter", "qty": 2, "unit": "tbsp"}, {"item": "butter", "qty": 0.25, "unit": "cup"}]})
    monkeypatch.setattr(planner, "PLANS_DIR", tmp_path)
    grocery = planner.generate_grocery_list(_plan(("dinner", "Toast")))
    printed = capsys.readouterr().out
    exported = (tmp_path / "grocery_list.md").read_text(encoding="utf-8")
    amount = planner.grocery_amount(grocery["butter"])
    assert amount in printed and f"- [ ] Butter — {amount}" in exported
    assert " + " in amount, "different units of the same item are kept apart, joined with a plus"
