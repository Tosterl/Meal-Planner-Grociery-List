#!/usr/bin/env python3
"""
Kroger API Integration for Meal Planner
Get real-time prices from Kroger stores.

Setup:
1. Sign up at https://developer.kroger.com
2. Create an application to get CLIENT_ID and CLIENT_SECRET
3. Set environment variables or create a .env file:
   KROGER_CLIENT_ID=your_client_id
   KROGER_CLIENT_SECRET=your_client_secret

Usage:
  python kroger_api.py search "chicken breast"
  python kroger_api.py price "grocery_list.json"
  python kroger_api.py update-prices
"""

import os
import sys
import io
import json
import base64
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# Fix Windows console encoding
if sys.platform == "win32" and hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding', '') != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    import requests
except ImportError:
    print("❌ Please install requests: pip install requests")
    sys.exit(1)

# ─── Config ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CACHE_FILE = BASE_DIR / "kroger_cache.json"
TOKEN_FILE = BASE_DIR / ".kroger_token.json"
USER_TOKEN_FILE = BASE_DIR / ".kroger_user_token.json"
PANTRY_FILE = BASE_DIR / "pantry.json"
MATCH_OVERRIDES_FILE = BASE_DIR / "match_overrides.json"

# Kroger API endpoints
KROGER_AUTH_URL = "https://api.kroger.com/v1/connect/oauth2/token"
KROGER_AUTHORIZE_URL = "https://api.kroger.com/v1/connect/oauth2/authorize"
KROGER_PRODUCTS_URL = "https://api.kroger.com/v1/products"
KROGER_LOCATIONS_URL = "https://api.kroger.com/v1/locations"
KROGER_CART_URL = "https://api.kroger.com/v1/cart/add"
KROGER_PROFILE_URL = "https://api.kroger.com/v1/identity/profile"

# API scopes needed (client credentials only supports product.compact)
KROGER_SCOPES = "product.compact"
# User OAuth scopes for cart access
KROGER_USER_SCOPES = "product.compact cart.basic:write profile.compact"
# Default redirect URI for the local API server
KROGER_REDIRECT_URI = "http://localhost:8099/api/kroger/callback"

# Load credentials from environment or .env file
def load_credentials():
    """Load Kroger API credentials from environment or .env file."""
    client_id = os.environ.get("KROGER_CLIENT_ID")
    client_secret = os.environ.get("KROGER_CLIENT_SECRET")

    # Try .env file if not in environment
    env_file = BASE_DIR / ".env"
    if (not client_id or not client_secret) and env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("KROGER_CLIENT_ID="):
                    client_id = line.split("=", 1)[1].strip().strip('"\'')
                elif line.startswith("KROGER_CLIENT_SECRET="):
                    client_secret = line.split("=", 1)[1].strip().strip('"\'')

    return client_id, client_secret


def get_access_token():
    """Get OAuth2 access token from Kroger API."""
    client_id, client_secret = load_credentials()

    if not client_id or not client_secret:
        print("❌ Kroger API credentials not found!")
        print("\nTo set up Kroger API:")
        print("1. Go to https://developer.kroger.com")
        print("2. Create an account and register an application")
        print("3. Create a .env file in this directory with:")
        print("   KROGER_CLIENT_ID=your_client_id")
        print("   KROGER_CLIENT_SECRET=your_client_secret")
        return None

    # Check for cached token
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            token_data = json.load(f)
        expires = datetime.fromisoformat(token_data.get("expires_at", "2000-01-01"))
        if datetime.now() < expires:
            return token_data.get("access_token")

    # Get new token
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    response = requests.post(
        KROGER_AUTH_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}"
        },
        data={"grant_type": "client_credentials", "scope": KROGER_SCOPES}
    )

    if response.status_code != 200:
        print(f"❌ Failed to get access token: {response.status_code}")
        print(response.text)
        return None

    data = response.json()
    token = data.get("access_token")
    expires_in = data.get("expires_in", 1800)  # Default 30 min

    # Cache the token
    token_data = {
        "access_token": token,
        "expires_at": (datetime.now() + timedelta(seconds=expires_in - 60)).isoformat()
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f)

    return token


def build_authorize_url(redirect_uri: str = None, state: str = None):
    """Build the Kroger OAuth authorize URL for user login."""
    from urllib.parse import urlencode
    client_id, _ = load_credentials()
    if not client_id:
        return None
    params = {
        "scope": KROGER_USER_SCOPES,
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri or KROGER_REDIRECT_URI,
    }
    if state:
        params["state"] = state
    return f"{KROGER_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str, redirect_uri: str = None):
    """Exchange an authorization code for a user access token."""
    client_id, client_secret = load_credentials()
    if not client_id or not client_secret:
        return None

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    response = requests.post(
        KROGER_AUTH_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or KROGER_REDIRECT_URI,
        },
    )

    if response.status_code != 200:
        print(f"❌ Token exchange failed: {response.status_code} {response.text}")
        return None

    data = response.json()
    save_user_token(data)
    return data


def save_user_token(token_data: dict):
    """Persist the user OAuth token with an absolute expiry timestamp."""
    expires_in = token_data.get("expires_in", 1800)
    payload = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": (datetime.now() + timedelta(seconds=expires_in - 60)).isoformat(),
        "scope": token_data.get("scope", KROGER_USER_SCOPES),
    }
    with open(USER_TOKEN_FILE, "w") as f:
        json.dump(payload, f)
    return payload


def load_user_token():
    """Load saved user token data, or None if not connected."""
    if not USER_TOKEN_FILE.exists():
        return None
    try:
        with open(USER_TOKEN_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def refresh_user_token():
    """Refresh the user access token using the saved refresh token."""
    saved = load_user_token()
    if not saved or not saved.get("refresh_token"):
        return None

    client_id, client_secret = load_credentials()
    if not client_id or not client_secret:
        return None

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    response = requests.post(
        KROGER_AUTH_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": saved["refresh_token"],
        },
    )

    if response.status_code != 200:
        print(f"❌ Token refresh failed: {response.status_code} {response.text}")
        return None

    data = response.json()
    # Kroger may not return a new refresh_token — preserve the old one if missing
    if not data.get("refresh_token"):
        data["refresh_token"] = saved["refresh_token"]
    return save_user_token(data)


def get_user_access_token():
    """Get a valid user access token, refreshing if needed. Returns None if not connected."""
    saved = load_user_token()
    if not saved:
        return None
    try:
        expires = datetime.fromisoformat(saved.get("expires_at", "2000-01-01"))
    except ValueError:
        expires = datetime.min
    if datetime.now() < expires:
        return saved.get("access_token")
    refreshed = refresh_user_token()
    return refreshed.get("access_token") if refreshed else None


def disconnect_user():
    """Remove the saved user OAuth token (logout)."""
    if USER_TOKEN_FILE.exists():
        USER_TOKEN_FILE.unlink()
        return True
    return False


