#!/usr/bin/env python3
"""
Recipe Scraper & Dietary Adapter
Scrapes recipes from URLs (using Schema.org JSON-LD) and adapts them for dietary needs.

Usage:
  python scraper.py "https://www.allrecipes.com/recipe/..."
  python scraper.py "https://www.budgetbytes.com/..."
  python scraper.py "https://..." --dairy-free
  python scraper.py "https://..." --dairy-free --save
  python scraper.py bulk urls.txt --dairy-free --save
"""

import sys
import io

# Fix Windows console encoding for emoji support
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import re
import argparse
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ─── Config ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
RECIPES_DIR = BASE_DIR / "recipes"
RECIPES_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── Dairy Substitutions ─────────────────────────────────────────────────────
DAIRY_ITEMS = {
    # item keyword -> { substitute, note }
    "milk": {
        "sub": "oat milk",
        "note": "Use any plant milk — oat works best for cooking, almond for lighter dishes"
    },
    "whole milk": {
        "sub": "full-fat oat milk",
        "note": "Full-fat oat or coconut milk for richness"
    },
    "buttermilk": {
        "sub": "oat milk + 1 tbsp lemon juice",
        "note": "Let it sit 5 min to curdle before using"
    },
    "heavy cream": {
        "sub": "full-fat coconut cream",
        "note": "Canned coconut cream is the best 1:1 swap for heavy cream"
    },
    "cream": {
        "sub": "coconut cream",
        "note": "Use full-fat coconut cream or cashew cream"
    },
    "half and half": {
        "sub": "oat creamer",
        "note": "Oat-based creamers work well here"
    },
    "butter": {
        "sub": "vegan butter (Earth Balance)",
        "note": "Earth Balance or Miyoko's are best for cooking; coconut oil works for baking"
    },
    "unsalted butter": {
        "sub": "unsalted vegan butter",
        "note": "Miyoko's unsalted is great for baking"
    },
    "cream cheese": {
        "sub": "dairy-free cream cheese (Kite Hill)",
        "note": "Kite Hill or Miyoko's are the best cream cheese subs"
    },
    "sour cream": {
        "sub": "dairy-free sour cream (Tofutti)",
        "note": "Tofutti or cashew-based sour cream; or blend soaked cashews with lemon"
    },
    "greek yogurt": {
        "sub": "coconut yogurt (unsweetened)",
        "note": "Silk or So Delicious coconut yogurt for cooking"
    },
    "yogurt": {
        "sub": "dairy-free yogurt",
        "note": "Coconut or oat-based yogurt"
    },
    "cheddar cheese": {
        "sub": "dairy-free cheddar (Violife)",
        "note": "Violife or Follow Your Heart shred/melt best"
    },
    "shredded cheddar cheese": {
        "sub": "dairy-free shredded cheddar",
        "note": "Violife shreds melt well for tacos/burritos"
    },
    "mozzarella": {
        "sub": "dairy-free mozzarella (Miyoko's)",
        "note": "Miyoko's fresh or Violife shreds for pizza"
    },
    "parmesan cheese": {
        "sub": "nutritional yeast",
        "note": "2 tbsp nutritional yeast per ½ cup parmesan; or use Violife parmesan block"
    },
    "parmesan": {
        "sub": "nutritional yeast",
        "note": "Nutritional yeast gives that umami/cheesy flavor"
    },
    "cheese": {
        "sub": "dairy-free cheese",
        "note": "Violife, Miyoko's, or Follow Your Heart are best melters"
    },
    "ricotta": {
        "sub": "tofu ricotta",
        "note": "Blend firm tofu with lemon juice, nutritional yeast, garlic, salt"
    },
    "whipped cream": {
        "sub": "coconut whipped cream",
        "note": "Chill canned coconut cream overnight, whip the solid part"
    },
    "ice cream": {
        "sub": "dairy-free ice cream",
        "note": "Oatly or So Delicious"
    },
    "condensed milk": {
        "sub": "coconut condensed milk",
        "note": "Nature's Charm makes a great coconut condensed milk"
    },
    "evaporated milk": {
        "sub": "coconut evaporated milk",
        "note": "Or simmer oat milk until reduced by half"
    },
    "ghee": {
        "sub": "ghee (usually lactose-free)",
        "note": "Most ghee is actually lactose-free since milk solids are removed — check the label"
    },
}

