# 🍽️ Meal Planner Pro

A complete meal planning toolkit: recipe scraper, dairy-free adaptation, weekly/monthly planning, store price comparison (Kroger, Whole Foods, Costco), grocery list generation, macro tracking, and Skylight calendar sync.

## Quick Start (Windows)

### First Time Setup

1. **Install Python** from [python.org/downloads](https://www.python.org/downloads/)
   - **Check "Add Python to PATH"** during install
2. **Install dependencies:**
   ```
   pip install requests beautifulsoup4
   ```
3. **Create a `.env` file** in this folder with your Kroger API credentials:
   ```
   KROGER_CLIENT_ID=your_client_id
   KROGER_CLIENT_SECRET=your_client_secret
   ```
   Get credentials at [developer.kroger.com](https://developer.kroger.com)

### Every Time You Open the Project

**Option 1 — Double-click `start.bat`** (easiest)

**Option 2 — Command Prompt:**
```
cd "C:\Users\Tosterloh\OneDrive - Caster Connection, Inc\Documents\Meal Planner Grocery List"
python api_server.py --zip YOUR_ZIP
```

Then open `index-pro.html` in your browser.

### What the API Server Does

The server (`api_server.py`) runs locally and enables:
- 🔍 **Kroger product search** in the Pantry tab
- 🚀 **Publish to Skylight** — pushes your meal plan to your Skylight calendar
- 🥫 **Pantry sync** — saves pantry items to a local file

Without the server running, the app still works for planning, recipes, and grocery lists — you just can't search Kroger or publish to Skylight.

## Skylight Calendar

Your meal plan syncs to Skylight via this URL:
```
webcal://tosterl.github.io/Meal-Planner-Grociery-List/meal-plan.ics
```

**How it works:**
1. Plan your meals in the **Plan & Calendar** tab
2. Click **🚀 Publish to Skylight** (requires `api_server.py` running)
3. The server regenerates the calendar and pushes to GitHub Pages
4. Skylight auto-refreshes every few hours

Each calendar event includes: recipe name, prep/cook time, nutrition, cost estimate, full ingredient list, cooking steps, and recipe image.

## Features

| Feature | Description |
|---|---|
| 📖 Recipes | Import from URL, add manually, or import JSON |
| 🧠 Smart Fill | Auto-plans week with overlapping ingredients |
| 💰 Budget Fill | Fills week under a target budget |
| 🛒 Kroger Search | Live product search with prices and aisle locations |
| 🥫 Pantry Tracker | Track what you have — grocery list auto-subtracts |
| 📊 Macro Tracker | Daily calorie/protein/carb/fat goals with ring charts |
| ⏱ Cooking Timers | Start from recipes or set custom timers |
| ⭐ Recipe Ratings | 1-5 star ratings on recipes |
| 🌙 Dark Mode | Toggle with header button or Ctrl+D |
| 📅 Calendar Sync | Publish to Skylight, Google, Outlook, Apple |
| 🗳️ Family Vote | Let family members vote on recipes |
| 🍳 What Can I Make | Finds recipes matching your pantry items |

## Recipe Scraper (`scraper.py`)

Scrapes recipes from any site using Schema.org JSON-LD (most major recipe sites).

### Supported Sites
allrecipes.com, budgetbytes.com, food.com, foodnetwork.com, simplyrecipes.com, seriouseats.com, epicurious.com, bonappetit.com, tasty.co, delish.com, minimalistbaker.com, pinchofyum.com, skinnytaste.com, and hundreds more.

### Commands

```bash
python scraper.py scrape "https://..." --dairy-free --save   # Scrape + adapt + save
python scraper.py scrape "https://..." --json                 # Output raw JSON
python scraper.py bulk urls.txt --dairy-free --save           # Bulk import
python scraper.py check-dairy "shredded cheddar cheese"       # Check ingredient
```

### Dairy-Free Substitutions

The `--dairy-free` flag auto-detects dairy and swaps with tested alternatives:

| Dairy Item | Substitution | Notes |
|---|---|---|
| Milk | Oat milk | Oat for cooking, almond for lighter dishes |
| Butter | Vegan butter (Earth Balance) | Miyoko's for baking |
| Heavy cream | Full-fat coconut cream | Canned, 1:1 swap |
| Sour cream | Tofutti / cashew cream | Blend soaked cashews + lemon as DIY |
| Cheddar | Violife shreds | Best melter for tacos/burritos |
| Parmesan | Nutritional yeast | 2 tbsp per 1/2 cup parmesan |
| Greek yogurt | Coconut yogurt | Silk or So Delicious |
| Cream cheese | Kite Hill | Miyoko's also excellent |

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+1-8 | Switch tabs |
| Ctrl+D | Toggle dark mode |
| Ctrl+T | Open timer |
| Esc | Close any modal |

## CLI Planner (`planner.py`)

Zero-dependency CLI alternative. `python planner.py --help` for usage.

## Tips

- Create a `urls.txt` with your go-to recipe URLs, then `python scraper.py bulk urls.txt --dairy-free --save`
- Update prices in the Pricing tab as you shop for accurate cost tracking
- Stock your pantry first — your grocery list shrinks dramatically
