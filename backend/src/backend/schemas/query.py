"""Validated intent extracted from a natural language query."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QueryPlan(BaseModel):
    """The complete, constrained query plan accepted by local execution."""

    model_config = ConfigDict(extra="forbid")

    operation: Literal["aggregate", "distinct", "inspect"]
    metric: Literal["sum", "count", "average"] | None
    target_column: str | None
    display_columns: list[str] = Field(max_length=20)
    person: str | None
    start_date: date | None
    end_date: date | None
    group_by: Literal["day", "week", "month", "person", "none"]
    file_path: str | None
    clarification_needed: bool
    clarification_question: str | None

    @model_validator(mode="after")
    def validate_range(self) -> "QueryPlan":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be earlier than or equal to end_date")
        if self.operation == "aggregate" and self.metric is None:
            raise ValueError("metric is required for aggregate operations")
        if self.operation == "distinct" and self.target_column is None:
            raise ValueError("target_column is required for distinct operations")
        if self.person is not None:
            self.person = self.person.strip() or None
        if self.target_column is not None:
            self.target_column = self.target_column.strip() or None
        self.display_columns = list(dict.fromkeys(value.strip() for value in self.display_columns if value.strip()))
        if self.clarification_question is not None:
            self.clarification_question = self.clarification_question.strip() or None
        return self


def gemini_response_schema() -> dict[str, object]:
    """Return the QueryPlan schema using fields supported by Gemini responseSchema."""
    schema = QueryPlan.model_json_schema()

    def convert(node: dict[str, object]) -> dict[str, object]:
        alternatives = node.get("anyOf")
        if isinstance(alternatives, list):
            concrete = next(
                alternative
                for alternative in alternatives
                if isinstance(alternative, dict) and alternative.get("type") != "null"
            )
            converted = convert(concrete)
            converted["nullable"] = True
            return converted

        converted = {
            key: value
            for key, value in node.items()
            if key not in {"title", "description", "additionalProperties"}
        }
        node_type = converted.get("type")
        if isinstance(node_type, str):
            converted["type"] = node_type.upper()
        if "const" in converted:
            converted["enum"] = [converted.pop("const")]
        properties = converted.get("properties")
        if isinstance(properties, dict):
            converted["properties"] = {
                name: convert(property_schema)
                for name, property_schema in properties.items()
            }
        return converted

    return convert(schema)
