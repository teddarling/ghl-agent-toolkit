"""Shared fixtures for the test suite."""

import json
import random
from pathlib import Path

import pytest

from ghl_toolkit.client import GHLClient
from ghl_toolkit.settings import Settings, get_settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        api_token="test-token",
        location_id="loc_test123",
        api_base_url="https://api.test",
    )


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(settings, sleeps):
    with GHLClient(settings, sleep=sleeps.append, rng=random.Random(42)) as ghl_client:
        yield ghl_client


@pytest.fixture
def load_fixture():
    def _load(name: str) -> dict:
        return json.loads((FIXTURES_DIR / name).read_text())

    return _load


class StubProvider:
    """Test double for the LLM Provider protocol.

    Queue ``(data, usage)`` tuples to be validated into the requested response
    model, or exception instances to be raised; records every prompt received.
    """

    def __init__(self, model: str = "claude-haiku-4-5") -> None:
        self.model = model
        self.queued: list[object] = []
        self.systems: list[str] = []
        self.users: list[str] = []

    @property
    def calls(self) -> int:
        return len(self.users)

    def complete(self, *, system, user, response_model, max_tokens):
        self.systems.append(system)
        self.users.append(user)
        item = self.queued.pop(0)
        if isinstance(item, Exception):
            raise item
        data, usage = item
        return response_model.model_validate(data), usage


@pytest.fixture
def stub_provider() -> StubProvider:
    return StubProvider()
