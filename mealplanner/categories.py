"""Grocery-store categorization of ingredient names.

Merged superset of the previously diverged keyword tables in planner.py
and audit_cart.py. Longest keyword wins, so "tomato paste" lands in
Pantry instead of matching "tomato" → Produce.
"""

GROCERY_CATEGORIES = {
    "Meat & Protein": [
        # No bare "ground" — "ground beef" already matches "beef", and the
        # old keyword misfiled "ground cumin" as meat
        "chicken", "beef", "pork", "turkey", "salmon", "shrimp", "fish",
        "sausage", "bacon", "steak", "tofu", "tempeh", "egg",
    ],
    "Produce": [
        "onion", "garlic", "tomato", "lettuce", "spinach", "carrot",
        "celery", "potato", "broccoli", "mushroom", "avocado", "lemon",
        "lime", "ginger", "cilantro", "parsley", "basil", "jalapeño",
        "jalapeno", "cucumber", "zucchini", "corn", "bell pepper",
        "green onion", "scallion", "blueberr", "strawberr", "banana",
        "apple",
    ],
    "Dairy": [
        "milk", "cheese", "butter", "cream", "yogurt", "sour cream",
    ],
    "Bread & Bakery": [
        "bread", "tortilla", "bun", "roll", "pita", "naan",
    ],
    "Pantry": [
        "rice", "pasta", "spaghetti", "noodle", "flour", "oats", "sugar",
        "oil", "vinegar", "soy sauce", "broth", "stock", "can", "bean",
        "lentil", "chickpea", "tomato sauce", "tomato paste",
        "coconut milk", "honey", "maple syrup", "peanut butter", "salsa",
        "seeds", "chia", "vanilla", "cornstarch",
    ],
    "Spices & Seasonings": [
        "salt", "pepper", "cumin", "paprika", "oregano", "thyme",
        "cinnamon", "chili powder", "cayenne", "turmeric", "curry",
        "garlic powder", "onion powder", "red pepper", "sesame",
    ],
}

CATEGORY_EMOJI = {
    "Meat & Protein": "🥩",
    "Produce": "🥬",
    "Dairy": "🧀",
    "Bread & Bakery": "🍞",
    "Pantry": "🥫",
    "Spices & Seasonings": "🧂",
    "Other": "🛒",
}

# (keyword, category), longest keyword first so specific phrases beat
# their substrings ("garlic powder" before "garlic")
_KEYWORDS = sorted(
    ((kw, cat) for cat, kws in GROCERY_CATEGORIES.items() for kw in kws),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def categorize(item: str) -> str:
    """Return the grocery category for an ingredient name, or 'Other'."""
    item_l = (item or "").lower()
    for kw, cat in _KEYWORDS:
        if kw in item_l:
            return cat
    return "Other"
