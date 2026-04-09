# 🍽️ Meal Planner Pro

A complete meal planning toolkit: recipe scraper, dairy-free adaptation, weekly/monthly planning, store price comparison (Kroger, Whole Foods, Costco), and grocery list generation.

## Quick Start

```bash
pip install requests beautifulsoup4

# Scrape a recipe + adapt for lactose intolerance + save
python scraper.py scrape "https://www.budgetbytes.com/one-pot-creamy-cajun-chicken-pasta/" --dairy-free --save

# Open the web UI
open index-pro.html
```

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

Handles false positives correctly (peanut butter, coconut milk, butternut squash).

## Web UI (`index-pro.html`)

Single-file HTML app. Features: recipes with images, weekly + calendar planning, Kroger/Whole Foods/Costco pricing, cost comparison, grocery lists with store pricing.

## CLI Planner (`planner.py`)

Zero-dependency CLI alternative. `python planner.py --help` for usage.

## Tips

- Create a `urls.txt` with your go-to recipe URLs, then `python scraper.py bulk urls.txt --dairy-free --save`
- Alias for convenience: `alias scrape='python scraper.py scrape --dairy-free --save'`
- Update prices in the Pricing tab as you shop for accurate cost tracking
