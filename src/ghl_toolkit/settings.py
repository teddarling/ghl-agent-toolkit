"""Application settings loaded from environment variables (or .env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the HighLevel API connection and the agent LLM layer."""

    model_config = SettingsConfigDict(
        env_prefix="GHL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_token: SecretStr
    location_id: str
    api_base_url: str = "https://services.leadconnectorhq.com"

    # Agent LLM layer — optional so read-only commands work without an Anthropic key.
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5"
    llm_max_tokens: int = 4096
    agent_budget_usd: float = 1.0
    llm_trace_path: Path = Path("llm-trace.jsonl")
    audit_log_path: Path = Path("audit.log.jsonl")
    proposals_path: Path = Path("proposals.jsonl")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loading them on first use."""
    return Settings()
