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
if sys.platform == "win32":
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

# Kroger API endpoints
KROGER_AUTH_URL = "https://api.kroger.com/v1/connect/oauth2/token"
KROGER_PRODUCTS_URL = "https://api.kroger.com/v1/products"
KROGER_LOCATIONS_URL = "https://api.kroger.com/v1/locations"
KROGER_CART_URL = "https://api.kroger.com/v1/cart/add"
KROGER_PROFILE_URL = "https://api.kroger.com/v1/identity/profile"

# API scopes needed (client credentials only supports product.compact)
KROGER_SCOPES = "product.compact"

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


def search_product(query: str, location_id: str = None):
    """Search for a product and get its price."""
    token = get_access_token()
    if not token:
        return None

    params = {
        "filter.term": query,
        "filter.limit": 5
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
            "fulfillment": fulfillment
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
    Add items to Kroger cart.

    Note: This requires user OAuth (not client credentials).
    User must authorize via browser flow first.

    items: list of {"upc": "...", "quantity": 1}
    """
    token = access_token or get_access_token()
    if not token:
        return False

    response = requests.put(
        KROGER_CART_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json={"items": items}
    )

    if response.status_code == 204:
        return True
    else:
        print(f"❌ Cart add failed: {response.status_code}")
        print(response.text)
        return False


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

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
