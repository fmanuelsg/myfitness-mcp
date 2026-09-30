"""Food details come from the v2 API, not the client-rendered page the library scrapes."""

from myfitnesspal_mcp.server import format_food_details, get_food_v2, mfp_api_headers

# Trimmed v2 record for a real food (2026-09-30): the library's scraper raised
# KeyError 'trans_fat' on it.
FOOD = {
    "id": "164248067900917",
    "description": "Chicken Breast",
    "brand_name": "",
    "verified": False,
    "nutritional_contents": {
        "energy": {"unit": "calories", "value": 187.0},
        "protein": 35.0,
        "fat": 4.0,
        "carbohydrates": 0.0,
        "grams": 113.0,
    },
    "serving_sizes": [{"value": 4.0, "unit": "oz"}, {"value": 1.0, "unit": "g"}],
}


def test_missing_nutrients_are_none_not_errors():
    data = format_food_details(FOOD, "164248067900917")
    assert data["description"] == "Chicken Breast"
    assert data["brand_name"] is None
    assert data["calories"] == 187.0
    assert data["nutrition_basis_grams"] == 113.0
    assert data["nutrition"]["protein"] == 35.0
    assert data["nutrition"]["trans_fat"] is None
    assert data["servings"] == ["4 oz", "1 g"]


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class FakeClient:
    BASE_API_URL = "https://api.myfitnesspal.com/"
    access_token = "tok"
    user_id = 42

    def __init__(self, response):
        self.session = FakeSession(response)


def test_get_food_v2_queries_by_id_with_api_headers():
    client = FakeClient(FakeResponse(200, {"items": [FOOD]}))
    assert get_food_v2(client, "164248067900917") is FOOD
    url, kwargs = client.session.calls[0]
    assert url == "https://api.myfitnesspal.com/v2/foods"
    assert kwargs["params"] == {"ids": "164248067900917"}
    assert kwargs["headers"] == mfp_api_headers(client)
    assert kwargs["headers"]["accept"] == "application/json"


def test_get_food_v2_unknown_id_raises():
    client = FakeClient(FakeResponse(200, {"items": []}))
    try:
        get_food_v2(client, "1")
    except RuntimeError as e:
        assert "No food found" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
