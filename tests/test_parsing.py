import pytest

from mealplanner import eval_fraction, parse_ingredient_string


@pytest.mark.parametrize(
    "line, qty, unit, item",
    [
        ("2 cups rice", 2, "cup", "rice"),
        ("1/2 lb chicken breast", 0.5, "lb", "chicken breast"),
        ("1 1/2 lb chicken breast", 1.5, "lb", "chicken breast"),
        ("1½ cup milk", 1.5, "cup", "milk"),
        ("½ cup vegetable broth", 0.5, "cup", "vegetable broth"),
        ("1.5 lb ground beef", 1.5, "lb", "ground beef"),
        ("3 large eggs", 3, "large", "eggs"),
        ("1 tablespoon olive oil", 1, "tbsp", "olive oil"),
        ("2 Tbsp. soy sauce", 2, "tbsp", "soy sauce"),
        ("pinch of salt", 1, "", "pinch of salt"),
        ("salt to taste", 1, "", "salt to taste"),
    ],
)
def test_parse_ingredient_string(line, qty, unit, item):
    parsed = parse_ingredient_string(line)
    assert parsed["qty"] == pytest.approx(qty)
    assert parsed["unit"] == unit
    assert parsed["item"] == item


def test_parenthetical_notes_removed():
    parsed = parse_ingredient_string("1 can (15 oz) black beans")
    assert parsed["item"] == "black beans"
    assert parsed["unit"] == "can"


def test_original_preserved():
    raw = "  1 1/2   lb  chicken  "
    assert parse_ingredient_string(raw)["original"] == raw.strip()


@pytest.mark.parametrize(
    "frac, expected",
    [("1/2", 0.5), ("3/4", 0.75), ("1/0", 0), ("garbage", 0)],
)
def test_eval_fraction(frac, expected):
    assert eval_fraction(frac) == expected
