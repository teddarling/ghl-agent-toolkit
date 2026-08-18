"""The ghl doctor command."""

import httpx
import pytest
import respx
from typer.testing import CliRunner

from ghl_toolkit.cli import app

BASE_URL = "https://api.test"

runner = CliRunner()


@pytest.fixture
def doctor_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GHL_API_TOKEN", "test-token")
    monkeypatch.setenv("GHL_LOCATION_ID", "loc_test123")
    monkeypatch.setenv("GHL_API_BASE_URL", BASE_URL)


def test_doctor_success(doctor_env, load_fixture):
    headers = {"X-RateLimit-Remaining": "8675", "X-RateLimit-Limit-Daily": "200000"}
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/locations/loc_test123").mock(
            return_value=httpx.Response(
                200, json=load_fixture("location_response.json"), headers=headers
            )
        )
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Test Location" in result.output
    assert "8675" in result.output


def test_doctor_invalid_token(doctor_env, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/locations/loc_test123").mock(
            return_value=httpx.Response(401, json=load_fixture("error_401.json"))
        )
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "token" in result.output.lower()


def test_doctor_unknown_location(doctor_env):
    body = {"statusCode": 404, "message": "Location not found", "error": "Not Found"}
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/locations/loc_test123").mock(return_value=httpx.Response(404, json=body))
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "GHL_LOCATION_ID" in result.output


def test_doctor_missing_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for var in ("GHL_API_TOKEN", "GHL_LOCATION_ID", "GHL_API_BASE_URL"):
        monkeypatch.delenv(var, raising=False)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 2
    assert ".env.example" in result.output


def test_doctor_missing_scope(doctor_env):
    body = {"statusCode": 403, "message": "Forbidden resource", "error": "Forbidden"}
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/locations/loc_test123").mock(return_value=httpx.Response(403, json=body))
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "locations.readonly" in result.output
