#!/usr/bin/env python3
"""
Local API Server — bridges the web UI to Kroger API.

Run this, then open index-pro.html. The Pantry tab can search Kroger
products directly in the browser.

Usage:
  python api_server.py                  # Start on port 8099
  python api_server.py --port 9000      # Custom port
  python api_server.py --zip 45202      # Set default store zip
"""

import sys
import io
import json
import argparse
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from datetime import datetime, timedelta

# Set UTF-8 encoding for Windows console
if sys.platform == "win32" and hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding', '') != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from kroger_api import (
    search_product, find_nearest_store, load_pantry, save_pantry,
    get_access_token
)

# Default store location (set via --zip)
DEFAULT_ZIP = None
CACHED_LOCATION_ID = None
CACHED_STORE_NAME = None


def get_location_id(zip_code=None):
    """Get and cache the store location ID."""
    global CACHED_LOCATION_ID, CACHED_STORE_NAME
    zc = zip_code or DEFAULT_ZIP
    if CACHED_LOCATION_ID and not zip_code:
        return CACHED_LOCATION_ID
    if zc:
        store = find_nearest_store(zc)
        if store:
            CACHED_LOCATION_ID = store.get("locationId")
            CACHED_STORE_NAME = store.get("name", "Unknown")
            return CACHED_LOCATION_ID
    return None


