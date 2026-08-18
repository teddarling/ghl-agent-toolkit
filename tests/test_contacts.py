"""Contacts read module: search, get-by-id, and pagination."""

import json
from datetime import datetime

import httpx
import respx

from ghl_toolkit.client import Contact, get_contact, iter_contacts, search_contacts

BASE_URL = "https://api.test"


def test_search_contacts_posts_correct_body(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/contacts/search").mock(
            return_value=httpx.Response(200, json=load_fixture("contacts_search_page1.json"))
        )
        search_contacts(client)

    request = route.calls.last.request
    assert json.loads(request.content) == {
        "locationId": "loc_test123",
        "page": 1,
        "pageLimit": 20,
    }
    assert request.headers["Version"] == "2021-07-28"


def test_search_contacts_parses_fields(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/contacts/search").mock(
            return_value=httpx.Response(200, json=load_fixture("contacts_search_page1.json"))
        )
        page = search_contacts(client)

    assert page.total == 4
    first = page.contacts[0]
    assert first.id == "con_test001"
    assert first.first_name == "Jane"
    assert first.email == "jane@x.test"
    assert first.tags == ["vip", "lead"]
    assert isinstance(first.date_added, datetime)
    assert first.date_added.year == 2026


def test_contact_extra_fields_ignored():
    contact = Contact.model_validate(
        {"id": "con_extra", "unknownField": "surprise", "nested": {"deep": True}}
    )

    assert contact.id == "con_extra"
    assert not hasattr(contact, "unknownField")


def test_get_contact_hits_path(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/contacts/con_test001").mock(
            return_value=httpx.Response(200, json=load_fixture("contact_response.json"))
        )
        contact = get_contact(client, "con_test001")

    assert route.called
    assert contact.id == "con_test001"
    assert contact.company_name == "Acme Testing Co"
    assert contact.city == "Testville"


def test_get_contact_missing_optionals(client):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/contacts/con_min").mock(
            return_value=httpx.Response(200, json={"contact": {"id": "con_min"}})
        )
        contact = get_contact(client, "con_min")

    assert contact.id == "con_min"
    assert contact.email is None
    assert contact.first_name is None
    assert contact.tags == []


def test_iter_contacts_paginates(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/contacts/search").mock(
            side_effect=[
                httpx.Response(200, json=load_fixture("contacts_search_page1.json")),
                httpx.Response(200, json=load_fixture("contacts_search_page2.json")),
            ]
        )
        contacts = list(iter_contacts(client, page_size=3))

    assert [c.id for c in contacts] == ["con_test001", "con_test002", "con_test003", "con_test004"]
    assert route.call_count == 2
    first_body = json.loads(route.calls[0].request.content)
    second_body = json.loads(route.calls[1].request.content)
    assert first_body["page"] == 1
    assert second_body["page"] == 2
    assert first_body["pageLimit"] == 3
    assert second_body["pageLimit"] == 3


def test_iter_contacts_stops_on_empty(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/contacts/search").mock(
            side_effect=[
                httpx.Response(200, json=load_fixture("contacts_search_page1.json")),
                httpx.Response(200, json={"contacts": [], "total": 3}),
            ]
        )
        contacts = list(iter_contacts(client, page_size=3))

    assert len(contacts) == 3
    assert route.call_count == 2
