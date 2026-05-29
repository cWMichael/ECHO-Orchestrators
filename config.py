"""
ECHO Orchestrator — Central Configuration
Reads from environment variables / .env file via pydantic-settings.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8020, ge=1, le=65535)
    debug: bool = Field(default=False)
    environment: Literal["development", "staging", "production"] = "development"
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    # ── Ollama (local) ────────────────────────────────────────────────────────
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL of the local Ollama instance",
    )
    # Maps to DEFAULT_LOCAL_MODEL in .env
    default_local_model: str = Field(
        default="echo-meta-14b",
        description="Ollama model for routine tasks (refactoring, testing, docs)",
    )
    ollama_timeout_seconds: int = Field(default=120, ge=10)

    # ── Routing ───────────────────────────────────────────────────────────────
    bypass_human_gate: bool = Field(
        default=False,
        description="Auto-approves tasks. Must never be True in production.",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_file_path: str = Field(default="logs/echo_metrics.jsonl")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def ollama_model(self) -> str:
        """Alias kept for backward-compatibility with BaseWorker."""
        return self.default_local_model

    # ── Validation ────────────────────────────────────────────────────────────

    @field_validator("bypass_human_gate")
    @classmethod
    def guard_production_bypass(cls, v: bool, info) -> bool:
        env = info.data.get("environment", "development")
        if v and env == "production":
            raise ValueError(
                "bypass_human_gate must not be True in production environment."
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton — import and call this everywhere."""
    return Settings()
