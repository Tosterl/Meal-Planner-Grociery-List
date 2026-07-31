import pytest

from mealplanner import slugify


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Chicken Stir Fry", "chicken-stir-fry"),
        ("Quick & Easy Garlic Noodles", "quick-easy-garlic-noodles"),
        ("Chicken w/ Broccoli", "chicken-w-broccoli"),
        ("Mom's \"Best\" Pie", "moms-best-pie"),
        ("  Spaced  Out  ", "spaced-out"),
        ("Crème Brûlée", "cr-me-br-l-e"),
        ("!!!", "recipe"),
        ("", "recipe"),
    ],
)
def test_slugify(name, expected):
    assert slugify(name) == expected


def test_slugify_never_escapes_directory():
    for hostile in ("../evil", "a/b/c", "..\\up", "recipe?.json"):
        slug = slugify(hostile)
        assert "/" not in slug and "\\" not in slug and ".." not in slug
