"""Validated structured query plans returned by Gemini."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class QuerySource(StrictModel):
    file_path: str = Field(min_length=1, max_length=500)
    sheet_name: str = Field(min_length=1, max_length=200)


class SelectItem(StrictModel):
    column: str = Field(min_length=1, max_length=200)
    role: Literal["value", "group_by", "aggregate"]
    function: Literal["sum", "count", "average", "min", "max"] | None = None
    output_name: str | None = Field(default=None, alias="as", max_length=200)

    @model_validator(mode="after")
    def validate_function(self) -> "SelectItem":
        if self.role == "aggregate" and self.function is None:
            raise ValueError("aggregate selections require a function")
        if self.role != "aggregate" and self.function is not None:
            raise ValueError("only aggregate selections may define a function")
        return self


class QueryFilter(StrictModel):
    column: str = Field(min_length=1, max_length=200)
    operator: Literal[
        "equals", "not_equals", "contains", "in", "between",
        "greater_than", "greater_or_equal", "less_than", "less_or_equal",
        "is_empty", "is_not_empty",
    ]
    value: str | None = None
    values: list[str] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_values(self) -> "QueryFilter":
        if self.operator in {"is_empty", "is_not_empty"}:
            if self.value is not None or self.values is not None:
                raise ValueError("empty checks do not accept values")
        elif self.operator in {"in", "between"}:
            if self.values is None or not self.values:
                raise ValueError(f"{self.operator} requires values")
            if self.operator == "between" and len(self.values) != 2:
                raise ValueError("between requires exactly two values")
            if self.value is not None:
                raise ValueError(f"{self.operator} uses values, not value")
        elif self.value is None or self.values is not None:
            raise ValueError(f"{self.operator} requires one value")
        return self


class SortItem(StrictModel):
    column: str = Field(min_length=1, max_length=200)
    direction: Literal["asc", "desc"]


class QueryStep(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    source: QuerySource
    operation: Literal["select", "distinct", "aggregate", "inspect"]
    select: list[SelectItem] = Field(default_factory=list, max_length=30)
    filters: list[QueryFilter] = Field(default_factory=list, max_length=50)
    order_by: list[SortItem] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=500, ge=1, le=5000)

    @model_validator(mode="after")
    def validate_operation(self) -> "QueryStep":
        if self.operation != "inspect" and not self.select:
            raise ValueError("select items are required for this operation")
        if self.operation == "distinct" and len(self.select) != 1:
            raise ValueError("distinct requires exactly one selected column")
        if self.operation == "aggregate" and not any(item.role == "aggregate" for item in self.select):
            raise ValueError("aggregate requires at least one aggregate selection")
        if self.operation == "aggregate" and any(item.role == "value" for item in self.select):
            raise ValueError("aggregate selections must be group_by or aggregate")
        if self.operation != "aggregate" and any(item.role == "aggregate" for item in self.select):
            raise ValueError("aggregate selections require operation=aggregate")
        return self


class CombinePlan(StrictModel):
    operation: Literal["none", "union", "join"] = "none"
    left_step: str | None = None
    right_step: str | None = None
    left_column: str | None = None
    right_column: str | None = None
    join_type: Literal["inner", "left", "full"] | None = None


class DisplayPlan(StrictModel):
    title: str = Field(default="Kết quả truy vấn", min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=500)
    columns: list[str] = Field(default_factory=list, max_length=30)
    visualization: Literal["text", "table", "bar", "line", "number"] = "text"


class MultiFileQueryPlan(StrictModel):
    """Gemini's full structured execution plan. It contains no executable SQL."""

    status: Literal["ready", "clarification_required"]
    steps: list[QueryStep] = Field(default_factory=list, max_length=2)
    combine: CombinePlan = Field(default_factory=CombinePlan)
    display: DisplayPlan = Field(default_factory=DisplayPlan)
    clarification_needed: bool = False
    clarification_question: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_plan(self) -> "MultiFileQueryPlan":
        if self.status == "clarification_required":
            if not self.clarification_question:
                raise ValueError("clarification plans require a question")
            if self.steps:
                raise ValueError("clarification plans cannot contain execution steps")
            if not self.clarification_needed:
                raise ValueError("clarification_needed must be true")
            return self

        if self.clarification_needed or self.clarification_question:
            raise ValueError("ready plans cannot request clarification")
        if not self.steps:
            raise ValueError("ready plans require at least one step")
        ids = [step.id for step in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("step ids must be unique")
        if self.combine.operation == "none":
            if any((self.combine.left_step, self.combine.right_step, self.combine.left_column,
                    self.combine.right_column, self.combine.join_type)):
                raise ValueError("combine details must be null when operation is none")
        else:
            if self.combine.left_step not in ids or self.combine.right_step not in ids:
                raise ValueError("combine steps must reference plan step ids")
            if self.combine.left_step == self.combine.right_step:
                raise ValueError("combine must reference two different steps")
            if self.combine.operation == "join":
                if not self.combine.left_column or not self.combine.right_column or not self.combine.join_type:
                    raise ValueError("join requires keys and a join type")
            elif any((self.combine.left_column, self.combine.right_column, self.combine.join_type)):
                raise ValueError("union does not accept join details")
        return self


def gemini_response_schema() -> dict[str, object]:
    """Return a compact provider schema; Pydantic performs strict validation locally."""
    string = {"type": "string"}
    select_item = {
        "type": "object",
        "properties": {
            "column": string,
            "role": {"type": "string", "enum": ["value", "group_by", "aggregate"]},
            "function": {"type": "string", "enum": ["sum", "count", "average", "min", "max"]},
            "as": string,
        },
        "required": ["column", "role"],
    }
    query_filter = {
        "type": "object",
        "properties": {
            "column": string,
            "operator": {
                "type": "string",
                "enum": [
                    "equals", "not_equals", "contains", "in", "between",
                    "greater_than", "greater_or_equal", "less_than", "less_or_equal",
                    "is_empty", "is_not_empty",
                ],
            },
            "value": string,
            "values": {"type": "array", "items": string},
        },
        "required": ["column", "operator"],
    }
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["ready", "clarification_required"]},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": string,
                        "source": {
                            "type": "object",
                            "properties": {"file_path": string, "sheet_name": string},
                            "required": ["file_path", "sheet_name"],
                        },
                        "operation": {
                            "type": "string",
                            "enum": ["select", "distinct", "aggregate", "inspect"],
                        },
                        "select": {"type": "array", "items": select_item},
                        "filters": {"type": "array", "items": query_filter},
                        "order_by": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "column": string,
                                    "direction": {"type": "string", "enum": ["asc", "desc"]},
                                },
                                "required": ["column", "direction"],
                            },
                        },
                        "limit": {"type": "integer"},
                    },
                    "required": ["id", "source", "operation", "select"],
                },
            },
            "combine": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["none", "union", "join"]},
                    "left_step": string,
                    "right_step": string,
                    "left_column": string,
                    "right_column": string,
                    "join_type": {"type": "string", "enum": ["inner", "left", "full"]},
                },
                "required": ["operation"],
            },
            "display": {
                "type": "object",
                "properties": {
                    "title": string,
                    "summary": string,
                    "columns": {"type": "array", "items": string},
                    "visualization": {
                        "type": "string",
                        "enum": ["text", "table", "bar", "line", "number"],
                    },
                },
                "required": ["title", "columns", "visualization"],
            },
            "clarification_needed": {"type": "boolean"},
            "clarification_question": string,
        },
        "required": ["status", "steps"],
    }
