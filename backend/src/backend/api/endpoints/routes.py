"""FastAPI endpoint definitions for config, vault, and query APIs."""

from __future__ import annotations

import ipaddress
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from io import BytesIO
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Path as PathParam
from fastapi.encoders import jsonable_encoder
from openpyxl import load_workbook
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from backend.config import Settings, get_settings, set_runtime_settings
from backend.clients.gemini import GeminiClientError, GeminiTimeoutError
from backend.clients.obsidian import ObsidianClient
from backend.services.query_service import ObsidianConfigurationError, query_sales


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ConfigResponse(BaseModel):
    obsidian_url: str | None
    obsidian_key_configured: bool
    gemini_api_key_configured: bool
    port: int


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obsidian_url: str | None = None
    obsidian_key: SecretStr | None = Field(default=None, min_length=1)

    @field_validator("obsidian_key", mode="before")
    @classmethod
    def trim_api_key(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("obsidian_url")
    @classmethod
    def validate_local_obsidian_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("obsidian_url must be a valid HTTP or HTTPS URL")
        if parsed.path not in {"", "/"}:
            raise ValueError("obsidian_url must point to the REST API host, without a path")
        try:
            parsed.port
        except ValueError as error:
            raise ValueError("obsidian_url contains an invalid port") from error
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("obsidian_url cannot contain credentials, a query, or a fragment")
        try:
            is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            is_loopback = parsed.hostname.lower() == "localhost"
        if not is_loopback:
            raise ValueError("obsidian_url must point to localhost or a loopback address")
        return value

    @model_validator(mode="after")
    def require_an_update(self) -> "ConfigUpdate":
        if self.obsidian_url is None and self.obsidian_key is None:
            raise ValueError("Provide obsidian_url and/or obsidian_key")
        return self


class VaultFilesResponse(BaseModel):
    files: list[str]
    total: int


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    context_length: int = Field(default=100, ge=0, le=1000)

    @field_validator("query")
    @classmethod
    def trim_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=2000)

    @field_validator("prompt")
    @classmethod
    def trim_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be blank")
        return value


router = APIRouter()


def _public_config(settings: Settings) -> ConfigResponse:
    return ConfigResponse(
        obsidian_url=settings.obsidian_url or None,
        obsidian_key_configured=bool(settings.obsidian_key),
        gemini_api_key_configured=bool(settings.gemini_api_key),
        port=settings.port,
    )


def _require_obsidian_settings() -> Settings:
    settings = get_settings()
    if not settings.obsidian_url or not settings.obsidian_key:
        raise HTTPException(
            status_code=503,
            detail="Configure OBSIDIAN_URL and OBSIDIAN_KEY with PUT /api/v1/config first",
        )
    return settings


def _obsidian_http_error(error: httpx.HTTPStatusError) -> HTTPException:
    status_code = error.response.status_code
    if status_code == 404:
        return HTTPException(status_code=404, detail="Vault file or directory not found")
    if status_code == 401:
        return HTTPException(status_code=502, detail="Obsidian rejected the configured API key")
    return HTTPException(status_code=502, detail="Obsidian REST API request failed")


def _obsidian_connection_error(error: httpx.RequestError) -> HTTPException:
    if isinstance(error, httpx.TimeoutException):
        return HTTPException(status_code=504, detail="Obsidian REST API request timed out")
    return HTTPException(status_code=503, detail="Could not connect to the Obsidian REST API")


def _validate_vault_file_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    segments = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or "\x00" in normalized
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise HTTPException(status_code=400, detail="path must be a valid path inside the vault")
    if not normalized.lower().endswith((".md", ".xlsx")):
        raise HTTPException(status_code=415, detail="Only .md and .xlsx files are supported")
    return normalized


def _excel_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time, timedelta)):
        return jsonable_encoder(value)
    return value


