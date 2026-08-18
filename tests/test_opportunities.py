"""Opportunities read module: search and cursor pagination."""

from datetime import datetime

import httpx
import respx

from ghl_toolkit.client import iter_opportunities, search_opportunities

BASE_URL = "https://api.test"


def test_search_opportunities_query_params(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/opportunities/search").mock(
            return_value=httpx.Response(200, json=load_fixture("opps_search_page1.json"))
        )
        search_opportunities(client)

    params = route.calls.last.request.url.params
    assert params["location_id"] == "loc_test123"
    assert params["limit"] == "20"


def test_search_opportunities_parses_fields(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/opportunities/search").mock(
            return_value=httpx.Response(200, json=load_fixture("opps_search_page1.json"))
        )
        page = search_opportunities(client)

    first = page.opportunities[0]
    assert first.id == "opp_test001"
    assert first.status == "open"
    assert first.monetary_value == 2500.0
    assert first.pipeline_stage_id == "stage_test001"
    assert isinstance(first.created_at, datetime)


def test_opportunity_page_meta_parsed(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/opportunities/search").mock(
            return_value=httpx.Response(200, json=load_fixture("opps_search_page1.json"))
        )
        page = search_opportunities(client)

    assert page.meta is not None
    assert page.meta.total == 3
    assert page.meta.start_after == 1719000000000
    assert page.meta.start_after_id == "opp_test002"
    assert page.meta.next_page == 2


def test_iter_opportunities_uses_start_after_cursor(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/opportunities/search").mock(
            side_effect=[
                httpx.Response(200, json=load_fixture("opps_search_page1.json")),
                httpx.Response(200, json=load_fixture("opps_search_page2.json")),
            ]
        )
        opportunities = list(iter_opportunities(client, page_size=2))

    assert [o.id for o in opportunities] == ["opp_test001", "opp_test002", "opp_test003"]
    assert route.call_count == 2
    first_params = route.calls[0].request.url.params
    second_params = route.calls[1].request.url.params
    assert "startAfter" not in first_params
    assert second_params["startAfter"] == "1719000000000"
    assert second_params["startAfterId"] == "opp_test002"
