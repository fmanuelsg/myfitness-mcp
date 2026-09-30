"""Goals are written to v2/nutrient-goals: only what was asked changes, calories as given."""

import copy
import json
from datetime import date

from myfitnesspal_mcp.server import new_goal_values, set_goals_v2

# A real account (2026-09-30): 1850 kcal with macros that add up to 1854.
CURRENT = {"calories": 1850, "carbohydrates": 231.0, "protein": 93.0, "fat": 62.0}


def test_calories_as_given_even_below_the_macros():
    # python-myfitnesspal raised this to 1854.
    assert new_goal_values(CURRENT, calories=1850, carbohydrates=231, protein=93, fat=62) == CURRENT


def test_one_macro_leaves_the_rest_alone():
    assert new_goal_values(CURRENT, protein=120) == {**CURRENT, "protein": 120}


def test_calories_alone_rescale_the_macros():
    assert new_goal_values(CURRENT, calories=2000) == {
        "calories": 2000, "carbohydrates": 250, "protein": 101, "fat": 67,
    }


def test_calories_with_some_macros_keep_the_others():
    assert new_goal_values(CURRENT, calories=2000, fat=70) == {**CURRENT, "calories": 2000, "fat": 70}


def goal(energy, unit="calories"):
    return {
        "energy": {"value": energy, "unit": unit},
        "carbohydrates": 231.0, "protein": 93.0, "fat": 62.0,
        "sodium": 2300.0, "sugar": 56.0, "meal_goals": [],
    }


def item(energy=1850.0, unit="calories"):
    return {
        "valid_from": "2023-03-27", "valid_to": "2100-01-01", "default_group_id": 0,
        "updated_at": "2023-03-27T15:20:09+0000",
        "default_goal": goal(energy, unit),
        "daily_goals": [{**goal(energy, unit), "day_of_week": d, "group_id": 0} for d in ("monday", "sunday")],
    }


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code = payload, status_code
        self.ok = status_code < 400

    def json(self):
        return self._payload


class GoalsSession:
    """GET returns the stored item; POST stores the posted one."""

    def __init__(self, stored):
        self.stored, self.posts = stored, []

    def get(self, url, params=None, headers=None):
        return FakeResponse({"items": [copy.deepcopy(self.stored)]})

    def post(self, url, data=None, headers=None):
        posted = json.loads(data)["item"]
        self.posts.append(posted)
        self.stored = posted
        return FakeResponse({})


class FakeClient:
    BASE_API_URL = "https://api.myfitnesspal.com/"
    access_token = "tok"
    user_id = 42

    def __init__(self, stored):
        self.session = GoalsSession(stored)


def test_posts_a_new_period_with_every_day_and_returns_what_was_stored():
    client = FakeClient(item())
    stored = set_goals_v2(client, date(2026, 9, 30), protein=120)
    posted = client.session.posts[0]
    assert posted["valid_from"] == "2026-09-30"
    assert not {"valid_to", "default_group_id", "updated_at"} & posted.keys()
    for g in [posted["default_goal"], *posted["daily_goals"]]:
        assert g["energy"] == {"value": 1850, "unit": "calories"}
        assert (g["protein"], g["carbohydrates"], g["fat"], g["sodium"]) == (120, 231.0, 62.0, 2300.0)
        assert "group_id" not in g
    assert stored == {**CURRENT, "protein": 120.0}


def test_kilojoule_accounts_are_written_in_kilojoules():
    client = FakeClient(item(energy=1850 * 4.184, unit="kilojoules"))
    stored = set_goals_v2(client, date(2026, 9, 30), calories=2000, carbohydrates=231, protein=93, fat=62)
    assert client.session.posts[0]["default_goal"]["energy"] == {"value": 2000 * 4.184, "unit": "kilojoules"}
    assert stored["calories"] == 2000
