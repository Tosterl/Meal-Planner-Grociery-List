#!/usr/bin/env python3
"""
Recipe → Package quantity calculator.

Given a recipe amount (e.g., "1.5 lb chicken breast"), a Kroger package size
(e.g., "1 lb"), and optionally the ingredient name, returns how many packages
to buy.

Why this is non-trivial:
  - Same family is easy:   "1.5 lb" / "1 lb" = 2 packages
  - Cross-family needs help: "8 slice bacon" + "12 oz" = ?
    Without an ingredient hint, we can't compare slices to ounces. With
    a hint of "bacon", we know 1 slice ≈ 1 oz, so 8 slice ≈ 8 oz, fits 1 pkg.

Usage:
    >>> from recipe_calculator import packages_needed
    >>> packages_needed("1.5 lb", "1 lb")
    2
    >>> packages_needed("8 slice", "12 oz", ingredient="bacon")
    1

CLI:
    python recipe_calculator.py "1.5 lb chicken breast" --package "1 lb"
    python recipe_calculator.py --test
"""

from __future__ import annotations

import argparse
import math
import re
import sys


# ────────────────────────────────────────────────────────────────────────────
# Unit families — convert any amount to a single base unit per family
# ────────────────────────────────────────────────────────────────────────────

# Weight: base unit = ounce
WEIGHT_TO_OZ = {
    "oz": 1.0, "ounce": 1.0, "ounces": 1.0,
    "lb": 16.0, "lbs": 16.0, "pound": 16.0, "pounds": 16.0,
    "g": 0.0353, "gram": 0.0353, "grams": 0.0353,
    "kg": 35.274, "kilo": 35.274, "kilogram": 35.274, "kilograms": 35.274,
}

# Volume: base unit = fluid ounce
VOLUME_TO_FLOZ = {
    "tsp": 0.1667, "teaspoon": 0.1667, "teaspoons": 0.1667,
    "tbsp": 0.5, "tablespoon": 0.5, "tablespoons": 0.5,
    "fl oz": 1.0, "floz": 1.0, "fl. oz.": 1.0, "fl. oz": 1.0,
    "fluid ounce": 1.0, "fluid ounces": 1.0,
    "cup": 8.0, "cups": 8.0, "c": 8.0,
    "pint": 16.0, "pints": 16.0, "pt": 16.0,
    "quart": 32.0, "quarts": 32.0, "qt": 32.0,
    "gallon": 128.0, "gallons": 128.0, "gal": 128.0,
    "ml": 0.03381, "l": 33.814, "liter": 33.814, "liters": 33.814,
}

# Count: base unit = single item
COUNT_UNITS = {
    "": 1.0, "ct": 1.0, "count": 1.0, "each": 1.0, "ea": 1.0,
    "pkg": 1.0, "package": 1.0, "packages": 1.0, "pk": 1.0, "pack": 1.0,
    "dozen": 12.0,
    "slice": 1.0, "slices": 1.0,
    "piece": 1.0, "pieces": 1.0,
    "clove": 1.0, "cloves": 1.0,
    "stalk": 1.0, "stalks": 1.0,
    "head": 1.0, "heads": 1.0,
    "bunch": 1.0, "bunches": 1.0,
    "sprig": 1.0, "sprigs": 1.0,
    "leaf": 1.0, "leaves": 1.0,
}


# ────────────────────────────────────────────────────────────────────────────
# Ingredient bridges — convert from "count" or "volume" to weight/volume for
# specific ingredients. Each entry maps an ingredient keyword to a converter:
#   { from_unit: (to_unit, multiplier) }
# Used when the recipe and package are in different families.
# ────────────────────────────────────────────────────────────────────────────