# Some dairy items are hidden in ingredient names
DAIRY_KEYWORDS = [
    "milk", "butter", "cream", "cheese", "yogurt", "whey", "casein",
    "lactose", "ricotta", "mozzarella", "cheddar", "parmesan",
    "brie", "gouda", "swiss", "provolone", "gruyere", "mascarpone",
    "queso", "paneer", "ghee", "custard",
]

# Items that contain dairy keywords but AREN'T dairy
DAIRY_FALSE_POSITIVES = [
    "coconut milk", "coconut cream", "oat milk", "almond milk", "soy milk",
    "cashew milk", "rice milk", "plant milk", "dairy-free", "vegan butter",
    "peanut butter", "almond butter", "sunflower butter", "cocoa butter",
    "shea butter", "buttercup squash", "butternut squash", "butterhead lettuce",
    "butter lettuce", "butter beans", "cream of tartar",
]


def is_dairy(ingredient_text: str) -> bool:
    """Check if an ingredient contains dairy."""
    text = ingredient_text.lower()

    # Check false positives first
    for fp in DAIRY_FALSE_POSITIVES:
        if fp in text:
            return False

    # Check for dairy keywords
    for kw in DAIRY_KEYWORDS:
        if kw in text:
            return True

    return False


def get_dairy_substitute(ingredient_text: str) -> dict | None:
    """Get the best dairy substitution for an ingredient."""
    text = ingredient_text.lower().strip()

    if not is_dairy(text):
        return None

    # Try exact matches first (longest match wins)
    best_match = None
    best_len = 0

    for key, sub in DAIRY_ITEMS.items():
        if key in text and len(key) > best_len:
            best_match = sub
            best_len = len(key)

    if best_match:
        return best_match

    # Generic fallback
    return {
        "sub": "dairy-free alternative",
        "note": "Check your store's dairy-free section for a substitute"
    }


def adapt_recipe_dairy_free(recipe: dict) -> dict:
    """Adapt a recipe to be dairy-free with substitutions."""
    adapted = recipe.copy()
    adapted["ingredients"] = []
    adapted["dairy_subs"] = []
    adapted["tags"] = list(recipe.get("tags", []))

    if "dairy-free" not in adapted["tags"]:
        adapted["tags"].append("dairy-free")

    has_dairy = False

    for ing in recipe.get("ingredients", []):
        item_text = ing.get("item", "")
        sub_info = get_dairy_substitute(item_text)

        if sub_info:
            has_dairy = True
            original_item = item_text

            # Create substituted ingredient
            new_ing = ing.copy()
            new_ing["item"] = sub_info["sub"]
            new_ing["original"] = original_item
            adapted["ingredients"].append(new_ing)

            adapted["dairy_subs"].append({
                "original": original_item,
                "substitute": sub_info["sub"],
                "note": sub_info["note"]
            })
        else:
            adapted["ingredients"].append(ing.copy())

    # Add note about substitutions
    if has_dairy:
        sub_notes = "; ".join([f"{s['original']} → {s['substitute']}" for s in adapted["dairy_subs"]])
        existing_notes = adapted.get("notes", "") or ""
        adapted["notes"] = f"🥛 DAIRY-FREE SWAPS: {sub_notes}. {existing_notes}".strip()

    return adapted


# ─── Recipe Scraping ──────────────────────────────────────────────────────────

