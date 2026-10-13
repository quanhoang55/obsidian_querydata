"""Small async client for the Obsidian Local REST API."""

from __future__ import annotations

from pathlib import PurePosixPath
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

import httpx

from backend.config import Settings, get_settings


class ObsidianClient:
    """Authenticated client for a locally hosted Obsidian REST API.

    Obsidian's default local API uses a self-signed certificate. Certificate
    verification is disabled for this local connection; use a trusted CA if
    the API is exposed beyond the local machine.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.obsidian_url or not self._settings.obsidian_key:
            raise ValueError("Obsidian is not configured; set OBSIDIAN_URL and OBSIDIAN_KEY")
        self._client = httpx.AsyncClient(
            base_url=self._settings.obsidian_url,
            headers={"Authorization": f"Bearer {self._settings.obsidian_key}"},
            timeout=self._settings.request_timeout,
            verify=False,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        """Return the REST plugin's root status response."""
        response = await self._client.get("/")
        response.raise_for_status()
        return response.json()

    async def search(self, query: str, context_length: int = 100) -> Any:
        """Run a full-text search across the vault."""
        response = await self._client.post(
            "/search/simple/",
            params={"query": query, "contextLength": context_length},
        )
        response.raise_for_status()
        return response.json()

    async def list_tags(self) -> Any:
        """Return the tag counts reported by Obsidian."""
        response = await self._client.get("/tags/")
        response.raise_for_status()
        return response.json()

    async def read_file(self, vault_path: str) -> str:
        """Read a vault file by its vault-relative path."""
        return (await self.read_file_bytes(vault_path)).decode("utf-8")

    async def read_file_bytes(self, vault_path: str) -> bytes:
        """Read a vault file without decoding binary formats such as XLSX."""
        normalized = vault_path.replace("\\", "/")
        if (
            not normalized
            or normalized.startswith("/")
            or "\x00" in normalized
            or any(part in {"", ".", ".."} for part in normalized.split("/"))
        ):
            raise ValueError("vault_path must be a non-empty path inside the vault")
        encoded_path = quote(normalized, safe="/")
        response = await self._client.get(f"/vault/{encoded_path}")
        response.raise_for_status()
        return response.content

    async def list_supported_files(self) -> list[str]:
        """Recursively list Markdown and Excel files in the vault."""
        pending = [""]
        visited: set[str] = set()
        supported: set[str] = set()

        while pending:
            directory = pending.pop()
            if directory in visited:
                continue
            visited.add(directory)
            suffix = f"{quote(directory, safe='/')}/" if directory else ""
            response = await self._client.get(f"/vault/{suffix}")
            response.raise_for_status()
            payload = response.json()
            entries = payload.get("files") if isinstance(payload, dict) else payload
            if not isinstance(entries, list):
                raise ValueError("Obsidian returned an invalid vault directory listing")

            for entry in entries:
                if not isinstance(entry, str) or not entry.strip():
                    continue
                is_directory = entry.endswith("/")
                name = entry.rstrip("/").replace("\\", "/")
                if name.startswith("/") or any(part in {".", ".."} for part in name.split("/")):
                    continue
                if directory and not name.startswith(f"{directory}/"):
                    name = f"{directory}/{name}"
                if is_directory:
                    pending.append(name)
                elif PurePosixPath(name).suffix.lower() in {".md", ".xlsx"}:
                    supported.add(name)

        return sorted(supported, key=str.casefold)

