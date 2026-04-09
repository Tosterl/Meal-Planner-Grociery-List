#!/usr/bin/env python3
"""
Meal Planner & Grocery List Generator
A CLI tool to manage recipes, plan weekly meals, and generate consolidated grocery lists.
"""

import sys
import io

# Fix Windows console encoding for emoji support
if sys.platform == "win32" and getattr(sys.stdout, 'encoding', '') != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import os
import random
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
RECIPES_DIR = BASE_DIR / "recipes"
PLANS_DIR = BASE_DIR / "plans"
FAVORITES_FILE = BASE_DIR / "favorites.json"
HISTORY_FILE = BASE_DIR / "usage_history.json"
BLOCKED_FILE = BASE_DIR / "blocked.json"

RECIPES_DIR.mkdir(exist_ok=True)
PLANS_DIR.mkdir(exist_ok=True)

# Ingredient unit normalization map
UNIT_ALIASES = {
    "tablespoon": "tbsp", "tablespoons": "tbsp",
    "teaspoon": "tsp", "teaspoons": "tsp",
    "cup": "cup", "cups": "cup",
    "ounce": "oz", "ounces": "oz",
    "pound": "lb", "pounds": "lb",
    "clove": "clove", "cloves": "clove",
    "can": "can", "cans": "can",
    "piece": "piece", "pieces": "piece",
    "slice": "slice", "slices": "slice",
    "whole": "whole",
}

MEAL_SLOTS = ["breakfast", "lunch", "dinner"]
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ─── Recipe Management ────────────────────────────────────────────────────────

def load_recipe(name: str) -> dict | None:
    """Load a single recipe by name."""
    filepath = RECIPES_DIR / f"{slugify(name)}.json"
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return None


def save_recipe(recipe: dict):
    """Save a recipe to disk."""
    filepath = RECIPES_DIR / f"{slugify(recipe['name'])}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(recipe, f, indent=2)
    print(f"✅ Recipe saved: {recipe['name']}")


def list_recipes(tag_filter: str = None) -> list[dict]:
    """List all recipes, optionally filtered by tag."""
    recipes = []
    for f in sorted(RECIPES_DIR.glob("*.json")):
        with open(f) as fh:
            recipe = json.load(fh)
            if tag_filter is None or tag_filter.lower() in [t.lower() for t in recipe.get("tags", [])]:
                recipes.append(recipe)
    return recipes


def delete_recipe(name: str):
    """Delete a recipe by name."""
    filepath = RECIPES_DIR / f"{slugify(name)}.json"
    if filepath.exists():
        filepath.unlink()
        print(f"🗑️  Deleted: {name}")
    else:
        print(f"❌ Recipe not found: {name}")


def add_recipe_interactive():
    """Walk the user through adding a recipe."""
    print("\n📝 Add New Recipe")
    print("-" * 40)

    name = input("Recipe name: ").strip()
    if not name:
        print("❌ Name required.")
        return

    if load_recipe(name):
        overwrite = input("Recipe already exists. Overwrite? (y/n): ").strip().lower()
        if overwrite != "y":
            return

    servings = input("Servings (default 4): ").strip()
    servings = int(servings) if servings.isdigit() else 4

    prep_time = input("Prep time in minutes (optional): ").strip()
    prep_time = int(prep_time) if prep_time.isdigit() else None

    cook_time = input("Cook time in minutes (optional): ").strip()
    cook_time = int(cook_time) if cook_time.isdigit() else None

    tags_input = input("Tags (comma-separated, e.g. quick,chicken,italian): ").strip()
    tags = [t.strip().lower() for t in tags_input.split(",") if t.strip()] if tags_input else []

    meal_types_input = input(f"Meal types (comma-separated: {', '.join(MEAL_SLOTS)}): ").strip()
    meal_types = [m.strip().lower() for m in meal_types_input.split(",") if m.strip()] if meal_types_input else ["dinner"]

    print("\n🥕 Ingredients (enter blank line when done)")
    print("   Format: quantity unit ingredient  (e.g. '2 cups rice' or '1 whole onion')")
    ingredients = []
    while True:
        line = input("   > ").strip()
        if not line:
            break
        parsed = parse_ingredient(line)
        if parsed:
            ingredients.append(parsed)
            print(f"     Added: {parsed['qty']} {parsed['unit']} {parsed['item']}")
        else:
            print("     ⚠️  Couldn't parse. Try: '2 cups rice' or '1 lb chicken'")

    print("\n📋 Instructions (enter blank line when done)")
    steps = []
    step_num = 1
    while True:
        line = input(f"   Step {step_num}: ").strip()
        if not line:
            break
        steps.append(line)
        step_num += 1

    notes = input("\nNotes (optional): ").strip() or None

    recipe = {
        "name": name,
        "servings": servings,
        "prep_time": prep_time,
        "cook_time": cook_time,
        "tags": tags,
        "meal_types": meal_types,
        "ingredients": ingredients,
        "steps": steps,
        "notes": notes,
        "created": datetime.now().isoformat(),
    }

    save_recipe(recipe)


