"""Conversation messages fetch: endpoint shape, the 2021-04-15 Version header, parsing."""

import httpx
import respx

from ghl_toolkit.client import fetch_messages

BASE_URL = "https://api.test"


def test_fetch_messages_path_params_and_version_header(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/conversations/conv_test001/messages").mock(
            return_value=httpx.Response(200, json=load_fixture("messages_response.json"))
        )
        fetch_messages(client, "conv_test001", limit=5)

    request = route.calls.last.request
    assert request.url.params["limit"] == "5"
    assert request.headers["Version"] == "2021-04-15"


def test_fetch_messages_parses_envelope(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/conversations/conv_test001/messages").mock(
            return_value=httpx.Response(200, json=load_fixture("messages_response.json"))
        )
        page = fetch_messages(client, "conv_test001")

    assert len(page.messages) == 3
    assert page.last_message_id == "msg_conv001_3"
    assert page.next_page is False


def test_fetch_messages_field_types(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/conversations/conv_test001/messages").mock(
            return_value=httpx.Response(200, json=load_fixture("messages_response.json"))
        )
        page = fetch_messages(client, "conv_test001")

    first, second, third = page.messages
    assert first.direction == "inbound"
    assert first.body == "Hi - do you have pricing for a kitchen remodel?"
    assert first.date_added.year == 2026
    assert second.direction == "outbound"
    assert third.body is None
