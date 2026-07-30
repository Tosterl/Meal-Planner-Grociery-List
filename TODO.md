# TODO

Backlog of features and improvements, in suggested build order.

## Local-only improvements (no deploy needed)

- [x] **Last-published timestamp + status banner** — DONE
  `/api/health` now includes `last_plan_at`. Header shows a small pill: green dot + "Plan: 2d ago" when fresh, gold "warn" if 8-14 days, pulsing red "stale!" if > 14 days. Hover for full timestamp.

- [x] **Cost cap in Smart Fill** — DONE
  Optional `$ cap:` input next to "🧠 Smart Fill Week". When set, recipe selection still uses the variety/leftover/overlap scoring, but if a candidate would blow the running budget total, it falls back to the cheapest alternative that fits. Toast at the end reports estimated total + over/under cap status.

- [x] **Match-learning** — DONE
  When a UPC is swapped in the Kroger review modal, the {cleaned_ingredient → product} mapping is saved server-side to `match_overrides.json`. The preview endpoint surfaces learned matches as the top alternative (auto-selected) on future runs. UI shows a 🧠 LEARNED badge on saved rows; click it to forget. A 👍 button on non-learned default matches lets you lock-in a good default without swapping.

## Deploy (unblocks phone access + cross-device sync)

- [x] **Deploy prep** — DONE (deploy itself is your call)
  Added `requirements.txt`, `Procfile`, `runtime.txt`. `api_server.py` now binds to `0.0.0.0` and reads `$PORT` / `$HOST` / `$DEFAULT_ZIP` from env when present. Frontend `API_BASE` checks `localStorage('mp2_api_base')` first (so you can override per-browser), then a `<meta name="api-base">` tag, then falls back to `localhost:8099`. See [DEPLOY.md](DEPLOY.md) for Cloudflare Tunnel / Render / Railway instructions.

- [ ] **Pick a host and deploy** (your call — ~5-30 min)
  See DEPLOY.md. Cloudflare Tunnel is fastest. Don't forget to register the new redirect URI in your Kroger developer app.

## Post-deploy improvements

- [ ] **Match-learning (synced v2)** — ~15 min after deploy
  Move the ingredient-to-UPC mapping from localStorage to a server-side `match_overrides.json` so phone + desktop share the same learnings.

- [ ] **Pantry sync** — ~20 min after deploy
  Hook `getPantry/setPantry` to POST to `/api/pantry` whenever it changes; load from server on app open. Pantry becomes shared across devices.

- [x] **Mobile CSS pass** — DONE
  Extended existing `@media` blocks with rules for Kroger review modal, audit modal, pantry sweep grid, Kroger product cards (vertical → row at 480px), calendar day cells, toast positioning. Added focus-visible outlines and color-transition smoothing.

- [x] **Visual hierarchy + dark mode auto-detect** — DONE
  `.btn-primary` now has inset highlight + stronger shadow; ghost buttons get a subtle hover background. Dark mode auto-detects via `prefers-color-scheme`, follows system theme by default, and respects manual toggle as override (stored in `mp2_theme`).

- [x] **Kroger checkout deep-link** — DONE
  After successful submit, the review modal flips to a celebration view: "🎉 Cart submitted!" with item count + estimated total + a big "🛒 Open Kroger to Schedule Pickup" link. Includes a 4-step "next steps" reminder (open cart, pick time, pay, confirm pickup in pantry).

- [x] **Pre-submit sanity gate** — DONE
  Before pushing to Kroger, a confirmation modal shows item count, total packages, estimated $, and % change vs last cart (from `mp2_last_cart_total`). Triggers a yellow "⚠️ Heads up" banner if cart > $250 or > 1.75x last cart. Cancel/confirm. After successful send, saves the new total for next-week comparison.

- [x] **Out-of-stock smart default** — DONE
  Preview endpoint now picks the first in-stock alternative as the default (instead of always alts[0]). Out-of-stock items still appear in the swap grid for manual override. `all_out_of_stock` flag returned when nothing is in stock.

