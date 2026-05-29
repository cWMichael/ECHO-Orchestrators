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

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key — required for tasks routed to the cloud backend",
    )
    # Maps to DEFAULT_CLOUD_MODEL in .env
    default_cloud_model: str = Field(
        default="claude-opus-4-6",
        description="Anthropic model for complex / architecture tasks",
    )
    anthropic_max_tokens: int = Field(default=4096, ge=256, le=32768)

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
    complexity_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Router threshold — above → Anthropic, below → Ollama",
    )
    bypass_human_gate: bool = Field(
        default=False,
        description="Auto-approves tasks. Must never be True in production.",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_file_path: str = Field(default="logs/echo_metrics.jsonl")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def anthropic_model(self) -> str:
        """Alias kept for backward-compatibility with BaseWorker."""
        return self.default_cloud_model

    @property
    def ollama_model(self) -> str:
        """Alias kept for backward-compatibility with BaseWorker."""
        return self.default_local_model

    # ── Validation ────────────────────────────────────────────────────────────

    @field_validator("anthropic_api_key")
    @classmethod
    def warn_missing_api_key(cls, v: str) -> str:
        if not v:
            import warnings
            warnings.warn(
                "ANTHROPIC_API_KEY is not set. "
                "Tasks routed to Anthropic will fail at runtime.",
                stacklevel=2,
            )
        return v

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
