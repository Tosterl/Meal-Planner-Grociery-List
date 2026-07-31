"""Shared core for the meal planner CLI tools and API server.

Single home for logic that was previously copy-pasted across planner.py,
scraper.py, and audit_cart.py (slugify, unit tables, ingredient parsing,
recipe/plan storage, grocery categorization).
"""

from .console import setup_utf8_console
from .text import slugify
from .units import UNIT_ALIASES, KNOWN_UNITS, normalize_unit
from .parsing import UNICODE_FRACTIONS, eval_fraction, parse_ingredient_string
from .storage import (
    BASE_DIR,
    RECIPES_DIR,
    PLANS_DIR,
    HISTORY_FILE,
    load_recipe,
    save_recipe,
    delete_recipe,
    list_recipes,
    load_latest_plan,
    load_usage_history,
    save_usage_history,
    record_usage,
)
from .categories import GROCERY_CATEGORIES, CATEGORY_EMOJI, categorize

__all__ = [
    "setup_utf8_console",
    "slugify",
    "UNIT_ALIASES",
    "KNOWN_UNITS",
    "normalize_unit",
    "UNICODE_FRACTIONS",
    "eval_fraction",
    "parse_ingredient_string",
    "BASE_DIR",
    "RECIPES_DIR",
    "PLANS_DIR",
    "HISTORY_FILE",
    "load_recipe",
    "save_recipe",
    "delete_recipe",
    "list_recipes",
    "load_latest_plan",
    "load_usage_history",
    "save_usage_history",
    "record_usage",
    "GROCERY_CATEGORIES",
    "CATEGORY_EMOJI",
    "categorize",
]
