"""Central configuration for telcoscope.

Loads from environment variables (and `.env` in the project root). All app
modules should import `settings` from here rather than reading os.environ
directly.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Database ---
    postgres_user: str = "telcoscope"
    postgres_password: str = "telcoscope"
    postgres_db: str = "telcoscope"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # --- Anthropic / LLM narrator ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    narrator_mode: Literal["mock", "live"] = "mock"

    # --- Synthetic data generator ---
    synth_num_cells: int = 100
    synth_days: int = 30
    synth_seed: int = 42

    # --- App ---
    log_level: str = "INFO"
    app_env: Literal["local", "ci", "staging", "prod"] = "local"

    @property
    def postgres_url(self) -> str:
        """SQLAlchemy connection URL."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn(self) -> str:
        """libpq-style DSN."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance.

    Cached so we don't re-parse the .env file on every import.
    """
    return Settings()


# Convenience re-export for ergonomic imports elsewhere.
settings = get_settings()
