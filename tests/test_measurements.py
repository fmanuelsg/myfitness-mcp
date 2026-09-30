"""Measurement summaries are computed oldest-to-newest, whatever order the library returns."""

from collections import OrderedDict
from datetime import date

from myfitnesspal_mcp.server import get_measurements_v2, measurements_payload


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
    """v2/measurements as seen live: newest first, fixed page size, paged by offset,
    type/date filters ignored."""

    def __init__(self, items, page_size=2):
        self.items, self.page_size, self.offsets = items, page_size, []

    def get(self, url, params=None, headers=None):
        offset = (params or {}).get("offset", 0)
        self.offsets.append(offset)
        page = self.items[offset : offset + self.page_size]
        return FakeResponse({"items": page, "has_more": offset + len(page) < len(self.items)})


class FakeClient:
    BASE_API_URL = "https://api.myfitnesspal.com/"
    access_token = "tok"
    user_id = 42

    def __init__(self, items):
        self.session = PagedSession(items)


ITEMS = [
    {"type": "Weight", "date": "2026-09-28", "value": 73.4},
    {"type": "Body Fat", "date": "2026-09-27", "value": 18.0},
    {"type": "Weight", "date": "2026-09-26", "value": 74.8},
    {"type": "Weight", "date": "2026-09-26", "value": 99.0},  # older entry, same day
    {"type": "Weight", "date": "2026-09-12", "value": 74.3},
    {"type": "Weight", "date": "2026-08-24", "value": 74.6},
    {"type": "Weight", "date": "2021-05-05", "value": 80.0},
]


def test_v2_filters_type_and_dates_and_pages_until_past_start():
    client = FakeClient(ITEMS)
    got = get_measurements_v2(client, "weight", date(2026, 9, 1), date(2026, 9, 27))
    assert got == {date(2026, 9, 26): 74.8, date(2026, 9, 12): 74.3}
    # Stops at the page holding 2026-08-24 (< start): never fetches the 2021 entry.
    assert client.session.offsets == [0, 2, 4]


def test_v2_reaches_old_ranges_beyond_the_first_page():
    client = FakeClient(ITEMS)
    assert get_measurements_v2(client, "Weight", date(2021, 1, 1), date(2021, 12, 31)) == {
        date(2021, 5, 5): 80.0
    }
