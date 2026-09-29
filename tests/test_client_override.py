"""get_mfp_client() honours a per-context client set by a multi-user host."""

import asyncio

import pytest

from myfitnesspal_mcp import server


def test_override_is_returned_without_loading_cookies(monkeypatch):
    def fail():
        raise AssertionError("cookie_loader must not be used when an override is set")

    monkeypatch.setattr(server.cookie_loader, "get_cookiejar", fail)
    sentinel = object()
    token = server.current_mfp_client.set(sentinel)
    try:
        assert server.get_mfp_client() is sentinel
    finally:
        server.current_mfp_client.reset(token)


def test_without_override_falls_back_to_cookie_loader(monkeypatch):
    class Loaded(Exception):
        pass

    def loader():
        raise Loaded

    monkeypatch.setattr(server.cookie_loader, "get_cookiejar", loader)
    with pytest.raises(Loaded):
        server.get_mfp_client()


def test_override_is_isolated_between_concurrent_tasks():
    async def run(client):
        server.current_mfp_client.set(client)
        await asyncio.sleep(0)
        return server.get_mfp_client()

    async def main():
        a, b = object(), object()
        return (a, b), await asyncio.gather(run(a), run(b))

    (a, b), results = asyncio.run(main())
    assert results == [a, b]
