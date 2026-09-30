"""Frequent foods come from top_foods, my foods from users/foods/mine (the web's routes)."""

from datetime import date

import pytest

from myfitnesspal_mcp.server import (
    delete_custom_food,
    fetch_frequent_foods,
    fetch_my_foods,
)


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def get(self, url, params=None, headers=None):
        self.calls.append((url.removeprefix("https://www.myfitnesspal.com/api/services/"), params))
        return FakeResponse(self.payload)


class FakeClient:
    BASE_URL_SECURE = "https://www.myfitnesspal.com/"

    def __init__(self, payload):
        self.session = FakeSession(payload)


def aggregate(description, entries, calories, brand="Casero"):
    return {
        "nutrient_total": calories,
        "entries_total": entries,
        "food": {"description": description, "id": description, "brand_name": brand, "version": "v"},
    }


def test_frequent_foods_sorted_by_times_logged_over_90_days():
    # top_foods sorts by the nutrient (calories), not by how often a food is logged.
    client = FakeClient([{
        "nutrient": "energy", "from": "2026-07-03", "to": "2026-09-30",
        "food_entry_aggregates": [
            aggregate("Tarta", 2, 1800),
            aggregate("Pascual - Leche", 150, 16800, brand="Pascual"),
            aggregate("Pan", 40, 8200, brand=None),
        ],
    }])
    items = fetch_frequent_foods(client, limit=2, today=date(2026, 9, 30))
    assert client.session.calls == [("top_foods?lists%5B%5D=energy", {"from": "2026-07-03", "to": "2026-09-30"})]
    assert [(i["name"], i["times_logged"], i["calories_per_entry"]) for i in items] == [
        ("Pascual - Leche", 150, 112),
        ("Pan", 40, 205),
    ]


def test_frequent_foods_with_nothing_logged():
    assert fetch_frequent_foods(FakeClient([]), limit=10, today=date(2026, 9, 30)) == []


def test_my_foods():
    client = FakeClient([{
        "id": "125094978231525", "version": "125094978231525",
        "description": "Naranja pelada (234 g)", "brand_name": "Casero", "public": False,
        "serving_sizes": [{"value": 1, "unit": "pieza (234 g)"}],
        "nutritional_contents": {"energy": {"unit": "calories", "value": 110}},
    }])
    assert fetch_my_foods(client, limit=10) == [{
        "name": "Casero - Naranja pelada (234 g)",
        "description": "Naranja pelada (234 g)",
        "brand_name": "Casero",
        "serving": "1 pieza (234 g)",
        "calories": 110,
        "public": False,
        "food_id": "125094978231525",
        "food_version": "125094978231525",
    }]


def test_my_foods_search_is_sent_to_mfp():
    client = FakeClient([])
    fetch_my_foods(client, limit=10, search="naranja")
    assert client.session.calls == [("users/foods/mine", {"search": "naranja"})]


class DeleteSession:
    """users/foods/mine lists ``foods``; DELETE removes one unless ``stuck``."""

    def __init__(self, foods, stuck=False, delete_status=204):
        self.foods, self.stuck, self.delete_status = foods, stuck, delete_status
        self.deleted = []

    def get(self, url, params=None, headers=None):
        if url.endswith("api/auth/csrf"):
            return FakeResponse({"csrfToken": "tok"})
        return FakeResponse(list(self.foods))

    def delete(self, url, headers=None):
        food_id = url.rsplit("/", 1)[1]
        self.deleted.append((food_id, headers["x-csrf-token"]))
        if not self.stuck:
            self.foods = [f for f in self.foods if f["id"] != food_id]
        response = FakeResponse(None)
        response.status_code = self.delete_status
        return response


OWN = [{"id": "93759010029157", "description": "Tortilla", "brand_name": "Casero"}]


def delete_client(**kwargs):
    client = FakeClient([])
    client.session = DeleteSession(OWN, **kwargs)
    return client


def test_delete_own_food():
    client = delete_client()
    assert delete_custom_food(client, "93759010029157") == {
        "food_id": "93759010029157", "name": "Casero - Tortilla", "deleted": True,
    }
    assert client.session.deleted == [("93759010029157", "tok")]


def test_delete_refuses_foods_the_account_did_not_create():
    # e.g. an mfp_id from mfp_search_food: nothing is sent to MFP.
    client = delete_client()
    with pytest.raises(RuntimeError, match="not one of the foods"):
        delete_custom_food(client, "164248067900917")
    assert client.session.deleted == []


def test_delete_reports_http_errors_and_unapplied_deletes():
    with pytest.raises(RuntimeError, match="HTTP 403"):
        delete_custom_food(delete_client(stuck=True, delete_status=403), "93759010029157")
    with pytest.raises(RuntimeError, match="still listed"):
        delete_custom_food(delete_client(stuck=True), "93759010029157")
