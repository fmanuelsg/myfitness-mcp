"""Frequent foods come from top_foods, my foods from users/foods/mine (the web's routes)."""

from datetime import date

from myfitnesspal_mcp.server import fetch_frequent_foods, fetch_my_foods


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
