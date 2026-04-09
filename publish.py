#!/usr/bin/env python3
"""
Publish Meal Plan — Calendar Sync & Kroger Cart

One command to:
  1. Generate a smart meal plan (or use existing)
  2. Export ICS calendar → push to GitHub Pages
  3. Google Calendar & Skylight auto-sync from the URL
  4. Build Kroger cart → ready for pickup

Usage:
  python publish.py                    # Full flow: plan + calendar + push
  python publish.py --plan-only        # Just generate a new plan
  python publish.py --calendar-only    # Just re-export and push calendar
  python publish.py --kroger --zip 45202  # Build Kroger cart for pickup
  python publish.py --all --zip 45202  # Everything: plan + calendar + Kroger cart
"""

import sys
import io

if sys.platform == "win32":
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import argparse
import json
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent

# GitHub Pages URL (set after enabling Pages on your repo)
GITHUB_USER = "Tosterl"
GITHUB_REPO = "Meal-Planner-Grociery-List"
PAGES_URL = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}"
ICS_FILENAME = "meal-plan.ics"


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR)
    if check and result.returncode != 0:
        print(f"  ❌ Command failed: {' '.join(cmd)}")
        if result.stderr:
            print(f"     {result.stderr.strip()}")
        return result
    return result


def step_generate_plan(days: int = 7, strategy: str = "smart") -> dict | None:
    """Generate a new meal plan using planner.py."""
    print("\n📋 Generating meal plan...")
    print(f"   Strategy: {strategy} | Days: {days}")

    # Import planner functions directly
    sys.path.insert(0, str(BASE_DIR))
    from planner import generate_plan, list_recipes

    recipes = list_recipes()
    if not recipes:
        print("  ❌ No recipes found. Add some first: python planner.py add")
        return None

    plan = generate_plan(days=days, strategy=strategy)

    if plan:
        print(f"  ✅ Plan created: {plan['stats']['unique_recipes']} recipes, "
              f"{plan['stats']['leftover_meals']} leftover meals")
    return plan


def step_export_calendar(timezone: str = "America/New_York") -> Path | None:
    """Export the latest plan to ICS format."""
    print("\n📅 Exporting calendar...")

    sys.path.insert(0, str(BASE_DIR))
    from planner import load_latest_plan, export_calendar_ics

    plan = load_latest_plan()
    if not plan:
        print("  ❌ No meal plan found. Generate one first.")
        return None

    ics_path = BASE_DIR / ICS_FILENAME
    export_calendar_ics(plan, ics_path, timezone=timezone)
    print(f"  ✅ Calendar exported to {ics_path.name}")
    return ics_path


def step_push_to_github() -> bool:
    """Commit and push the ICS file to GitHub for Pages hosting."""
    print("\n🚀 Publishing to GitHub Pages...")

    # Check if there are changes to the ICS file
    result = run_cmd(["git", "status", "--porcelain", ICS_FILENAME], check=False)
    if not result.stdout.strip():
        print("  ℹ️  No calendar changes to push.")
        return True

    # Stage, commit, push
    run_cmd(["git", "add", ICS_FILENAME])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    run_cmd(["git", "commit", "-m", f"chore: Update meal plan calendar ({timestamp})"])
    result = run_cmd(["git", "push"], check=False)

    if result.returncode == 0:
        print(f"  ✅ Published!")
        return True
    else:
        print(f"  ❌ Push failed. You may need to run: git push")
        return False


def step_kroger_cart(zip_code: str) -> bool:
    """Build Kroger cart from grocery list — ready for pickup."""
    print(f"\n🛒 Building Kroger cart (zip: {zip_code})...")

    # Generate grocery list first
    sys.path.insert(0, str(BASE_DIR))
    from planner import load_latest_plan, generate_grocery_list, categorize_groceries, export_grocery_markdown

    plan = load_latest_plan()
    if not plan:
        print("  ❌ No meal plan found.")
        return False

    grocery = generate_grocery_list(plan)
    if not grocery:
        print("  ❌ Could not generate grocery list.")
        return False

    sections = categorize_groceries(grocery)
    export_grocery_markdown(grocery, sections, BASE_DIR / "plans" / "grocery_list.md")

    # Now build Kroger cart
    from kroger_api import find_nearest_store, build_grocery_cart, generate_shopping_list_by_aisle, export_cart_json

    store = find_nearest_store(zip_code)
    if not store:
        print(f"  ❌ No Kroger store found near {zip_code}")
        return False

    location_id = store.get("locationId")
    store_name = store.get("name", "Unknown")
    address = store.get("address", {})
    print(f"  📍 Store: {store_name}")
    print(f"     {address.get('addressLine1', '')}, {address.get('city', '')} {address.get('state', '')}\n")

    # Build cart from grocery items
    grocery_items = [{"item": item, "qty": 1} for item in grocery.keys()]
    cart_items = build_grocery_cart(grocery_items, location_id)

    if not cart_items:
        print("  ❌ Could not build cart.")
        return False

    # Show organized by aisle
    print("\n" + "=" * 50)
    generate_shopping_list_by_aisle(cart_items)

    # Export cart JSON
    cart_path = BASE_DIR / "kroger_cart.json"
    export_cart_json(cart_items, cart_path)

    # Summary
    found = [c for c in cart_items if not c.get("error")]
    total = sum(c.get("price", 0) * c.get("quantity", 1) for c in found)
    out_of_stock = [c for c in found if not c.get("in_stock", True)]

    print(f"\n{'=' * 50}")
    print(f"  🛒 Cart Summary")
    print(f"     Items found: {len(found)}/{len(cart_items)}")
    print(f"     Estimated total: ${total:.2f}")
    if out_of_stock:
        print(f"     ⚠️  Out of stock: {len(out_of_stock)} items")
        for item in out_of_stock:
            print(f"        • {item['search_term']}")
    print(f"\n  📦 Cart exported to: {cart_path.name}")
    print(f"     Open Kroger app → scan/add items for pickup!")

    return True


