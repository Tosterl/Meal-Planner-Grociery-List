#!/usr/bin/env python3
"""
Audit Tool — what *should* be in your Kroger cart for the current meal plan.

Reads the latest meal plan and your pantry, computes the ideal grocery list
with smart package quantities, and prints a clean report you can compare
against kroger.com/cart by eye.

Usage:
  python audit_cart.py                      # Print ideal cart for current week
  python audit_cart.py --days 7             # Plan window in days (default: 7)
  python audit_cart.py --kroger             # Also fetch live Kroger prices/sizes
  python audit_cart.py --zip 45202          # Required with --kroger
  python audit_cart.py --json               # Machine-readable output
  python audit_cart.py --markdown           # Save report to plans/cart_audit.md

Examples:
  python audit_cart.py --kroger --zip 45202 > audit.txt
  python audit_cart.py --markdown
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

import recipe_calculator as rc
from mealplanner import (
    categorize,
    list_recipes,
    load_latest_plan,
    normalize_unit,
    setup_utf8_console,
    slugify,
)


# ────────────────────────────────────────────────────────────────────────────
# Data loaders
# ────────────────────────────────────────────────────────────────────────────

def build_recipe_lookup() -> dict[str, dict]:
    """Index recipes by slug (and lowercased-name key) to match plan entries."""
    out = {}
    for recipe in list_recipes():
        name = recipe.get("name", "")
        out[slugify(name)] = recipe
        name_key = name.lower().replace(" ", "-")
        if name_key:
            out[name_key] = recipe
    return out


def load_kroger_pantry() -> list[dict]:
    pantry_file = BASE_DIR / "pantry.json"
    if not pantry_file.exists():
        return []
    try:
        with open(pantry_file, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    # Pantry can be either a flat list or wrapped under "items"
    if isinstance(data, dict):
        data = data.get("items") or data.get("kroger") or []
    if not isinstance(data, list):
        return []
    # Filter to dict entries only
    return [p for p in data if isinstance(p, dict)]


# ────────────────────────────────────────────────────────────────────────────
# Aggregation
# ────────────────────────────────────────────────────────────────────────────

def collect_meals_for_window(plan: dict, days: int) -> list[str]:
    """Collect recipe names from the next `days` worth of meals starting today."""
    today = datetime.now().date()
    end = today + timedelta(days=days)

    # plan format: { days: [{ day: "Monday", meals: { breakfast: {name: "..."} } }] }
    # The plan also has a "created" date — use it to anchor the week
    created_str = plan.get("created", "")
    try:
        anchor = datetime.fromisoformat(created_str.split("T")[0]).date()
    except (ValueError, IndexError):
        anchor = today

    # Find the Monday at/before the anchor
    anchor -= timedelta(days=anchor.weekday())

    recipes_in_window = []
    for i, day in enumerate(plan.get("days", [])):
        day_date = anchor + timedelta(days=i)
        if day_date < today or day_date >= end:
            continue
        for meal_data in day.get("meals", {}).values():
            name = meal_data["name"] if isinstance(meal_data, dict) else meal_data
            if name:
                recipes_in_window.append(name)

    return recipes_in_window


def aggregate_ingredients(
    recipe_names: list[str], recipes: dict
) -> tuple[dict[str, dict[str, float]], list[str]]:
    """Sum ingredients across all planned recipes.

    Returns ({ item: { unit: qty } }, [missing recipe names]).
    """
    grocery: dict[str, dict[str, float]] = {}
    missing_recipes = []

    for name in recipe_names:
        # Try direct slug, then name-lowered slug
        clean_name = name.replace(" (leftover)", "").strip()
        if "(leftover)" in name.lower():
            continue  # Don't re-shop leftovers

        slug = slugify(clean_name)
        recipe = recipes.get(slug) or recipes.get(clean_name.lower().replace(" ", "-"))

        if not recipe:
            missing_recipes.append(clean_name)
            continue

        for ing in recipe.get("ingredients", []):
            item = (ing.get("item") or "").lower().strip()
            unit = normalize_unit(ing.get("unit") or "")
            qty = float(ing.get("qty") or 0)
            if not item or qty <= 0:
                continue
            grocery.setdefault(item, {})
            grocery[item][unit] = grocery[item].get(unit, 0) + qty

    return grocery, missing_recipes


def covered_by_pantry(item: str, pantry: list[dict]) -> dict | None:
    """Find a pantry product whose name closely matches the ingredient."""
    food_nouns = {
        # Different food categories
        "chicken", "beef", "pork", "fish", "salmon", "shrimp",
        "cake", "cookie", "cookies", "cereal", "pasta", "noodle", "noodles",
        "chips", "crisps", "bar", "bars",
        # Different forms / preparations
        "sauce", "salsa", "dressing", "paste", "stir-in",
        # Different product types
        "soda", "drink", "drinks", "water", "juice", "tea", "coffee",
        # Personal care (not food)
        "conditioner", "shampoo", "lotion", "spray", "cream", "scrub",
        # Ground/processed when fresh is intended
        "powder", "seed",  # blocks "cumin seed" / "ginger powder" etc.
    }
    item_words = item.split()
    for p in pantry:
        product_words = (p.get("name", "").lower().split())
        # Check for consecutive whole-word match
        for i in range(len(product_words) - len(item_words) + 1):
            if product_words[i:i + len(item_words)] == item_words:
                tail = product_words[i + len(item_words):]
                if any(w in food_nouns for w in tail):
                    continue  # "honey chicken" doesn't cover "honey"
                return p
    return None


_BASE_UNIT_LABEL = {"weight": "oz", "volume": "fl oz", "count": "ct"}


def pantry_quantity_covers(units: dict[str, float], pantry_item: dict) -> tuple[bool, str]:
    """Does the pantry item's amount actually cover the needed quantity?

    Returns (covers, shortfall_note). Owning 1 tbsp of olive oil should not
    zero out a recipe needing a cup. When the pantry size is unparseable or
    the units live in different families (e.g. "2 cloves" vs a 3-oz jar),
    we can't compare — fall back to the legacy assume-covered behavior.
    """
    p_qty, p_unit = rc.parse_amount(str(pantry_item.get("size") or ""))
    if p_qty is None or p_qty <= 0:
        return True, ""
    count = float(pantry_item.get("qty") or 1)
    p_base, p_family = rc.to_base(p_qty * max(count, 1), p_unit)
    if p_base is None:
        return True, ""

    for unit, qty in units.items():
        n_base, n_family = rc.to_base(qty, unit)
        if n_base is None or n_family != p_family:
            continue  # not comparable — don't block coverage on it
        if n_base > p_base + 1e-9:
            label = _BASE_UNIT_LABEL[p_family]
            return False, f"have ~{p_base:g} {label}, need ~{n_base:g} {label}"
    return True, ""


def format_needed(units: dict[str, float]) -> str:
    parts = []
    for unit, qty in units.items():
        q_str = f"{qty:g}"
        parts.append(f"{q_str} {unit}".strip())
    return " + ".join(parts)


# ────────────────────────────────────────────────────────────────────────────
# Live Kroger lookup (optional — needs --kroger)
# ────────────────────────────────────────────────────────────────────────────

def fetch_live_match(item: str, location_id: str | None) -> dict | None:
    from kroger_api import search_alternatives, clean_ingredient_query
    cleaned = clean_ingredient_query(item)
    alts = search_alternatives(cleaned, location_id, limit=1) or []
    return alts[0] if alts else None


def get_location_id(zip_code: str) -> str | None:
    if not zip_code:
        return None
    from kroger_api import find_nearest_store
    store = find_nearest_store(zip_code)
    return store.get("locationId") if store else None


# ────────────────────────────────────────────────────────────────────────────
# Report builders
# ────────────────────────────────────────────────────────────────────────────

def build_audit(days: int, live: bool, zip_code: str | None) -> dict:
    """Compute the audit report data."""
    plan = load_latest_plan()
    if not plan:
        return {"error": "No meal plan found in plans/ — run 'python publish.py' first"}

    recipes = build_recipe_lookup()
    if not recipes:
        return {"error": "No recipes found in recipes/"}

    pantry = load_kroger_pantry()
    meal_names = collect_meals_for_window(plan, days)
    grocery, missing = aggregate_ingredients(meal_names, recipes)

    location_id = get_location_id(zip_code) if (live and zip_code) else None

    cart_items = []
    pantry_skipped = []
    total_estimated = 0.0

    for item, units in sorted(grocery.items()):
        in_pantry = covered_by_pantry(item, pantry)
        needed = format_needed(units)

        pantry_shortfall = ""
        if in_pantry:
            covers, pantry_shortfall = pantry_quantity_covers(units, in_pantry)
            if covers:
                pantry_skipped.append({
                    "item": item,
                    "needed": needed,
                    "covered_by": in_pantry.get("name", ""),
                    "have_qty": in_pantry.get("qty", 1),
                })
                continue
            # Partial coverage: still needs buying — flag it in the report

        entry = {
            "item": item,
            "needed": needed,
            "pantry_partial": pantry_shortfall or None,
            "category": categorize(item),
            "package_qty": 1,  # default
            "match": None,
            "match_size": None,
            "match_price": None,
        }

        if live:
            match = fetch_live_match(item, location_id)
            if match:
                from kroger_api import compute_packages_needed
                pkg_size = match.get("size", "")
                pkgs = compute_packages_needed(needed, pkg_size, ingredient=item, fallback=1)
                entry["match"] = match.get("name")
                entry["match_brand"] = match.get("brand")
                entry["match_size"] = pkg_size
                entry["match_price"] = match.get("price")
                entry["match_upc"] = match.get("upc")
                entry["package_qty"] = pkgs
                if match.get("price"):
                    total_estimated += pkgs * match["price"]

        cart_items.append(entry)

    return {
        "plan_created": plan.get("created"),
        "plan_window_days": days,
        "meals_in_window": len(meal_names),
        "missing_recipes": missing,
        "cart_items": cart_items,
        "pantry_skipped": pantry_skipped,
        "estimated_total": total_estimated if live else None,
    }


def render_text(audit: dict) -> str:
    if "error" in audit:
        return f"❌ {audit['error']}\n"

    lines = []
    lines.append("=" * 72)
    lines.append("  KROGER CART AUDIT — what your cart SHOULD look like")
    lines.append("=" * 72)
    lines.append(f"  Plan created:      {audit['plan_created']}")
    lines.append(f"  Window:            next {audit['plan_window_days']} days "
                 f"({audit['meals_in_window']} meals)")

    if audit["missing_recipes"]:
        lines.append("")
        lines.append("  ⚠️  Recipes missing from disk:")
        for r in audit["missing_recipes"]:
            lines.append(f"      - {r}")

    # Group cart items by category
    by_cat: dict[str, list[dict]] = {}
    for item in audit["cart_items"]:
        by_cat.setdefault(item["category"], []).append(item)

    lines.append("")
    lines.append("  ─" * 36)
    lines.append("  TO ORDER (compare to kroger.com/cart):")
    lines.append("  ─" * 36)

    for cat in sorted(by_cat.keys()):
        lines.append(f"\n  {cat}:")
        for item in by_cat[cat]:
            need = item["needed"]
            if item.get("match"):
                price_str = f"${item['match_price']:.2f}" if item.get("match_price") else "$?"
                line_total = item["match_price"] * item["package_qty"] if item.get("match_price") else 0
                lines.append(f"    [{item['package_qty']}x] {item['item']:<25} need {need}")
                lines.append(f"          -> {item['match']} ({item['match_size']}) "
                             f"@ {price_str} = ${line_total:.2f}")
            else:
                lines.append(f"    [{item['package_qty']}x] {item['item']:<25} need {need}")
            if item.get("pantry_partial"):
                lines.append(f"          ⚠️  pantry has some, not enough ({item['pantry_partial']})")

    if audit["pantry_skipped"]:
        lines.append("")
        lines.append("  ─" * 36)
        lines.append(f"  ALREADY IN PANTRY (skipped — {len(audit['pantry_skipped'])} items):")
        lines.append("  ─" * 36)
        for it in audit["pantry_skipped"]:
            lines.append(f"    • {it['item']:<25} (need {it['needed']}, have {it['have_qty']}x of '{it['covered_by']}')")

    if audit.get("estimated_total"):
        lines.append("")
        lines.append("  " + "=" * 36)
        lines.append(f"  ESTIMATED TOTAL: ${audit['estimated_total']:.2f}")
        lines.append("  " + "=" * 36)

    lines.append("")
    lines.append("  Compare this list to kroger.com/cart and remove or add items as needed.")
    lines.append("")
    return "\n".join(lines)


def render_markdown(audit: dict) -> str:
    if "error" in audit:
        return f"# Cart Audit\n\n**Error:** {audit['error']}\n"

    lines = ["# Kroger Cart Audit", ""]
    lines.append(f"- **Plan created:** {audit['plan_created']}")
    lines.append(f"- **Window:** next {audit['plan_window_days']} days ({audit['meals_in_window']} meals)")
    if audit.get("estimated_total"):
        lines.append(f"- **Estimated total:** ${audit['estimated_total']:.2f}")
    lines.append("")

    if audit["missing_recipes"]:
        lines.append("## ⚠️ Missing recipes")
        for r in audit["missing_recipes"]:
            lines.append(f"- {r}")
        lines.append("")

    by_cat: dict[str, list[dict]] = {}
    for item in audit["cart_items"]:
        by_cat.setdefault(item["category"], []).append(item)

    lines.append("## To Order")
    for cat in sorted(by_cat.keys()):
        lines.append(f"\n### {cat}")
        lines.append("")
        lines.append("| Qty | Item | Need | Match | Size | Price | Line total |")
        lines.append("|---:|---|---|---|---|---:|---:|")
        for item in by_cat[cat]:
            qty = item["package_qty"]
            match = item.get("match") or "_(not looked up)_"
            size = item.get("match_size") or ""
            price = f"${item['match_price']:.2f}" if item.get("match_price") else ""
            total = f"${item['match_price'] * qty:.2f}" if item.get("match_price") else ""
            lines.append(f"| {qty} | {item['item']} | {item['needed']} | {match} | {size} | {price} | {total} |")
        lines.append("")

    if audit["pantry_skipped"]:
        lines.append(f"## Already in pantry ({len(audit['pantry_skipped'])} skipped)")
        lines.append("")
        for it in audit["pantry_skipped"]:
            lines.append(f"- **{it['item']}** (need {it['needed']}) — have {it['have_qty']}× of *{it['covered_by']}*")
        lines.append("")

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit your Kroger cart against the current meal plan",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--days", type=int, default=7, help="Plan window in days (default: 7)")
    parser.add_argument("--kroger", action="store_true", help="Fetch live Kroger prices and matches")
    parser.add_argument("--zip", help="Zip code for Kroger store (used with --kroger)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--markdown", action="store_true", help="Save markdown report to plans/cart_audit.md")
    args = parser.parse_args(argv)

    audit = build_audit(args.days, args.kroger, args.zip)

    if args.json:
        print(json.dumps(audit, indent=2, default=str))
    elif args.markdown:
        out = render_markdown(audit)
        out_path = BASE_DIR / "plans" / "cart_audit.md"
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(out, encoding="utf-8")
        print(f"Saved: {out_path}")
        print()
        print(out)
    else:
        print(render_text(audit))

    return 0


if __name__ == "__main__":
    setup_utf8_console()
    sys.exit(main())
