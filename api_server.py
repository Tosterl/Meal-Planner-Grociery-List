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
import os
import argparse
import secrets
import subprocess
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from datetime import datetime, timedelta

# Set UTF-8 encoding for Windows console (reconfigure is idempotent-safe)
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from kroger_api import (
    search_product, search_alternatives, clean_ingredient_query,
    compute_packages_needed,
    find_nearest_store, load_pantry, save_pantry,
    get_access_token, build_authorize_url, exchange_code_for_token,
    load_user_token, get_user_access_token, disconnect_user, add_to_cart,
    load_match_overrides, save_match_override, delete_match_override,
    get_match_override,
)

# Default store location (set via --zip)
DEFAULT_ZIP = None
CACHED_LOCATION_ID = None
CACHED_STORE_NAME = None

# Filled in by main() once the port is known; used for CORS checks
SERVER_PORT = 8099

# Pending OAuth state values → issued-at timestamp (login CSRF protection)
OAUTH_STATES = {}
OAUTH_STATE_TTL = 600  # seconds

TOKEN_FILE = BASE_DIR / ".api_token"

# Static files the server is allowed to serve (no path traversal possible —
# anything not in this map is a 404)
STATIC_FILES = {
    "/": ("index-pro.html", "text/html; charset=utf-8"),
    "/index.html": ("index-pro.html", "text/html; charset=utf-8"),
    "/index-pro.html": ("index-pro.html", "text/html; charset=utf-8"),
    "/vote.html": ("vote.html", "text/html; charset=utf-8"),
    "/meal-planner.ico": ("meal-planner.ico", "image/x-icon"),
    "/favicon.ico": ("meal-planner.ico", "image/x-icon"),
    "/meal-plan.ics": ("meal-plan.ics", "text/calendar; charset=utf-8"),
}


def load_or_create_api_token():
    """Persistent random token gating all state-changing endpoints.

    The token is injected into the HTML the server serves, so pages loaded
    from http://localhost:<port>/ authenticate automatically. Random web
    pages can't read it (CORS) and so can't POST to the API.
    """
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    except OSError:
        pass
    token = secrets.token_hex(16)
    TOKEN_FILE.write_text(token, encoding="utf-8")
    return token


API_TOKEN = load_or_create_api_token()