def show_recipe(name: str):
    """Display a recipe in a readable format."""
    recipe = load_recipe(name)
    if not recipe:
        print(f"❌ Recipe not found: {name}")
        return

    print(f"\n{'=' * 50}")
    print(f"  {recipe['name']}")
    print(f"{'=' * 50}")
    print(f"  Servings: {recipe['servings']}")

    times = []
    if recipe.get("prep_time"):
        times.append(f"Prep: {recipe['prep_time']}min")
    if recipe.get("cook_time"):
        times.append(f"Cook: {recipe['cook_time']}min")
    if times:
        total = (recipe.get("prep_time") or 0) + (recipe.get("cook_time") or 0)
        times.append(f"Total: {total}min")
        print(f"  {' | '.join(times)}")

    if recipe.get("tags"):
        print(f"  Tags: {', '.join(recipe['tags'])}")
    if recipe.get("meal_types"):
        print(f"  Meals: {', '.join(recipe['meal_types'])}")

    print(f"\n  🥕 Ingredients:")
    for ing in recipe.get("ingredients", []):
        qty = format_qty(ing["qty"])
        unit = f" {ing['unit']}" if ing["unit"] else ""
        print(f"     • {qty}{unit} {ing['item']}")

    if recipe.get("steps"):
        print(f"\n  📋 Instructions:")
        for i, step in enumerate(recipe["steps"], 1):
            print(f"     {i}. {step}")

    if recipe.get("notes"):
        print(f"\n  📝 Notes: {recipe['notes']}")
    print()


# ─── Meal Planning ────────────────────────────────────────────────────────────

