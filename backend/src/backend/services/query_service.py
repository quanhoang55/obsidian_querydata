"""Interpret query prompts and execute validated plans against Obsidian data."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from backend.clients.gemini import GeminiClient
from backend.clients.obsidian import ObsidianClient
from backend.config import Settings
from backend.schemas.query import QueryPlan
from backend.services.query_engine import aggregate_sales, describe_documents, normalize_text


class ObsidianConfigurationError(Exception):
    """Obsidian credentials are needed to execute a valid query plan."""


async def query_sales(prompt: str, settings: Settings) -> dict[str, Any]:
    """Read vault schemas, interpret against them, and execute the plan locally."""
    documents = await _load_vault_documents(settings)
    available_files = describe_documents(documents)
    prompt_schemas = _schemas_for_prompt(prompt, available_files)
    gemini = GeminiClient(settings)
    try:
        plan = await gemini.create_query_plan(prompt, prompt_schemas)
    finally:
        await gemini.close()

    plan = _apply_explicit_column_wildcard(prompt, plan, prompt_schemas)
    if plan.clarification_needed:
        return _clarification_response(prompt, plan)

    result = aggregate_sales(prompt, documents, plan.model_dump(mode="json"))
    result["query_plan"] = plan.model_dump(mode="json")
    return result


def _schemas_for_prompt(
    prompt: str,
    available_files: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Keep schema context focused on an explicitly named vault file."""
    match = re.search(r"((?:[\w().-]+/)*[\w().-]+\.(?:xlsx|md))\b", prompt, re.IGNORECASE)
    if not match:
        return available_files
    requested = match.group(1).replace("\\", "/").casefold()
    selected = [
        file_info for file_info in available_files
        if str(file_info.get("file", "")).replace("\\", "/").casefold() == requested
    ]
    return selected or available_files


def _apply_explicit_column_wildcard(
    prompt: str,
    plan: QueryPlan,
    available_files: list[dict[str, object]],
) -> QueryPlan:
    """Resolve explicit header-prefix requests against real headers before execution."""
    wildcard = re.search(r"([^\s,;?*]+)\*", prompt)
    if not wildcard:
        return plan

    prefix = normalize_text(wildcard.group(1).strip("`'\""))
    columns = list(dict.fromkeys(
        str(column)
        for file_info in available_files
        if isinstance(file_info.get("sheets"), list)
        for sheet in file_info["sheets"]
        if isinstance(sheet, dict) and isinstance(sheet.get("columns"), list)
        for column in sheet["columns"]
        if normalize_text(str(column)).startswith(prefix)
    ))
    if len(columns) == 1:
        update: dict[str, Any] = {"target_column": columns[0], "display_columns": [columns[0]]}
        if plan.operation == "aggregate":
            update["operation"] = "distinct"
            update["metric"] = None
        return plan.model_copy(update=update)
    if len(columns) > 1:
        question = f"Which column do you mean: {', '.join(columns)}?"
    else:
        question = f"I couldn't find a column starting with '{wildcard.group(1)}' in the available files. Which column should I use?"
    return plan.model_copy(update={
        "clarification_needed": True,
        "clarification_question": question,
    })


def _clarification_response(prompt: str, plan: QueryPlan) -> dict[str, Any]:
    return {
        "status": "clarification_required",
        "query": prompt,
        "answer": plan.clarification_question or "Please clarify what sales data you want to query.",
        "query_plan": plan.model_dump(mode="json"),
        "files_scanned": 0,
        "rows_parsed": 0,
        "matched_rows": 0,
        "total": 0,
        "grouped_results": {},
        "data": {"columns": [], "rows": []},
        "warnings": [],
    }


async def _load_vault_documents(settings: Settings) -> list[tuple[str, str | bytes]]:
    """Fetch supported Markdown and Excel files with bounded concurrency."""
    if not settings.obsidian_url or not settings.obsidian_key:
        raise ObsidianConfigurationError("Configure OBSIDIAN_URL and OBSIDIAN_KEY before querying the vault")

    async with ObsidianClient(settings) as obsidian:
        paths = await obsidian.list_supported_files()
        semaphore = asyncio.Semaphore(8)

        async def read_document(path: str) -> tuple[str, str | bytes]:
            async with semaphore:
                content = await obsidian.read_file_bytes(path)
            if path.lower().endswith(".md"):
                return path, content.decode("utf-8")
            return path, content

        return list(await asyncio.gather(*(read_document(path) for path in paths)))
