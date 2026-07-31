"""Recipe, plan, and usage-history storage.

All file I/O is UTF-8 explicitly (Windows defaults to cp1252 otherwise).
Directory arguments default to the project layout but are injectable for
tests.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from .text import slugify

BASE_DIR = Path(__file__).resolve().parent.parent
RECIPES_DIR = BASE_DIR / "recipes"
PLANS_DIR = BASE_DIR / "plans"
HISTORY_FILE = BASE_DIR / "usage_history.json"

RECIPES_DIR.mkdir(exist_ok=True)
PLANS_DIR.mkdir(exist_ok=True)


def _recipe_path(name: str, recipes_dir: Path) -> Path:
    return recipes_dir / f"{slugify(name)}.json"


def load_recipe(name: str, recipes_dir: Path = RECIPES_DIR) -> dict | None:
    """Load a single recipe by name (or slug)."""
    filepath = _recipe_path(name, recipes_dir)
    if filepath.exists():
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_recipe(recipe: dict, recipes_dir: Path = RECIPES_DIR) -> Path:
    """Save a recipe to disk; returns the file path."""
    filepath = _recipe_path(recipe["name"], recipes_dir)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(recipe, f, indent=2, ensure_ascii=False)
    return filepath


def delete_recipe(name: str, recipes_dir: Path = RECIPES_DIR) -> bool:
    """Delete a recipe by name; returns True if it existed."""
    filepath = _recipe_path(name, recipes_dir)
    if filepath.exists():
        filepath.unlink()
        return True
    return False


def list_recipes(tag_filter: str = None, recipes_dir: Path = RECIPES_DIR) -> list[dict]:
    """List all recipes, optionally filtered by tag. Skips corrupt files."""
    recipes = []
    for f in sorted(recipes_dir.glob("*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                recipe = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        if tag_filter is None or tag_filter.lower() in [
            t.lower() for t in recipe.get("tags", [])
        ]:
            recipes.append(recipe)
    return recipes


def load_latest_plan(plans_dir: Path = PLANS_DIR) -> dict | None:
    """Load the most recent plan file."""
    plans = sorted(plans_dir.glob("plan_*.json"), reverse=True)
    if plans:
        with open(plans[0], encoding="utf-8") as f:
            return json.load(f)
    return None


def load_usage_history(history_file: Path = HISTORY_FILE) -> dict:
    if history_file.exists():
        try:
            with open(history_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_usage_history(history: dict, history_file: Path = HISTORY_FILE):
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def record_usage(recipe_names: list[str], date: str = None,
                 history_file: Path = HISTORY_FILE):
    """Record that recipes were used on a date; prunes entries > 90 days old.

    (The old version kept the last 90 *entries* despite saying "days".)
    """
    history = load_usage_history(history_file)
    date = date or datetime.now().strftime("%Y-%m-%d")
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

    for name in recipe_names:
        slug = slugify(name)
        dates = set(history.get(slug, []))
        dates.add(date)
        history[slug] = sorted(d for d in dates if d >= cutoff)

    save_usage_history(history, history_file)