# ─── Match overrides (the "match-learning" feature) ──────────────────────────
# When the user swaps a Kroger product in the review modal, we save the
# ingredient → UPC mapping here so future runs auto-pin the same product.

def _override_key(ingredient: str) -> str:
    return (ingredient or "").strip().lower()


def load_match_overrides() -> dict:
    """Load the saved {ingredient: product_snapshot} mapping."""
    if not MATCH_OVERRIDES_FILE.exists():
        return {}
    try:
        with open(MATCH_OVERRIDES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_match_override(ingredient: str, product: dict) -> dict:
    """
    Save (or update) a learned match. `product` is a dict with at least 'upc';
    we store name/size/brand/image_url/price for fast UI rendering later.
    """
    key = _override_key(ingredient)
    if not key or not product or not product.get("upc"):
        return {}

    overrides = load_match_overrides()
    overrides[key] = {
        "upc": product["upc"],
        "name": product.get("name", ""),
        "brand": product.get("brand", ""),
        "size": product.get("size", ""),
        "image_url": product.get("image_url"),
        "price": product.get("price"),
        "saved_at": datetime.now().isoformat(),
    }
    with open(MATCH_OVERRIDES_FILE, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)
    return overrides[key]


def delete_match_override(ingredient: str) -> bool:
    """Remove a learned match. Returns True if something was deleted."""
    key = _override_key(ingredient)
    overrides = load_match_overrides()
    if key in overrides:
        del overrides[key]
        with open(MATCH_OVERRIDES_FILE, "w", encoding="utf-8") as f:
            json.dump(overrides, f, indent=2)
        return True
    return False


def get_match_override(ingredient: str) -> dict | None:
    """Look up a learned match for an ingredient (returns None if not saved)."""
    return load_match_overrides().get(_override_key(ingredient))


def find_nearest_store(zipcode: str = None):
    """Find the nearest Kroger store by zip code."""
    token = get_access_token()
    if not token:
        return None

    params = {"filter.limit": 1}
    if zipcode:
        params["filter.zipCode.near"] = zipcode

    response = requests.get(
        KROGER_LOCATIONS_URL,
        headers={"Authorization": f"Bearer {token}"},
        params=params
    )

    if response.status_code == 200:
        data = response.json()
        locations = data.get("data", [])
        if locations:
            return locations[0]

    return None


import re

# Words that are units, not what you'd search for
_UNIT_WORDS = {
    "tsp","tbsp","cup","cups","oz","ounce","ounces","lb","lbs","pound","pounds",
    "g","gram","grams","kg","ml","l","liter","liters","clove","cloves","slice",
    "slices","stalk","stalks","bunch","bunches","can","cans","jar","jars","pkg",
    "package","packages","head","heads","piece","pieces","pinch","pinches",
    "dash","dashes","stick","sticks","bag","bags","box","boxes","bottle","bottles",
    "small","medium","large","xlarge","mini","whole","fresh","dried","frozen",
}

# Descriptors that don't help product matching
_FILLER_WORDS = {
    "to","taste","optional","or","and","of","each","a","an","the","plus","more",
    "for","with","without","such","as","like","about","approximately",
}


# Common ingredients whose default Kroger search returns a wrong-category
# product. Map cleaned ingredient -> a more specific search term.
# Values are biased toward fresh produce / actual baking ingredients.
INGREDIENT_QUERY_OVERRIDES = {
    # Fresh produce — often beat by branded snack/sauce products
    "lemon":            "fresh lemon",
    "lemons":           "fresh lemons",
    "lime":             "fresh lime",
    "limes":            "fresh limes",
    "avocado":          "fresh avocado hass",
    "avocados":         "fresh avocados",
    "blueberries":      "fresh blueberries",
    "strawberries":     "fresh strawberries",
    "raspberries":      "fresh raspberries",
    "tomato":           "fresh tomato",
    "tomatoes":         "fresh tomatoes",
    "red bell pepper":  "fresh red bell pepper",
    "green bell pepper":"fresh green bell pepper",
    "bell pepper":      "fresh bell pepper",
    "onion":            "yellow onion",
    "yellow onion":     "yellow onion fresh",
    "spinach":          "fresh spinach",
    "lettuce":          "iceberg lettuce head",
    "carrot":           "carrots fresh",
    "carrots":          "carrots fresh",
    "celery":           "celery stalks",
    "potato":           "russet potato",
    "potatoes":         "russet potatoes",
    "garlic":           "fresh garlic bulb",
    "ginger":           "ginger root fresh",
    "fresh ginger":     "ginger root fresh",
    "fresh parsley":    "fresh parsley bunch",
    "parsley":          "fresh parsley",
    "cilantro":         "fresh cilantro",
    "basil":            "fresh basil",

    # Pantry — adjacent products often outrank the real one
    "honey":            "pure honey",
    "soy sauce":        "kikkoman soy sauce",
    "cornstarch":       "argo cornstarch",
    "cumin":            "ground cumin spice",
    "ground cumin":     "ground cumin spice",
    "cinnamon":         "ground cinnamon spice",
    "vanilla extract":  "pure vanilla extract",
    "baking soda":      "arm hammer baking soda",
    "baking powder":    "double acting baking powder",

    # Things that are easy to confuse
    "salsa":            "jar salsa",
    "rice":             "long grain rice",
    "white rice":       "long grain white rice",
    "milk":             "milk gallon",
    "butter":           "butter sticks salted",
    "unsalted butter":  "butter sticks unsalted",
    "eggs":             "large eggs grade a",
    "olive oil":        "extra virgin olive oil",
    "vegetable oil":    "vegetable oil",
    "sesame oil":       "toasted sesame oil",
}


def clean_ingredient_query(raw: str) -> str:
    """
    Turn a recipe ingredient string into a Kroger-search-friendly query.

    Examples:
      "1.5 lb chicken breast"             -> "chicken breast"
      "2 large flour tortillas"           -> "flour tortillas"
      "0.25 cup shredded cheddar cheese"  -> "shredded cheddar cheese"
      "1 (13.5oz) can coconut milk"       -> "coconut milk"
      "vegan butter (Earth Balance)"      -> "vegan butter Earth Balance"
      "boneless, skinless chicken breast" -> "boneless skinless chicken breast"
      "garlic, minced"                    -> "garlic"
    """
    if not raw:
        return ""

    s = str(raw).strip()

    # Strip parentheticals that contain digits (size hints) — keep brand parens
    s = re.sub(r"\([^)]*\d[^)]*\)", " ", s)
    # Convert remaining parentheticals to bare words ("(Earth Balance)" -> "Earth Balance")
    s = re.sub(r"[()]", " ", s)

    # Strip leading qty/fractions like "1.5", "1/2", "0.25"
    s = re.sub(r"^[\d\s\./]+", "", s)

    # Remove punctuation
    s = re.sub(r"[,;:]", " ", s)

    # Tokenize and drop unit/filler words
    tokens = [t for t in re.split(r"\s+", s) if t]
    cleaned = []
    for t in tokens:
        low = t.lower()
        # Drop standalone numbers
        if re.fullmatch(r"[\d\./]+", t):
            continue
        # Drop trailing-modifier participles common in recipes
        if low in _FILLER_WORDS:
            continue
        if low in _UNIT_WORDS:
            continue
        # Drop preparation verbs that confuse search ("minced", "chopped")
        if low in {"minced","chopped","diced","sliced","crushed","grated","cubed","peeled","cooked","raw"}:
            continue
        cleaned.append(t)

    result = " ".join(cleaned).strip()
    if not result:
        result = s.strip()

    # Override known problem ingredients with a more specific search term
    return INGREDIENT_QUERY_OVERRIDES.get(result.lower(), result)


# ─── Smart package-quantity math ──────────────────────────────────────────
# Convert any amount to a single base unit per family so we can compare
# "1.5 lb" needed vs "1 lb" package, or "3 cup" needed vs "1 gal" package.
import math as _math

_WEIGHT_OZ = {  # base: oz
    "oz": 1, "ounce": 1, "ounces": 1,
    "lb": 16, "lbs": 16, "pound": 16, "pounds": 16,
    "g": 0.0353, "gram": 0.0353, "grams": 0.0353,
    "kg": 35.274, "kilo": 35.274, "kilogram": 35.274,
}

_VOLUME_FLOZ = {  # base: fl oz
    "tsp": 0.1667, "teaspoon": 0.1667, "teaspoons": 0.1667,
    "tbsp": 0.5, "tablespoon": 0.5, "tablespoons": 0.5,
    "fl oz": 1, "floz": 1, "fl. oz.": 1, "fl. oz": 1, "fluid ounce": 1,
    "cup": 8, "cups": 8, "c": 8,
    "pint": 16, "pints": 16, "pt": 16,
    "quart": 32, "quarts": 32, "qt": 32,
    "gallon": 128, "gallons": 128, "gal": 128,
    "ml": 0.03381, "l": 33.814, "liter": 33.814, "liters": 33.814,
}

_COUNT = {  # base: count
    "": 1, "ct": 1, "count": 1, "each": 1, "ea": 1,
    "pkg": 1, "package": 1, "packages": 1,
    "dozen": 12,
    "slice": 1, "slices": 1,
    "piece": 1, "pieces": 1,
    "clove": 1, "cloves": 1,
    "stalk": 1, "stalks": 1,
    "head": 1, "heads": 1,
    "pk": 1, "pack": 1,
}


def _parse_amount(s):
    """Parse '8 slice' / '1.5 lb' / '0.5 cup' / '1/2 cup' into (qty, unit)."""
    if not s:
        return None, None
    s = str(s).strip().lower()
    # Match: optional whole number, optional fraction, optional unit
    m = re.match(r"^([\d]+(?:\.\d+)?)\s*(?:(\d+)\s*/\s*(\d+))?\s*(.*)?$", s)
    if not m:
        # Try pure fraction: "1/2 cup"
        m2 = re.match(r"^(\d+)\s*/\s*(\d+)\s*(.*)?$", s)
        if not m2:
            return None, None
        num, den, unit = m2.groups()
        try:
            qty = float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None, None
        return qty, (unit or "").strip()
    whole, num, den, unit = m.groups()
    try:
        qty = float(whole) if whole else 0.0
        if num and den:
            qty += float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        return None, None
    return qty, (unit or "").strip()


def _to_base(qty, unit):
    """Convert (qty, unit) to (base_value, family). Returns (None, None) if unit unknown."""
    u = (unit or "").strip().lower()
    if u in _WEIGHT_OZ:
        return qty * _WEIGHT_OZ[u], "weight"
    if u in _VOLUME_FLOZ:
        return qty * _VOLUME_FLOZ[u], "volume"
    if u in _COUNT:
        return qty * _COUNT[u], "count"
    return None, None


def compute_packages_needed(needed_str: str, package_size: str, ingredient: str = None, fallback: int = 1) -> int:
    """
    Compute Kroger package count needed. Delegates to the dedicated
    recipe_calculator module which handles cross-family conversions
    (e.g., "8 slice bacon" -> "12 oz package") via ingredient bridges.
    """
    from recipe_calculator import packages_needed
    return packages_needed(needed_str, package_size, ingredient=ingredient, fallback=fallback)


# ─── Category-based filtering ─────────────────────────────────────────────
# Kroger product responses include `categories` like ["Produce", "Fresh Fruit"].
# We use these to reject cross-department mismatches (e.g., conditioner
# returned for "cumin" because the brand name contains the word).

# Hard rule: these are NEVER food. Reject any food-ingredient match where the
# product has any of these categories. (Substring match, case-insensitive.)
NEVER_FOOD_CATEGORIES = {
    "personal care", "hair care", "skin care", "bath & body",
    "household", "automotive", "office", "school",
    "pet", "baby care", "diapers",
    "health & wellness", "vitamins", "medicine",
    "lawn & garden", "hardware", "outdoor",
    "alcohol", "wine", "beer", "spirits",  # not always wrong but never matches a recipe ingredient
    "tobacco",
    "floral",
}

# Per-ingredient expected category substrings. Match any -> rank boost.
# These are checked case-insensitively as substrings.
INGREDIENT_CATEGORY_HINTS = {
    # Produce
    "lemon": ["produce", "fruit", "citrus"],
    "lemons": ["produce", "fruit", "citrus"],
    "lime": ["produce", "fruit", "citrus"],
    "limes": ["produce", "fruit", "citrus"],
    "avocado": ["produce", "fruit"],
    "avocados": ["produce", "fruit"],
    "blueberries": ["produce", "fruit", "berries", "frozen fruit"],
    "strawberries": ["produce", "fruit", "berries"],
    "raspberries": ["produce", "fruit", "berries"],
    "tomato": ["produce", "vegetable"],
    "tomatoes": ["produce", "vegetable"],
    "red bell pepper": ["produce", "vegetable", "pepper"],
    "bell pepper": ["produce", "vegetable", "pepper"],
    "onion": ["produce", "vegetable"],
    "yellow onion": ["produce", "vegetable"],
    "garlic": ["produce", "vegetable"],
    "ginger": ["produce", "vegetable", "spice"],
    "fresh ginger": ["produce", "vegetable"],
    "spinach": ["produce", "vegetable", "salad"],
    "lettuce": ["produce", "vegetable", "salad"],
    "carrot": ["produce", "vegetable"],
    "carrots": ["produce", "vegetable"],
    "celery": ["produce", "vegetable"],
    "broccoli": ["produce", "vegetable", "frozen vegetable"],
    "broccoli florets": ["produce", "vegetable", "frozen vegetable"],
    "potato": ["produce", "vegetable"],
    "potatoes": ["produce", "vegetable"],
    "parsley": ["produce", "herbs"],
    "fresh parsley": ["produce", "herbs"],
    "cilantro": ["produce", "herbs"],
    "basil": ["produce", "herbs"],

    # Meat / Seafood
    "chicken": ["meat", "poultry"],
    "chicken breast": ["meat", "poultry"],
    "chicken thighs": ["meat", "poultry"],
    "ground beef": ["meat", "beef"],
    "beef": ["meat", "beef"],
    "steak": ["meat", "beef"],
    "bacon": ["meat", "bacon", "breakfast meat"],
    "pork": ["meat", "pork"],
    "ground pork": ["meat", "pork"],
    "sausage": ["meat", "sausage"],
    "salmon": ["seafood", "fish"],
    "shrimp": ["seafood"],
    "fish": ["seafood", "fish"],
    "turkey": ["meat", "poultry", "turkey"],

    # Dairy
    "milk": ["dairy", "milk"],
    "butter": ["dairy", "butter"],
    "cheese": ["dairy", "cheese"],
    "shredded cheddar cheese": ["dairy", "cheese"],
    "shredded cheese": ["dairy", "cheese"],
    "parmesan cheese": ["dairy", "cheese"],
    "cream cheese": ["dairy", "cheese"],
    "yogurt": ["dairy", "yogurt"],
    "greek yogurt": ["dairy", "yogurt"],
    "sour cream": ["dairy"],
    "heavy cream": ["dairy"],
    "eggs": ["dairy", "eggs"],
    "egg": ["dairy", "eggs"],

    # Pantry / cooking
    "olive oil": ["pantry", "oils", "cooking oil"],
    "vegetable oil": ["pantry", "oils", "cooking oil"],
    "sesame oil": ["pantry", "oils", "international"],
    "coconut oil": ["pantry", "oils"],
    "soy sauce": ["pantry", "international", "asian", "condiment"],
    "honey": ["pantry", "sweeteners", "honey"],
    "salsa": ["pantry", "sauce", "international", "condiment"],
    "vinegar": ["pantry", "vinegar"],
    "sugar": ["pantry", "baking", "sweeteners"],
    "brown sugar": ["pantry", "baking", "sweeteners"],
    "flour": ["pantry", "baking"],
    "all-purpose flour": ["pantry", "baking"],
    "cornstarch": ["pantry", "baking"],
    "baking soda": ["pantry", "baking"],
    "baking powder": ["pantry", "baking"],
    "vanilla extract": ["pantry", "baking"],

    # Spices
    "cumin": ["spices", "seasoning", "pantry"],
    "ground cumin": ["spices", "seasoning", "pantry"],
    "cinnamon": ["spices", "seasoning", "baking"],
    "chili powder": ["spices", "seasoning"],
    "garlic powder": ["spices", "seasoning"],
    "onion powder": ["spices", "seasoning"],
    "paprika": ["spices", "seasoning"],
    "oregano": ["spices", "seasoning", "herbs"],
    "thyme": ["spices", "seasoning", "herbs"],
    "rosemary": ["spices", "seasoning", "herbs"],
    "red pepper flakes": ["spices", "seasoning"],
    "black pepper": ["spices", "seasoning"],
    "salt": ["spices", "seasoning", "salt"],

    # Grains / bread
    "rice": ["pantry", "rice", "grains"],
    "jasmine rice": ["pantry", "rice"],
    "white rice": ["pantry", "rice"],
    "brown rice": ["pantry", "rice"],
    "pasta": ["pantry", "pasta"],
    "spaghetti": ["pantry", "pasta"],
    "noodles": ["pantry", "pasta", "international"],
    "rolled oats": ["breakfast", "cereal", "oats", "pantry"],
    "oats": ["breakfast", "cereal", "oats", "pantry"],
    "bread": ["bakery", "bread"],
    "tortillas": ["bakery", "bread", "tortilla", "international"],
    "large flour tortillas": ["bakery", "bread", "tortilla"],
    "small flour tortillas": ["bakery", "bread", "tortilla"],

    # Other
    "chia seeds": ["pantry", "baking", "health", "seeds"],
    "peanut butter": ["pantry"],
    "jam": ["pantry"],
    "broth": ["pantry", "soup", "broth"],
    "chicken broth": ["pantry", "soup", "broth"],
    "beef broth": ["pantry", "soup", "broth"],
}


def _category_score(ingredient: str, product_categories: list, product_name: str = "") -> int:
    """
    Score a product's category fit for an ingredient.
    Returns:
       -1000   hard-reject (never-food category)
        +N     boost score (matches expected category)
         0     neutral (unknown ingredient, or no match — leave Kroger ranking)
    """
    if not product_categories:
        return 0

    cats_lower = [c.lower() for c in product_categories]

    # Hard reject: any never-food category match (substring)
    for cat in cats_lower:
        for blocked in NEVER_FOOD_CATEGORIES:
            if blocked in cat:
                return -1000

    # Look up category hints for this ingredient
    key = (ingredient or "").lower().strip()
    hints = INGREDIENT_CATEGORY_HINTS.get(key)
    if not hints:
        # Try a shorter form (last 2 words) — handles "fresh chicken breast" -> "chicken breast"
        parts = key.split()
        for i in range(1, len(parts)):
            tail = " ".join(parts[i:])
            if tail in INGREDIENT_CATEGORY_HINTS:
                hints = INGREDIENT_CATEGORY_HINTS[tail]
                break
    if not hints:
        return 0

    # +1 per category hint matched (case-insensitive substring)
    score = 0
    for hint in hints:
        hint_l = hint.lower()
        for cat in cats_lower:
            if hint_l in cat:
                score += 2
                break
    return score


def search_alternatives(query: str, location_id: str = None, limit: int = 6):
    """
    Search for product matches with smart fallback for short results.
    Returns up to `limit` results, ranked by category fit > stock > pickup.
    Hard-mismatched categories (Personal Care for food, etc.) are dropped.
    """
    cleaned = clean_ingredient_query(query)
    products = search_product(cleaned, location_id) or []

    # If too few results, try a shorter query (drop adjectives)
    if len(products) < 3:
        tokens = cleaned.split()
        if len(tokens) > 2:
            short = " ".join(tokens[-2:])  # last two words usually the noun
            extra = search_product(short, location_id) or []
            seen_upcs = {p.get("upc") for p in products if p.get("upc")}
            for p in extra:
                if p.get("upc") and p["upc"] not in seen_upcs:
                    products.append(p)
                    seen_upcs.add(p["upc"])

    # Annotate each product with a category score, drop hard-rejects
    scored = []
    for p in products:
        score = _category_score(cleaned, p.get("categories") or [], p.get("name", ""))
        if score <= -1000:
            continue  # never-food category — drop entirely
        p["_category_score"] = score
        scored.append(p)

    # Rank: category fit (desc) > in-stock > pickup-eligible > Kroger order
    def rank(p):
        in_stock = p.get("stock_level") in ("HIGH", "LOW")
        pickup = (p.get("fulfillment") or {}).get("curbside") or (p.get("fulfillment") or {}).get("instore")
        return (
            -p.get("_category_score", 0),  # higher score first (negate for asc sort)
            0 if in_stock else 1,
            0 if pickup else 1,
        )

    scored.sort(key=rank)
    return scored[:limit]


def search_product(query: str, location_id: str = None):
    """Search for a product and get its price."""
    token = get_access_token()
    if not token:
        return None

    params = {
        "filter.term": query,
        "filter.limit": 20
    }
    if location_id:
        params["filter.locationId"] = location_id

    response = requests.get(
        KROGER_PRODUCTS_URL,
        headers={"Authorization": f"Bearer {token}"},
        params=params
    )

    if response.status_code != 200:
        print(f"❌ Search failed: {response.status_code}")
        return None

    data = response.json()
    products = data.get("data", [])

    results = []
    for product in products:
        name = product.get("description", "Unknown")
        brand = product.get("brand", "")

        # Get aisle locations (at product level per OpenAPI spec)
        aisle_locations = product.get("aisleLocations", [])
        aisle_info = None
        if aisle_locations:
            loc = aisle_locations[0]
            aisle_info = {
                "description": loc.get("description", "Unknown"),
                "number": loc.get("number"),
                "bay": loc.get("bayNumber"),
                "shelf": loc.get("shelfNumber"),
                "side": loc.get("side")
            }

        # Get price and inventory from items array
        items = product.get("items", [])
        price = None
        promo_price = None
        size = None
        stock_level = None
        fulfillment = {}

        if items:
            item = items[0]

            # Price info
            price_info = item.get("price", {})
            price = price_info.get("regular")
            promo_price = price_info.get("promo")
            size = item.get("size", "")

            # Inventory/stock level (HIGH, LOW, TEMPORARILY_OUT_OF_STOCK)
            inventory = item.get("inventory", {})
            stock_level = inventory.get("stockLevel")

            # Fulfillment options
            fulfill = item.get("fulfillment", {})
            fulfillment = {
                "instore": fulfill.get("instore", False),
                "curbside": fulfill.get("curbside", False),
                "delivery": fulfill.get("delivery", False),
                "shiptohome": fulfill.get("shiptohome", False)
            }

        # Get product image
        image_url = None
        images = product.get("images", [])
        for img in images:
            if img.get("perspective") == "front":
                sizes = img.get("sizes", [])
                # Prefer medium, fall back to small or thumbnail
                for preferred in ["medium", "small", "thumbnail", "large"]:
                    match = next((s for s in sizes if s.get("size") == preferred), None)
                    if match:
                        image_url = match.get("url")
                        break
                break

        # Categories tell us the product's department(s) — used to reject
        # cross-department mismatches (e.g., "Personal Care" hair product
        # for a food ingredient query). Kroger returns these as strings.
        raw_categories = product.get("categories", []) or []
        categories = []
        for c in raw_categories:
            if isinstance(c, str):
                categories.append(c)
            elif isinstance(c, dict):
                # Defensive — handle potential dict shape
                name_field = c.get("name") or c.get("description")
                if name_field:
                    categories.append(name_field)

        # Temperature controls (Refrigerated/Frozen/Ambient) — useful hint
        temperature = product.get("temperature", {})
        if isinstance(temperature, dict):
            temp_indicator = temperature.get("indicator")
        else:
            temp_indicator = None

        results.append({
            "name": name,
            "brand": brand,
            "price": promo_price or price,  # Use promo if available
            "regular_price": price,
            "promo_price": promo_price,
            "size": size,
            "product_id": product.get("productId"),
            "upc": product.get("upc"),
            "aisle": aisle_info,
            "stock_level": stock_level,
            "fulfillment": fulfillment,
            "image_url": image_url,
            "categories": categories,
            "temperature": temp_indicator,
            "product_page_uri": product.get("productPageURI"),
        })

    return results


def update_price_database(location_id: str = None):
    """Update the price cache with real Kroger prices."""
    # Common grocery items to price
    items_to_price = [
        "chicken breast", "ground beef", "ground turkey", "bacon", "eggs",
        "milk", "butter", "cheese cheddar", "sour cream", "cream cheese",
        "rice white", "pasta spaghetti", "olive oil", "vegetable oil",
        "onion yellow", "garlic", "tomatoes", "bell pepper", "jalapeno",
        "broccoli", "carrots", "potatoes", "frozen corn", "black beans",
        "flour", "sugar", "honey", "soy sauce", "sriracha",
        "tortillas flour", "oats", "bread"
    ]

    print("🛒 Fetching real Kroger prices...")
    print(f"   Searching {len(items_to_price)} items...\n")

    prices = {}
    promo_count = 0

    for item in items_to_price:
        results = search_product(item, location_id)
        if results and results[0].get("price"):
            best = results[0]

            # Check for promo pricing
            is_promo = (best.get("promo_price") and best.get("regular_price")
                       and best["promo_price"] < best["regular_price"])

            prices[item] = {
                "name": best["name"],
                "price": best["price"],
                "regular_price": best.get("regular_price"),
                "promo_price": best.get("promo_price"),
                "size": best["size"],
                "product_id": best.get("product_id"),
                "upc": best.get("upc"),
                "stock_level": best.get("stock_level"),
                "updated": datetime.now().isoformat()
            }

            # Display with promo indicator
            if is_promo:
                promo_count += 1
                print(f"   🏷️  {item}: ${best['promo_price']:.2f} (was ${best['regular_price']:.2f}) - {best['size']}")
            else:
                print(f"   ✅ {item}: ${best['price']:.2f} ({best['size']})")
        else:
            print(f"   ❌ {item}: not found")

    # Save to cache
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "updated": datetime.now().isoformat(),
            "location_id": location_id,
            "prices": prices
        }, f, indent=2)

    print(f"\n💾 Saved {len(prices)} prices to {CACHE_FILE.name}")
    if promo_count > 0:
        print(f"🏷️  Found {promo_count} items on sale!")
    return prices


