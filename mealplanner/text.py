"""Text utilities."""

import re


def slugify(name: str) -> str:
    """Convert a recipe name to a filename-safe slug.

    Whitelist approach: anything that isn't a-z/0-9 collapses to a hyphen,
    so names with /, &, : etc. can never escape the recipes/ directory.
    """
    slug = name.lower().strip().replace("'", "").replace('"', "")
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or "recipe"
