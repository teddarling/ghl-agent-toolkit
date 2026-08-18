"""CLI read commands: contacts, opps, and convos with rich table output."""

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from ghl_toolkit.cli import app

BASE_URL = "https://api.test"

runner = CliRunner()


@pytest.fixture
def cli_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GHL_API_TOKEN", "test-token")
    monkeypatch.setenv("GHL_LOCATION_ID", "loc_test123")
    monkeypatch.setenv("GHL_API_BASE_URL", BASE_URL)


def test_contacts_list_renders_table(cli_env, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/contacts/search").mock(
            return_value=httpx.Response(200, json=load_fixture("contacts_search_page1.json"))
        )
        result = runner.invoke(app, ["contacts", "list"])

    assert result.exit_code == 0
    assert "con_test001" in result.output
    assert "Jane" in result.output
    assert "jane@x.test" in result.output


def test_contacts_list_limit_passed_through(cli_env, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/contacts/search").mock(
            return_value=httpx.Response(200, json=load_fixture("contacts_search_page1.json"))
        )
        result = runner.invoke(app, ["contacts", "list", "--limit", "5"])

    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content)["pageLimit"] == 5


def test_contacts_list_empty_state(cli_env):
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/contacts/search").mock(
            return_value=httpx.Response(200, json={"contacts": [], "total": 0})
        )
        result = runner.invoke(app, ["contacts", "list"])

    assert result.exit_code == 0
    assert "No contacts found." in result.output


def test_contacts_list_json_flag(cli_env, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/contacts/search").mock(
            return_value=httpx.Response(200, json=load_fixture("contacts_search_page1.json"))
        )
        result = runner.invoke(app, ["contacts", "list", "--json"])

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["contacts"][0]["id"] == "con_test001"


def test_contacts_get_renders_fields(cli_env, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/contacts/con_test001").mock(
            return_value=httpx.Response(200, json=load_fixture("contact_response.json"))
        )
        result = runner.invoke(app, ["contacts", "get", "con_test001"])

    assert result.exit_code == 0
    assert "Jane" in result.output
    assert "jane@x.test" in result.output


def test_contacts_get_not_found(cli_env):
    body = {"statusCode": 404, "message": "Contact not found", "error": "Not Found"}
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/contacts/con_test001").mock(return_value=httpx.Response(404, json=body))
        result = runner.invoke(app, ["contacts", "get", "con_test001"])

    assert result.exit_code == 1
    assert "con_test001" in result.output


def test_opps_list_renders_table(cli_env, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/opportunities/search").mock(
            return_value=httpx.Response(200, json=load_fixture("opps_search_page1.json"))
        )
        result = runner.invoke(app, ["opps", "list"])

    assert result.exit_code == 0
    assert "opp_test001" in result.output
    assert "open" in result.output


def test_opps_list_empty_state(cli_env):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/opportunities/search").mock(
            return_value=httpx.Response(200, json={"opportunities": [], "meta": {"total": 0}})
        )
        result = runner.invoke(app, ["opps", "list"])

    assert result.exit_code == 0
    assert "No opportunities found." in result.output


def test_convos_list_renders_table(cli_env, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/conversations/search").mock(
            return_value=httpx.Response(200, json=load_fixture("convos_search.json"))
        )
        result = runner.invoke(app, ["convos", "list"])

    assert result.exit_code == 0
    assert "conv_test001" in result.output
    assert "Jane" in result.output


def test_convos_list_empty_state(cli_env, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/conversations/search").mock(
            return_value=httpx.Response(200, json=load_fixture("convos_search_empty.json"))
        )
        result = runner.invoke(app, ["convos", "list"])

    assert result.exit_code == 0
    assert "No conversations found." in result.output


@pytest.mark.parametrize(
    "command",
    [
        ["contacts", "list"],
        ["contacts", "get", "con_test001"],
        ["opps", "list"],
        ["convos", "list"],
    ],
    ids=["contacts-list", "contacts-get", "opps-list", "convos-list"],
)
def test_read_commands_missing_config_exit_2(monkeypatch, tmp_path, command):
    monkeypatch.chdir(tmp_path)
    for var in ("GHL_API_TOKEN", "GHL_LOCATION_ID", "GHL_API_BASE_URL"):
        monkeypatch.delenv(var, raising=False)

    result = runner.invoke(app, command)

    assert result.exit_code == 2
    assert ".env.example" in result.output


def test_contacts_list_auth_error_exit_1(cli_env, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/contacts/search").mock(
            return_value=httpx.Response(401, json=load_fixture("error_401.json"))
        )
        result = runner.invoke(app, ["contacts", "list"])

    assert result.exit_code == 1
