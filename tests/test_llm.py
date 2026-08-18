"""The provider-thin LLM layer: structured output, retry, cost budget, and tracing."""

import json

import httpx
import pytest
import respx
from pydantic import BaseModel

from ghl_toolkit.llm import (
    AnthropicProvider,
    BudgetExceeded,
    CostBudget,
    LlmClient,
    LlmRefusal,
    MalformedOutputError,
    Usage,
)
from ghl_toolkit.settings import Settings

ANTHROPIC_URL = "https://api.anthropic.com"


class Answer(BaseModel):
    answer: str


def _settings(**overrides) -> Settings:
    fields = {
        "api_token": "test-token",
        "location_id": "loc_test123",
        "anthropic_api_key": "sk-test-fake-anthropic",
        "anthropic_model": "claude-haiku-4-5",
    }
    fields.update(overrides)
    return Settings(_env_file=None, **fields)


def _anthropic_body(
    text: str, stop_reason: str = "end_turn", input_tokens: int = 42, output_tokens: int = 7
) -> dict:
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def test_anthropic_provider_request_shape():
    provider = AnthropicProvider(_settings())
    with respx.mock(base_url=ANTHROPIC_URL) as router:
        route = router.post("/v1/messages").mock(
            return_value=httpx.Response(200, json=_anthropic_body('{"answer": "hi"}'))
        )
        parsed, usage = provider.complete(
            system="You classify things.",
            user="Classify this.",
            response_model=Answer,
            max_tokens=4096,
        )

    request = route.calls.last.request
    body = json.loads(request.content)
    assert body["model"] == "claude-haiku-4-5"
    assert body["max_tokens"] == 4096
    assert body["system"] == "You classify things."
    assert body["messages"] == [{"role": "user", "content": "Classify this."}]
    # If the SDK serializes structured output under a different key, report it back to the
    # plan rather than silently adjusting this assertion.
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert request.headers["x-api-key"] == "sk-test-fake-anthropic"
    assert parsed == Answer(answer="hi")
    assert usage.input_tokens == 42
    assert usage.output_tokens == 7


def test_anthropic_provider_refusal_raises():
    provider = AnthropicProvider(_settings())
    with respx.mock(base_url=ANTHROPIC_URL) as router:
        route = router.post("/v1/messages").mock(
            return_value=httpx.Response(200, json=_anthropic_body("", stop_reason="refusal"))
        )
        with pytest.raises(LlmRefusal):
            provider.complete(system="s", user="u", response_model=Answer, max_tokens=64)

    assert route.call_count == 1


def test_malformed_then_valid_retries(stub_provider, tmp_path):
    stub_provider.queued = [
        MalformedOutputError("not json at all", "answer: field required"),
        ({"answer": "ok"}, Usage(input_tokens=100, output_tokens=20)),
    ]
    llm = LlmClient(stub_provider, CostBudget(1.0), tmp_path / "trace.jsonl")

    parsed, usage = llm.complete(
        system="s", user="original question", response_model=Answer, max_tokens=64
    )

    assert parsed == Answer(answer="ok")
    assert usage.input_tokens == 100
    assert stub_provider.calls == 2
    assert "original question" in stub_provider.users[1]
    assert "answer: field required" in stub_provider.users[1]


def test_retry_exhaustion_raises(stub_provider, tmp_path):
    stub_provider.queued = [MalformedOutputError("bad", "answer: field required") for _ in range(3)]
    llm = LlmClient(stub_provider, CostBudget(1.0), tmp_path / "trace.jsonl")

    with pytest.raises(MalformedOutputError):
        llm.complete(system="s", user="u", response_model=Answer, max_tokens=64)

    assert stub_provider.calls == 3


def test_budget_accumulates_cost():
    budget = CostBudget(1.0)

    budget.charge("claude-haiku-4-5", Usage(input_tokens=1000, output_tokens=500))

    assert budget.spent_usd == pytest.approx(0.0035)


def test_budget_hard_stop(stub_provider, tmp_path):
    stub_provider.queued = [
        ({"answer": "one"}, Usage(input_tokens=1000, output_tokens=500)),
        ({"answer": "two"}, Usage(input_tokens=1000, output_tokens=500)),
    ]
    llm = LlmClient(stub_provider, CostBudget(0.001), tmp_path / "trace.jsonl")

    llm.complete(system="s", user="u", response_model=Answer, max_tokens=64)
    with pytest.raises(BudgetExceeded):
        llm.complete(system="s", user="u", response_model=Answer, max_tokens=64)

    assert stub_provider.calls == 1


def test_unknown_model_pricing_raises():
    budget = CostBudget(1.0)

    with pytest.raises((KeyError, ValueError)):
        budget.charge("not-a-real-model", Usage(input_tokens=1, output_tokens=1))


def test_trace_entries_written(stub_provider, tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    stub_provider.queued = [
        MalformedOutputError("not json", "answer: field required"),
        ({"answer": "ok"}, Usage(input_tokens=100, output_tokens=20)),
    ]
    llm = LlmClient(stub_provider, CostBudget(1.0), trace_path)

    llm.complete(
        system="the system prompt", user="the user prompt", response_model=Answer, max_tokens=64
    )

    entries = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert len(entries) == 2
    first, second = entries
    assert first["attempt"] == 1
    assert "answer: field required" in first["error"]
    assert first["system"] == "the system prompt"
    assert first["user"] == "the user prompt"
    assert second["attempt"] == 2
    assert second["input_tokens"] == 100
    assert second["output_tokens"] == 20
    assert second["cost_usd"] == pytest.approx(0.0002)
