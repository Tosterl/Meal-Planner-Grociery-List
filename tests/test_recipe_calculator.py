import pytest

import recipe_calculator as rc


@pytest.mark.parametrize(
    "text, qty, unit",
    [
        ("1.5 lb", 1.5, "lb"),
        ("12 oz", 12, "oz"),
        ("1 1/2 cup", 1.5, "cup"),
        ("½ cup", 0.5, "cup"),
        ("8", 8, ""),
    ],
)
def test_parse_amount(text, qty, unit):
    got_qty, got_unit = rc.parse_amount(text)
    assert got_qty == pytest.approx(qty)
    assert got_unit == unit


@pytest.mark.parametrize(
    "needed, package, ingredient, expected",
    [
        # Straight weight conversion
        ("1.5 lb", "1 lb", None, 2),
        ("1.5 lb", "3 lb", None, 1),
        ("24 oz", "1 lb", None, 2),
        # Volume
        ("3 cups", "32 fl oz", None, 1),
        # Count-based needs default to 1 package
        ("8", "12 ct", None, 1),
        # Ingredient bridges: slices of bacon -> oz
        ("8 slices", "12 oz", "bacon", 1),
        # Garlic cloves -> oz
        ("3 cloves", "3 oz", "garlic", 1),
    ],
)
def test_packages_needed(needed, package, ingredient, expected):
    assert rc.packages_needed(needed, package, ingredient) == expected


def test_builtin_suite_passes():
    """The module ships its own 23-case table; keep it green."""
    assert rc.run_tests() == 0