def allowed_origins():
    origins = {
        f"http://localhost:{SERVER_PORT}",
        f"http://127.0.0.1:{SERVER_PORT}",
        # file:// pages send "Origin: null"; kept so the old workflow still
        # reads data. Mutations still require the token either way.
        "null",
    }
    extra = os.environ.get("ALLOWED_ORIGIN")
    if extra:
        origins.add(extra.rstrip("/"))
    return origins


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
        # Echo the origin only if it's on the allowlist; unknown origins get
        # no CORS headers, so their browsers block both reads and writes.
        origin = self.headers.get("Origin")
        if origin and origin in allowed_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-MP-Token")

    def _check_auth(self):
        """True if the request carries the local API token."""
        return secrets.compare_digest(
            self.headers.get("X-MP-Token", ""), API_TOKEN
        )

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

    def _dispatch(self, handler, *args):
        """Run a route handler; convert uncaught errors to a JSON 500."""
        try:
            handler(*args)
        except Exception as e:
            print(f"❌ Unhandled error on {self.path}: {type(e).__name__}: {e}")
            try:
                self._error(f"Server error: {type(e).__name__}: {e}", 500)
            except Exception:
                pass  # client already gone / headers already sent

    def do_GET(self):
        self._dispatch(self._route_get)

    def _serve_static(self, path):
        filename, content_type = STATIC_FILES[path]
        file_path = BASE_DIR / filename
        if not file_path.exists():
            self._error("Not found", 404)
            return
        data = file_path.read_bytes()
        if content_type.startswith("text/html"):
            # Inject the API token so same-origin pages authenticate
            # automatically; file:// opens skip this and stay read-only.
            data = data.replace(
                b"<meta charset=\"UTF-8\">",
                b"<meta charset=\"UTF-8\">\n"
                + f'<meta name="mp-token" content="{API_TOKEN}">'.encode("utf-8"),
                1,
            )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _route_get(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path in STATIC_FILES:
            self._serve_static(path)
        elif path == "/api/search":
            self._handle_search(params)
        elif path == "/api/pantry":
            self._handle_pantry_get()
        elif path == "/api/plan":
            self._handle_plan_get()
        elif path == "/api/recipes":
            self._handle_recipes_get()
        elif path == "/api/store":
            self._handle_store(params)
        elif path == "/api/health":
            self._handle_health()
        elif path == "/api/kroger/login":
            self._handle_kroger_login()
        elif path == "/api/kroger/callback":
            self._handle_kroger_callback(params)
        elif path == "/api/kroger/status":
            self._handle_kroger_status()
        elif path == "/api/audit":
            self._handle_audit(params)
        elif path == "/api/match-overrides":
            self._handle_match_overrides_get()
        else:
            self._error("Not found", 404)

    def do_POST(self):
        self._dispatch(self._route_post)

    def _route_post(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if not self._check_auth():
            self._error("Unauthorized — missing or invalid X-MP-Token", 401)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""

        if path == "/api/pantry":
            self._handle_pantry_add(body)
        elif path == "/api/store":
            self._handle_store_set(body)
        elif path == "/api/publish":
            self._handle_publish(body)
        elif path == "/api/kroger/cart":
            self._handle_kroger_cart_add(body)
        elif path == "/api/kroger/cart/preview":
            self._handle_kroger_cart_preview(body)
        elif path == "/api/kroger/disconnect":
            self._handle_kroger_disconnect()
        elif path == "/api/match-overrides":
            self._handle_match_overrides_save(body)
        else:
            self._error("Not found", 404)

    def do_DELETE(self):
        self._dispatch(self._route_delete)

    def _route_delete(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if not self._check_auth():
            self._error("Unauthorized — missing or invalid X-MP-Token", 401)
            return

        if path == "/api/pantry":
            self._handle_pantry_remove(params)
        elif path == "/api/match-overrides":
            self._handle_match_overrides_delete(params)
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

    # ─── Kroger OAuth (user-level cart access) ──────────────────────────────
    def _handle_kroger_login(self):
        """Return the Kroger authorize URL so the UI can redirect the user."""
        state = secrets.token_urlsafe(16)
        now = time.time()
        # Drop expired states, then register this one
        for s, ts in list(OAUTH_STATES.items()):
            if now - ts > OAUTH_STATE_TTL:
                del OAUTH_STATES[s]
        OAUTH_STATES[state] = now
        url = build_authorize_url(state=state)
        if not url:
            self._error("Kroger credentials not configured")
            return
        self._json_response({"authorize_url": url})

    def _handle_kroger_callback(self, params):
        """OAuth redirect target — exchange the code for a user token."""
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]
        state = params.get("state", [None])[0]

        # Reject callbacks we didn't initiate (login CSRF)
        issued_at = OAUTH_STATES.pop(state, None) if state else None
        if issued_at is None or time.time() - issued_at > OAUTH_STATE_TTL:
            self._html_response(self._oauth_result_html(
                ok=False,
                message="Login session expired or invalid — please try connecting again.",
            ))
            return

        if error:
            self._html_response(self._oauth_result_html(
                ok=False, message=f"Kroger denied access: {error}"
            ))
            return
        if not code:
            self._html_response(self._oauth_result_html(
                ok=False, message="No authorization code received"
            ))
            return

        token = exchange_code_for_token(code)
        if not token:
            self._html_response(self._oauth_result_html(
                ok=False, message="Token exchange failed — check server logs"
            ))
            return

        print("  ✅ Kroger account connected")
        self._html_response(self._oauth_result_html(
            ok=True, message="Connected! You can close this tab and return to the meal planner."
        ))

    def _handle_kroger_status(self):
        """Report whether a user OAuth token is active."""
        saved = load_user_token()
        if not saved:
            self._json_response({"connected": False})
            return
        try:
            expires = datetime.fromisoformat(saved.get("expires_at", "2000-01-01"))
        except ValueError:
            expires = datetime.min
        self._json_response({
            "connected": True,
            "expires_at": saved.get("expires_at"),
            "expired": datetime.now() >= expires,
            "scope": saved.get("scope"),
        })

    def _handle_kroger_disconnect(self):
        """Clear the saved user OAuth token."""
        removed = disconnect_user()
        self._json_response({"ok": True, "removed": removed})

    def _handle_kroger_cart_add(self, body):
        """Resolve grocery items to UPCs and push them to the user's Kroger cart."""
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._error("Invalid JSON")
            return

        if not get_user_access_token():
            self._error("Not connected to a Kroger account", 401)
            return

        items_in = data.get("items", [])
        modality = data.get("modality", "PICKUP")
        zip_code = data.get("zip") or DEFAULT_ZIP
        if not items_in:
            self._error("No items provided")
            return

        location_id = get_location_id(zip_code) if zip_code else None
        cart_items = []
        not_found = []

        for entry in items_in:
            # Allow either a pre-resolved UPC or a free-text query
            upc = entry.get("upc")
            qty = int(entry.get("quantity") or entry.get("qty") or 1)
            if upc:
                cart_items.append({"upc": upc, "quantity": qty, "modality": modality})
                continue

            query = entry.get("name") or entry.get("item") or entry.get("query")
            if not query:
                continue

            # search_product returns a list of matches — take the top result
            results = search_product(query, location_id) or []
            product = results[0] if results else None
            if product and product.get("upc"):
                cart_items.append({
                    "upc": product["upc"],
                    "quantity": qty,
                    "modality": modality,
                })
            else:
                not_found.append(query)

        if not cart_items:
            self._json_response({
                "ok": False,
                "added": 0,
                "not_found": not_found,
                "error": "No items could be matched to Kroger products",
            })
            return

        # Kroger limits cart payload size — chunk if needed
        success_count = 0
        errors = []
        chunk_size = 50
        for i in range(0, len(cart_items), chunk_size):
            chunk = cart_items[i:i + chunk_size]
            ok, err = add_to_cart(chunk)
            if ok:
                success_count += len(chunk)
            else:
                errors.append(err)

        self._json_response({
            "ok": success_count > 0,
            "added": success_count,
            "not_found": not_found,
            "errors": errors,
            "modality": modality,
        })

    def _handle_kroger_cart_preview(self, body):
        """
        Resolve grocery items into product matches WITHOUT adding to cart.
        Returns each item with its top suggestion + alternatives so the user
        can review and substitute before sending to Kroger.
        """
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._error("Invalid JSON")
            return

        items_in = data.get("items", [])
        zip_code = data.get("zip") or DEFAULT_ZIP
        if not items_in:
            self._error("No items provided")
            return

        location_id = get_location_id(zip_code) if zip_code else None

        previews = []
        for entry in items_in:
            raw_name = entry.get("name") or entry.get("item") or entry.get("query") or ""
            qty = int(entry.get("quantity") or entry.get("qty") or 1)
            cleaned = clean_ingredient_query(raw_name)
            needed = entry.get("needed", "")

            # If user already pinned a UPC for this, skip the search
            if entry.get("upc"):
                previews.append({
                    "raw": raw_name,
                    "cleaned": cleaned,
                    "needed": needed,
                    "quantity": qty,
                    "alternatives": [],
                    "selected_upc": entry["upc"],
                    "pinned": True,
                    "pinned_name": entry.get("pinned_name", raw_name),
                    "pinned_image": entry.get("pinned_image"),
                    "pinned_price": entry.get("pinned_price"),
                })
                continue

            # Check for a previously-learned match for this ingredient.
            # If found, surface it as the top alternative and auto-select.
            learned = get_match_override(cleaned)

            alts = search_alternatives(cleaned or raw_name, location_id, limit=6) or []

            if learned and learned.get("upc"):
                learned_alt = {
                    "name": learned.get("name", ""),
                    "brand": learned.get("brand", ""),
                    "size": learned.get("size", ""),
                    "upc": learned["upc"],
                    "price": learned.get("price"),
                    "image_url": learned.get("image_url"),
                    "stock_level": "HIGH",
                    "fulfillment": {},
                    "learned": True,
                }
                # Prepend learned, drop any duplicate of the same UPC from search
                alts = [learned_alt] + [a for a in alts if a.get("upc") != learned_alt["upc"]]

            # Smart default qty: convert recipe needed amount vs package size,
            # using the raw ingredient name as a hint for cross-family conversions
            # (e.g. "8 slice" bacon -> "12 oz" package)
            smart_qty = qty
            if alts and alts[0] and alts[0].get("size"):
                smart_qty = compute_packages_needed(
                    needed,
                    alts[0]["size"],
                    ingredient=raw_name,
                    fallback=qty,
                )

            # Default-select the first in-stock alternative; fall back to alts[0]
            # if nothing is in stock. Out-of-stock items still appear in the
            # alternatives list for manual swap.
            in_stock_alt = next(
                (a for a in alts if a.get("stock_level") in ("HIGH", "LOW") and a.get("upc")),
                None,
            )
            default_alt = in_stock_alt or (alts[0] if alts else None)
            selected_upc = default_alt.get("upc") if default_alt else None

            # Re-run smart qty against the actually-selected alternative
            if default_alt and default_alt.get("size"):
                smart_qty = compute_packages_needed(
                    needed,
                    default_alt["size"],
                    ingredient=raw_name,
                    fallback=qty,
                )

            previews.append({
                "raw": raw_name,
                "cleaned": cleaned,
                "needed": needed,
                "quantity": smart_qty,
                "alternatives": alts,
                "selected_upc": selected_upc,
                "all_out_of_stock": (default_alt is not None and default_alt.get("stock_level") == "TEMPORARILY_OUT_OF_STOCK"),
                "learned": bool(learned),
                "pinned": False,
            })

        self._json_response({"items": previews, "modality": data.get("modality", "PICKUP")})

    def _handle_health(self):
        """Server status + freshness of the latest plan (for the header pill)."""
        plans_dir = BASE_DIR / "plans"
        last_plan_iso = None
        last_plan_file = None
        if plans_dir.exists():
            plan_files = sorted(plans_dir.glob("plan_*.json"), reverse=True)
            if plan_files:
                last_plan_file = plan_files[0].name
                try:
                    with open(plan_files[0], encoding="utf-8") as f:
                        plan_data = json.load(f)
                    last_plan_iso = plan_data.get("created")
                except (json.JSONDecodeError, OSError):
                    pass
                # Fallback to file mtime if no `created` field
                if not last_plan_iso:
                    last_plan_iso = datetime.fromtimestamp(plan_files[0].stat().st_mtime).isoformat()
        self._json_response({
            "status": "ok",
            "store": CACHED_STORE_NAME,
            "last_plan_at": last_plan_iso,
            "last_plan_file": last_plan_file,
        })

    def _handle_match_overrides_get(self):
        """Return all saved ingredient -> product mappings."""
        self._json_response({"overrides": load_match_overrides()})

    def _handle_match_overrides_save(self, body):
        """Save (or update) a learned ingredient -> product match."""
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._error("Invalid JSON")
            return
        ingredient = data.get("ingredient")
        product = data.get("product")
        if not ingredient or not product or not product.get("upc"):
            self._error("Need 'ingredient' and 'product' (with upc)")
            return
        saved = save_match_override(ingredient, product)
        self._json_response({"ok": True, "saved": saved})

    def _handle_match_overrides_delete(self, params):
        """Forget a learned match for one ingredient."""
        ingredient = params.get("ingredient", [None])[0]
        if not ingredient:
            self._error("Missing 'ingredient' parameter")
            return
        removed = delete_match_override(ingredient)
        self._json_response({"ok": True, "removed": removed})

    def _handle_audit(self, params):
        """Compute and return the cart audit (what cart SHOULD look like for current plan)."""
        try:
            from audit_cart import build_audit
        except ImportError as e:
            self._error(f"Audit module unavailable: {e}", 500)
            return

        try:
            days = int(params.get("days", ["7"])[0])
        except ValueError:
            days = 7
        live = params.get("kroger", ["false"])[0].lower() in ("true", "1", "yes")
        zip_code = params.get("zip", [DEFAULT_ZIP])[0] if params.get("zip") else DEFAULT_ZIP

        audit = build_audit(days, live, zip_code)
        self._json_response(audit)

    def _html_response(self, html, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    @staticmethod
    def _oauth_result_html(ok: bool, message: str):
        color = "#16a34a" if ok else "#dc2626"
        icon = "✅" if ok else "❌"
        title = "Kroger Connected" if ok else "Connection Failed"
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; padding: 3rem 1.5rem;
       text-align: center; background: #fafafa; color: #111; }}
.card {{ max-width: 440px; margin: 0 auto; background: white; padding: 2.5rem 2rem;
        border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,.08); }}
.icon {{ font-size: 3rem; margin-bottom: 0.5rem; }}
h1 {{ color: {color}; margin: 0.5rem 0 1rem; font-size: 1.4rem; }}
p {{ color: #555; line-height: 1.5; margin: 0; }}
button {{ margin-top: 1.5rem; padding: 0.6rem 1.4rem; border: none; border-radius: 8px;
         background: #2563eb; color: white; font-weight: 600; cursor: pointer; }}
</style></head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{message}</p>
    <button onclick="window.close()">Close</button>
  </div>
  <script>
    if (window.opener) {{
      try {{ window.opener.postMessage({{ kroger_oauth: true, ok: {str(ok).lower()} }}, "*"); }} catch (e) {{}}
    }}
  </script>
</body></html>"""

    def log_message(self, format, *args):
        """Quieter logging."""
        msg = format % args
        if "OPTIONS" not in msg:  # Skip CORS preflight noise
            sys.stderr.write(f"  {msg}\n")


def main():
    # Cloud hosts (Render, Railway, Fly, Heroku) inject PORT and require 0.0.0.0
    env_port = os.environ.get("PORT")
    is_cloud = bool(env_port)

    parser = argparse.ArgumentParser(description="Local Kroger API bridge for Meal Planner")
    parser.add_argument("--port", type=int, default=int(env_port) if env_port else 8099,
                        help="Port to run on (default: 8099, or $PORT if set)")
    parser.add_argument("--host", default=os.environ.get("HOST") or ("0.0.0.0" if is_cloud else "127.0.0.1"),
                        help="Host to bind to (default: 127.0.0.1 local, 0.0.0.0 cloud)")
    parser.add_argument("--zip", help="Default zip code for Kroger store")
    args = parser.parse_args()

    global DEFAULT_ZIP, SERVER_PORT
    DEFAULT_ZIP = args.zip or os.environ.get("DEFAULT_ZIP")
    SERVER_PORT = args.port

    # Pre-check Kroger credentials (optional — server works without them for sync/publish)
    token = get_access_token()
    if not token:
        print("\n⚠️  Kroger API credentials not found — Kroger search disabled.")
        print("   To enable: create .env with KROGER_CLIENT_ID and KROGER_CLIENT_SECRET")
        print("   Plan sync, publishing, and recipes still work!\n")

    # Pre-load store if zip provided
    if DEFAULT_ZIP and token:
        lid = get_location_id(DEFAULT_ZIP)
        if lid:
            print(f"  📍 Store: {CACHED_STORE_NAME}")
        else:
            print(f"  ⚠️  No store found for zip {DEFAULT_ZIP}")

    server = ThreadingHTTPServer((args.host, args.port), KrogerAPIHandler)
    print(f"\n🛒 Meal Planner server running on {args.host}:{args.port}")
    if not is_cloud:
        print(f"   Open http://localhost:{args.port}/ in your browser.")
        print(f"   (Opening index-pro.html directly still works read-only; to enable")
        print(f"   editing from file://, run this once in the browser console:")
        print(f"   localStorage.setItem('mp2_api_token', '{API_TOKEN}') )")
    print(f"   Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
