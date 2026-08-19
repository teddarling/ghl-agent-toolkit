"""Application settings loaded from environment variables (or .env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# GHL's Ed25519 webhook signing key, quoted from the official Webhook Integration
# Guide (https://marketplace.gohighlevel.com/docs/webhook/WebhookIntegrationGuide/).
# A public key, not a secret; overridable so tests can verify with their own pair.
GHL_WEBHOOK_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAi2HR1srL4o18O8BRa7gVJY7G7bupbN3H9AwJrHCDiOg=
-----END PUBLIC KEY-----
"""


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
    # lead_scorer target field: resolved by key unless an explicit id is configured.
    score_field_key: str = "lead_score"
    score_field_id: str | None = None
    llm_trace_path: Path = Path("llm-trace.jsonl")
    audit_log_path: Path = Path("audit.log.jsonl")
    proposals_path: Path = Path("proposals.jsonl")

    # Webhook server. Demo mode runs the whole loop on seeded data with no credentials.
    demo_mode: bool = False
    webhook_shared_secret: SecretStr | None = None
    webhook_verify_signature: bool = False
    webhook_public_key: str = GHL_WEBHOOK_PUBLIC_KEY


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loading them on first use."""
    return Settings()