- [x] **Substitution flow at pickup** — DONE
  Each 🕒 pending pantry card now has a 🔄 button next to "✅ Got it". Click → modal opens with the original product shown + a Kroger search pre-filled with the cleaned ingredient name. Pick the substitute → pantry record updated (UPC, name, image, price), status flips to confirmed, and `match_overrides.json` learns "ingredient → substitute UPC" so next week's send goes straight to that brand.

## Bugs surfaced from real use

- [x] **Pantry fuzzy-match too aggressive** — DONE
  Now requires consecutive whole-word match AND rejects matches where the product has a different food/category noun trailing (chicken/sauce/water/paste/conditioner/etc.). Fixed honey→honey-chicken, cumin→hair-conditioner, lemon→lemon-water, garlic→garlic-paste.

- [x] **Default product matches sometimes pick adjacent categories** — DONE (round 2)
  Round 1: `INGREDIENT_QUERY_OVERRIDES` (~50 ingredients) bias search toward correct department.
  Round 2: parse Kroger's `categories` field and filter results. `NEVER_FOOD_CATEGORIES` (Personal Care, Hair Care, Pet, Automotive, etc.) automatically rejected for any food ingredient. `INGREDIENT_CATEGORY_HINTS` (~106 entries) score remaining results — real lemons (+6) outrank Sprite (0) which outranks rejected items (gone).

- [x] **Recipe quantity sent as package count** — DONE
  Was sending recipe qty (e.g., 8 eggs = 8 cartons!). Now defaults to 1 package and uses `recipe_calculator.py` to compute smart defaults via unit conversion + ingredient-specific bridges.

## Tooling

- [x] **`recipe_calculator.py`** — DONE
  Standalone Python module. `python recipe_calculator.py "1.5 lb" --package "1 lb"` returns 2. Handles 23 test cases, ingredient bridges (slice→oz for bacon, clove→oz for garlic, cup→oz for dry goods), unicode fractions, multi-unit needs.

- [x] **`audit_cart.py`** — DONE
  CLI tool that reads latest plan + pantry, computes the ideal cart with smart quantities, and prints a comparison-friendly report. Supports `--kroger --zip 45202` for live prices, `--markdown` for a saved report, `--json` for machine output. Run: `python audit_cart.py`.

## Smart pantry / inventory

- [x] **Auto-populate pantry on successful Kroger order** — DONE
  After "Send to Kroger Cart" succeeds, each ordered UPC now lands in the Kroger pantry with the ordered quantity. Existing pantry items get their qty incremented (UPC dedupe). Next grocery list will automatically subtract these.

- [x] **Pending-pickup status + manual confirmation** — DONE
  Auto-populated items are marked `status: 'pending_pickup'` with an `ordered_at` timestamp. Pantry cards for pending items show a 🕒 PENDING badge with relative time, a yellow/gold border, and a green "✅ Got it" button to confirm. Bulk "Confirm all N pickups" button appears at the top of the Kroger Products section. Items still pending > 7 days trigger a warning toast on app load.

- [x] **Pantry sweep (Sunday "what's gone?" check)** — DONE
  Manual "🧹 Sweep" button on the pantry view shows all items as a checkable grid. Auto-prompts once per Sunday if it's been > 6 days since the last sweep. Stores last-sweep date in `mp2_last_sweep`.

- [x] **Auto-decrement during the week** — DONE
  New "🍴 Cooked Today" button on the pantry view. Click → for each ingredient in today's non-leftover recipes, finds a matching pantry item (whole-word match) and decrements qty by 1. Items hitting 0 are removed. Tracks `mp2_last_decrement_date` so a re-run on the same day prompts confirmation. Button shows "✅ Cooked Today" (faded) once run.

## Acknowledged limitations (no fix possible)

- Kroger API does not expose programmatic checkout — pickup time + payment must be completed in the Kroger app/site.
