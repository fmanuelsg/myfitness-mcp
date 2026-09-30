"""Measurement summaries are computed oldest-to-newest, whatever order the library returns."""

from collections import OrderedDict
from datetime import date

import pytest

from myfitnesspal_mcp.server import (
    get_measurements_v2,
    measurements_payload,
    resolve_measurement_type,
    set_measurement_v2,
)


def test_newest_first_input_gives_chronological_summary():
    # python-myfitnesspal order, seen on a real account (2026-09-30).
    raw = OrderedDict(
        [(date(2026, 9, 28), 73.4), (date(2026, 9, 26), 74.8), (date(2026, 9, 12), 74.3)]
    )
    data = measurements_payload(raw, "Weight", date(2026, 8, 31), date(2026, 9, 30))
    assert list(data["values"]) == ["2026-09-12", "2026-09-26", "2026-09-28"]
    assert data["summary"]["earliest"] == 74.3
    assert data["summary"]["latest"] == 73.4
    assert data["summary"]["change"] == -0.9


def test_single_value_has_zero_change_and_empty_has_no_summary():
    one = measurements_payload({date(2026, 9, 28): 73.4}, "Weight", date(2026, 9, 1), date(2026, 9, 30))
    assert one["summary"]["change"] == 0
    assert "summary" not in measurements_payload({}, "Weight", date(2026, 9, 1), date(2026, 9, 30))


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class PagedSession:
    """v2/measurements as seen live (2026-09-30): only Weight unless ``types`` is
    given, filtered by ``from``/``to``, newest first, fixed page size, paged by offset.
    Also serves the web's measurement-types route."""

    def __init__(self, items, page_size=2, types=("Neck", "Waist", "Body Fat %")):
        self.items, self.page_size, self.types = items, page_size, types
        self.offsets, self.queries, self.type_requests = [], [], 0

    def get(self, url, params=None, headers=None):
        if url.endswith("/measurements/types"):
            self.type_requests += 1
            return FakeResponse([{"id": i, "description": d} for i, d in enumerate(self.types)])
        params = params or {}
        self.queries.append(params)
        offset = params.get("offset", 0)
        self.offsets.append(offset)
        wanted = params.get("types", "Weight")
        items = [
            i
            for i in self.items
            if i["type"] == wanted
            and params.get("from", "0000") <= i["date"] <= params.get("to", "9999")
        ]
        page = items[offset : offset + self.page_size]
        return FakeResponse({"items": page, "has_more": offset + len(page) < len(items)})


class FakeClient:
    BASE_API_URL = "https://api.myfitnesspal.com/"
    BASE_URL_SECURE = "https://www.myfitnesspal.com/"
    access_token = "tok"
    user_id = 42

    def __init__(self, items):
        self.session = PagedSession(items)


ITEMS = [
    {"type": "Weight", "date": "2026-09-28", "value": 73.4},
    {"type": "Body Fat %", "date": "2026-09-27", "value": 18.0},
    {"type": "Weight", "date": "2026-09-26", "value": 74.8},
    {"type": "Weight", "date": "2026-09-26", "value": 99.0},  # older entry, same day
    {"type": "Weight", "date": "2026-09-12", "value": 74.3},
    {"type": "Weight", "date": "2026-08-24", "value": 74.6},
    {"type": "Weight", "date": "2021-05-05", "value": 80.0},
]


def test_v2_asks_for_the_type_and_dates_and_pages():
    client = FakeClient(ITEMS)
    got = get_measurements_v2(client, "Weight", date(2026, 9, 1), date(2026, 9, 27))
    assert got == {date(2026, 9, 26): 74.8, date(2026, 9, 12): 74.3}
    assert client.session.queries[0] == {"types": "Weight", "from": "2026-09-01", "to": "2026-09-27"}
    assert client.session.offsets == [0, 2]


def test_v2_reads_types_other_than_weight():
    # Without ``types`` the endpoint only returns Weight: Body Fat % came back empty.
    client = FakeClient(ITEMS)
    got = get_measurements_v2(client, "Body Fat %", date(2026, 9, 1), date(2026, 9, 30))
    assert got == {date(2026, 9, 27): 18.0}


def test_resolve_measurement_type_matches_the_account_names():
    client = FakeClient(ITEMS)
    assert resolve_measurement_type(client, "weight") == "Weight"
    assert client.session.type_requests == 0
    assert resolve_measurement_type(client, "body fat") == "Body Fat %"
    assert resolve_measurement_type(client, "WAIST") == "Waist"
    with pytest.raises(ValueError, match="Neck, Waist, Body Fat %"):
        resolve_measurement_type(client, "Biceps")


def test_v2_reaches_old_ranges_beyond_the_first_page():
    client = FakeClient(ITEMS)
    assert get_measurements_v2(client, "Weight", date(2021, 1, 1), date(2021, 12, 31)) == {
        date(2021, 5, 5): 80.0
    }


class WritableSession(PagedSession):
    """The web's write routes: the weight upsert (MFP keeps it in pounds and serves
    it back in the account's unit) and the PUT for other types."""

    def __init__(self, items, store=True):
        super().__init__(items)
        self.puts, self.store = [], store

    def put(self, url, json=None, headers=None):
        self.puts.append((url.removeprefix("https://www.myfitnesspal.com/api/"), json))
        if self.store:
            if "upsert" in url:
                item = json["item"]
                self.items.insert(0, {"id": "1", "type": "Weight", "value": item["value"],
                                      "unit": item["unit"], "date": item["entry_date"]})
            else:
                self.items.insert(0, {"id": "2", **json["items"][0]})
        return FakeResponse({})


def writable_client(unit="kilograms", store=True):
    client = FakeClient([])
    client.session = WritableSession([], store=store)
    client.user_metadata = {"unit_preferences": {"weight": unit}}
    return client


def test_set_weight_uses_the_upsert_in_the_account_unit_and_returns_what_was_stored():
    client = writable_client()
    stored = set_measurement_v2(client, "Weight", 73.4, date(2026, 9, 30))
    assert client.session.puts == [
        ("services/incubator/measurements/upsert",
         {"item": {"entry_date": "2026-09-30", "unit": "kilograms", "value": 73.4, "type": "weight"}})
    ]
    assert stored == {"id": "1", "type": "Weight", "value": 73.4, "unit": "kilograms", "date": "2026-09-30"}


def test_set_weight_in_stones_accounts_is_sent_in_pounds():
    client = writable_client(unit="stones")
    set_measurement_v2(client, "Weight", 160, date(2026, 9, 30))
    assert client.session.puts[0][1]["item"]["unit"] == "pounds"


def test_set_other_types_uses_the_measurements_put():
    client = writable_client()
    stored = set_measurement_v2(client, "Waist", 80, date(2026, 9, 30))
    assert client.session.puts == [
        ("user-measurements/measurements", {"items": [{"type": "Waist", "value": 80, "date": "2026-09-30"}]})
    ]
    assert stored["id"] == "2" and stored["value"] == 80


def test_set_measurement_fails_if_it_does_not_show_up():
    with pytest.raises(RuntimeError, match="not in the account"):
        set_measurement_v2(writable_client(store=False), "Weight", 73.4, date(2026, 9, 30))
