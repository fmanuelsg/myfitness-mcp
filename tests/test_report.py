"""Reports cover the whole range asked for, dated by MFP's own dates."""

from datetime import date, timedelta

import pytest

from myfitnesspal_mcp.server import get_report_values

TODAY = date(2026, 9, 30)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code = payload, status_code

    def json(self):
        return self._payload


class ReportSession:
    """The reports endpoint as seen live: the last N days up to today, as "M/D"."""

    def __init__(self, today=TODAY, status_code=200):
        self.today, self.status_code, self.urls = today, status_code, []

    def get(self, url, headers=None):
        self.urls.append(url)
        if self.status_code != 200:
            return FakeResponse({"error": "internal"}, self.status_code)
        days = int(url.rsplit("/", 1)[1].removesuffix(".json"))
        results = [
            {"date": f"{d.month}/{d.day}", "total": d.day}
            for d in (self.today - timedelta(days=n) for n in reversed(range(days)))
        ]
        return FakeResponse({"outcome": {"results": results}})


class FakeClient:
    BASE_URL_SECURE = "https://www.myfitnesspal.com/"

    def __init__(self, **kwargs):
        self.session = ReportSession(**kwargs)


def test_includes_the_first_day_of_the_range():
    # 23→29 used to come back as 24→29.
    client = FakeClient()
    report = get_report_values(client, "Net Calories", date(2026, 9, 23), date(2026, 9, 29), today=TODAY)
    assert list(report) == [date(2026, 9, d) for d in range(23, 30)]
    assert client.session.urls == [
        "https://www.myfitnesspal.com/api/services/reports/results/nutrition/Net Calories/9.json"
    ]


def test_dates_across_new_year():
    client = FakeClient(today=date(2027, 1, 2))
    report = get_report_values(client, "Protein", date(2026, 12, 30), date(2027, 1, 2), today=date(2027, 1, 2))
    assert list(report) == [date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 1), date(2027, 1, 2)]


def test_mfp_error_says_how_far_back_reports_go():
    client = FakeClient(status_code=500)
    with pytest.raises(RuntimeError, match="about 100 days back"):
        get_report_values(client, "Net Calories", date(2026, 1, 1), date(2026, 1, 31), today=TODAY)
