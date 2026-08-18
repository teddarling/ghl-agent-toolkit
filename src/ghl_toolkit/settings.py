"""Application settings loaded from environment variables (or .env)."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the HighLevel API connection."""

    model_config = SettingsConfigDict(
        env_prefix="GHL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_token: SecretStr
    location_id: str


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loading them on first use."""
    return Settings()
