"""Fasts: local times in the account's time zone, write-only v2/diary/fasting_entry."""

import json

import pytest

from myfitnesspal_mcp.server import delete_fast, write_fast

FAST_ID = "D536E26B-6BD9-46CE-AEF8-E3BEF1F105FE"


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code, self.text = status_code, text


class FakeSession:
    def __init__(self, status_code):
        self.status_code, self.calls = status_code, []

    def _call(self, method, url, data=None, headers=None):
        self.calls.append((method, url.removeprefix("https://api.myfitnesspal.com/"), json.loads(data) if data else None))
        return FakeResponse(self.status_code, '{"error_description":"fasting entry not found"}')

    def post(self, url, **kwargs):
        return self._call("POST", url, **kwargs)

    def patch(self, url, **kwargs):
        return self._call("PATCH", url, **kwargs)

    def delete(self, url, **kwargs):
        return self._call("DELETE", url, **kwargs)


class FakeClient:
    BASE_API_URL = "https://api.myfitnesspal.com/"
    access_token = "tok"
    user_id = 42

    def __init__(self, status_code, time_zone="Europe/Madrid"):
        self.session = FakeSession(status_code)
        self.user_metadata = {"location_preferences": {"time_zone": time_zone}}


def sent_times(client):
    item = client.session.calls[0][2]["items"][0]
    return item["fast_started"], item["fast_ended"]


def test_local_times_use_the_profile_time_zone():
    # Madrid is UTC+1 in February and UTC+2 in summer.
    client = FakeClient(201)
    fast = write_fast(client, "2020-02-28T20:00", "2020-02-29T12:00")
    assert sent_times(client) == ("2020-02-28T19:00:00Z", "2020-02-29T11:00:00Z")
    assert fast["fast_started"] == "2020-02-28T20:00:00+01:00"
    assert fast["time_zone"] == "Europe/Madrid"
    assert fast["duration_hours"] == 16
    assert client.session.calls[0][:2] == ("POST", "v2/diary/fasting_entry")

    client = FakeClient(201)
    write_fast(client, "2026-09-29T20:00", "2026-09-30T12:00")
    assert sent_times(client) == ("2026-09-29T18:00:00Z", "2026-09-30T10:00:00Z")


def test_explicit_offsets_are_converted_and_shown_locally():
    client = FakeClient(201)
    fast = write_fast(client, "2026-09-29T18:00:00Z", "2026-09-30T12:00:00+02:00")
    assert sent_times(client) == ("2026-09-29T18:00:00Z", "2026-09-30T10:00:00Z")
    assert fast["fast_started"] == "2026-09-29T20:00:00+02:00"


def test_without_profile_time_zone_local_times_are_refused():
    with pytest.raises(ValueError, match="offset"):
        write_fast(FakeClient(201, time_zone=None), "2026-09-29T20:00", "2026-09-30T12:00")
    # With offsets it still works, shown in UTC.
    fast = write_fast(FakeClient(201, time_zone=None), "2026-09-29T20:00Z", "2026-09-30T12:00Z")
    assert fast["time_zone"] == "UTC"


def test_end_must_follow_start_and_nothing_is_sent():
    client = FakeClient(201)
    with pytest.raises(ValueError, match="end after"):
        write_fast(client, "2026-09-30T12:00", "2026-09-29T20:00")
    with pytest.raises(ValueError, match="ISO 8601"):
        write_fast(client, "ayer a las 8", "2026-09-29T20:00")
    assert client.session.calls == []


def test_new_fast_gets_an_uppercase_uuid():
    client = FakeClient(201)
    fast_id = write_fast(client, "2026-09-29T20:00", "2026-09-30T12:00")["id"]
    assert fast_id == fast_id.upper() and len(fast_id) == 36
    assert client.session.calls[0][2]["items"][0]["id"] == fast_id


def test_update_replaces_both_times():
    client = FakeClient(204)
    fast = write_fast(client, "2026-09-29T21:00", "2026-09-30T13:00", entry_id=FAST_ID)
    assert client.session.calls[0][:2] == ("PATCH", f"v2/diary/fasting_entry/{FAST_ID}")
    assert fast["id"] == FAST_ID


def test_unknown_id_says_fasts_cannot_be_listed():
    with pytest.raises(RuntimeError, match="cannot list fasts"):
        write_fast(FakeClient(404), "2026-09-29T21:00", "2026-09-30T13:00", entry_id=FAST_ID)
    with pytest.raises(RuntimeError, match="cannot list fasts"):
        delete_fast(FakeClient(404), FAST_ID)


def test_delete():
    client = FakeClient(204)
    assert delete_fast(client, FAST_ID) == {"id": FAST_ID, "deleted": True}
    assert client.session.calls == [("DELETE", f"v2/diary/fasting_entry/{FAST_ID}", None)]