def scrape_recipe(url: str) -> dict | None:
    """Scrape a recipe from a URL."""
    print(f"\n🔍 Fetching: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ❌ Failed to fetch: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Strategy 1: JSON-LD (Schema.org Recipe)
    recipe = extract_jsonld(soup)
    if recipe:
        print(f"  ✅ Found via JSON-LD: {recipe['name']}")
        recipe["source_url"] = url
        return recipe

    # Strategy 2: Microdata
    recipe = extract_microdata(soup)
    if recipe:
        print(f"  ✅ Found via microdata: {recipe['name']}")
        recipe["source_url"] = url
        return recipe

    # Strategy 3: Meta tags / Open Graph
    recipe = extract_meta(soup, url)
    if recipe:
        print(f"  ⚠️  Partial recipe from meta tags: {recipe['name']}")
        recipe["source_url"] = url
        return recipe

    print("  ❌ No recipe data found on this page")
    return None


def extract_jsonld(soup: BeautifulSoup) -> dict | None:
    """Extract recipe from JSON-LD structured data."""
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue

        recipes = find_recipe_in_jsonld(data)
        if recipes:
            return parse_schema_recipe(recipes[0])

    return None


def find_recipe_in_jsonld(data) -> list:
    """Recursively find Recipe objects in JSON-LD data."""
    results = []

    if isinstance(data, dict):
        schema_type = data.get("@type", "")
        if isinstance(schema_type, list):
            schema_type = " ".join(schema_type)

        if "Recipe" in schema_type:
            results.append(data)
        elif "@graph" in data:
            for item in data["@graph"]:
                results.extend(find_recipe_in_jsonld(item))
        else:
            for val in data.values():
                if isinstance(val, (dict, list)):
                    results.extend(find_recipe_in_jsonld(val))

    elif isinstance(data, list):
        for item in data:
            results.extend(find_recipe_in_jsonld(item))

    return results


def parse_schema_recipe(data: dict) -> dict:
    """Parse a Schema.org Recipe into our format."""
    name = data.get("name", "Untitled Recipe")

    # Parse times
    prep_time = parse_duration(data.get("prepTime"))
    cook_time = parse_duration(data.get("cookTime"))
    total_time = parse_duration(data.get("totalTime"))

    if not prep_time and not cook_time and total_time:
        cook_time = total_time

    # Parse servings
    servings = 4
    yield_val = data.get("recipeYield")
    if yield_val:
        if isinstance(yield_val, list):
            yield_val = yield_val[0]
        nums = re.findall(r"\d+", str(yield_val))
        if nums:
            servings = int(nums[0])

    # Parse ingredients
    ingredients = []
    for ing_str in data.get("recipeIngredient", []):
        parsed = parse_ingredient_string(ing_str)
        ingredients.append(parsed)

    # Parse instructions
    steps = []
    instructions = data.get("recipeInstructions", [])
    if isinstance(instructions, str):
        # Sometimes it's just a big string
        steps = [s.strip() for s in instructions.split("\n") if s.strip()]
    elif isinstance(instructions, list):
        for item in instructions:
            if isinstance(item, str):
                steps.append(item.strip())
            elif isinstance(item, dict):
                if item.get("@type") == "HowToSection":
                    for sub in item.get("itemListElement", []):
                        if isinstance(sub, dict):
                            steps.append(sub.get("text", "").strip())
                        elif isinstance(sub, str):
                            steps.append(sub.strip())
                else:
                    text = item.get("text", "").strip()
                    if text:
                        steps.append(text)

    # Parse tags / categories
    tags = []
    category = data.get("recipeCategory", [])
    if isinstance(category, str):
        category = [category]
    tags.extend([c.lower().strip() for c in category if c])

    cuisine = data.get("recipeCuisine", [])
    if isinstance(cuisine, str):
        cuisine = [cuisine]
    tags.extend([c.lower().strip() for c in cuisine if c])

    keywords = data.get("keywords", "")
    if isinstance(keywords, str):
        tags.extend([k.strip().lower() for k in keywords.split(",") if k.strip()])
    elif isinstance(keywords, list):
        tags.extend([k.lower().strip() for k in keywords if k])

    # Deduplicate tags
    tags = list(dict.fromkeys(tags))[:10]  # Keep max 10

    # Image
    image_url = None
    image = data.get("image")
    if isinstance(image, str):
        image_url = image
    elif isinstance(image, list) and image:
        image_url = image[0] if isinstance(image[0], str) else image[0].get("url")
    elif isinstance(image, dict):
        image_url = image.get("url")

    # Guess meal types from tags/name
    meal_types = guess_meal_types(name, tags)

    # Description as notes
    notes = data.get("description", "")
    if len(notes) > 300:
        notes = notes[:297] + "..."

    return {
        "name": name,
        "servings": servings,
        "prep_time": prep_time,
        "cook_time": cook_time,
        "tags": tags,
        "meal_types": meal_types,
        "ingredients": ingredients,
        "steps": steps,
        "notes": notes or None,
        "image_url": image_url,
        "created": datetime.now().isoformat(),
    }


def extract_microdata(soup: BeautifulSoup) -> dict | None:
    """Fallback: extract from HTML microdata attributes."""
    recipe_el = soup.find(itemtype=re.compile(r"schema\.org/Recipe", re.I))
    if not recipe_el:
        return None

    name = ""
    name_el = recipe_el.find(itemprop="name")
    if name_el:
        name = name_el.get_text(strip=True)

    ingredients = []
    for el in recipe_el.find_all(itemprop="recipeIngredient"):
        text = el.get_text(strip=True)
        if text:
            ingredients.append(parse_ingredient_string(text))

    steps = []
    for el in recipe_el.find_all(itemprop="recipeInstructions"):
        text = el.get_text(strip=True)
        if text:
            steps.append(text)

    if not name or not ingredients:
        return None

    image_el = recipe_el.find(itemprop="image")
    image_url = None
    if image_el:
        image_url = image_el.get("src") or image_el.get("content")

    return {
        "name": name,
        "servings": 4,
        "prep_time": None,
        "cook_time": None,
        "tags": [],
        "meal_types": guess_meal_types(name, []),
        "ingredients": ingredients,
        "steps": steps,
        "notes": None,
        "image_url": image_url,
        "created": datetime.now().isoformat(),
    }


def extract_meta(soup: BeautifulSoup, url: str) -> dict | None:
    """Last resort: get whatever we can from meta tags."""
    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title:
        title = og_title.get("content")
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

    if not title:
        return None

    image_url = None
    og_image = soup.find("meta", property="og:image")
    if og_image:
        image_url = og_image.get("content")

    desc = None
    og_desc = soup.find("meta", property="og:description")
    if og_desc:
        desc = og_desc.get("content")

    return {
        "name": title,
        "servings": 4,
        "prep_time": None,
        "cook_time": None,
        "tags": [],
        "meal_types": ["dinner"],
        "ingredients": [],
        "steps": [],
        "notes": f"Imported from {urlparse(url).netloc}. {desc or ''} Ingredients need manual entry.",
        "image_url": image_url,
        "created": datetime.now().isoformat(),
    }


# ─── Parsing Helpers ──────────────────────────────────────────────────────────

def parse_duration(iso_str) -> int | None:
    """Parse ISO 8601 duration (PT1H30M) to minutes."""
    if not iso_str:
        return None
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", str(iso_str))
    if not match:
        # Try plain number
        nums = re.findall(r"\d+", str(iso_str))
        return int(nums[0]) if nums else None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes if (hours or minutes) else None


def parse_ingredient_string(text: str) -> dict:
    """Parse a natural language ingredient string into structured data."""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)

    # Common fraction patterns: ½, ¼, ¾, ⅓, ⅔, 1/2, etc
    unicode_fracs = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 0.33, "⅔": 0.67,
                     "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875}

    qty = 0
    rest = text

    # Try to extract leading number(s)
    # Patterns: "1 1/2", "1½", "1/2", "1.5", "1"
    m = re.match(r"^(\d+)\s+(\d+/\d+)\s+(.*)", text)
    if m:
        qty = int(m.group(1)) + eval_fraction(m.group(2))
        rest = m.group(3)
    else:
        m = re.match(r"^(\d+)([½¼¾⅓⅔⅛⅜⅝⅞])\s+(.*)", text)
        if m:
            qty = int(m.group(1)) + unicode_fracs.get(m.group(2), 0)
            rest = m.group(3)
        else:
            m = re.match(r"^([½¼¾⅓⅔⅛⅜⅝⅞])\s+(.*)", text)
            if m:
                qty = unicode_fracs.get(m.group(1), 0)
                rest = m.group(2)
            else:
                m = re.match(r"^(\d+/\d+)\s+(.*)", text)
                if m:
                    qty = eval_fraction(m.group(1))
                    rest = m.group(2)
                else:
                    m = re.match(r"^(\d+\.?\d*)\s+(.*)", text)
                    if m:
                        qty = float(m.group(1))
                        rest = m.group(2)
                    else:
                        return {"qty": 1, "unit": "", "item": text}

    # Now extract unit from rest
    unit = ""
    known_units = [
        "tablespoons", "tablespoon", "tbsp", "tbs",
        "teaspoons", "teaspoon", "tsp",
        "cups", "cup",
        "ounces", "ounce", "oz",
        "pounds", "pound", "lbs", "lb",
        "cloves", "clove",
        "cans", "can",
        "slices", "slice",
        "pieces", "piece",
        "pinch", "pinches",
        "dash", "dashes",
        "bunch", "bunches",
        "head", "heads",
        "stalk", "stalks",
        "sprig", "sprigs",
        "large", "medium", "small",
        "whole",
        "quart", "quarts", "qt",
        "pint", "pints", "pt",
        "gallon", "gallons", "gal",
        "liter", "liters", "ml", "milliliters",
        "gram", "grams", "g", "kg", "kilogram",
        "package", "packages", "pkg",
        "container", "containers",
        "jar", "jars",
        "bottle", "bottles",
        "bag", "bags",
        "box", "boxes",
    ]

    UNIT_NORMALIZE = {
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
    }

    rest_words = rest.split()
    if rest_words:
        first = rest_words[0].lower().rstrip(".,")
        if first in known_units:
            unit = UNIT_NORMALIZE.get(first, first)
            rest = " ".join(rest_words[1:])

    # Clean up item name
    item = rest.strip().rstrip(".,")
    # Remove parenthetical notes for cleaner item names but keep them in mind
    item_clean = re.sub(r"\s*\(.*?\)\s*", " ", item).strip()

    if not item_clean:
        item_clean = item

    return {
        "qty": round(qty, 3) if qty else 1,
        "unit": unit,
        "item": item_clean,
    }