INGREDIENT_BRIDGES = {
    # Bacon: 1 slice ≈ 1 oz (raw American bacon)
    "bacon": {"slice": ("oz", 1.0), "slices": ("oz", 1.0)},

    # Eggs: 1 large egg ≈ 1.76 oz (mostly used as count anyway)
    "egg":  {"each": ("ct", 1.0)},
    "eggs": {"each": ("ct", 1.0)},

    # Garlic: 1 clove ≈ 0.18 oz, 1 head ≈ 1.4 oz
    "garlic": {"clove": ("oz", 0.18), "cloves": ("oz", 0.18),
               "head": ("oz", 1.4),  "heads": ("oz", 1.4)},

    # Citrus: medium lemon ≈ 4 oz, lime ≈ 2 oz
    "lemon":  {"each": ("oz", 4.0)},
    "lemons": {"each": ("oz", 4.0)},
    "lime":   {"each": ("oz", 2.0)},
    "limes":  {"each": ("oz", 2.0)},

    # Produce — count to weight (medium-sized assumptions)
    "onion":      {"each": ("oz", 6.0)},
    "onions":     {"each": ("oz", 6.0)},
    "tomato":     {"each": ("oz", 5.0)},
    "tomatoes":   {"each": ("oz", 5.0)},
    "avocado":    {"each": ("oz", 6.0)},
    "avocados":   {"each": ("oz", 6.0)},
    "potato":     {"each": ("oz", 6.0)},
    "potatoes":   {"each": ("oz", 6.0)},
    "bell pepper":  {"each": ("oz", 5.0)},
    "bell peppers": {"each": ("oz", 5.0)},
    "carrot":     {"each": ("oz", 2.0)},
    "carrots":    {"each": ("oz", 2.0)},
    "celery":     {"stalk": ("oz", 1.7), "stalks": ("oz", 1.7)},
    "lettuce":    {"head": ("oz", 16.0), "heads": ("oz", 16.0)},

    # Dry goods — cup to oz
    "flour":              {"cup": ("oz", 4.4), "cups": ("oz", 4.4)},
    "all-purpose flour":  {"cup": ("oz", 4.4), "cups": ("oz", 4.4)},
    "sugar":              {"cup": ("oz", 7.05), "cups": ("oz", 7.05)},
    "brown sugar":        {"cup": ("oz", 7.5), "cups": ("oz", 7.5)},
    "rice":               {"cup": ("oz", 6.5), "cups": ("oz", 6.5)},
    "jasmine rice":       {"cup": ("oz", 6.5), "cups": ("oz", 6.5)},
    "rolled oats":        {"cup": ("oz", 3.0), "cups": ("oz", 3.0)},
    "oats":               {"cup": ("oz", 3.0), "cups": ("oz", 3.0)},
    "chia seeds":         {"tbsp": ("oz", 0.42), "tbsp": ("oz", 0.42),
                           "cup": ("oz", 5.6),  "cups": ("oz", 5.6)},
    "broccoli florets":   {"cup": ("oz", 3.0),  "cups": ("oz", 3.0)},
    "broccoli":           {"cup": ("oz", 3.0),  "cups": ("oz", 3.0)},
    "spinach":            {"cup": ("oz", 1.0),  "cups": ("oz", 1.0)},
    "blueberries":        {"cup": ("oz", 5.0),  "cups": ("oz", 5.0)},
    "shredded cheese":    {"cup": ("oz", 4.0),  "cups": ("oz", 4.0)},
    "shredded cheddar cheese":  {"cup": ("oz", 4.0), "cups": ("oz", 4.0)},
    "shredded mozzarella":      {"cup": ("oz", 3.0), "cups": ("oz", 3.0)},
    "parmesan cheese":    {"cup": ("oz", 3.5), "cups": ("oz", 3.5)},

    # Meats: cup of cooked/diced ≈ 5-6 oz
    "ground beef":        {"cup": ("oz", 8.0), "cups": ("oz", 8.0)},
    "chicken":            {"cup": ("oz", 5.0), "cups": ("oz", 5.0)},
    "chicken breast":     {"cup": ("oz", 5.0), "cups": ("oz", 5.0)},

    # Tortillas: count to count (count units already match Kroger ct)
    "tortilla":  {"each": ("ct", 1.0)},
    "tortillas": {"each": ("ct", 1.0)},
}


