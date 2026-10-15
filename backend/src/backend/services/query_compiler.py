"""Validate structured Gemini plans and compile safe parameterized SQL."""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.schemas.query import MultiFileQueryPlan, QueryStep, SelectItem
from backend.services.query_engine import normalize_text
from backend.services.schema_catalog import catalog_columns


MAX_PLAN_STEPS = 2
MAX_FILES = 2


class InvalidQueryPlan(ValueError):
    """A validated Gemini plan refers to unavailable or incompatible data."""


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _source_key(file_path: str, sheet_name: str) -> tuple[str, str]:
    return file_path.replace("\\", "/").casefold(), sheet_name.casefold()


def _resolve_column(requested: str, columns: list[dict[str, Any]]) -> tuple[str, str]:
    normalized = normalize_text(requested).strip()
    exact = [column for column in columns if normalize_text(column["name"]).strip() == normalized]
    if exact:
        return str(exact[0]["name"]), str(exact[0]["type"])
    alias_matches = [
        column for column in columns
        if any(normalize_text(str(alias)).strip() == normalized for alias in column.get("aliases", []))
    ]
    if len(alias_matches) == 1:
        column = alias_matches[0]
        return str(column["name"]), str(column["type"])
    if len(alias_matches) > 1:
        raise InvalidQueryPlan(f"Column '{requested}' matches multiple columns")
    raise InvalidQueryPlan(f"Column '{requested}' is not present in the selected sheet")


def validate_plan(plan: MultiFileQueryPlan, catalog: dict[str, Any]) -> None:
    if len(plan.steps) > MAX_PLAN_STEPS:
        raise InvalidQueryPlan(f"A query may contain at most {MAX_PLAN_STEPS} steps")
    index = catalog_columns(catalog)
    canonical_sources = {
        _source_key(str(file_entry["file_path"]), str(sheet["name"])): (
            str(file_entry["file_path"]), str(sheet["name"])
        )
        for file_entry in catalog.get("files", [])
        for sheet in file_entry.get("sheets", [])
    }
    referenced_files: set[str] = set()
    for step in plan.steps:
        key = _source_key(step.source.file_path, step.source.sheet_name)
        columns = index.get(key)
        if columns is None:
            raise InvalidQueryPlan(
                f"Source '{step.source.file_path}' sheet '{step.source.sheet_name}' is not in the local catalog"
            )
        step.source.file_path, step.source.sheet_name = canonical_sources[key]
        if step.operation == "inspect" and not step.select:
            step.select = [
                SelectItem(column=column["name"], role="value", function=None, output_name=column["name"])
                for column in columns[:30]
            ]
        referenced_files.add(key[0])
        output_names: set[str] = set()
        for item in step.select:
            column_name, column_type = _resolve_column(item.column, columns)
            item.column = column_name
            if item.role == "aggregate" and item.function in {"sum", "average"} and column_type != "number":
                raise InvalidQueryPlan(f"Column '{column_name}' is not numeric")
            output_name = item.output_name or (
                column_name if item.role != "aggregate" else f"{item.function}({column_name})"
            )
            if output_name in output_names:
                raise InvalidQueryPlan(f"Duplicate result column '{output_name}'")
            item.output_name = output_name
            output_names.add(output_name)
        for query_filter in step.filters:
            column_name, column_type = _resolve_column(query_filter.column, columns)
            query_filter.column = column_name
            if query_filter.operator in {"greater_than", "greater_or_equal", "less_than", "less_or_equal"} and column_type not in {"number", "date"}:
                raise InvalidQueryPlan(f"Comparison filter requires a number or date column: '{column_name}'")
            if query_filter.operator == "between" and column_type not in {"number", "date"}:
                raise InvalidQueryPlan(f"between filter requires a number or date column: '{column_name}'")
            if column_type == "date":
                values = query_filter.values or ([query_filter.value] if query_filter.value is not None else [])
                for value in values:
                    try:
                        date.fromisoformat(value)
                    except ValueError as error:
                        raise InvalidQueryPlan(f"Date filter for '{column_name}' must use YYYY-MM-DD") from error
        for sort_item in step.order_by:
            if sort_item.column not in output_names:
                raise InvalidQueryPlan(f"Sort column '{sort_item.column}' is not in the step output")
    if len(referenced_files) > MAX_FILES:
        raise InvalidQueryPlan(f"A query may use at most {MAX_FILES} files")
    if plan.combine.operation == "none" and len(plan.steps) != 1:
        raise InvalidQueryPlan("A plan with multiple steps must combine them")
    if plan.combine.operation != "none" and len(plan.steps) != 2:
        raise InvalidQueryPlan("A combine plan must contain exactly two steps")
    if plan.combine.operation == "join":
        by_id = {step.id: step for step in plan.steps}
        left = _step_output_types(by_id[plan.combine.left_step or ""], catalog)
        right = _step_output_types(by_id[plan.combine.right_step or ""], catalog)
        if plan.combine.left_column not in left or plan.combine.right_column not in right:
            raise InvalidQueryPlan("Join keys must be output columns of their respective steps")
        left_type = left[plan.combine.left_column or ""]
        right_type = right[plan.combine.right_column or ""]
        if left_type != right_type and "unknown" not in {left_type, right_type}:
            raise InvalidQueryPlan("Join keys have incompatible column types")
        right_visible = [column for column in right if column != plan.combine.right_column]
        duplicates = set(left).intersection(right_visible)
        if duplicates:
            raise InvalidQueryPlan("Join output has duplicate columns: " + ", ".join(sorted(duplicates)))
    if plan.combine.operation == "union":
        by_id = {step.id: step for step in plan.steps}
        left = _step_output_types(by_id[plan.combine.left_step or ""], catalog)
        right = _step_output_types(by_id[plan.combine.right_step or ""], catalog)
        if list(left) != list(right):
            raise InvalidQueryPlan("Union steps must return columns with the same names and order")
        for column in left:
            if left[column] != right[column] and "unknown" not in {left[column], right[column]}:
                raise InvalidQueryPlan(f"Union column '{column}' has incompatible types")
    final_columns = _final_output_columns(plan)
    if plan.display.columns:
        missing = [column for column in plan.display.columns if column not in final_columns]
        if missing:
            raise InvalidQueryPlan(f"Display columns are not present in the result: {', '.join(missing)}")