def eval_fraction(frac_str: str) -> float:
    """Safely evaluate a fraction string like '1/2'."""
    try:
        parts = frac_str.split("/")
        return float(parts[0]) / float(parts[1])
    except (ValueError, ZeroDivisionError, IndexError):
        return 0


def guess_meal_types(name: str, tags: list) -> list:
    """Guess meal types from recipe name and tags."""
    text = (name + " " + " ".join(tags)).lower()

    types = []
    breakfast_kw = ["breakfast", "pancake", "waffle", "omelette", "omelet",
                    "french toast", "eggs", "muffin", "smoothie", "granola",
                    "overnight oats", "cereal", "bacon and eggs"]
    lunch_kw = ["sandwich", "wrap", "salad", "soup", "lunch"]

    for kw in breakfast_kw:
        if kw in text:
            types.append("breakfast")
            break

    for kw in lunch_kw:
        if kw in text:
            types.append("lunch")
            break

    types.append("dinner")  # Almost everything can be dinner
    return list(dict.fromkeys(types))


def slugify(name: str) -> str:
    return name.lower().strip().replace(" ", "-").replace("'", "").replace('"', "")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🍽️  Recipe Scraper & Dietary Adapter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py scrape "https://www.allrecipes.com/recipe/24074/alysias-basic-meat-lasagna/"
  python scraper.py scrape "https://www.budgetbytes.com/one-pot-creamy-cajun-chicken-pasta/" --dairy-free
  python scraper.py scrape "https://..." --dairy-free --save
  python scraper.py bulk urls.txt --dairy-free --save
  python scraper.py check-dairy "shredded cheddar cheese"

