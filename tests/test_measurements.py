"""Measurement summaries are computed oldest-to-newest, whatever order the library returns."""

from collections import OrderedDict
from datetime import date

from myfitnesspal_mcp.server import measurements_payload


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
