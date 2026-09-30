"""A rejected session must not pass for a search with no results."""

import myfitnesspal
import pytest

from myfitnesspal_mcp import server
from myfitnesspal_mcp.server import (
    MfpSessionRejected,
    SearchFoodInput,
    ensure_not_login,
    mfp_search_food,
    search_foods,
)

BASE = "https://www.myfitnesspal.com/"
SEARCH_PAGE = b'<html><form><input name="authenticity_token" value="tok"></form></html>'
RESULTS = b"""<html><body><h2>Matching Foods:</h2><ul>
<li class="matched-food">
  <div class="search-title-container"><a data-external-id="164248067900917">Chicken Breast</a></div>
  <p class="search-nutritional-info">Generic, 4 oz, 187 calories</p>
</li></ul></body></html>"""
# What POST /food/search answers once MFP stops accepting the session
# (2026-09-30): the login page, whose embedded translations include the text
# the library looks for.
LOGIN = b'<html><script>{"food.matchingFoods":"Matching Foods:"}</script></html>'


class FakeResponse:
    def __init__(self, url, content):
        self.url = url
        self.content = content


class FakeSession:
    def __init__(self, post_response):
        self.post_response = post_response
        self.posts = []

    def get(self, url, **kwargs):
        return FakeResponse(url, SEARCH_PAGE)

    def post(self, url, data=None, **kwargs):
        self.posts.append(data)
        return self.post_response


class FakeClient:
    BASE_URL_SECURE = BASE
    _get_food_search_results = myfitnesspal.Client._get_food_search_results

    def __init__(self, post_response):
        self.session = FakeSession(post_response)


def login_redirect():
    return FakeResponse(f"{BASE}account/login?callbackUrl=%2Ffood%2Fsearch", LOGIN)


def test_results_are_parsed():
    client = FakeClient(FakeResponse(f"{BASE}food/search", RESULTS))
    items = search_foods(client, "chicken breast")
    assert [(i.mfp_id, i.name, i.calories) for i in items] == [
        (164248067900917, "Chicken Breast", 187.0)
    ]
    assert client.session.posts[0]["authenticity_token"] == "tok"
    assert client.session.posts[0]["search"] == "chicken breast"


def test_login_redirect_raises_instead_of_no_results():
    with pytest.raises(MfpSessionRejected):
        search_foods(FakeClient(login_redirect()), "arroz")


def test_ensure_not_login_accepts_other_pages():
    ensure_not_login(FakeResponse(f"{BASE}food/search", RESULTS))
    with pytest.raises(MfpSessionRejected):
        ensure_not_login(login_redirect())


async def test_tool_reports_the_rejected_session():
    token = server.current_mfp_client.set(FakeClient(login_redirect()))
    try:
        result = await mfp_search_food(SearchFoodInput(query="arroz"))
    finally:
        server.current_mfp_client.reset(token)
    assert result.startswith("Error searching foods: MyFitnessPal rejected the session")
