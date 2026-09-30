"""Serving choice when logging or editing by unit (AdamWalt/myfitnesspal-mcp-python#18)."""

import lxml.html
import pytest

from myfitnesspal_mcp.server import (
    choose_serving,
    parse_serving_label,
    resolve_entry_serving,
)

# Serving sizes of real foods (v2 serving_sizes / edit form, 2026-09-30).
MILK = [(100.0, "ml"), (1.0, "ml"), (1.0, "container (1000 mls ea.)"), (1.0, "cup")]
CHICKEN = [(4.0, "oz"), (1.0, "medium"), (1.0, "oz"), (1.0, "g"), (1.0, "lb(s)")]
BREAD = [(55.0, "gramo"), (1.0, "gramo")]
YOGURT = [(125.0, "g (1 yogur)")]


def test_bare_unit_prefers_value_one_so_quantity_is_literal():
    # "100 ml" comes first: 200 ml must be 200 x "1 ml", not 200 x "100 ml".
    assert choose_serving(MILK, "ml", 200) == (1, 200)
    assert choose_serving(CHICKEN, "oz", 5) == (2, 5)


@pytest.mark.parametrize("unit", ["g", "gramos", "Gramo", "grams", "gr"])
def test_unit_spellings_match(unit):
    assert choose_serving(BREAD, unit, 80) == (1, 80)
    assert choose_serving(CHICKEN, unit, 150) == (3, 150)


def test_only_a_multi_unit_serving_divides_the_amount():
    assert choose_serving(YOGURT, "g", 150) == (0, 1.2)
    assert choose_serving([(100.0, "g")], "g", 150) == (0, 1.5)


def test_full_label_counts_servings():
    assert choose_serving(MILK, "100 ml", 2) == (0, 2)
    assert choose_serving(MILK, "1 container (1000 mls ea.)", 1) == (2, 1)
    assert choose_serving(CHICKEN, "lb(s)", 1) == (4, 1)


def test_default_serving_words_fall_back_to_first():
    assert choose_serving(CHICKEN, "ración", 2) == (0, 2)
    assert choose_serving(CHICKEN, "serving", 2) == (0, 2)


def test_unknown_unit_lists_servings_and_never_guesses():
    with pytest.raises(ValueError) as err:
        choose_serving(CHICKEN, "tbsp", 1)
    assert "4 oz, 1 medium, 1 oz, 1 g, 1 lb(s)" in str(err.value)


def test_bare_unit_needs_a_quantity():
    with pytest.raises(ValueError, match="quantity"):
        choose_serving(MILK, "ml", None)


@pytest.mark.parametrize(
    ("label", "parsed"),
    [
        ("100 ml", (100.0, "ml")),
        ("1 container (1000 mls ea.)", (1.0, "container (1000 mls ea.)")),
        ("1/2 cup", (0.5, "cup")),
        ("1,5 tazas", (1.5, "tazas")),
        ("breast", (1.0, "breast")),
    ],
)
def test_parse_serving_label(label, parsed):
    assert parse_serving_label(label) == parsed


def edit_form(selected="11", quantity="1.0"):
    mark = ' selected="selected"'
    options = "".join(
        f'<option value="{wid}"{mark if wid == selected else ""}>{label}</option>'
        for wid, label in (("11", "100 ml"), ("12", "1 ml"), ("13", "1 cup"))
    )
    html = (
        '<form id="edit_entry_form">'
        f'<input name="food_entry[quantity]" value="{quantity}">'
        f'<select name="food_entry[weight_id]">{options}</select></form>'
    )
    return lxml.html.fromstring(html)


def test_edit_keeps_serving_and_quantity_by_default():
    assert resolve_entry_serving(edit_form("13", "2.0"), None, None, None) == ("13", "2.0")
    assert resolve_entry_serving(edit_form("13", "2.0"), None, None, 3) == ("13", "3")


def test_edit_by_bare_unit_is_literal():
    assert resolve_entry_serving(edit_form(), None, "ml", 250) == ("12", "250")


def test_edit_by_full_label_counts_servings():
    assert resolve_entry_serving(edit_form("11", "1.5"), None, "1 cup", 2) == ("13", "2")
    # Same serving as now: the quantity may be left as it is.
    assert resolve_entry_serving(edit_form("11", "1.5"), None, "100 ml", None) == ("11", "1.5")


def test_changing_serving_without_quantity_is_refused():
    # Seen on a real entry: 250 x '1 ml' became 250 x '1 cup'.
    with pytest.raises(ValueError, match="quantity"):
        resolve_entry_serving(edit_form("12", "250"), None, "1 cup", None)
    with pytest.raises(ValueError, match="quantity"):
        resolve_entry_serving(edit_form("12", "250"), "13", None, None)


def test_edit_raw_weight_id_wins():
    assert resolve_entry_serving(edit_form(), "99", "ml", 5) == ("99", "5")
