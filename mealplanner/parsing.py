"""Ingredient string parsing.

One parser for all entry points (interactive add, web scrape, CLI import).
Handles: "2 cups rice", "1/2 lb chicken", "1 1/2 lb chicken", "1½ cup milk",
"½ cup broth", "1.5 lb beef", and bare items with no quantity.
"""

import re

from .units import KNOWN_UNITS, normalize_unit

UNICODE_FRACTIONS = {
    "½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 0.33, "⅔": 0.67,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}


def eval_fraction(frac_str: str) -> float:
    """Safely evaluate a fraction string like '1/2'. Returns 0 on garbage."""
    try:
        num, den = frac_str.split("/")
        return float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        return 0


def parse_ingredient_string(text: str) -> dict:
    """Parse a natural-language ingredient line into structured data.

    Returns {"qty": float, "unit": str, "item": str, "original": str}.
    The original raw string is preserved so bad parses can be re-parsed
    after parser improvements.
    """
    original = text.strip()
    text = re.sub(r"\s+", " ", original)

    qty = 0
    rest = text

    # Leading quantity: "1 1/2", "1½", "½", "1/2", "1.5", "1"
    if m := re.match(r"^(\d+)\s+(\d+/\d+)\s+(.*)", text):
        qty = int(m.group(1)) + eval_fraction(m.group(2))
        rest = m.group(3)
    elif m := re.match(r"^(\d+)([½¼¾⅓⅔⅛⅜⅝⅞])\s*(.*)", text):
        qty = int(m.group(1)) + UNICODE_FRACTIONS.get(m.group(2), 0)
        rest = m.group(3)
    elif m := re.match(r"^([½¼¾⅓⅔⅛⅜⅝⅞])\s*(.*)", text):
        qty = UNICODE_FRACTIONS.get(m.group(1), 0)
        rest = m.group(2)
    elif m := re.match(r"^(\d+/\d+)\s+(.*)", text):
        qty = eval_fraction(m.group(1))
        rest = m.group(2)
    elif m := re.match(r"^(\d+\.?\d*)\s+(.*)", text):
        qty = float(m.group(1))
        rest = m.group(2)
    else:
        return {"qty": 1, "unit": "", "item": text, "original": original}

    # Unit token right after the quantity
    unit = ""
    rest_words = rest.split()
    if rest_words:
        first = rest_words[0].lower().rstrip(".,")
        if first in KNOWN_UNITS:
            unit = normalize_unit(first)
            rest = " ".join(rest_words[1:])

    # Clean up item name; drop parenthetical notes
    item = rest.strip().rstrip(".,")
    item_clean = re.sub(r"\s*\(.*?\)\s*", " ", item).strip()
    if not item_clean:
        item_clean = item

    return {
        "qty": round(qty, 3) if qty else 1,
        "unit": unit,
        "item": item_clean,
        "original": original,
    }