# ────────────────────────────────────────────────────────────────────────────
# Parsing
# ────────────────────────────────────────────────────────────────────────────

UNICODE_FRACTIONS = {
    "½": 0.5, "⅓": 1/3, "⅔": 2/3, "¼": 0.25, "¾": 0.75,
    "⅕": 0.2, "⅖": 0.4, "⅗": 0.6, "⅘": 0.8,
    "⅙": 1/6, "⅚": 5/6, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}


def parse_amount(s: str) -> tuple[float | None, str | None]:
    """
    Parse an amount string into (quantity, unit).

    Examples:
        "1.5 lb"       -> (1.5, "lb")
        "1/2 cup"      -> (0.5, "cup")
        "1 1/2 cup"    -> (1.5, "cup")
        "8 slice"      -> (8.0, "slice")
        "1 (16 oz)"    -> (1.0, "")  — parentheticals are stripped
        "12 fl oz"     -> (12.0, "fl oz")
        "½ cup"        -> (0.5, "cup")
        "32 oz"        -> (32.0, "oz")
    """
    if not s:
        return None, None

    text = str(s).strip().lower()

    # Replace unicode fractions with decimal equivalents
    for char, val in UNICODE_FRACTIONS.items():
        text = text.replace(char, f" {val} ")

    # Strip parenthetical hints like "1 (13.5 oz) can"
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return None, None

    # Try patterns from most specific to least:
    # "1 1/2 cup" — mixed number
    m = re.match(r"^(\d+)\s+(\d+)\s*/\s*(\d+)\s*(.*)$", text)
    if m:
        whole, num, den, unit = m.groups()
        try:
            qty = float(whole) + float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None, None
        return qty, _normalize_unit(unit)

    # "1/2 cup" — pure fraction
    m = re.match(r"^(\d+)\s*/\s*(\d+)\s*(.*)$", text)
    if m:
        num, den, unit = m.groups()
        try:
            qty = float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None, None
        return qty, _normalize_unit(unit)

    # "1.5 lb" or "12 oz" or "1 each"
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(.*)$", text)
    if m:
        num, unit = m.groups()
        try:
            qty = float(num)
        except ValueError:
            return None, None
        return qty, _normalize_unit(unit)

    return None, None