Supported sites (any site with Schema.org Recipe data):
  allrecipes.com, budgetbytes.com, food.com, foodnetwork.com,
  simplyrecipes.com, seriouseats.com, epicurious.com, bonappetit.com,
  tasty.co, delish.com, cookinglight.com, myrecipes.com,
  minimalistbaker.com, pinchofyum.com, skinnytaste.com, and many more!
        """,
    )

    subparsers = parser.add_subparsers(dest="command")

    # Single URL scrape
    scrape_parser = subparsers.add_parser("scrape", help="Scrape a recipe from a URL")
    scrape_parser.add_argument("url", help="Recipe URL to scrape")
    scrape_parser.add_argument("--dairy-free", "-df", action="store_true",
                               help="Adapt recipe for lactose intolerance")
    scrape_parser.add_argument("--save", "-s", action="store_true",
                               help="Save to recipes/ directory")
    scrape_parser.add_argument("--json", "-j", action="store_true",
                               help="Output raw JSON")

    # Bulk import
    bulk_parser = subparsers.add_parser("bulk", help="Import multiple URLs from a file")
    bulk_parser.add_argument("file", help="Text file with one URL per line")
    bulk_parser.add_argument("--dairy-free", "-df", action="store_true")
    bulk_parser.add_argument("--save", "-s", action="store_true")

    # Check dairy
    check_parser = subparsers.add_parser("check-dairy", help="Check an ingredient for dairy")
    check_parser.add_argument("ingredient", help="Ingredient to check")

    args = parser.parse_args()

    if args.command == "scrape":
        recipe = scrape_recipe(args.url)
        if not recipe:
            sys.exit(1)

        if args.dairy_free:
            recipe = adapt_recipe_dairy_free(recipe)
            if recipe.get("dairy_subs"):
                print(f"\n  🥛 Dairy substitutions made:")
                for sub in recipe["dairy_subs"]:
                    print(f"     {sub['original']}  →  {sub['substitute']}")
                    print(f"       💡 {sub['note']}")

        if args.json:
            print(json.dumps(recipe, indent=2))
        else:
            print_recipe(recipe)

        if args.save:
            save_recipe(recipe)

    elif args.command == "bulk":
        # Bulk import
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"❌ File not found: {args.file}")
            sys.exit(1)

        urls = [line.strip() for line in filepath.read_text().splitlines() if line.strip() and not line.startswith("#")]
        print(f"📋 Found {len(urls)} URLs to scrape\n")

        success = 0
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}]", end="")
            recipe = scrape_recipe(url)
            if recipe:
                if args.dairy_free:
                    recipe = adapt_recipe_dairy_free(recipe)
                if args.save:
                    save_recipe(recipe)
                success += 1
            time.sleep(1)  # Be polite

        print(f"\n{'='*50}")
        print(f"✅ Successfully scraped {success}/{len(urls)} recipes")

    elif args.command == "check-dairy":
        ing = args.ingredient
        if is_dairy(ing):
            sub = get_dairy_substitute(ing)
            print(f"🥛 \"{ing}\" contains dairy!")
            if sub:
                print(f"   Substitute: {sub['sub']}")
                print(f"   Tip: {sub['note']}")
        else:
            print(f"✅ \"{ing}\" is dairy-free!")

    else:
        parser.print_help()


def print_recipe(recipe: dict):
    """Pretty print a recipe."""
    print(f"\n{'='*55}")
    print(f"  {recipe['name']}")
    print(f"{'='*55}")
    print(f"  Servings: {recipe['servings']}")

    times = []
    if recipe.get("prep_time"): times.append(f"Prep: {recipe['prep_time']}min")
    if recipe.get("cook_time"): times.append(f"Cook: {recipe['cook_time']}min")
    if times:
        total = (recipe.get("prep_time") or 0) + (recipe.get("cook_time") or 0)
        times.append(f"Total: {total}min")
        print(f"  {' | '.join(times)}")

    if recipe.get("tags"):
        print(f"  Tags: {', '.join(recipe['tags'][:8])}")

    if recipe.get("image_url"):
        print(f"  Image: {recipe['image_url'][:80]}...")

    if recipe.get("source_url"):
        print(f"  Source: {recipe['source_url']}")

    print(f"\n  🥕 Ingredients ({len(recipe.get('ingredients', []))}):")
    for ing in recipe.get("ingredients", []):
        qty = ing.get("qty", "")
        unit = f" {ing.get('unit', '')}" if ing.get("unit") else ""
        original = f"  (was: {ing['original']})" if ing.get("original") else ""
        print(f"     • {qty}{unit} {ing['item']}{original}")

    if recipe.get("steps"):
        print(f"\n  📋 Steps ({len(recipe['steps'])}):")
        for i, step in enumerate(recipe["steps"], 1):
            print(f"     {i}. {step[:120]}{'...' if len(step) > 120 else ''}")

    if recipe.get("notes"):
        print(f"\n  📝 {recipe['notes'][:200]}")

    print()


def save_recipe(recipe: dict):
    """Save recipe to the recipes directory."""
    slug = slugify(recipe["name"])
    filepath = RECIPES_DIR / f"{slug}.json"

    # Remove internal tracking fields before saving
    save_data = {k: v for k, v in recipe.items() if k != "dairy_subs"}

    with open(filepath, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"  💾 Saved: {filepath}")


if __name__ == "__main__":
    main()
