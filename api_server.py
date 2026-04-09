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
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

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

    # Pre-check Kroger credentials
    token = get_access_token()
    if not token:
        print("\n❌ Cannot start — Kroger API credentials missing.")
        print("   Run: python kroger_api.py setup")
        sys.exit(1)

    # Pre-load store if zip provided
    if args.zip:
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
