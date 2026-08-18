"""Provider-thin LLM layer: structured output, retry, cost budget, and tracing.

Agents depend only on the ``Provider`` protocol; ``AnthropicProvider`` is the
first implementation. Everything the harness owns — malformed-output retry,
the hard-stop cost budget, and the per-attempt trace log — lives in
``LlmClient`` and works with any provider.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import pydantic
from anthropic import Anthropic, transform_schema
from pydantic import BaseModel

from ghl_toolkit.settings import Settings

# USD per million tokens (input, output). Source: platform.claude.com/docs/en/docs/
# about-claude/pricing via the claude-api reference, retrieved 2026-08-18. Budget
# math refuses unknown models rather than guessing a rate.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

RETRY_ATTEMPTS = 3


class Usage(BaseModel):
    """Token counts reported by the provider for a single call."""

    input_tokens: int
    output_tokens: int


class BudgetExceeded(Exception):
    """The per-run cost budget is exhausted; no further LLM calls are allowed."""


class LlmRefusal(Exception):
    """The model declined to answer. Never retried — the decline is deterministic."""


class MalformedOutputError(Exception):
    """The model's output failed pydantic validation against the response model."""

    def __init__(self, raw_text: str, error: str, usage: Usage | None = None) -> None:
        super().__init__(f"model output failed validation: {error}")
        self.raw_text = raw_text
        self.error = error
        self.usage = usage


class Provider(Protocol):
    """A single-shot, stateless structured-output completion."""

    model: str

    def complete[T: BaseModel](
        self, *, system: str, user: str, response_model: type[T], max_tokens: int
    ) -> tuple[T, Usage]: ...


class CostBudget:
    """Hard USD ceiling for a run. ``check()`` gates before every call."""

    def __init__(self, limit_usd: float) -> None:
        self.limit_usd = limit_usd
        self.spent_usd = 0.0

    def check(self) -> None:
        if self.spent_usd >= self.limit_usd:
            raise BudgetExceeded(
                f"LLM budget exhausted: spent ${self.spent_usd:.4f} of a "
                f"${self.limit_usd:.4f} limit"
            )

    def charge(self, model: str, usage: Usage) -> float:
        try:
            input_rate, output_rate = PRICING[model]
        except KeyError:
            raise KeyError(
                f"No pricing known for model {model!r}; add it to PRICING before use."
            ) from None
        cost = (usage.input_tokens * input_rate + usage.output_tokens * output_rate) / 1_000_000
        self.spent_usd += cost
        return cost


class AnthropicProvider:
    """Anthropic Messages API provider using native structured outputs.

    The SDK's ``messages.parse`` helper validates eagerly and raises a bare
    ``ValidationError`` on refusals and malformed output, hiding the response
    (stop_reason, usage, raw text) that this layer's retry and budget logic
    needs. So the request is made with ``messages.create`` plus the same
    ``output_config`` the SDK's own ``transform_schema`` builds — the wire
    format is identical to ``parse`` — and validation happens here, where
    refusal and malformed output become typed, actionable errors.
    """

    def __init__(self, settings: Settings) -> None:
        if settings.anthropic_api_key is None:
            raise ValueError("GHL_ANTHROPIC_API_KEY is not configured")
        self.model = settings.anthropic_model
        self._client = Anthropic(api_key=settings.anthropic_api_key.get_secret_value())

    def complete[T: BaseModel](
        self, *, system: str, user: str, response_model: type[T], max_tokens: int
    ) -> tuple[T, Usage]:
        schema = transform_schema(response_model.model_json_schema())
        message = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"schema": schema, "type": "json_schema"}},
        )
        usage = Usage(
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
        if message.stop_reason == "refusal":
            raise LlmRefusal("the model declined to produce a response")
        raw_text = "".join(block.text for block in message.content if block.type == "text")
        try:
            parsed = response_model.model_validate_json(raw_text)
        except pydantic.ValidationError as exc:
            raise MalformedOutputError(raw_text, str(exc), usage=usage) from exc
        return parsed, usage


class LlmClient:
    """What agents call: budget-gated, validation-retried, fully traced."""

    def __init__(self, provider: Provider, budget: CostBudget, trace_path: Path) -> None:
        self._provider = provider
        self._budget = budget
        self._trace_path = Path(trace_path)

    def complete[T: BaseModel](
        self, *, system: str, user: str, response_model: type[T], max_tokens: int
    ) -> tuple[T, Usage]:
        prompt = user
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            self._budget.check()
            entry: dict[str, object] = {
                "ts": datetime.now(UTC).isoformat(),
                "model": self._provider.model,
                "system": system,
                "user": prompt,
                "attempt": attempt,
            }
            try:
                parsed, usage = self._provider.complete(
                    system=system,
                    user=prompt,
                    response_model=response_model,
                    max_tokens=max_tokens,
                )
            except MalformedOutputError as exc:
                entry["error"] = exc.error
                entry["raw_response"] = exc.raw_text
                if exc.usage is not None:
                    entry["input_tokens"] = exc.usage.input_tokens
                    entry["output_tokens"] = exc.usage.output_tokens
                    entry["cost_usd"] = self._budget.charge(self._provider.model, exc.usage)
                self._trace(entry)
                if attempt == RETRY_ATTEMPTS:
                    raise
                prompt = (
                    f"{user}\n\nYour previous response failed validation:\n{exc.error}\n"
                    "Return only JSON matching the schema."
                )
                continue
            cost = self._budget.charge(self._provider.model, usage)
            entry["response"] = parsed.model_dump()
            entry["input_tokens"] = usage.input_tokens
            entry["output_tokens"] = usage.output_tokens
            entry["cost_usd"] = cost
            self._trace(entry)
            return parsed, usage
        raise AssertionError("unreachable: the retry loop always returns or raises")

    def _trace(self, entry: dict[str, object]) -> None:
        self._trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self._trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