def _normalize_unit(s: str) -> str:
    """Lowercase, trim, collapse spaces. Leaves multi-word units like 'fl oz' intact."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def to_base(qty: float, unit: str) -> tuple[float | None, str | None]:
    """Convert (qty, unit) to (base_value, family). Family is 'weight'|'volume'|'count'."""
    u = _normalize_unit(unit)
    if u in WEIGHT_TO_OZ:
        return qty * WEIGHT_TO_OZ[u], "weight"
    if u in VOLUME_TO_FLOZ:
        return qty * VOLUME_TO_FLOZ[u], "volume"
    if u in COUNT_UNITS:
        return qty * COUNT_UNITS[u], "count"
    return None, None


def apply_ingredient_bridge(
    qty: float, unit: str, ingredient: str | None
) -> tuple[float, str] | None:
    """
    Try to convert (qty, unit) to a different unit family using
    ingredient-specific knowledge. Returns (new_qty, new_unit) or None.
    """
    if not ingredient:
        return None
    name = ingredient.lower().strip()
    u = _normalize_unit(unit)

    # Try exact ingredient match first, then progressively shorter variants
    # ("shredded cheddar cheese" -> "cheddar cheese" -> "cheese")
    candidates = [name]
    parts = name.split()
    for i in range(1, len(parts)):
        candidates.append(" ".join(parts[i:]))

    for cand in candidates:
        bridge = INGREDIENT_BRIDGES.get(cand)
        if bridge and u in bridge:
            new_unit, multiplier = bridge[u]
            return qty * multiplier, new_unit
    return None


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────

def packages_needed(
    needed: str,
    package_size: str,
    ingredient: str | None = None,
    fallback: int = 1,
) -> int:
    """
    Compute how many packages of `package_size` are required to satisfy `needed`.

    Args:
        needed:       Recipe-needed amount string ("1.5 lb", "8 slice", "3 cup")
        package_size: Kroger package size string ("1 lb", "12 oz", "1 gal")
        ingredient:   Optional ingredient name (e.g., "bacon", "garlic") used
                      to bridge cross-family conversions
        fallback:     Returned when units can't be reconciled (default: 1)

    Returns:
        Number of packages (always >= 1).
    """
    if not needed or not package_size:
        return fallback

    p_qty, p_unit = parse_amount(package_size)
    if p_qty is None or p_qty <= 0:
        return fallback
    p_base, p_family = to_base(p_qty, p_unit)
    if p_base is None or p_base <= 0:
        return fallback

    # Multi-unit needed strings ("1 lb + 0.5 cup") — try each part, take max
    parts = [p.strip() for p in str(needed).split("+")]
    best = 0
    matched_any = False

    for part in parts:
        n_qty, n_unit = parse_amount(part)
        if n_qty is None or n_qty <= 0:
            continue
        n_base, n_family = to_base(n_qty, n_unit)
        if n_base is None:
            continue

        # Same family — direct comparison
        if n_family == p_family:
            matched_any = True
            best = max(best, math.ceil(n_base / p_base))
            continue

        # Different families — try ingredient bridge
        bridged = apply_ingredient_bridge(n_qty, n_unit, ingredient)
        if bridged:
            b_qty, b_unit = bridged
            b_base, b_family = to_base(b_qty, b_unit)
            if b_base is not None and b_family == p_family:
                matched_any = True
                best = max(best, math.ceil(b_base / p_base))

    if not matched_any:
        return fallback
    return max(1, int(best))


def explain(needed: str, package_size: str, ingredient: str | None = None) -> str:
    """Human-readable trace of the calculation, useful for debugging."""
    n_qty, n_unit = parse_amount(needed)
    p_qty, p_unit = parse_amount(package_size)

    lines = [
        f"Need:    {needed!r}  -> qty={n_qty}, unit={n_unit!r}",
        f"Package: {package_size!r}  -> qty={p_qty}, unit={p_unit!r}",
    ]
    if ingredient:
        lines.append(f"Ingredient hint: {ingredient!r}")

    if n_qty and p_qty:
        n_base, n_fam = to_base(n_qty, n_unit)
        p_base, p_fam = to_base(p_qty, p_unit)
        lines.append(f"Need base:    {n_base} ({n_fam})")
        lines.append(f"Package base: {p_base} ({p_fam})")

        if n_fam == p_fam and n_base and p_base:
            pkgs = math.ceil(n_base / p_base)
            lines.append(f"Same family -> {n_base}/{p_base} = {pkgs} package(s)")
        elif ingredient:
            bridged = apply_ingredient_bridge(n_qty, n_unit, ingredient)
            if bridged:
                lines.append(f"Bridge: {n_qty} {n_unit} -> {bridged[0]} {bridged[1]}")

    result = packages_needed(needed, package_size, ingredient)
    lines.append(f"=> {result} package(s)")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# Tests
# ────────────────────────────────────────────────────────────────────────────

def run_tests() -> int:
    """Run a suite of test cases. Returns exit code (0 = all pass)."""
    cases = [
        # (needed, package, ingredient, expected, description)
        ("1.5 lb", "1 lb",   None,           2, "1.5 lb chicken / 1 lb pkg"),
        ("1 lb",   "1 lb",   None,           1, "1 lb / 1 lb"),
        ("2 lb",   "1 lb",   None,           2, "2 lb / 1 lb"),
        ("8",      "18 ct",  None,           1, "8 eggs / 18-ct carton"),
        ("4",      "6 ct",   None,           1, "4 tortillas / 6-pack"),
        ("8 slice","12 oz",  "bacon",        1, "8 slice bacon / 12 oz pkg"),
        ("16 slice","12 oz", "bacon",        2, "16 slice bacon / 12 oz pkg"),
        ("3 cup",  "1 gal",  None,           1, "3 cup milk / 1 gal"),
        ("16 cup", "1 gal",  None,           1, "16 cup milk / 1 gal (boundary)"),
        ("17 cup", "1 gal",  None,           2, "17 cup milk / 1 gal -> 2"),
        ("6 tbsp", "12 oz",  "chia seeds",   1, "6 tbsp chia seeds / 12 oz bag"),
        ("1.5 cup","32 oz",  "greek yogurt", 1, "1.5 cup yogurt / 32 oz"),
        ("8 clove","4 oz",   "garlic",       1, "8 clove garlic / 4 oz paste"),
        ("100 clove","4 oz", "garlic",       5, "100 cloves -> bulk"),
        ("1.5 lb", "16 oz",  None,           2, "1.5 lb / 16 oz (16 oz = 1 lb)"),
        ("3 cup",  "16 fl oz", None,         2, "3 cup milk / 16 fl oz pint"),
        ("2 cup",  "32 oz",  "rolled oats",  1, "2 cup oats (6 oz) / 32 oz"),
        ("1 each", "1 each", "lemon",        1, "1 lemon / 1 each"),
        ("",       "1 lb",   None,           1, "empty needed -> fallback"),
        ("garbage","1 lb",   None,           1, "unparseable -> fallback"),
        ("1 lb + 0.5 cup", "1 lb", None,     1, "multi-unit, only lb matches -> 1"),
        ("2 lb + 0.5 cup", "1 lb", None,     2, "multi-unit, lb dominates"),
        ("0.25 cup", "16 oz", None,          1, "0.25 cup volume / 16 oz weight"),
    ]

    passed = 0
    failed = []
    for needed, pkg, ing, expected, desc in cases:
        got = packages_needed(needed, pkg, ingredient=ing)
        ok = got == expected
        marker = "PASS" if ok else "FAIL"
        line = f"  {marker} {desc:<45s} need={needed!r:20s} pkg={pkg!r:12s} ing={ing!r:18s} -> {got} (expected {expected})"
        if ok:
            passed += 1
            print(line)
        else:
            failed.append(line)
            print(line)

    print()
    print(f"  {passed}/{len(cases)} passed")
    if failed:
        print("  FAILED:")
        for line in failed:
            print(f"    {line}")
        return 1
    return 0


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Calculate how many Kroger packages a recipe ingredient needs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python recipe_calculator.py "1.5 lb" --package "1 lb"
  python recipe_calculator.py "8 slice" --package "12 oz" --ingredient bacon
  python recipe_calculator.py "3 cup" --package "1 gal"
  python recipe_calculator.py --test
""",
    )
    parser.add_argument("needed", nargs="?", help='Recipe amount (e.g., "1.5 lb")')
    parser.add_argument("--package", "-p", help='Kroger package size (e.g., "1 lb")')
    parser.add_argument("--ingredient", "-i", help="Ingredient name for cross-family conversion")
    parser.add_argument("--explain", "-e", action="store_true", help="Show calculation trace")
    parser.add_argument("--test", action="store_true", help="Run the test suite")
    args = parser.parse_args(argv)

    if args.test:
        return run_tests()

    if not args.needed or not args.package:
        parser.print_help()
        return 1

    if args.explain:
        print(explain(args.needed, args.package, args.ingredient))
    else:
        result = packages_needed(args.needed, args.package, ingredient=args.ingredient)
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
