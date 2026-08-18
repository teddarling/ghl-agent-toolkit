"""Tests for the settings module."""

import pytest
from pydantic import ValidationError

from ghl_toolkit.settings import Settings


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GHL_API_TOKEN", "test-token")
    monkeypatch.setenv("GHL_LOCATION_ID", "loc-123")

    settings = Settings(_env_file=None)

    assert settings.api_token.get_secret_value() == "test-token"
    assert settings.location_id == "loc-123"


def test_settings_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GHL_API_TOKEN", raising=False)
    monkeypatch.delenv("GHL_LOCATION_ID", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_api_token_not_leaked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GHL_API_TOKEN", "super-secret-token")
    monkeypatch.setenv("GHL_LOCATION_ID", "loc-123")

    settings = Settings(_env_file=None)

    assert "super-secret-token" not in repr(settings)
    assert str(settings.api_token) == "**********"
