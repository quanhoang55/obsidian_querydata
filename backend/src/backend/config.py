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
    obsidian_url: str
    obsidian_key: str
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    port: int = 8000
    request_timeout: float = 20.0
    gemini_timeout: float = 90.0

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        file_values = _read_env_file(env_file or BACKEND_DIR / ".env")
        # Real process environment always takes precedence over the file.
        values = {**file_values, **os.environ}
        url = values.get("OBSIDIAN_URL", "").strip().rstrip("/")
        key = values.get("OBSIDIAN_KEY", "").strip()
        if url and not url.startswith(("https://", "http://")):
            raise ValueError("OBSIDIAN_URL must start with http:// or https://")
        try:
            port = int(values.get("PORT", "8000"))
        except ValueError as exc:
            raise ValueError("PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        try:
            gemini_timeout = float(values.get("GEMINI_TIMEOUT", "90"))
        except ValueError as exc:
            raise ValueError("GEMINI_TIMEOUT must be a number of seconds") from exc
        if gemini_timeout <= 0:
            raise ValueError("GEMINI_TIMEOUT must be greater than zero")
        return cls(
            obsidian_url=url,
            obsidian_key=key,
            gemini_api_key=values.get("GEMINI_API_KEY", "").strip(),
            gemini_model=values.get("GEMINI_MODEL", "gemini-2.5-flash").strip(),
            port=port,
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