def generate_plan(days: int = 7, meals: list[str] = None, strategy: str = "random",
                  cooldown_days: int = 14, optimize_groceries: bool = True,
                  use_leftovers: bool = True):
    """Generate a meal plan.

    Strategies:
    - random: Pure random selection
    - variety: Avoid repeats within the plan
    - smart: Optimize for ingredient overlap + variety over time

    If use_leftovers=True, recipes with multiple servings will fill subsequent
    meal slots as leftovers, reducing the number of unique recipes needed.
    """
    meals = meals or MEAL_SLOTS
    all_recipes = list_recipes()

    # Remove any recipes the user has blocked ("never again")
    blocked = load_blocked()
    if blocked:
        all_recipes = [r for r in all_recipes if slugify(r["name"]) not in blocked]

    if not all_recipes:
        print("❌ No recipes found. Add some first with: planner.py add")
        return

    plan = {"created": datetime.now().isoformat(), "days": [], "strategy": strategy}

    # For smart strategy, load history and favorites
    history = load_usage_history() if strategy == "smart" else {}
    favorites = load_favorites() if strategy == "smart" else []

    # Smart planning config
    smart_config = {
        "overlap_weight": 3.0,      # Points per shared ingredient
        "recency_penalty": 1.5,     # Penalty multiplier for recent usage
        "cooldown_days": cooldown_days,
        "favorite_bonus": 2.0,
    }

    # Track all selected recipes for ingredient overlap calculation
    selected_recipes = []
    # Track when each recipe was last used in this plan (index in selected_recipes)
    plan_usage = {}
    # Track leftover servings: {recipe_name: {"servings": N, "meal_types": [...]}}
    leftovers = {}

    # Build flat list of all meal slots
    meal_slots = []
    for i in range(days):
        day_name = DAYS_OF_WEEK[i % 7]
        for meal in meals:
            meal_slots.append({"day_index": i, "day_name": day_name, "meal": meal})

    # Initialize days structure
    for i in range(days):
        plan["days"].append({"day": DAYS_OF_WEEK[i % 7], "meals": {}})

    leftover_count = 0

    for slot in meal_slots:
        day_idx = slot["day_index"]
        meal = slot["meal"]

        # Check for available leftovers first
        if use_leftovers:
            available = None
            for name, data in leftovers.items():
                if data["servings"] > 0 and meal in data["meal_types"]:
                    available = (name, data)
                    break

            if available:
                name, data = available
                plan["days"][day_idx]["meals"][meal] = {
                    "name": f"{name} (leftover)",
                    "servings": 1,
                    "is_leftover": True
                }
                data["servings"] -= 1
                leftover_count += 1
                continue

        # Filter recipes suitable for this meal type
        suitable = [r for r in all_recipes if meal in r.get("meal_types", ["dinner"])]
        if not suitable:
            suitable = all_recipes  # fallback to all if none tagged

        if strategy == "random":
            chosen = random.choice(suitable)

        elif strategy == "variety":
            # Avoid repeats within the plan
            used_names = {m["name"].replace(" (leftover)", "") for d in plan["days"] for m in d["meals"].values() if isinstance(m, dict)}
            unused = [r for r in suitable if r["name"] not in used_names]
            chosen = random.choice(unused) if unused else random.choice(suitable)

        elif strategy == "smart":
            # Smart selection: optimize for ingredient overlap and avoid recent repeats
            used_names = {m["name"].replace(" (leftover)", "") for d in plan["days"] for m in d["meals"].values() if isinstance(m, dict)}
            # Prefer unused recipes, but allow repeats if necessary (small recipe pool)
            candidates = [r for r in suitable if r["name"] not in used_names]
            if not candidates:
                candidates = suitable  # fallback if we've exhausted options

            chosen = smart_select_recipe(candidates, selected_recipes, history,
                                         favorites, smart_config, plan_usage)
            if not chosen:
                chosen = random.choice(suitable)

        else:
            chosen = random.choice(suitable)

        plan["days"][day_idx]["meals"][meal] = {"name": chosen["name"], "servings": chosen["servings"]}
        selected_recipes.append(chosen)
        # Track when this recipe was last used in this plan
        plan_usage[chosen["name"]] = len(selected_recipes) - 1

        # Track leftovers (servings - 1 because we eat one now)
        if use_leftovers and chosen.get("servings", 1) > 1:
            leftovers[chosen["name"]] = {
                "servings": chosen["servings"] - 1,
                "meal_types": chosen.get("meal_types", ["dinner"])
            }

    # Record usage for smart strategy
    if strategy == "smart":
        recipe_names = [r["name"] for r in selected_recipes]
        record_usage(recipe_names)

    # Calculate and show optimization stats
    if selected_recipes:
        all_ingredients = set()
        for r in selected_recipes:
            all_ingredients.update(get_ingredient_set(r))

        total_meals = len(meal_slots)
        plan["stats"] = {
            "unique_ingredients": len(all_ingredients),
            "unique_recipes": len(selected_recipes),
            "leftover_meals": leftover_count,
            "total_meals": total_meals,
            "avg_ingredients_per_recipe": round(
                sum(len(get_ingredient_set(r)) for r in selected_recipes) / len(selected_recipes), 1
            )
        }

    # Save plan
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    plan_file = PLANS_DIR / f"plan_{timestamp}.json"
    with open(plan_file, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    print_plan(plan)
    print(f"\n💾 Plan saved to: {plan_file.name}")
    return plan


def print_plan(plan: dict):
    """Pretty print a meal plan."""
    print(f"\n{'=' * 55}")
    strategy = plan.get('strategy', 'random')
    strategy_label = {
        "random": "random",
        "variety": "variety",
        "smart": "smart - grocery optimized"
    }.get(strategy, strategy)
    print(f"  🗓️  Meal Plan ({strategy_label})")
    print(f"{'=' * 55}")

    for day in plan["days"]:
        print(f"\n  📅 {day['day']}")
        for meal, recipe in day["meals"].items():
            if isinstance(recipe, dict):
                print(f"     {meal.capitalize():12s} → {recipe['name']}")
            else:
                print(f"     {meal.capitalize():12s} → {recipe}")

    # Show optimization stats if available
    if "stats" in plan:
        stats = plan["stats"]
        print(f"\n  {'─' * 45}")
        print(f"  📊 Efficiency Stats:")
        print(f"     • {stats.get('unique_recipes', stats.get('total_recipes', 0))} recipes to cook")
        if stats.get('leftover_meals', 0) > 0:
            print(f"     • {stats['leftover_meals']} leftover meals (no cooking!)")
        print(f"     • {stats.get('total_meals', stats.get('unique_recipes', 0))} total meals")
        print(f"     • {stats['unique_ingredients']} unique grocery items")
        print(f"     • {stats['avg_ingredients_per_recipe']} avg ingredients/recipe")


def load_latest_plan() -> dict | None:
    """Load the most recent plan."""
    plans = sorted(PLANS_DIR.glob("plan_*.json"), reverse=True)
    if plans:
        with open(plans[0]) as f:
            return json.load(f)
    return None


# ─── Grocery List ─────────────────────────────────────────────────────────────

def generate_grocery_list(plan: dict = None, scale: float = 1.0) -> dict:
    """Generate a consolidated grocery list from a meal plan."""
    if plan is None:
        plan = load_latest_plan()
        if not plan:
            print("❌ No meal plan found. Generate one first with: planner.py plan")
            return {}

    # Collect all ingredients
    grocery = defaultdict(lambda: defaultdict(float))  # {item: {unit: qty}}

    for day in plan["days"]:
        for meal, recipe_ref in day["meals"].items():
            recipe_name = recipe_ref["name"] if isinstance(recipe_ref, dict) else recipe_ref
            recipe = load_recipe(recipe_name)
            if not recipe:
                print(f"  ⚠️  Recipe not found: {recipe_name}")
                continue

            for ing in recipe.get("ingredients", []):
                item = ing["item"].lower().strip()
                unit = normalize_unit(ing.get("unit", ""))
                qty = ing.get("qty", 0) * scale
                grocery[item][unit] += qty

    # Print and return
    print(f"\n{'=' * 50}")
    print(f"  🛒 Grocery List")
    if scale != 1.0:
        print(f"  (scaled {scale}x)")
    print(f"{'=' * 50}")

    # Group by likely store section
    sections = categorize_groceries(grocery)
    sorted_grocery = {}

    for section, items in sorted(sections.items()):
        print(f"\n  📦 {section}")
        for item in sorted(items):
            parts = []
            for unit, qty in grocery[item].items():
                qty_str = format_qty(qty)
                if unit:
                    parts.append(f"{qty_str} {unit}")
                else:
                    parts.append(qty_str)
            amount = " + ".join(parts)
            display_name = item.title()
            print(f"     ☐ {display_name} — {amount}")
            sorted_grocery[item] = dict(grocery[item])

    print()

    # Export to file
    export_path = PLANS_DIR / "grocery_list.md"
    export_grocery_markdown(grocery, sections, export_path, scale)
    print(f"💾 Exported to: {export_path}")

    return sorted_grocery


def export_calendar_ics(plan: dict, filepath: Path, timezone: str = "America/New_York"):
    """Export meal plan to ICS format for Google Calendar, Outlook, Skylight, etc.
    Supports both one-time import and URL subscription (auto-refresh)."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Meal Planner Pro//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Meal Plan",
        f"X-WR-TIMEZONE:{timezone}",
        # Tell subscribing calendars to refresh every 6 hours
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
        # Timezone definition (US Eastern)
        "BEGIN:VTIMEZONE",
        f"TZID:{timezone}",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:-0500",
        "TZOFFSETTO:-0400",
        "TZNAME:EDT",
        "DTSTART:19700308T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:-0400",
        "TZOFFSETTO:-0500",
        "TZNAME:EST",
        "DTSTART:19701101T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    # Meal times (approximate)
    meal_times = {
        "breakfast": ("0800", "0900"),
        "lunch": ("1200", "1300"),
        "dinner": ("1830", "1930"),
    }

    # Meal emojis
    meal_emoji = {
        "breakfast": "🍳",
        "lunch": "🥗",
        "dinner": "🍽️",
    }

    # Get start date from plan or use next Monday
    created = plan.get("created", datetime.now().isoformat())
    try:
        start_date = datetime.fromisoformat(created.split("T")[0])
    except:
        start_date = datetime.now()

    # Find next Monday if not already Monday
    days_until_monday = (7 - start_date.weekday()) % 7
    if days_until_monday == 0 and start_date.weekday() != 0:
        days_until_monday = 7
    start_date = start_date + timedelta(days=days_until_monday)

    # Timestamp for DTSTAMP (when this file was generated)
    now_stamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")

    uid_counter = 0
    for i, day in enumerate(plan.get("days", [])):
        current_date = start_date + timedelta(days=i)
        date_str = current_date.strftime("%Y%m%d")

        for meal, recipe_data in day.get("meals", {}).items():
            recipe_name = recipe_data["name"] if isinstance(recipe_data, dict) else recipe_data
            is_leftover = "(leftover)" in recipe_name
            clean_name = recipe_name.replace(" (leftover)", "")

            start_time, end_time = meal_times.get(meal, ("1200", "1300"))
            emoji = meal_emoji.get(meal, "🍴")

            uid_counter += 1
            uid = f"mealplan-{date_str}-{meal}-{uid_counter}@mealplanner"

            summary = f"{emoji} {meal.capitalize()}: {recipe_name}"

            # Build rich description with full recipe details
            desc_parts = [f"Recipe: {clean_name}"]
            if is_leftover:
                desc_parts.append("(Leftover - no cooking needed!)")

            recipe = load_recipe(clean_name)
            if recipe:
                # Servings
                if recipe.get("servings"):
                    desc_parts.append(f"Servings: {recipe['servings']}")

                # Prep & cook times
                times = []
                if recipe.get("prep_time"):
                    times.append(f"Prep: {recipe['prep_time']} min")
                if recipe.get("cook_time"):
                    times.append(f"Cook: {recipe['cook_time']} min")
                total_time = (recipe.get("prep_time") or 0) + (recipe.get("cook_time") or 0)
                if total_time:
                    times.append(f"Total: {total_time} min")
                if times:
                    desc_parts.append(" | ".join(times))

                # Ingredients
                if recipe.get("ingredients") and not is_leftover:
                    desc_parts.append("")
                    desc_parts.append("--- Ingredients ---")
                    for ing in recipe["ingredients"]:
                        q = str(ing.get("qty", "")) if ing.get("qty") else ""
                        u = f" {ing['unit']}" if ing.get("unit") else ""
                        desc_parts.append(f"• {q}{u} {ing['item']}".strip())

                # Steps
                if recipe.get("steps") and not is_leftover:
                    desc_parts.append("")
                    desc_parts.append("--- Steps ---")
                    for j, step in enumerate(recipe["steps"], 1):
                        desc_parts.append(f"{j}. {step}")

                # Notes
                if recipe.get("notes"):
                    desc_parts.append("")
                    desc_parts.append(f"Tip: {recipe['notes']}")

                # Source URL
                if recipe.get("source_url"):
                    desc_parts.append("")
                    desc_parts.append(f"Source: {recipe['source_url']}")

            description = "\\n".join(desc_parts)

            event_lines = [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART;TZID={timezone}:{date_str}T{start_time}00",
                f"DTEND;TZID={timezone}:{date_str}T{end_time}00",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
            ]
            if recipe and recipe.get("image_url"):
                event_lines.append(f"IMAGE;VALUE=URI:{recipe['image_url']}")
            if recipe and recipe.get("source_url"):
                event_lines.append(f"URL:{recipe['source_url']}")
            event_lines.extend([
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ])
            lines.extend(event_lines)

    lines.append("END:VCALENDAR")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))


def export_grocery_markdown(grocery: dict, sections: dict, filepath: Path, scale: float = 1.0):
    """Export grocery list as markdown."""
    lines = [f"# 🛒 Grocery List", f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    if scale != 1.0:
        lines.append(f"Scaled: {scale}x")
    lines.append("")

    for section, items in sorted(sections.items()):
        lines.append(f"## {section}")
        for item in sorted(items):
            parts = []
            for unit, qty in grocery[item].items():
                qty_str = format_qty(qty)
                if unit:
                    parts.append(f"{qty_str} {unit}")
                else:
                    parts.append(qty_str)
            amount = " + ".join(parts)
            lines.append(f"- [ ] {item.title()} — {amount}")
        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def categorize_groceries(grocery: dict) -> dict:
    """Simple keyword-based categorization of grocery items."""
    categories = {
        "🥩 Meat & Protein": ["chicken", "beef", "pork", "turkey", "salmon", "shrimp", "fish", "sausage",
                               "bacon", "steak", "ground", "tofu", "tempeh", "egg"],
        "🥬 Produce": ["onion", "garlic", "tomato", "pepper", "lettuce", "spinach", "carrot", "celery",
                        "potato", "broccoli", "mushroom", "avocado", "lemon", "lime", "ginger",
                        "cilantro", "parsley", "basil", "jalapeño", "cucumber", "zucchini", "corn",
                        "bell pepper", "green onion", "scallion"],
        "🧀 Dairy": ["milk", "cheese", "butter", "cream", "yogurt", "sour cream", "egg"],
        "🍞 Bread & Bakery": ["bread", "tortilla", "bun", "roll", "pita", "naan"],
        "🥫 Pantry": ["rice", "pasta", "flour", "sugar", "oil", "vinegar", "soy sauce", "broth",
                       "stock", "can", "bean", "lentil", "chickpea", "tomato sauce", "tomato paste",
                       "coconut milk", "honey", "maple syrup", "peanut butter"],
        "🧂 Spices & Seasonings": ["salt", "pepper", "cumin", "paprika", "oregano", "thyme",
                                     "cinnamon", "chili powder", "cayenne", "turmeric", "curry",
                                     "garlic powder", "onion powder"],
    }

    result = defaultdict(set)
    categorized = set()

    for item in grocery:
        item_lower = item.lower()
        placed = False
        for section, keywords in categories.items():
            if any(kw in item_lower for kw in keywords):
                result[section].add(item)
                placed = True
                categorized.add(item)
                break
        if not placed:
            result["🛍️ Other"].add(item)

    return dict(result)


# ─── Favorites ────────────────────────────────────────────────────────────────

def toggle_favorite(name: str):
    """Add or remove a recipe from favorites."""
    favs = load_favorites()
    slug = slugify(name)
    if slug in favs:
        favs.remove(slug)
        print(f"💔 Removed from favorites: {name}")
    else:
        if load_recipe(name):
            favs.append(slug)
            print(f"❤️  Added to favorites: {name}")
        else:
            print(f"❌ Recipe not found: {name}")
            return

    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(favs, f)


def load_favorites() -> list:
    if FAVORITES_FILE.exists():
        with open(FAVORITES_FILE) as f:
            return json.load(f)
    return []


# ─── Blocked Recipes ("Never Again") ─────────────────────────────────────────

def load_blocked() -> list:
    """Load list of blocked recipe slugs."""
    if BLOCKED_FILE.exists():
        with open(BLOCKED_FILE) as f:
            return json.load(f)
    return []


def save_blocked(blocked: list):
    """Save blocked recipe slugs to disk."""
    with open(BLOCKED_FILE, "w", encoding="utf-8") as f:
        json.dump(blocked, f)


# ─── Usage History & Smart Planning ───────────────────────────────────────────

def load_usage_history() -> dict:
    """Load recipe usage history. Format: {recipe_slug: [list of ISO date strings]}"""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}


def save_usage_history(history: dict):
    """Save recipe usage history."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def record_usage(recipe_names: list[str], date: str = None):
    """Record that recipes were used on a given date."""
    history = load_usage_history()
    date = date or datetime.now().strftime("%Y-%m-%d")

    for name in recipe_names:
        slug = slugify(name)
        if slug not in history:
            history[slug] = []
        if date not in history[slug]:
            history[slug].append(date)
            # Keep only last 90 days of history
            history[slug] = sorted(history[slug])[-90:]

    save_usage_history(history)


def days_since_last_used(recipe_name: str, history: dict) -> int:
    """Return number of days since recipe was last used. Returns 999 if never used."""
    slug = slugify(recipe_name)
    if slug not in history or not history[slug]:
        return 999

    last_used = max(history[slug])
    last_date = datetime.strptime(last_used, "%Y-%m-%d")
    return (datetime.now() - last_date).days


def get_ingredient_set(recipe: dict) -> set:
    """Extract normalized ingredient names from a recipe."""
    ingredients = set()
    for ing in recipe.get("ingredients", []):
        # Normalize: lowercase, strip, remove common modifiers
        item = ing["item"].lower().strip()
        # Remove prep instructions like "diced", "minced", etc.
        for word in ["diced", "minced", "chopped", "sliced", "crushed", "fresh", "dried"]:
            item = item.replace(word, "").strip()
        ingredients.add(item)
    return ingredients


def calculate_ingredient_overlap(recipe: dict, selected_recipes: list[dict]) -> int:
    """Calculate how many ingredients this recipe shares with already-selected recipes."""
    if not selected_recipes:
        return 0

    recipe_ingredients = get_ingredient_set(recipe)

    # Collect all ingredients from selected recipes
    selected_ingredients = set()
    for r in selected_recipes:
        selected_ingredients.update(get_ingredient_set(r))

    # Count overlap
    overlap = recipe_ingredients & selected_ingredients
    return len(overlap)


def score_recipe(recipe: dict, selected_recipes: list[dict], history: dict,
                 favorites: list, config: dict, plan_usage: dict = None) -> float:
    """
    Score a recipe for smart selection.

    Higher score = better choice

    Factors:
    - Ingredient overlap with selected recipes (+ points)
    - Days since last used in history (penalty if too recent)
    - Same-plan usage (heavy penalty for repeats, prefer spreading out)
    - Favorite status (small bonus)
    """
    score = 0.0
    plan_usage = plan_usage or {}

    # Ingredient overlap: +3 points per shared ingredient
    overlap = calculate_ingredient_overlap(recipe, selected_recipes)
    score += overlap * config.get("overlap_weight", 3.0)

    # Recency penalty: discourage if used within cooldown period
    days_ago = days_since_last_used(recipe["name"], history)
    cooldown = config.get("cooldown_days", 14)

    if days_ago < cooldown:
        # Penalty scales with how recently it was used
        # Used yesterday = -20 points, used 13 days ago = -1.4 points
        penalty = (cooldown - days_ago) * config.get("recency_penalty", 1.5)
        score -= penalty
    else:
        # Small bonus for recipes not used in a while (encourages rotation)
        score += min(days_ago / 30, 5)  # Max +5 for very old recipes

    # Same-plan repeat penalty: heavily discourage repeating within same plan
    # This ensures that if we MUST repeat, we spread them out
    recipe_name = recipe["name"]
    if recipe_name in plan_usage:
        meals_since_last = len(selected_recipes) - plan_usage[recipe_name]
        # Heavy penalty that decreases the longer ago it was used in this plan
        # Just used = -50, used 5 meals ago = -10
        repeat_penalty = max(50 - (meals_since_last * 8), 5)
        score -= repeat_penalty

    # Favorite bonus
    if slugify(recipe["name"]) in favorites:
        score += config.get("favorite_bonus", 2.0)

    return score


def smart_select_recipe(candidates: list[dict], selected_recipes: list[dict],
                        history: dict, favorites: list, config: dict,
                        plan_usage: dict = None) -> dict:
    """Select the best recipe using smart scoring."""
    if not candidates:
        return None

    plan_usage = plan_usage or {}

    # Score all candidates
    scored = []
    for recipe in candidates:
        s = score_recipe(recipe, selected_recipes, history, favorites, config, plan_usage)
        scored.append((s, recipe))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Add some randomness: pick from top 3 candidates weighted by score
    top_n = min(3, len(scored))
    top_candidates = scored[:top_n]

    # Weighted random selection (higher scores more likely)
    min_score = min(s for s, _ in top_candidates)
    weights = [s - min_score + 1 for s, _ in top_candidates]  # Shift to positive
    total = sum(weights)
    weights = [w / total for w in weights]

    r = random.random()
    cumulative = 0
    for i, w in enumerate(weights):
        cumulative += w
        if r <= cumulative:
            return top_candidates[i][1]

    return top_candidates[0][1]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    """Convert a recipe name to a filename-safe slug."""
    return name.lower().strip().replace(" ", "-").replace("'", "").replace('"', "")


def normalize_unit(unit: str) -> str:
    """Normalize unit strings."""
    unit = unit.lower().strip().rstrip(".")
    return UNIT_ALIASES.get(unit, unit)


def parse_ingredient(line: str) -> dict | None:
    """Parse an ingredient string like '2 cups rice' or '1/2 lb chicken breast'."""
    parts = line.strip().split()
    if len(parts) < 2:
        return None

    # Parse quantity (handle fractions like 1/2)
    qty_str = parts[0]
    try:
        if "/" in qty_str:
            num, den = qty_str.split("/")
            qty = float(num) / float(den)
        else:
            qty = float(qty_str)
    except ValueError:
        # Entire line might be the item with no qty
        return {"qty": 1, "unit": "", "item": line.strip()}

    # Check if second part is a unit
    potential_unit = parts[1].lower().rstrip(".")
    if potential_unit in UNIT_ALIASES or potential_unit in UNIT_ALIASES.values():
        unit = normalize_unit(potential_unit)
        item = " ".join(parts[2:])
    else:
        unit = ""
        item = " ".join(parts[1:])

    if not item:
        return None

    return {"qty": qty, "unit": unit, "item": item}


def format_qty(qty: float) -> str:
    """Format a quantity for display, using fractions where sensible."""
    if qty == int(qty):
        return str(int(qty))

    # Common fractions
    fractions = {0.25: "¼", 0.33: "⅓", 0.5: "½", 0.67: "⅔", 0.75: "¾"}
    whole = int(qty)
    frac = qty - whole

    for val, symbol in fractions.items():
        if abs(frac - val) < 0.05:
            return f"{whole}{symbol}" if whole else symbol

    return f"{qty:.1f}"


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🍽️  Meal Planner & Grocery List Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python planner.py add                    Add a new recipe interactively
  python planner.py list                   List all recipes
  python planner.py list --tag quick       List recipes tagged 'quick'
  python planner.py show "Chicken Stir Fry"  Show recipe details
  python planner.py plan                   Generate a 7-day meal plan (smart mode)
  python planner.py plan --strategy smart  Optimize for grocery efficiency
  python planner.py plan --cooldown 21     Don't repeat recipes within 21 days
  python planner.py plan --days 5 --meals dinner  Plan 5 dinners only
  python planner.py grocery                Generate grocery list from latest plan
  python planner.py grocery --scale 2      Double all quantities
  python planner.py fav "Chicken Stir Fry" Toggle favorite
  python planner.py delete "Old Recipe"    Delete a recipe
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # add
    subparsers.add_parser("add", help="Add a new recipe interactively")

    # list
    list_parser = subparsers.add_parser("list", help="List all recipes")
    list_parser.add_argument("--tag", "-t", help="Filter by tag")

    # show
    show_parser = subparsers.add_parser("show", help="Show a recipe")
    show_parser.add_argument("name", help="Recipe name")

    # delete
    del_parser = subparsers.add_parser("delete", help="Delete a recipe")
    del_parser.add_argument("name", help="Recipe name")

    # plan
    plan_parser = subparsers.add_parser("plan", help="Generate a meal plan")
    plan_parser.add_argument("--days", "-d", type=int, default=7, help="Number of days (default 7)")
    plan_parser.add_argument("--meals", "-m", nargs="+", default=MEAL_SLOTS, help="Meal slots to fill")
    plan_parser.add_argument("--strategy", "-s", choices=["random", "variety", "smart"], default="smart",
                             help="Selection strategy: random, variety, or smart (default: smart)")
    plan_parser.add_argument("--cooldown", "-c", type=int, default=14,
                             help="Days before a recipe can repeat (smart strategy, default 14)")
    plan_parser.add_argument("--no-leftovers", action="store_true",
                             help="Disable leftover optimization (cook fresh every meal)")

    # grocery
    grocery_parser = subparsers.add_parser("grocery", help="Generate grocery list from meal plan")
    grocery_parser.add_argument("--scale", type=float, default=1.0, help="Scale quantities (e.g. 2 for double)")

    # fav
    fav_parser = subparsers.add_parser("fav", help="Toggle favorite")
    fav_parser.add_argument("name", help="Recipe name")

    # block / unblock / blocked
    block_parser = subparsers.add_parser("block", help="Block a recipe (never suggest it again)")
    block_parser.add_argument("name", help="Recipe name")

    unblock_parser = subparsers.add_parser("unblock", help="Remove a recipe from the blocked list")
    unblock_parser.add_argument("name", help="Recipe name")

    subparsers.add_parser("blocked", help="List all blocked recipes")

    # import (from JSON)
    import_parser = subparsers.add_parser("import", help="Import recipe from a JSON file")
    import_parser.add_argument("filepath", help="Path to JSON file")

    # history
    subparsers.add_parser("history", help="Show recipe usage history")

    # calendar export
    cal_parser = subparsers.add_parser("calendar", help="Export meal plan to calendar (.ics)")
    cal_parser.add_argument("--output", "-o", default="meal-plan.ics", help="Output file (default: meal-plan.ics)")

    # sync - export all recipes for web UI
    sync_parser = subparsers.add_parser("sync", help="Sync recipes with web UI")
    sync_parser.add_argument("--export", "-e", action="store_true", help="Export recipes for web UI import")
    sync_parser.add_argument("--import-web", "-i", metavar="FILE", help="Import from web UI export file")

    args = parser.parse_args()

    if args.command == "add":
        add_recipe_interactive()

    elif args.command == "list":
        recipes = list_recipes(args.tag)
        if not recipes:
            print("No recipes found." + (f" (tag: {args.tag})" if args.tag else ""))
            print("Add one with: python planner.py add")
        else:
            print(f"\n📚 Recipes ({len(recipes)}):")
            favs = load_favorites()
            for r in recipes:
                fav = " ❤️" if slugify(r["name"]) in favs else ""
                tags = f"  [{', '.join(r.get('tags', []))}]" if r.get("tags") else ""
                total = (r.get("prep_time") or 0) + (r.get("cook_time") or 0)
                time_str = f"  ({total}min)" if total else ""
                print(f"   • {r['name']}{fav}{tags}{time_str}")

    elif args.command == "show":
        show_recipe(args.name)

    elif args.command == "delete":
        delete_recipe(args.name)

    elif args.command == "plan":
        generate_plan(days=args.days, meals=args.meals, strategy=args.strategy,
                      cooldown_days=getattr(args, 'cooldown', 14),
                      use_leftovers=not getattr(args, 'no_leftovers', False))

    elif args.command == "grocery":
        generate_grocery_list(scale=args.scale)

    elif args.command == "fav":
        toggle_favorite(args.name)

    elif args.command == "block":
        slug = slugify(args.name)
        blocked = load_blocked()
        if slug in blocked:
            print(f"⛔ Already blocked: {args.name}")
        elif not load_recipe(args.name):
            print(f"❌ Recipe not found: {args.name}")
        else:
            blocked.append(slug)
            save_blocked(blocked)
            print(f"⛔ Blocked: {args.name}")

    elif args.command == "unblock":
        slug = slugify(args.name)
        blocked = load_blocked()
        if slug in blocked:
            blocked.remove(slug)
            save_blocked(blocked)
            print(f"✅ Unblocked: {args.name}")
        else:
            print(f"❌ Not in blocked list: {args.name}")

    elif args.command == "blocked":
        blocked = load_blocked()
        if not blocked:
            print("No recipes are blocked.")
        else:
            print(f"\n⛔ Blocked Recipes ({len(blocked)}):")
            for slug in blocked:
                print(f"   • {slug.replace('-', ' ').title()}")
            print()

    elif args.command == "import":
        try:
            with open(args.filepath) as f:
                recipe = json.load(f)
            save_recipe(recipe)
        except Exception as e:
            print(f"❌ Import failed: {e}")

    elif args.command == "history":
        history = load_usage_history()
        if not history:
            print("📜 No usage history yet. Generate a plan with --strategy smart to start tracking.")
        else:
            print(f"\n{'=' * 50}")
            print("  📜 Recipe Usage History")
            print(f"{'=' * 50}\n")

            # Sort by most recent use
            items = []
            for slug, dates in history.items():
                if dates:
                    last = max(dates)
                    days = days_since_last_used(slug.replace("-", " ").title(), history)
                    items.append((days, slug, len(dates), last))

            items.sort()  # Sort by days since last used

            for days, slug, count, last in items:
                name = slug.replace("-", " ").title()
                if days == 0:
                    ago = "today"
                elif days == 1:
                    ago = "yesterday"
                else:
                    ago = f"{days} days ago"
                print(f"  • {name}")
                print(f"    Last used: {ago} | Total uses: {count}")
            print()

    elif args.command == "calendar":
        plan = load_latest_plan()
        if not plan:
            print("❌ No meal plan found. Generate one first with: planner.py plan")
        else:
            output_path = Path(args.output)
            if not output_path.is_absolute():
                output_path = BASE_DIR / output_path
            export_calendar_ics(plan, output_path)
            print(f"📅 Calendar exported to: {output_path}")
            print(f"\n┌─────────────────────────────────────────────────┐")
            print(f"│  📱 SKYLIGHT CALENDAR SYNC                       │")
            print(f"├─────────────────────────────────────────────────┤")
            print(f"│  Option 1: Via Google Calendar (Recommended)    │")
            print(f"│  1. Import .ics to Google Calendar              │")
            print(f"│  2. Skylight auto-syncs with Google             │")
            print(f"│                                                 │")
            print(f"│  Option 2: Direct Skylight Import               │")
            print(f"│  1. Email the .ics file to yourself             │")
            print(f"│  2. Open on phone → Add to Skylight calendar    │")
            print(f"└─────────────────────────────────────────────────┘")
            print(f"\nOther calendars:")
            print(f"  • Google Calendar: Settings → Import & Export → Import")
            print(f"  • Outlook: File → Open & Export → Import/Export")
            print(f"  • Apple Calendar: File → Import")

    elif args.command == "sync":
        if args.export:
            # Export all recipes as a single JSON for web UI import
            recipes = list_recipes()
            history = load_usage_history()
            output = {
                "recipes": recipes,
                "usage_history": history,
                "exported_at": datetime.now().isoformat()
            }
            export_path = BASE_DIR / "web-sync-export.json"
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2)
            print(f"✅ Exported {len(recipes)} recipes to: {export_path}")
            print("   Open this file in the web UI using the Import button.")

        elif args.import_web:
            # Import from web UI export
            try:
                with open(args.import_web, encoding="utf-8") as f:
                    data = json.load(f)

                imported = 0
                recipes = data.get("recipes", data if isinstance(data, list) else [data])
                for recipe in recipes:
                    if recipe.get("name"):
                        save_recipe(recipe)
                        imported += 1

                # Merge usage history
                if "usage_history" in data:
                    history = load_usage_history()
                    for slug, dates in data["usage_history"].items():
                        if slug not in history:
                            history[slug] = []
                        for d in dates:
                            if d not in history[slug]:
                                history[slug].append(d)
                        history[slug] = sorted(history[slug])[-90:]
                    save_usage_history(history)
                    print("  📜 Usage history merged.")

                print(f"✅ Imported {imported} recipes from web UI.")
            except Exception as e:
                print(f"❌ Import failed: {e}")
        else:
            print("Usage: planner.py sync --export  OR  planner.py sync --import-web <file>")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
