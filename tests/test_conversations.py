"""Conversations read module: single-page search."""

import httpx
import respx

from ghl_toolkit.client import search_conversations

BASE_URL = "https://api.test"


def test_search_conversations_query_params(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/conversations/search").mock(
            return_value=httpx.Response(200, json=load_fixture("convos_search.json"))
        )
        search_conversations(client)

    params = route.calls.last.request.url.params
    assert params["locationId"] == "loc_test123"
    assert params["limit"] == "20"


def test_search_conversations_parses_fields(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/conversations/search").mock(
            return_value=httpx.Response(200, json=load_fixture("convos_search.json"))
        )
        page = search_conversations(client)

    first = page.conversations[0]
    assert first.id == "conv_test001"
    assert first.contact_name == "Jane Tester"
    assert first.last_message_body == "Thanks, that works for me!"
    assert first.unread_count == 2


def test_search_conversations_empty_total_zero(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/conversations/search").mock(
            return_value=httpx.Response(200, json=load_fixture("convos_search_empty.json"))
        )
        page = search_conversations(client)

    assert page.conversations == []
    assert page.total == 0
