import json

from mealplanner import storage


def make_recipe(name, tags=None):
    return {"name": name, "servings": 4, "tags": tags or [], "ingredients": []}


def test_save_load_roundtrip(tmp_path):
    recipe = make_recipe("Test Chicken & Rice")
    path = storage.save_recipe(recipe, recipes_dir=tmp_path)
    assert path.name == "test-chicken-rice.json"
    assert storage.load_recipe("Test Chicken & Rice", recipes_dir=tmp_path) == recipe


def test_list_recipes_filters_by_tag(tmp_path):
    storage.save_recipe(make_recipe("A", tags=["Dinner"]), recipes_dir=tmp_path)
    storage.save_recipe(make_recipe("B", tags=["breakfast"]), recipes_dir=tmp_path)
    assert len(storage.list_recipes(recipes_dir=tmp_path)) == 2
    dinner = storage.list_recipes(tag_filter="dinner", recipes_dir=tmp_path)
    assert [r["name"] for r in dinner] == ["A"]


def test_list_recipes_skips_corrupt_files(tmp_path):
    storage.save_recipe(make_recipe("Good"), recipes_dir=tmp_path)
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert [r["name"] for r in storage.list_recipes(recipes_dir=tmp_path)] == ["Good"]


def test_delete_recipe(tmp_path):
    storage.save_recipe(make_recipe("Gone"), recipes_dir=tmp_path)
    assert storage.delete_recipe("Gone", recipes_dir=tmp_path) is True
    assert storage.delete_recipe("Gone", recipes_dir=tmp_path) is False


def test_load_latest_plan_picks_newest(tmp_path):
    (tmp_path / "plan_2026-01-01_000000.json").write_text(
        json.dumps({"id": "old"}), encoding="utf-8")
    (tmp_path / "plan_2026-06-01_000000.json").write_text(
        json.dumps({"id": "new"}), encoding="utf-8")
    assert storage.load_latest_plan(plans_dir=tmp_path)["id"] == "new"


def test_record_usage_dedupes_and_prunes(tmp_path):
    hist_file = tmp_path / "history.json"
    storage.record_usage(["Tacos"], date="2020-01-01", history_file=hist_file)
    storage.record_usage(["Tacos"], history_file=hist_file)  # today
    storage.record_usage(["Tacos"], history_file=hist_file)  # duplicate today
    history = storage.load_usage_history(hist_file)
    # The 2020 entry is older than 90 days and pruned; today kept once
    assert len(history["tacos"]) == 1
