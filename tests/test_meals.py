"""Meals are read from the account, never from a fixed 0-3 table (Dinner bug)."""

import lxml.html
import pytest

from myfitnesspal_mcp.server import parse_account_meals, resolve_meal


def diary_html(meals):
    """Minimal diary page with the structure MFP serves: a meal_header row, the
    entries, then a 'bottom' row whose links carry the meal id."""
    rows = []
    for meal_id, name in meals:
        rows.append(f'<tr class="meal_header"><td class="first alt">{name}</td><td>Calories</td></tr>')
        rows.append(f'<tr><td><a data-food-entry-id="1{meal_id}">Food</a></td></tr>')
        rows.append(
            '<tr class="bottom"><td>'
            f'<a href="/user/someone/diary/add?meal={meal_id}">Add Food</a>'
            f'<a href="/food/quick_add?meal={meal_id}">Quick Add</a>'
            f'<a href="/food/copy_meal?from_date=2026-09-29&from_meal={meal_id}&to_meal=0">Copy</a>'
            "</td></tr>"
        )
        rows.append('<tr class="spacer"><td></td></tr>')
    return lxml.html.fromstring(f"<html><body><table>{''.join(rows)}</table></body></html>")


# Order observed on a real account (2026-09-29): Snacks before Dinner.
REAL = [("0", "Breakfast"), ("1", "Lunch"), ("2", "Snacks"), ("3", "Dinner")]


def test_parse_reads_ids_from_links_not_position():
    assert parse_account_meals(diary_html(REAL)) == REAL


def test_parse_custom_and_extra_meals():
    meals = [("0", "Desayuno"), ("1", "Media mañana"), ("2", "Comida"), ("5", "Cena")]
    assert parse_account_meals(diary_html(meals)) == meals


@pytest.mark.parametrize(
    "requested, expected",
    [
        ("Dinner", ("3", "Dinner")),
        ("dinner", ("3", "Dinner")),
        ("  DINNER ", ("3", "Dinner")),
        ("Cena", ("3", "Dinner")),
        ("Snack", ("2", "Snacks")),
        ("merienda", ("2", "Snacks")),
        ("Desayuno", ("0", "Breakfast")),
        ("Almuerzo", ("1", "Lunch")),
        ("comida", ("1", "Lunch")),
    ],
)
def test_resolve_on_real_account(requested, expected):
    assert resolve_meal(requested, REAL) == expected


def test_resolve_account_names_win_over_aliases():
    meals = [("0", "Desayuno"), ("1", "Comida"), ("2", "Merienda"), ("3", "Cena")]
    assert resolve_meal("Dinner", meals) == ("3", "Cena")
    assert resolve_meal("Lunch", meals) == ("1", "Comida")
    assert resolve_meal("cena", meals) == ("3", "Cena")


def test_resolve_accents_and_custom_names():
    meals = [("0", "Breakfast"), ("4", "Media mañana")]
    assert resolve_meal("media manana", meals) == ("4", "Media mañana")


@pytest.mark.parametrize("requested", ["Brunch", "2", "3", "", "  "])
def test_unknown_meals_are_rejected_not_defaulted(requested):
    with pytest.raises(ValueError, match="Breakfast, Lunch, Snacks, Dinner"):
        resolve_meal(requested, REAL)


def test_alias_missing_from_account_is_rejected():
    with pytest.raises(ValueError):
        resolve_meal("Dinner", [("0", "Breakfast"), ("1", "Lunch")])
