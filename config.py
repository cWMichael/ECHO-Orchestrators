"""
ECHO Orchestrator - Central Configuration
Reads from environment variables / .env file via pydantic-settings.
"""

from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALLOWED_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server (nur Legacy FastAPI — Desktop-Pfad startet keinen HTTP-Server)
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8020, ge=1, le=65535)
    debug: bool = Field(default=False)
    environment: Literal["development", "staging", "production"] = "development"
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:7860"]
    )

    # Ollama (lokal — ausschließlich localhost)
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        description="Base URL der lokalen Ollama-Instanz (127.0.0.1 / localhost / ::1)",
    )
    default_local_model: str = Field(
        default="echo-meta-14b",
        description="Ollama model for local worker tasks",
    )
    ollama_timeout_seconds: int = Field(default=120, ge=10)

    # Routing / approval
    bypass_human_gate: bool = Field(
        default=False,
        description="Auto-approves tasks. Must never be True in production.",
    )

    # Projekt-Wurzel für Worker-Datei-Operationen
    # MUSS explizit auf das Zielprojekt zeigen — niemals "." oder das Orchestrator-Verzeichnis.
    # Beispiel: project_root = E:\Projects\cyberFlow
    project_root: str = Field(
        default="",
        description=(
            "Absoluter Pfad zum Zielprojekt. "
            "Der Orchestrator schreibt Dateien und erzeugt Git-Branches ausschließlich dort. "
            "Muss in der .env gesetzt sein."
        ),
    )

    # Logging
    log_file_path: str = Field(default="logs/echo_metrics.jsonl")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @property
    def ollama_model(self) -> str:
        """Alias kept for backward-compatibility with BaseWorker."""
        return self.default_local_model

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_localhost(cls, v: str) -> str:
        parsed = urlparse(v.strip())
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"ollama_base_url muss http(s) sein, nicht '{parsed.scheme or '(leer)'}'."
            )
        host = (parsed.hostname or "").lower()
        if host not in _ALLOWED_LOCAL_HOSTS:
            raise ValueError(
                f"ollama_base_url muss lokal sein (127.0.0.1, localhost, ::1), "
                f"nicht '{host}'. Remote-Ollama ist in dieser Runtime nicht erlaubt."
            )
        return v.strip().rstrip("/")

    @field_validator("project_root")
    @classmethod
    def validate_project_root(cls, v: str) -> str:
        from pathlib import Path
        import sys

        if not v:
            raise ValueError(
                "project_root ist nicht gesetzt. "
                "Trage den absoluten Pfad zum Zielprojekt in die .env ein. "
                "Beispiel: PROJECT_ROOT=E:\\Projects\\cyberFlow"
            )

        target = Path(v).resolve()

        if not target.exists():
            raise ValueError(
                f"project_root '{target}' existiert nicht. "
                "Verzeichnis anlegen oder Pfad korrigieren."
            )

        # Sicherheitscheck: Orchestrator darf nicht sein eigenes Verzeichnis beschreiben
        orchestrator_dir = Path(sys.argv[0]).resolve().parent
        if target == orchestrator_dir or str(target).startswith(str(orchestrator_dir)):
            raise ValueError(
                f"project_root darf nicht auf das Orchestrator-Verzeichnis zeigen: '{target}'. "
                "Zielprojekt und Orchestrator müssen getrennte Verzeichnisse sein."
            )

        return str(target)

    @field_validator("bypass_human_gate")
    @classmethod
    def guard_production_bypass(cls, v: bool, info) -> bool:
        env = info.data.get("environment", "development")
        if v and env == "production":
            raise ValueError(
                "bypass_human_gate must not be True in production environment."
            )
        return v


_settings_instance: Settings | None = None
_project_root_override: str | None = None


def set_project_root_override(path: str) -> str:
    """Setzt die aktive Zielprojekt-Wurzel zur Laufzeit (validiert wie project_root)."""
    global _settings_instance, _project_root_override
    if _settings_instance is None:
        _settings_instance = Settings()
    data = _settings_instance.model_dump()
    data["project_root"] = path
    validated = Settings.model_validate(data).project_root
    _project_root_override = validated
    return validated


def get_project_root_override() -> str | None:
    return _project_root_override


def get_settings() -> Settings:
    """Singleton mit optionaler Laufzeit-Überschreibung von project_root."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    if _project_root_override:
        return _settings_instance.model_copy(update={"project_root": _project_root_override})
    return _settings_instance
