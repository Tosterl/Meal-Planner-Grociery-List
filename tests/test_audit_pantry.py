import pytest

from audit_cart import covered_by_pantry, pantry_quantity_covers


@pytest.mark.parametrize(
    "needed, item, covers",
    [
        # 1 tbsp needed, own a 16.9 fl oz bottle -> plenty
        ({"tbsp": 1}, {"size": "16.9 fl oz", "qty": 1}, True),
        # need 2 cups (16 fl oz), own a 8 fl oz bottle -> NOT covered
        ({"cup": 2}, {"size": "8 fl oz", "qty": 1}, False),
        # ...but two of those bottles cover it
        ({"cup": 2}, {"size": "8 fl oz", "qty": 2}, True),
        # need 1.5 lb, own a 12 oz pack -> not covered
        ({"lb": 1.5}, {"size": "12 oz", "qty": 1}, False),
        # need 1.5 lb, own a 2 lb pack -> covered
        ({"lb": 1.5}, {"size": "2 lb", "qty": 1}, True),
        # cross-family (cloves vs weight) -> can't compare, assume covered
        ({"clove": 3}, {"size": "3 oz", "qty": 1}, True),
        # unparseable size -> legacy assume-covered
        ({"cup": 2}, {"size": "family size!", "qty": 1}, True),
        ({"cup": 2}, {}, True),
    ],
)
def test_pantry_quantity_covers(needed, item, covers):
    got, note = pantry_quantity_covers(needed, item)
    assert got is covers
    if not covers:
        assert "need" in note  # shortfall note is populated


def test_covered_by_pantry_still_name_matches():
    pantry = [{"name": "Simple Truth Honey Chicken Bites"}, {"name": "Local Honey 12 oz"}]
    hit = covered_by_pantry("honey", pantry)
    assert hit and hit["name"] == "Local Honey 12 oz"
