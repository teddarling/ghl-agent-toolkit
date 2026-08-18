"""Pagination helper."""

import httpx
import respx

from ghl_toolkit.client.http import iter_pages

BASE_URL = "https://api.test"


def test_iterates_all_pages_in_order():
    pages = {
        None: (["a", "b"], "cursor-1"),
        "cursor-1": (["c"], "cursor-2"),
        "cursor-2": (["d", "e"], None),
    }

    assert list(iter_pages(lambda cursor: pages[cursor])) == ["a", "b", "c", "d", "e"]


def test_empty_first_page_yields_nothing():
    assert list(iter_pages(lambda cursor: ([], None))) == []


def test_stops_when_cursor_is_none():
    calls: list[str | None] = []

    def fetch(cursor):
        calls.append(cursor)
        return (["only"], None)

    assert list(iter_pages(fetch)) == ["only"]
    assert calls == [None]


def test_pagination_over_http(client):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/items").mock(
            side_effect=[
                httpx.Response(200, json={"items": ["a", "b"], "next": "cursor-1"}),
                httpx.Response(200, json={"items": ["c"], "next": None}),
            ]
        )

        def fetch(cursor):
            params = {"cursor": cursor} if cursor else {}
            data = client.get("/items", params=params).json()
            return data["items"], data["next"]

        assert list(iter_pages(fetch)) == ["a", "b", "c"]

    assert route.call_count == 2