def print_subscribe_instructions():
    """Print calendar subscription URLs and setup instructions."""
    ics_url = f"{PAGES_URL}/{ICS_FILENAME}"

    print(f"\n{'=' * 60}")
    print(f"  📅 CALENDAR SUBSCRIPTION")
    print(f"{'=' * 60}")
    print(f"\n  Your meal plan URL:")
    print(f"  {ics_url}")
    print(f"\n  ┌─────────────────────────────────────────────────────┐")
    print(f"  │  GOOGLE CALENDAR                                    │")
    print(f"  ├─────────────────────────────────────────────────────┤")
    print(f"  │  1. Go to calendar.google.com                       │")
    print(f"  │  2. Click '+' next to 'Other calendars'             │")
    print(f"  │  3. Select 'From URL'                               │")
    print(f"  │  4. Paste the URL above                             │")
    print(f"  │  5. Click 'Add calendar'                            │")
    print(f"  │                                                     │")
    print(f"  │  ✅ Auto-refreshes every 6 hours!                   │")
    print(f"  └─────────────────────────────────────────────────────┘")
    print(f"\n  ┌─────────────────────────────────────────────────────┐")
    print(f"  │  SKYLIGHT CALENDAR                                  │")
    print(f"  ├─────────────────────────────────────────────────────┤")
    print(f"  │  Option A: Sync via Google Calendar (recommended)   │")
    print(f"  │  1. Subscribe in Google Calendar (above)            │")
    print(f"  │  2. In Skylight app → Settings → Calendars          │")
    print(f"  │  3. Connect your Google account                     │")
    print(f"  │  4. Enable 'Meal Plan' calendar                     │")
    print(f"  │                                                     │")
    print(f"  │  Option B: Direct ICS subscription                  │")
    print(f"  │  1. In Skylight app → Settings → Calendars          │")
    print(f"  │  2. Add calendar → 'Other' or 'ICS URL'            │")
    print(f"  │  3. Paste the URL above                             │")
    print(f"  └─────────────────────────────────────────────────────┘")
    print(f"\n  ┌─────────────────────────────────────────────────────┐")
    print(f"  │  APPLE / OUTLOOK                                    │")
    print(f"  ├─────────────────────────────────────────────────────┤")
    print(f"  │  Apple: Calendar → File → New Calendar Subscription │")
    print(f"  │  Outlook: Add calendar → From internet              │")
    print(f"  │  Paste the URL above.                               │")
    print(f"  └─────────────────────────────────────────────────────┘")
    print(f"\n  When you re-run 'python publish.py', the calendar")
    print(f"  updates automatically — no re-subscribing needed!\n")


def main():
    parser = argparse.ArgumentParser(
        description="Publish meal plan to calendar & Kroger cart",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python publish.py                     Generate plan + publish calendar
  python publish.py --kroger --zip 45202  Also build Kroger pickup cart
  python publish.py --all --zip 45202   Full flow: plan + calendar + Kroger
  python publish.py --calendar-only     Just re-push existing calendar
  python publish.py --days 5            Plan for 5 days instead of 7
        """,
    )
    parser.add_argument("--days", type=int, default=7, help="Days to plan (default: 7)")
    parser.add_argument("--strategy", default="smart", choices=["random", "variety", "smart"],
                        help="Planning strategy (default: smart)")
    parser.add_argument("--timezone", default="America/New_York",
                        help="Timezone for calendar events (default: America/New_York)")
    parser.add_argument("--plan-only", action="store_true", help="Only generate a meal plan")
    parser.add_argument("--calendar-only", action="store_true", help="Only export and push calendar")
    parser.add_argument("--kroger", action="store_true", help="Build Kroger cart for pickup")
    parser.add_argument("--zip", help="Zip code for Kroger store")
    parser.add_argument("--all", action="store_true", help="Full flow: plan + calendar + Kroger")
    parser.add_argument("--no-push", action="store_true", help="Skip pushing to GitHub")

    args = parser.parse_args()

    print("🍽️  Meal Planner — Publish")
    print("=" * 40)

    if args.all:
        args.kroger = True

    if args.kroger and not args.zip:
        print("❌ --zip is required for Kroger cart. Example: --zip 45202")
        sys.exit(1)

    # Step 1: Generate plan (unless calendar-only)
    if not args.calendar_only:
        plan = step_generate_plan(days=args.days, strategy=args.strategy)
        if not plan:
            sys.exit(1)

    if args.plan_only:
        print("\n✅ Done! Plan generated. Run without --plan-only to publish.")
        return

    # Step 2: Export calendar
    ics_path = step_export_calendar(timezone=args.timezone)
    if not ics_path:
        sys.exit(1)

    # Step 3: Push to GitHub Pages
    if not args.no_push:
        step_push_to_github()
        print_subscribe_instructions()
    else:
        print(f"\n  ℹ️  Skipped push. File ready at: {ics_path}")

    # Step 4: Kroger cart (optional)
    if args.kroger:
        step_kroger_cart(args.zip)

    print("\n✅ All done!")


if __name__ == "__main__":
    main()