def get_cached_prices():
    """Load cached Kroger prices."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return None


def get_product_location(product_id: str, location_id: str):
    """Get aisle location and stock info for a product at a specific store."""
    token = get_access_token()
    if not token:
        return None

    response = requests.get(
        f"{KROGER_PRODUCTS_URL}/{product_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"filter.locationId": location_id}
    )

    if response.status_code == 200:
        data = response.json().get("data", {})

        # Aisle locations are at product level (per OpenAPI spec)
        aisle_locations = data.get("aisleLocations", [])
        aisle_desc = "Unknown"
        aisle_details = None
        if aisle_locations:
            loc = aisle_locations[0]
            aisle_desc = loc.get("description", "Unknown")
            aisle_details = {
                "number": loc.get("number"),
                "bay": loc.get("bayNumber"),
                "shelf": loc.get("shelfNumber"),
                "side": loc.get("side")
            }

        # Stock level from items array
        items = data.get("items", [])
        stock_level = None
        in_stock = True
        fulfillment = {}

        if items:
            item = items[0]
            inventory = item.get("inventory", {})
            stock_level = inventory.get("stockLevel")

            # Consider in stock if HIGH or LOW, not if TEMPORARILY_OUT_OF_STOCK
            in_stock = stock_level in (None, "HIGH", "LOW")

            fulfill = item.get("fulfillment", {})
            fulfillment = {
                "instore": fulfill.get("instore", False),
                "curbside": fulfill.get("curbside", False),
                "delivery": fulfill.get("delivery", False),
                "shiptohome": fulfill.get("shiptohome", False)
            }

        return {
            "aisle": aisle_desc,
            "aisle_details": aisle_details,
            "stock_level": stock_level,
            "inStock": in_stock,
            "fulfillment": fulfillment
        }
    return None


def add_to_cart(items: list, access_token: str = None):
    """
    Add items to the authenticated user's Kroger cart.

    Requires a user OAuth token with the cart.basic:write scope.
    Returns (success: bool, error_message: str|None).

    items: list of {"upc": "...", "quantity": 1, "modality": "PICKUP"}
    """
    token = access_token or get_user_access_token()
    if not token:
        return False, "Not connected to a Kroger account. Click 'Connect Kroger' first."

    response = requests.put(
        KROGER_CART_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"items": items},
    )

    if response.status_code == 204:
        return True, None

    msg = f"Cart add failed: {response.status_code} {response.text}"
    print(f"❌ {msg}")
    return False, msg


def export_cart_json(cart_items: list, output_file: str = None):
    """
    Export cart items to JSON for Kroger Cart API.
    Returns list of {upc, quantity, modality} items ready for cart API.
    """
    cart_api_items = []

    for item in cart_items:
        if item.get("error") or not item.get("upc"):
            continue

        cart_api_items.append({
            "upc": item["upc"],
            "quantity": item.get("quantity", 1),
            "modality": "PICKUP"  # or "DELIVERY"
        })

    if output_file:
        output_path = Path(output_file)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "items": cart_api_items,
                "generated": datetime.now().isoformat(),
                "item_count": len(cart_api_items)
            }, f, indent=2)
        print(f"\n📦 Exported {len(cart_api_items)} items to {output_path.name}")

    return cart_api_items


def build_grocery_cart(grocery_list: list, location_id: str):
    """
    Build a cart-ready list from grocery items.
    Returns list of products with UPCs and aisle locations.
    """
    token = get_access_token()
    if not token:
        return None

    cart_items = []

    print("🛒 Building your Kroger cart...\n")

    for item in grocery_list:
        item_name = item.get("item", item) if isinstance(item, dict) else item
        qty = item.get("qty", 1) if isinstance(item, dict) else 1

        # search_product now returns aisle/stock info directly
        results = search_product(item_name, location_id)

        if results and results[0].get("price"):
            product = results[0]

            # Get aisle info from search result (already included)
            aisle_info = product.get("aisle")
            aisle_desc = aisle_info.get("description", "Unknown") if aisle_info else "Unknown"
            stock_level = product.get("stock_level")

            # Stock status emoji
            if stock_level == "HIGH":
                stock_emoji = "✅"
                stock_text = "In Stock"
            elif stock_level == "LOW":
                stock_emoji = "⚠️"
                stock_text = "Low Stock"
            elif stock_level == "TEMPORARILY_OUT_OF_STOCK":
                stock_emoji = "❌"
                stock_text = "Out of Stock"
            else:
                stock_emoji = "✅"
                stock_text = "Available"

            # Price display (show promo if different)
            price_display = f"${product['price']:.2f}"
            if product.get("promo_price") and product.get("regular_price"):
                if product["promo_price"] < product["regular_price"]:
                    price_display = f"${product['promo_price']:.2f} (was ${product['regular_price']:.2f})"

            cart_items.append({
                "search_term": item_name,
                "product_name": product["name"],
                "product_id": product["product_id"],
                "upc": product.get("upc"),
                "price": product["price"],
                "regular_price": product.get("regular_price"),
                "promo_price": product.get("promo_price"),
                "size": product["size"],
                "quantity": max(1, int(qty)),
                "aisle": aisle_desc,
                "aisle_details": aisle_info,
                "stock_level": stock_level,
                "in_stock": stock_level != "TEMPORARILY_OUT_OF_STOCK",
                "fulfillment": product.get("fulfillment", {})
            })

            print(f"  {stock_emoji} {item_name} ({stock_text})")
            print(f"     → {product['name'][:45]}...")
            print(f"     → {price_display} | {aisle_desc}\n")
        else:
            print(f"  ❌ {item_name} - not found\n")
            cart_items.append({
                "search_term": item_name,
                "product_name": None,
                "error": "Not found"
            })

    return cart_items


def generate_shopping_list_by_aisle(cart_items: list):
    """Organize shopping list by aisle for efficient shopping."""
    by_aisle = {}
    not_found = []
    out_of_stock = []

    for item in cart_items:
        if item.get("error"):
            not_found.append(item["search_term"])
            continue

        if item.get("stock_level") == "TEMPORARILY_OUT_OF_STOCK":
            out_of_stock.append(item["search_term"])

        aisle = item.get("aisle", "Unknown")
        if aisle not in by_aisle:
            by_aisle[aisle] = []
        by_aisle[aisle].append(item)

    # Print organized list
    print("\n" + "=" * 55)
    print("  🛒 SHOPPING LIST BY AISLE")
    print("=" * 55)

    total = 0
    savings = 0

    for aisle in sorted(by_aisle.keys()):
        print(f"\n📍 {aisle}")
        for item in by_aisle[aisle]:
            # Stock indicator
            stock = item.get("stock_level")
            if stock == "LOW":
                stock_icon = " ⚠️"
            elif stock == "TEMPORARILY_OUT_OF_STOCK":
                stock_icon = " ❌"
            else:
                stock_icon = ""

            print(f"   ☐ {item['product_name'][:40]}{stock_icon}")

            # Price with promo indicator
            item_total = item['price'] * item['quantity']
            price_str = f"${item['price']:.2f}"

            if item.get("promo_price") and item.get("regular_price"):
                if item["promo_price"] < item["regular_price"]:
                    saved = (item["regular_price"] - item["promo_price"]) * item['quantity']
                    savings += saved
                    price_str = f"${item['promo_price']:.2f} 🏷️ SALE"

            print(f"     {price_str} × {item['quantity']} = ${item_total:.2f}")
            total += item_total

    if out_of_stock:
        print(f"\n❌ Out of stock: {', '.join(out_of_stock)}")

    if not_found:
        print(f"\n⚠️  Not found: {', '.join(not_found)}")

    print(f"\n{'─' * 55}")
    if savings > 0:
        print(f"  🏷️  Sale Savings: -${savings:.2f}")
    print(f"  💰 Estimated Total: ${total:.2f}")
    print("=" * 55)

    return by_aisle, total


# ─── Pantry ───────────────────────────────────────────────────────────────────

def load_pantry() -> dict:
    """Load pantry from JSON file."""
    if PANTRY_FILE.exists():
        with open(PANTRY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"items": [], "updated": None}


def save_pantry(pantry: dict):
    """Save pantry to JSON file."""
    pantry["updated"] = datetime.now().isoformat()
    with open(PANTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(pantry, f, indent=2, ensure_ascii=False)


def pantry_search(query: str, zip_code: str):
    """Search Kroger for a product and let the user pick one to add to pantry."""
    store = find_nearest_store(zip_code)
    if not store:
        print(f"❌ No Kroger store found near {zip_code}")
        return

    location_id = store.get("locationId")
    store_name = store.get("name", "Unknown")
    print(f"\n📍 Store: {store_name}")
    print(f"🔍 Searching for: {query}\n")

    results = search_product(query, location_id)
    if not results:
        print(f"❌ No results for '{query}'")
        return

    # Display results
    for i, r in enumerate(results, 1):
        price_str = f"${r['price']:.2f}" if r.get("price") else "N/A"
        if r.get("promo_price") and r.get("regular_price") and r["promo_price"] < r["regular_price"]:
            price_str = f"${r['promo_price']:.2f} (was ${r['regular_price']:.2f}) 🏷️"

        stock = r.get("stock_level")
        stock_str = ""
        if stock == "HIGH": stock_str = "✅"
        elif stock == "LOW": stock_str = "⚠️ Low"
        elif stock == "TEMPORARILY_OUT_OF_STOCK": stock_str = "❌ Out"

        aisle = r.get("aisle")
        aisle_str = f" | 📍 {aisle['description']}" if aisle and aisle.get("description") else ""

        print(f"  [{i}] {r['name']}")
        print(f"      {r['brand']} | {r['size']} | {price_str} {stock_str}{aisle_str}")
        print()

    print(f"  [0] Cancel\n")

    try:
        choice = int(input("Pick a product to add to pantry: ").strip())
    except (ValueError, EOFError):
        print("❌ Cancelled")
        return

    if choice < 1 or choice > len(results):
        print("❌ Cancelled")
        return

    product = results[choice - 1]

    # Ask quantity
    try:
        qty_input = input(f"How many? (default: 1): ").strip()
        qty = int(qty_input) if qty_input else 1
    except (ValueError, EOFError):
        qty = 1

    # Build pantry item
    pantry_item = {
        "name": product["name"],
        "brand": product.get("brand", ""),
        "size": product.get("size", ""),
        "qty": qty,
        "price": product.get("price"),
        "regular_price": product.get("regular_price"),
        "promo_price": product.get("promo_price"),
        "product_id": product.get("product_id"),
        "upc": product.get("upc"),
        "aisle": product.get("aisle"),
        "stock_level": product.get("stock_level"),
        "store": store_name,
        "location_id": location_id,
        "added": datetime.now().isoformat()
    }

    pantry = load_pantry()

    # Check if already in pantry (by UPC)
    existing = next((i for i, item in enumerate(pantry["items"])
                     if item.get("upc") == pantry_item["upc"]), None)
    if existing is not None:
        pantry["items"][existing]["qty"] += qty
        print(f"\n✅ Updated quantity: {pantry['items'][existing]['name']} "
              f"(now {pantry['items'][existing]['qty']})")
    else:
        pantry["items"].append(pantry_item)
        print(f"\n✅ Added to pantry: {pantry_item['name']} × {qty}")

    save_pantry(pantry)
    print(f"   Saved to: {PANTRY_FILE.name}")


def pantry_list():
    """Display current pantry contents."""
    pantry = load_pantry()
    items = pantry.get("items", [])

    if not items:
        print("\n🥫 Your pantry is empty.")
        print("   Add items with: python kroger_api.py pantry-add \"item\" --zip YOUR_ZIP")
        return

    print(f"\n🥫 My Pantry ({len(items)} items)")
    if pantry.get("updated"):
        print(f"   Last updated: {pantry['updated'][:16].replace('T', ' ')}")
    print(f"{'─' * 55}")

    total_value = 0
    for i, item in enumerate(items, 1):
        price = item.get("price", 0) or 0
        item_total = price * item.get("qty", 1)
        total_value += item_total

        price_str = f"${price:.2f}" if price else "N/A"
        size_str = f" ({item['size']})" if item.get("size") else ""
        brand_str = f" — {item['brand']}" if item.get("brand") else ""

        aisle = item.get("aisle")
        aisle_str = f"  📍 {aisle['description']}" if aisle and aisle.get("description") else ""

        print(f"  [{i:2d}] {item['name'][:40]}{size_str}")
        print(f"       {item.get('qty', 1)}× | {price_str}{brand_str}{aisle_str}")

    print(f"\n{'─' * 55}")
    print(f"  🥫 {len(items)} items | Estimated value: ${total_value:.2f}")


def pantry_remove(index: int):
    """Remove an item from pantry by its list number."""
    pantry = load_pantry()
    items = pantry.get("items", [])

    if index < 1 or index > len(items):
        print(f"❌ Invalid item number. Use 1-{len(items)}")
        return

    removed = items.pop(index - 1)
    save_pantry(pantry)
    print(f"✅ Removed: {removed['name']}")


def pantry_clear():
    """Clear entire pantry."""
    pantry = {"items": [], "updated": datetime.now().isoformat()}
    save_pantry(pantry)
    print("✅ Pantry cleared.")


# ─── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="🛒 Kroger API Price Lookup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python kroger_api.py setup              Interactive setup wizard
  python kroger_api.py search "chicken"   Search for products
  python kroger_api.py update             Update price cache
  python kroger_api.py show               Show cached prices
  python kroger_api.py pantry-add "milk" --zip 45202  Search & add to pantry
  python kroger_api.py pantry             Show pantry contents
  python kroger_api.py pantry-remove 3    Remove item #3 from pantry
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # setup
    subparsers.add_parser("setup", help="Interactive setup wizard")

    # search
    search_parser = subparsers.add_parser("search", help="Search for a product")
    search_parser.add_argument("query", help="Product to search for")
    search_parser.add_argument("--zip", help="Zip code for store location")

    # update
    update_parser = subparsers.add_parser("update", help="Update price cache")
    update_parser.add_argument("--zip", help="Zip code for store location")

    # show
    subparsers.add_parser("show", help="Show cached prices")

    # cart - build shopping cart from meal plan
    cart_parser = subparsers.add_parser("cart", help="Build shopping cart from grocery list")
    cart_parser.add_argument("--zip", required=True, help="Zip code for store location")
    cart_parser.add_argument("--plan", help="Path to meal plan JSON (default: latest)")

    # aisles - show shopping list organized by aisle
    aisle_parser = subparsers.add_parser("aisles", help="Get aisle locations for grocery list")
    aisle_parser.add_argument("--zip", required=True, help="Zip code for store location")
    aisle_parser.add_argument("--export", help="Export cart JSON file for Kroger API")

    # pantry-add - search Kroger and add to pantry
    pantry_add_parser = subparsers.add_parser("pantry-add", help="Search Kroger and add product to pantry")
    pantry_add_parser.add_argument("query", help="Product to search for")
    pantry_add_parser.add_argument("--zip", required=True, help="Zip code for store location")

    # pantry - show pantry contents
    subparsers.add_parser("pantry", help="Show pantry contents")

    # pantry-remove - remove item from pantry
    pantry_rm_parser = subparsers.add_parser("pantry-remove", help="Remove item from pantry by number")
    pantry_rm_parser.add_argument("number", type=int, help="Item number (from pantry list)")

    # pantry-clear - clear all pantry items
    subparsers.add_parser("pantry-clear", help="Clear entire pantry")

    args = parser.parse_args()

    if args.command == "setup":
        print("\n🛒 Kroger API Setup Wizard")
        print("=" * 40)
        print("\n1. Go to https://developer.kroger.com")
        print("2. Click 'Sign Up' and create an account")
        print("3. Go to 'My Applications' and create a new app")
        print("4. Copy your Client ID and Client Secret\n")

        client_id = input("Enter Client ID: ").strip()
        client_secret = input("Enter Client Secret: ").strip()

        if client_id and client_secret:
            env_file = BASE_DIR / ".env"
            with open(env_file, "w") as f:
                f.write(f'KROGER_CLIENT_ID="{client_id}"\n')
                f.write(f'KROGER_CLIENT_SECRET="{client_secret}"\n')
            print(f"\n✅ Credentials saved to {env_file}")
            print("   Run 'python kroger_api.py update' to fetch prices!")
        else:
            print("❌ Setup cancelled")

    elif args.command == "search":
        location_id = None
        if args.zip:
            store = find_nearest_store(args.zip)
            if store:
                location_id = store.get("locationId")
                print(f"📍 Using store: {store.get('name', 'Unknown')}\n")

        results = search_product(args.query, location_id)
        if results:
            print(f"🔍 Results for '{args.query}':\n")
            for r in results:
                # Price display
                if r.get('promo_price') and r.get('regular_price') and r['promo_price'] < r['regular_price']:
                    price = f"${r['promo_price']:.2f} (was ${r['regular_price']:.2f}) 🏷️"
                elif r.get('price'):
                    price = f"${r['price']:.2f}"
                else:
                    price = "N/A"

                # Stock display
                stock = r.get('stock_level')
                if stock == "HIGH":
                    stock_str = "✅ In Stock"
                elif stock == "LOW":
                    stock_str = "⚠️ Low Stock"
                elif stock == "TEMPORARILY_OUT_OF_STOCK":
                    stock_str = "❌ Out of Stock"
                else:
                    stock_str = ""

                # Aisle display
                aisle = r.get('aisle')
                aisle_str = aisle.get('description', '') if aisle else ''

                print(f"  • {r['name']}")
                print(f"    {r['brand']} | {price} | {r['size']}")
                if aisle_str:
                    print(f"    📍 {aisle_str}")
                if stock_str:
                    print(f"    {stock_str}")
                print()
        else:
            print(f"❌ No results for '{args.query}'")

    elif args.command == "update":
        location_id = None
        if args.zip:
            store = find_nearest_store(args.zip)
            if store:
                location_id = store.get("locationId")
                print(f"📍 Using store: {store.get('name', 'Unknown')}\n")

        update_price_database(location_id)

    elif args.command == "show":
        cache = get_cached_prices()
        if cache:
            print(f"\n🛒 Cached Kroger Prices")
            print(f"   Updated: {cache.get('updated', 'Unknown')}\n")
            for item, data in cache.get("prices", {}).items():
                print(f"  • {item}: ${data['price']:.2f} ({data['size']})")
        else:
            print("❌ No cached prices. Run 'python kroger_api.py update' first.")

    elif args.command == "cart" or args.command == "aisles":
        # Find store
        store = find_nearest_store(args.zip)
        if not store:
            print("❌ Could not find a Kroger store near that zip code")
            sys.exit(1)

        location_id = store.get("locationId")
        print(f"📍 Store: {store.get('name', 'Unknown')}")
        print(f"   {store.get('address', {}).get('addressLine1', '')}")
        print(f"   {store.get('address', {}).get('city', '')}, {store.get('address', {}).get('state', '')}\n")

        # Load grocery list from latest plan
        plans_dir = BASE_DIR / "plans"
        grocery_file = plans_dir / "grocery_list.md"

        if not grocery_file.exists():
            print("❌ No grocery list found. Generate one with: python planner.py grocery")
            sys.exit(1)

        # Parse grocery list from markdown
        grocery_items = []
        with open(grocery_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("- [ ]"):
                    # Format: "- [ ] Item Name — quantity"
                    item_part = line[5:].strip()
                    if " — " in item_part:
                        item_name = item_part.split(" — ")[0].strip()
                    else:
                        item_name = item_part
                    grocery_items.append(item_name.lower())

        if not grocery_items:
            print("❌ Grocery list is empty")
            sys.exit(1)

        print(f"📋 Found {len(grocery_items)} items in grocery list\n")

        # Build cart with aisle locations
        cart_items = build_grocery_cart(
            [{"item": item, "qty": 1} for item in grocery_items[:20]],  # Limit to 20 for demo
            location_id
        )

        # Show organized by aisle
        generate_shopping_list_by_aisle(cart_items)

        # Export cart if requested
        if hasattr(args, 'export') and args.export:
            export_cart_json(cart_items, args.export)
        else:
            # Always save to default location
            export_cart_json(cart_items, BASE_DIR / "kroger_cart.json")

    elif args.command == "pantry-add":
        pantry_search(args.query, args.zip)

    elif args.command == "pantry":
        pantry_list()

    elif args.command == "pantry-remove":
        pantry_remove(args.number)

    elif args.command == "pantry-clear":
        if input("Clear entire pantry? (y/n): ").strip().lower() == "y":
            pantry_clear()
        else:
            print("❌ Cancelled")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
