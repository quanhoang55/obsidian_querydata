"""Orchestrate schema discovery, Gemini planning, and local SQL execution."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.clients.gemini import GeminiClient, GeminiInvalidResponseError
from backend.config import Settings
from backend.schemas.query import CombinePlan, MultiFileQueryPlan
from backend.services.local_vault import LocalVault, VaultNotSelectedError
from backend.services.query_compiler import InvalidQueryPlan, validate_plan
from backend.services.query_executor import execute_plan
from backend.services.query_engine import normalize_text
from backend.services.schema_catalog import build_schema_catalog


class VaultConfigurationError(Exception):
    """A local vault folder has not been selected or is unavailable."""


async def query_files(prompt: str, settings: Settings) -> dict[str, Any]:
    """Interpret a prompt against the local schema catalog and execute its plan."""
    try:
        vault = LocalVault(settings.vault_path)
    except VaultNotSelectedError as error:
        raise VaultConfigurationError(str(error)) from error
    catalog = await asyncio.to_thread(build_schema_catalog, vault)
    relevant_catalog = _catalog_for_prompt(prompt, catalog)

    gemini = GeminiClient(settings)
    try:
        plan = await gemini.create_query_plan(prompt, relevant_catalog["files"])
    except GeminiInvalidResponseError as error:
        # Malformed model output is a clarification case, never an executable plan.
        question = (
            f"I understood your request as: ‘{prompt}’. Is that interpretation correct? "
            "Please confirm and specify the exact file, column, or calculation if you meant a particular one."
        )
        clarification_plan = MultiFileQueryPlan(
            status="clarification_required",
            clarification_needed=True,
            clarification_question=question,
        )
        return _clarification_response(
            prompt,
            clarification_plan,
            [*catalog.get("warnings", []), {"file": "Gemini", "message": str(error)}],
        )
    finally:
        await gemini.close()

    if plan.status == "clarification_required":
        return _clarification_response(prompt, plan, catalog.get("warnings", []))
    try:
        validate_plan(plan, catalog)
    except InvalidQueryPlan as error:
        return _clarification_response(prompt, plan, [
            *catalog.get("warnings", []),
            {"file": "query", "message": str(error)},
        ], question="I could not safely map the request to the available file schemas. Please clarify the file, sheet, or column.")

    result = await asyncio.to_thread(execute_plan, vault, plan, catalog)
    result["query"] = prompt
    return result


def _catalog_for_prompt(prompt: str, catalog: dict[str, Any], max_sheets: int = 40) -> dict[str, Any]:
    """Focus Gemini context on prompt-matching sheets while keeping explicit files."""
    available = catalog.get("files", [])
    prompt_path = prompt.replace("\\", "/").casefold()
    selected = [
        item for item in available
        if str(item.get("file_path", "")).replace("\\", "/").casefold() in prompt_path
    ]
    if selected:
        return {"files": selected, "warnings": catalog.get("warnings", [])}

    tokens = {
        token for token in normalize_text(prompt).split()
        if len(token) > 1 and token not in {"tat", "cac", "trong", "cua", "theo", "ngay", "thang", "nam", "from", "with", "the", "all", "list"}
    }
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    index = 0
    for file_entry in available:
        for sheet in file_entry.get("sheets", []):
            terms = set(normalize_text(
                str(file_entry.get("file_path", "")) + " " + str(sheet.get("name", "")) + " " + " ".join(
                    str(value)
                    for column in sheet.get("columns", [])
                    for value in [column.get("name", ""), *column.get("aliases", [])]
                )
            ).split())
            score = len(tokens.intersection(terms))
            ranked.append((score, index, {"file_path": file_entry["file_path"], "sheets": [sheet]}))
            index += 1
    if len(ranked) <= max_sheets:
        selected_sheets = [item for _, _, item in ranked]
    else:
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected_sheets = [item for _, _, item in ranked[:max_sheets]]
    merged: dict[str, dict[str, Any]] = {}
    for item in selected_sheets:
        merged.setdefault(item["file_path"], {"file_path": item["file_path"], "sheets": []})
        merged[item["file_path"]]["sheets"].extend(item["sheets"])
    return {"files": list(merged.values()), "warnings": catalog.get("warnings", [])}


def _clarification_response(
    prompt: str,
    plan: MultiFileQueryPlan,
    warnings: list[dict[str, str]],
    question: str | None = None,
) -> dict[str, Any]:
    clarification_question = question or plan.clarification_question or "Please clarify which columns or files to query."
    response_plan = plan
    if plan.status == "ready":
        response_plan = plan.model_copy(update={
            "status": "clarification_required",
            "steps": [],
            "combine": CombinePlan(
                operation="none", left_step=None, right_step=None,
                left_column=None, right_column=None, join_type=None,
            ),
            "clarification_needed": True,
            "clarification_question": clarification_question,
        })
    return {
        "status": "clarification_required",
        "query": prompt,
        "answer": clarification_question,
        "plan": response_plan.model_dump(mode="json", by_alias=True),
        "display": response_plan.display.model_dump(mode="json"),
        "result": {"columns": [], "rows": [], "row_count": 0, "truncated": False},
        "step_results": [],
        "sources": [],
        "warnings": warnings,
    }