class KrogerAPIHandler(BaseHTTPRequestHandler):
    """Handle API requests from the web UI."""

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _error(self, msg, status=400):
        self._json_response({"error": msg}, status)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/search":
            self._handle_search(params)
        elif path == "/api/pantry":
            self._handle_pantry_get()
        elif path == "/api/plan":
            self._handle_plan_get()
        elif path == "/api/recipes":
            self._handle_recipes_get()
        elif path == "/api/userdata":
            self._handle_userdata_get()
        elif path == "/api/store":
            self._handle_store(params)
        elif path == "/api/health":
            self._json_response({"status": "ok", "store": CACHED_STORE_NAME})
        else:
            self._error("Not found", 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""

        if path == "/api/pantry":
            self._handle_pantry_add(body)
        elif path == "/api/store":
            self._handle_store_set(body)
        elif path == "/api/publish":
            self._handle_publish(body)
        elif path == "/api/userdata":
            self._handle_userdata_save(body)
        else:
            self._error("Not found", 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/pantry":
            self._handle_pantry_remove(params)
        else:
            self._error("Not found", 404)

    def _handle_search(self, params):
        """Search Kroger products."""
        query = params.get("q", [""])[0]
        if not query:
            self._error("Missing query parameter 'q'")
            return

        zip_code = params.get("zip", [None])[0]
        location_id = get_location_id(zip_code)

        results = search_product(query, location_id)
        if results is None:
            self._error("Kroger API error — check your credentials", 502)
            return

        # Add image URLs from Kroger product data if available
        self._json_response({
            "results": results,
            "store": CACHED_STORE_NAME,
            "query": query
        })

    def _handle_pantry_get(self):
        """Get current pantry contents."""
        pantry = load_pantry()
        self._json_response(pantry)

    def _handle_pantry_add(self, body):
        """Add a product to the pantry."""
        try:
            item = json.loads(body)
        except json.JSONDecodeError:
            self._error("Invalid JSON")
            return

        if not item.get("name"):
            self._error("Missing product name")
            return

        pantry = load_pantry()

        # Check for existing item by UPC
        existing = next(
            (i for i, p in enumerate(pantry["items"]) if p.get("upc") == item.get("upc")),
            None
        )

        if existing is not None:
            pantry["items"][existing]["qty"] = pantry["items"][existing].get("qty", 1) + item.get("qty", 1)
        else:
            from datetime import datetime
            item["added"] = datetime.now().isoformat()
            item["store"] = CACHED_STORE_NAME
            pantry["items"].append(item)

        save_pantry(pantry)
        self._json_response({"ok": True, "count": len(pantry["items"])})

    def _handle_pantry_remove(self, params):
        """Remove an item from pantry by index."""
        try:
            index = int(params.get("index", ["-1"])[0])
        except ValueError:
            self._error("Invalid index")
            return

        pantry = load_pantry()
        if index < 0 or index >= len(pantry["items"]):
            self._error("Index out of range")
            return

        removed = pantry["items"].pop(index)
        save_pantry(pantry)
        self._json_response({"ok": True, "removed": removed["name"]})

    def _handle_store(self, params):
        """Get current store info."""
        self._json_response({
            "store": CACHED_STORE_NAME,
            "location_id": CACHED_LOCATION_ID,
            "zip": DEFAULT_ZIP
        })

    def _handle_store_set(self, body):
        """Set the store zip code."""
        global DEFAULT_ZIP, CACHED_LOCATION_ID, CACHED_STORE_NAME
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._error("Invalid JSON")
            return

        zip_code = data.get("zip")
        if not zip_code:
            self._error("Missing zip code")
            return

        DEFAULT_ZIP = zip_code
        CACHED_LOCATION_ID = None
        CACHED_STORE_NAME = None
        location_id = get_location_id(zip_code)

        if location_id:
            self._json_response({"ok": True, "store": CACHED_STORE_NAME})
        else:
            self._error(f"No Kroger store found near {zip_code}")

    def _handle_plan_get(self):
        """Return the latest plan converted to UI format, plus metadata."""
        plans_dir = BASE_DIR / "plans"
        plans = sorted(plans_dir.glob("plan_*.json"), reverse=True) if plans_dir.exists() else []

        if not plans:
            self._json_response({"plan": {}, "source": None, "message": "No plans found"})
            return

        with open(plans[0], encoding="utf-8") as f:
            plan_data = json.load(f)

        # Convert Python format to UI format { "2026-04-13-breakfast": "Recipe Name" }
        ui_plan = {}
        created = plan_data.get("created", "")
        try:
            start_date = datetime.fromisoformat(created.split("T")[0])
        except (ValueError, IndexError):
            start_date = datetime.now()

        # Find the Monday of that week
        days_since_monday = start_date.weekday()
        start_monday = start_date - timedelta(days=days_since_monday)

        for i, day in enumerate(plan_data.get("days", [])):
            current_date = start_monday + timedelta(days=i)
            date_str = current_date.strftime("%Y-%m-%d")
            for meal, recipe_data in day.get("meals", {}).items():
                recipe_name = recipe_data["name"] if isinstance(recipe_data, dict) else recipe_data
                ui_plan[f"{date_str}-{meal}"] = recipe_name

        self._json_response({
            "plan": ui_plan,
            "source": plans[0].name,
            "created": created
        })

    def _handle_recipes_get(self):
        """Return all recipes from the recipes folder."""
        recipes_dir = BASE_DIR / "recipes"
        recipes = {}
        if recipes_dir.exists():
            for recipe_file in recipes_dir.glob("*.json"):
                try:
                    with open(recipe_file, encoding="utf-8") as f:
                        recipe = json.load(f)
                    slug = recipe_file.stem
                    recipes[slug] = recipe
                except (json.JSONDecodeError, IOError):
                    continue
        self._json_response({"recipes": recipes, "count": len(recipes)})

    def _handle_userdata_get(self):
        """Return saved user data (weight log, macro goals, ratings, favorites, etc.)."""
        userdata_path = BASE_DIR / "userdata.json"
        if userdata_path.exists():
            try:
                with open(userdata_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._json_response(data)
            except (json.JSONDecodeError, IOError) as e:
                self._error(f"Failed to read userdata: {e}", 500)
        else:
            self._json_response({})

    def _handle_userdata_save(self, body):
        """Save user data to userdata.json and push to git."""
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._error("Invalid JSON")
            return

        if not isinstance(data, dict):
            self._error("Userdata must be an object")
            return

        # Add metadata
        data["_updated"] = datetime.now().isoformat()

        userdata_path = BASE_DIR / "userdata.json"

        # Read existing to compare
        existing = {}
        if userdata_path.exists():
            try:
                with open(userdata_path, encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        # Compare ignoring metadata
        existing_compare = {k: v for k, v in existing.items() if not k.startswith("_")}
        new_compare = {k: v for k, v in data.items() if not k.startswith("_")}

        if existing_compare == new_compare:
            self._json_response({"ok": True, "message": "No changes", "changed": False})
            return

        # Write file
        with open(userdata_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Git add, commit, push (silent)
        try:
            subprocess.run(["git", "add", "userdata.json"],
                           cwd=str(BASE_DIR), check=True, capture_output=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            subprocess.run(["git", "commit", "-m", f"chore: Update user data ({timestamp})"],
                           cwd=str(BASE_DIR), check=True, capture_output=True)
            result = subprocess.run(["git", "push"],
                                    cwd=str(BASE_DIR), capture_output=True, text=True)
            if result.returncode == 0:
                self._json_response({"ok": True, "message": "Saved and pushed", "changed": True})
            else:
                self._json_response({"ok": True, "message": "Saved locally, push failed", "changed": True, "push_error": result.stderr})
        except FileNotFoundError:
            self._json_response({"ok": True, "message": "Saved locally, git not available", "changed": True})
        except subprocess.CalledProcessError:
            self._json_response({"ok": True, "message": "Saved locally", "changed": True})

    def _handle_publish(self, body):
        """Receive plan from UI, save as plan JSON, regenerate ICS, push to GitHub."""
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._error("Invalid JSON")
            return

        ui_plan = data.get("plan", {})
        if not ui_plan:
            self._error("No plan data provided")
            return

        # Convert UI format { "2026-04-13-breakfast": "Recipe Name" }
        # to Python format { days: [{ day: "Monday", meals: { breakfast: { name: "..." } } }] }
        date_meals = {}  # { "2026-04-13": { "breakfast": "Name", ... } }
        for key, recipe_name in ui_plan.items():
            parts = key.rsplit("-", 1)
            if len(parts) != 2:
                continue
            date_str, meal = parts[0], parts[1]
            if meal not in ("breakfast", "lunch", "dinner"):
                continue
            if date_str not in date_meals:
                date_meals[date_str] = {}
            date_meals[date_str][meal] = recipe_name

        if not date_meals:
            self._error("No valid meals found in plan")
            return

        # Sort dates and build plan
        sorted_dates = sorted(date_meals.keys())
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        days = []
        for date_str in sorted_dates:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                day_name = day_names[dt.weekday()]
            except ValueError:
                day_name = "Unknown"

            meals = {}
            for meal, recipe_name in date_meals[date_str].items():
                is_leftover = "(leftover)" in recipe_name
                meals[meal] = {
                    "name": recipe_name,
                    "servings": 1 if is_leftover else 4,
                    **({"is_leftover": True} if is_leftover else {})
                }
            days.append({"day": day_name, "meals": meals})

        plan = {
            "created": datetime.now().isoformat(),
            "days": days
        }

        # Save plan JSON
        plans_dir = BASE_DIR / "plans"
        plans_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        plan_path = plans_dir / f"plan_{timestamp}.json"
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
        print(f"  📋 Plan saved: {plan_path.name}")

        # Generate ICS
        try:
            sys.path.insert(0, str(BASE_DIR))
            from planner import export_calendar_ics
            ics_path = BASE_DIR / "meal-plan.ics"
            export_calendar_ics(plan, ics_path)
            print(f"  📅 Calendar updated: {ics_path.name}")
        except Exception as e:
            self._error(f"Failed to generate calendar: {str(e)}", 500)
            return

        # Git add, commit, push
        try:
            subprocess.run(["git", "add", "meal-plan.ics", str(plan_path)],
                           cwd=str(BASE_DIR), check=True, capture_output=True)
            commit_msg = f"chore: Update meal plan calendar ({timestamp})"
            subprocess.run(["git", "commit", "-m", commit_msg],
                           cwd=str(BASE_DIR), check=True, capture_output=True)
            result = subprocess.run(["git", "push"],
                                    cwd=str(BASE_DIR), capture_output=True, text=True)
            if result.returncode == 0:
                print(f"  🚀 Pushed to GitHub!")
                self._json_response({
                    "ok": True,
                    "message": "Calendar published! Skylight will update within a few hours.",
                    "plan_file": plan_path.name,
                    "ics_file": "meal-plan.ics"
                })
            else:
                print(f"  ⚠️  Push failed: {result.stderr}")
                self._json_response({
                    "ok": True,
                    "message": "Calendar generated but push failed. Run 'git push' manually.",
                    "plan_file": plan_path.name,
                    "push_error": result.stderr
                })
        except FileNotFoundError:
            self._json_response({
                "ok": True,
                "message": "Calendar generated but git not found. Push manually.",
                "plan_file": plan_path.name
            })
        except subprocess.CalledProcessError as e:
            # Commit may fail if nothing changed
            self._json_response({
                "ok": True,
                "message": "Calendar generated. No changes to push.",
                "plan_file": plan_path.name
            })

    def log_message(self, format, *args):
        """Quieter logging."""
        msg = format % args
        if "OPTIONS" not in msg:  # Skip CORS preflight noise
            sys.stderr.write(f"  {msg}\n")


def main():
    parser = argparse.ArgumentParser(description="Local Kroger API bridge for Meal Planner")
    parser.add_argument("--port", type=int, default=8099, help="Port to run on (default: 8099)")
    parser.add_argument("--zip", help="Default zip code for Kroger store")
    args = parser.parse_args()

    global DEFAULT_ZIP
    DEFAULT_ZIP = args.zip

    # Pre-check Kroger credentials (optional — server works without them for sync/publish)
    token = get_access_token()
    if not token:
        print("\n⚠️  Kroger API credentials not found — Kroger search disabled.")
        print("   To enable: create .env with KROGER_CLIENT_ID and KROGER_CLIENT_SECRET")
        print("   Plan sync, publishing, and recipes still work!\n")

    # Pre-load store if zip provided
    if args.zip and token:
        lid = get_location_id(args.zip)
        if lid:
            print(f"  📍 Store: {CACHED_STORE_NAME}")
        else:
            print(f"  ⚠️  No store found for zip {args.zip}")

    server = HTTPServer(("127.0.0.1", args.port), KrogerAPIHandler)
    print(f"\n🛒 Kroger API Server running on http://localhost:{args.port}")
    print(f"   Open index-pro.html in your browser — Pantry tab can now search Kroger!")
    print(f"   Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
