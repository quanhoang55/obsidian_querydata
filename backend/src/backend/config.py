"""Application settings loaded from environment variables and backend/.env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
_runtime_settings: "Settings | None" = None


def _read_env_file(path: Path) -> dict[str, str]:
    """Read a small dotenv file without requiring a third-party parser."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", maxsplit=1)[0].rstrip()
        values[key.strip()] = value
    return values


@dataclass(frozen=True, slots=True)
class Settings:
    vault_path: str | None = None
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    port: int = 8000
    gemini_timeout: float = 90.0

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        file_values = _read_env_file(env_file or BACKEND_DIR / ".env")
        # Real process environment always takes precedence over the file.
        values = {**file_values, **os.environ}
        # Desktop settings saved through the Settings API override development
        # defaults from .env and are stored per user outside the app bundle.
        from backend.services.app_settings_store import get_api_key, read_preferences

        preferences = read_preferences()
        stored_key = get_api_key()
        try:
            gemini_timeout = float(preferences.get("gemini_timeout", values.get("GEMINI_TIMEOUT", "90")))
        except ValueError as exc:
            raise ValueError("GEMINI_TIMEOUT must be a number of seconds") from exc
        if gemini_timeout <= 0:
            raise ValueError("GEMINI_TIMEOUT must be greater than zero")
        return cls(
            vault_path=str(preferences.get("vault_path") or "").strip() or None,
            gemini_api_key=(
                stored_key
                or ("" if preferences.get("gemini_api_key_cleared") else values.get("GEMINI_API_KEY", "").strip())
            ),
            gemini_model=str(preferences.get("gemini_model", values.get("GEMINI_MODEL", "gemini-2.5-flash"))).strip(),
            port=int(values.get("OBSIDIANQUERY_PORT", "8000")),
            gemini_timeout=gemini_timeout,
        )


def set_runtime_settings(settings: Settings) -> None:
    """Replace settings for this running process without writing credentials to disk."""
    global _runtime_settings
    _runtime_settings = settings
    get_settings.cache_clear()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings, cached for the application lifetime."""
    return _runtime_settings or Settings.from_env()