def _step_output_columns(step: QueryStep) -> list[str]:
    if step.operation == "inspect" and not step.select:
        return []
    return [
        item.output_name or (
            item.column if item.role != "aggregate" else f"{item.function}({item.column})"
        )
        for item in step.select
    ]


def _step_output_types(step: QueryStep, catalog: dict[str, Any]) -> dict[str, str]:
    index = catalog_columns(catalog)
    columns = index[_source_key(step.source.file_path, step.source.sheet_name)]
    source_types = {column["name"]: str(column["type"]) for column in columns}
    output: dict[str, str] = {}
    for item in step.select:
        name = item.output_name or item.column
        if item.role == "aggregate" and item.function in {"sum", "count", "average"}:
            output[name] = "number"
        else:
            output[name] = source_types.get(item.column, "unknown")
    return output


def _final_output_columns(plan: MultiFileQueryPlan) -> list[str]:
    by_id = {step.id: step for step in plan.steps}
    if plan.combine.operation == "none":
        return _step_output_columns(plan.steps[0])
    left = by_id[plan.combine.left_step or ""]
    right = by_id[plan.combine.right_step or ""]
    if plan.combine.operation == "union":
        return _step_output_columns(left)
    return _step_output_columns(left) + [
        column for column in _step_output_columns(right) if column != plan.combine.right_column
    ]


def _filter_value(value: str, column_type: str) -> Any:
    if column_type == "number":
        try:
            return float(value.replace(",", ""))
        except ValueError as error:
            raise InvalidQueryPlan(f"Invalid number filter value '{value}'") from error
    if column_type == "date":
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise InvalidQueryPlan("Date filter values must use YYYY-MM-DD") from error
    if column_type == "boolean":
        if value.casefold() not in {"true", "false"}:
            raise InvalidQueryPlan("Boolean filter values must be true or false")
        return value.casefold() == "true"
    return value


def compile_step(step: QueryStep, relation: str, columns: list[dict[str, Any]]) -> tuple[str, list[Any]]:
    projections: list[str] = []
    group_columns: list[str] = []
    for item in step.select:
        source = _quote(item.column)
        output = _quote(item.output_name or item.column)
        if item.role == "aggregate":
            function = {"sum": "SUM", "count": "COUNT", "average": "AVG", "min": "MIN", "max": "MAX"}[item.function or "count"]
            projections.append(f"{function}({source}) AS {output}")
        elif item.role == "group_by":
            projections.append(f"{source} AS {output}")
            group_columns.append(source)
        else:
            projections.append(f"{source} AS {output}")

    if step.operation == "inspect" and not projections:
        projections = ["*"]
    if step.operation == "distinct":
        distinct = "DISTINCT "
    else:
        distinct = ""
    clauses = [f"SELECT {distinct}{', '.join(projections)} FROM {_quote(relation)}"]
    parameters: list[Any] = []
    conditions: list[str] = []
    types_by_name = {column["name"]: column["type"] for column in columns}
    op_sql = {
        "equals": "=", "not_equals": "<>", "greater_than": ">",
        "greater_or_equal": ">=", "less_than": "<", "less_or_equal": "<=",
    }
    for item in step.filters:
        column = _quote(item.column)
        kind = types_by_name[item.column]
        if item.operator in op_sql:
            conditions.append(f"{column} {op_sql[item.operator]} ?")
            parameters.append(_filter_value(item.value or "", kind))
        elif item.operator == "contains":
            conditions.append(f"strpos(lower(CAST({column} AS VARCHAR)), lower(?)) > 0")
            parameters.append(item.value or "")
        elif item.operator == "in":
            values = item.values or []
            conditions.append(f"{column} IN ({', '.join('?' for _ in values)})")
            parameters.extend(_filter_value(value, kind) for value in values)
        elif item.operator == "between":
            values = item.values or []
            if kind == "date":
                if date.fromisoformat(values[0]) > date.fromisoformat(values[1]):
                    raise InvalidQueryPlan(f"Date range for '{item.column}' is reversed")
            elif kind == "number":
                if _filter_value(values[0], kind) > _filter_value(values[1], kind):
                    raise InvalidQueryPlan(f"Numeric range for '{item.column}' is reversed")
            conditions.append(f"{column} BETWEEN ? AND ?")
            parameters.extend(_filter_value(value, kind) for value in values)
        elif item.operator == "is_empty":
            conditions.append(f"({column} IS NULL OR trim(CAST({column} AS VARCHAR)) = '')")
        elif item.operator == "is_not_empty":
            conditions.append(f"({column} IS NOT NULL AND trim(CAST({column} AS VARCHAR)) <> '')")
    if conditions:
        clauses.append("WHERE " + " AND ".join(conditions))
    if group_columns:
        clauses.append("GROUP BY " + ", ".join(group_columns))
    if step.order_by:
        ordering = ", ".join(f"{_quote(item.column)} {item.direction.upper()}" for item in step.order_by)
        clauses.append(f"ORDER BY {ordering}")
    clauses.append("LIMIT ?")
    parameters.append(step.limit)
    return " ".join(clauses), parameters
