import pytest

from mealplanner import KNOWN_UNITS, normalize_unit


@pytest.mark.parametrize(
    "raw, canonical",
    [
        ("tablespoon", "tbsp"),
        ("Tablespoons", "tbsp"),
        ("tbs", "tbsp"),
        ("tbsp.", "tbsp"),
        ("teaspoons", "tsp"),
        ("cups", "cup"),
        ("ounce", "oz"),
        ("Pounds", "lb"),
        ("lbs", "lb"),
        ("cloves", "clove"),
        ("quart", "qt"),
        ("grams", "g"),
        ("", ""),
        ("bottle", "bottle"),
        ("mystery-unit", "mystery-unit"),
    ],
)
def test_normalize_unit(raw, canonical):
    assert normalize_unit(raw) == canonical


def test_canonical_forms_are_known():
    # Every alias target must itself be recognizable as a unit
    for target in ("tbsp", "tsp", "cup", "oz", "lb", "qt", "pt", "gal"):
        assert target in KNOWN_UNITS
