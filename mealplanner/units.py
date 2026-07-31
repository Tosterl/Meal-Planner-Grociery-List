"""Canonical ingredient-unit vocabulary.

Merged from the three previously divergent tables in planner.py,
scraper.py, and audit_cart.py — so "tablespoon" and "tbsp" now aggregate
to the same grocery line everywhere.
"""

# alias (as typed / scraped) -> canonical short form
UNIT_ALIASES = {
    "tablespoons": "tbsp", "tablespoon": "tbsp", "tbs": "tbsp",
    "teaspoons": "tsp", "teaspoon": "tsp",
    "cups": "cup",
    "ounces": "oz", "ounce": "oz",
    "pounds": "lb", "pound": "lb", "lbs": "lb",
    "cloves": "clove",
    "cans": "can",
    "slices": "slice",
    "pieces": "piece",
    "pinches": "pinch",
    "dashes": "dash",
    "bunches": "bunch",
    "heads": "head",
    "stalks": "stalk",
    "sprigs": "sprig",
    "quarts": "qt", "quart": "qt",
    "pints": "pt", "pint": "pt",
    "gallons": "gal", "gallon": "gal",
    "liters": "l", "liter": "l",
    "milliliters": "ml",
    "grams": "g", "gram": "g",
    "kilograms": "kg", "kilogram": "kg",
    "packages": "pkg", "package": "pkg",
    "containers": "container",
    "jars": "jar",
    "bottles": "bottle",
    "bags": "bag",
    "boxes": "box",
}

# Everything recognizable as a unit token (aliases + canonical forms +
# unit-like words with no shorter form)
KNOWN_UNITS = (
    set(UNIT_ALIASES)
    | set(UNIT_ALIASES.values())
    | {
        "cup", "tbsp", "tsp", "oz", "lb",
        "clove", "can", "slice", "piece",
        "pinch", "dash", "bunch", "head", "stalk", "sprig",
        "large", "medium", "small", "whole",
    }
)


def normalize_unit(unit: str) -> str:
    """Lowercase, strip trailing dots, and map aliases to canonical form."""
    unit = (unit or "").lower().strip().rstrip(".")
    return UNIT_ALIASES.get(unit, unit)