def _upstream_results(payload: Any, field: str) -> list[Any]:
    results = payload.get(field, []) if isinstance(payload, dict) else payload
    if not isinstance(results, list):
        raise ValueError(f"Obsidian response did not contain a {field} list")
    return results


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Report that the FastAPI process is responding."""
    return HealthResponse(status="ok")


@router.get("/api/v1/config", response_model=ConfigResponse, tags=["config"])
async def read_config() -> ConfigResponse:
    """Return connection settings without exposing the API key."""
    return _public_config(get_settings())


@router.put("/api/v1/config", response_model=ConfigResponse, tags=["config"])
async def update_config(payload: ConfigUpdate) -> ConfigResponse:
    """Update Obsidian connection settings for this running process."""
    current = get_settings()
    updated = replace(
        current,
        obsidian_url=payload.obsidian_url or current.obsidian_url,
        obsidian_key=(
            payload.obsidian_key.get_secret_value()
            if payload.obsidian_key is not None
            else current.obsidian_key
        ),
    )
    if not updated.obsidian_url or not updated.obsidian_key:
        raise HTTPException(
            status_code=422,
            detail="Both obsidian_url and obsidian_key must be configured before vault access",
        )
    set_runtime_settings(updated)
    return _public_config(updated)


@router.get("/api/v1/vault/files", response_model=VaultFilesResponse, tags=["vault"])
async def list_vault_files() -> VaultFilesResponse:
    """List supported Markdown and Excel files recursively."""
    settings = _require_obsidian_settings()
    try:
        async with ObsidianClient(settings) as obsidian:
            files = await obsidian.list_supported_files()
    except httpx.HTTPStatusError as error:
        raise _obsidian_http_error(error) from error
    except httpx.RequestError as error:
        raise _obsidian_connection_error(error) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=502, detail="Obsidian returned an invalid file listing") from error
    return VaultFilesResponse(files=files, total=len(files))


@router.get("/api/v1/vault/files/{path:path}", tags=["vault"])
async def read_vault_file(
    path: str = PathParam(..., description="Vault-relative path to an .md or .xlsx file"),
) -> dict[str, Any]:
    """Read a Markdown file or return workbook sheets as JSON rows."""
    vault_path = _validate_vault_file_path(path)
    settings = _require_obsidian_settings()
    try:
        async with ObsidianClient(settings) as obsidian:
            content = await obsidian.read_file_bytes(vault_path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except httpx.HTTPStatusError as error:
        raise _obsidian_http_error(error) from error
    except httpx.RequestError as error:
        raise _obsidian_connection_error(error) from error

    if vault_path.lower().endswith(".md"):
        try:
            markdown = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=422, detail="Markdown file is not valid UTF-8") from error
        return {"path": vault_path, "type": "markdown", "content": markdown}

    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        sheets = [
            {
                "name": worksheet.title,
                "rows": [
                    [_excel_value(value) for value in row]
                    for row in worksheet.iter_rows(values_only=True)
                ],
            }
            for worksheet in workbook.worksheets
        ]
        workbook.close()
    except Exception as error:
        raise HTTPException(status_code=422, detail="Excel file could not be parsed") from error
    return {"path": vault_path, "type": "excel", "sheets": sheets}


@router.post("/api/v1/vault/search", tags=["vault"])
async def search_vault(payload: SearchRequest) -> dict[str, Any]:
    """Search note text through Obsidian's full-text search endpoint."""
    settings = _require_obsidian_settings()
    try:
        async with ObsidianClient(settings) as obsidian:
            upstream = await obsidian.search(payload.query, payload.context_length)
        results = _upstream_results(upstream, "results")
    except httpx.HTTPStatusError as error:
        raise _obsidian_http_error(error) from error
    except httpx.RequestError as error:
        raise _obsidian_connection_error(error) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=502, detail="Obsidian returned an invalid search response") from error
    return {"query": payload.query, "results": results, "total": len(results)}


@router.post("/api/v1/query", tags=["query"])
async def query_vault(payload: QueryRequest) -> dict[str, Any]:
    """Interpret the prompt, then aggregate matching local vault rows."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Set GEMINI_API_KEY to enable natural language queries")
    try:
        return await query_sales(payload.prompt, settings)
    except ObsidianConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except GeminiTimeoutError as error:
        raise HTTPException(status_code=504, detail="Gemini query interpretation timed out") from error
    except GeminiClientError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except httpx.HTTPStatusError as error:
        raise _obsidian_http_error(error) from error
    except httpx.RequestError as error:
        raise _obsidian_connection_error(error) from error
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=422, detail="A Markdown file is not valid UTF-8") from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail="Obsidian returned invalid vault data") from error


@router.get("/api/v1/query/examples", tags=["query"])
async def query_examples() -> dict[str, list[str]]:
    """Return sample prompts supported by the prototype query parser."""
    return {
        "examples": [
            "Tổng doanh số tháng này",
            "Tổng doanh số của Nam từ ngày 01/05/2026 đến 10/05/2026",
            "Doanh số của Lan trong tuần trước",
        ]
    }


@router.get("/api/v1/tags", tags=["vault"])
async def list_vault_tags() -> dict[str, Any]:
    """Return Obsidian tag names and usage counts."""
    settings = _require_obsidian_settings()
    try:
        async with ObsidianClient(settings) as obsidian:
            upstream = await obsidian.list_tags()
        tags = _upstream_results(upstream, "tags")
    except httpx.HTTPStatusError as error:
        raise _obsidian_http_error(error) from error
    except httpx.RequestError as error:
        raise _obsidian_connection_error(error) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=502, detail="Obsidian returned an invalid tag response") from error

    normalized_tags = []
    for tag in tags:
        if isinstance(tag, str):
            normalized_tags.append({"name": tag.removeprefix("#"), "count": 0})
        elif isinstance(tag, dict) and isinstance(tag.get("name"), str):
            raw_count = tag.get("count", tag.get("tagCount", 0))
            count = raw_count if isinstance(raw_count, int) and raw_count >= 0 else 0
            normalized_tags.append(
                {
                    "name": tag["name"].removeprefix("#"),
                    "count": count,
                }
            )
    normalized_tags.sort(key=lambda tag: tag["name"].casefold())
    return {"tags": normalized_tags, "total": len(normalized_tags)}


