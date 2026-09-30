"""Water is millilitres on the wire; set_water posts to /food/water with the page CSRF header."""

from datetime import date

import lxml.html
import pytest

from myfitnesspal_mcp.server import set_water_intake, water_payload

DAY = date(2020, 2, 29)


def test_payload_reads_millilitres_not_cups():
    # day.water from python-myfitnesspal is the "milliliters" field.
    assert water_payload(473.18, DAY) == {"date": "2020-02-29", "water_ml": 473.18, "water_cups": 2.0}


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.response


class FakeClient:
    BASE_URL_SECURE = "https://www.myfitnesspal.com/"

    def __init__(self, response, csrf="tok123"):
        self.session = FakeSession(response)
        meta = f'<meta name="csrf-token" content="{csrf}">' if csrf else ""
        self.page = lxml.html.fromstring(f"<html><head>{meta}</head><body><p>diary</p></body></html>")

    def _get_document_for_url(self, url):
        return self.page


def test_set_water_posts_millilitres_with_csrf_header():
    client = FakeClient(FakeResponse(200, {"item": {"date": "2020-02-29", "milliliters": 473.18}}))
    assert set_water_intake(client, DAY, 2) == 473.18
    url, kwargs = client.session.posts[0]
    assert url == "https://www.myfitnesspal.com/food/water"
    assert kwargs["data"] == {"milliliters": 473.18, "date": "2020-02-29"}
    assert kwargs["headers"]["X-CSRF-Token"] == "tok123"


def test_set_water_http_error_raises():
    client = FakeClient(FakeResponse(422, {}))
    with pytest.raises(RuntimeError, match="HTTP 422"):
        set_water_intake(client, DAY, 1)
