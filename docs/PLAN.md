# Gemini Query Layer: Implementation Plan

## Goal

Convert a natural language prompt into a validated JSON query intent with Gemini, then execute aggregate, distinct-value, or inspect operations against Obsidian Markdown and Excel tables locally.

## Query Plan Contract

`POST /api/v1/query` continues to accept `{"prompt": "..."}`. Gemini returns a JSON object matching `QueryPlan`:

```json
{
  "operation": "distinct",
  "metric": null,
  "target_column": "Người bán",
  "display_columns": ["Người bán"],
  "person": "Lan",
  "start_date": "2026-10-05",
  "end_date": "2026-10-11",
  "group_by": "none",
  "file_path": null,
  "clarification_needed": false,
  "clarification_question": null
}
```

- `operation`: `aggregate`, `distinct`, or `inspect`.
- `metric`: `sum`, `count`, or `average` for aggregate operations; null otherwise.
- `target_column`: the column to aggregate or enumerate; resolved against workbook headers locally.
- `display_columns`: only the relevant fields the frontend should highlight.
- `person`, `start_date`, and `end_date`: nullable filters; dates are ISO `YYYY-MM-DD`.
- `group_by`: `day`, `week`, `month`, `person`, or `none`.
- `file_path`: optionally limit local parsing to a requested vault-relative `.md` or `.xlsx` path.
- `person`, date range, and grouping remain optional filters for supported sales-table headers.
- `clarification_needed` and `clarification_question`: indicate that the prompt is ambiguous or unsupported.
- Reject unknown fields, unsupported enum values, invalid dates, and reversed date ranges before execution.
- Keep the Gemini wire schema within the API's supported schema fields; enforce strict extra-field rejection locally with Pydantic.

## Request Flow

1. Load supported vault documents and extract file names, sheet names, and column headers locally.
2. Send the prompt, current date, and header-only schema metadata to Gemini. Request JSON constrained by the `QueryPlan` schema. Do not send workbook rows or chat history.
3. Parse and validate the response into `QueryPlan`.
4. If clarification is needed, return a clarification response.
5. Parse rows locally and execute the plan’s operation, column selection, and filters.
6. Return the original prompt, serialized `query_plan`, a concise answer, a display-ready selection, and warnings. Never send vault contents to Gemini.

## Failure Behavior

- Missing Gemini or Obsidian configuration: `503` with a configuration message.
- Gemini timeout: `504`.
- Gemini connection failures and provider rejections return a safe diagnostic; provider responses include status/code while redacting the configured key.
- Malformed/invalid JSON: `502`; do not scan Obsidian.
- Obsidian connection failure: preserve the existing `503`/`504` mappings; invalid upstream data remains `502`.
- Valid plan with no matching rows: `200` and `status: "no_results"`.
- Clarification response: `200` and `status: "clarification_required"`, without vault access.

## Implementation Checklist

- [x] Add the typed Pydantic `QueryPlan` and use it as Gemini’s structured response schema.
- [x] Validate model output before passing it to local query execution.
- [x] Send Gemini locally extracted file, worksheet, and header metadata so it can ground column selection; keep table row values local.
- [x] Execute metrics, filters, and grouping locally and include the serialized plan in the response.
- [x] Keep prompts as the only user data sent to Gemini; keep vault content and chat history local.
- [x] Map Gemini and Obsidian failures to clear HTTP errors.
- [x] Add focused tests for schema validation, Gemini JSON handling, clarification short-circuiting, and local aggregation.
- [x] Align the privacy rule and backend README with the Gemini flow.

## Verification

Run from `backend/`:

```sh
PYTHONPATH=src uv run python -m unittest discover -s tests -v
```

Acceptance: a valid sales prompt produces a validated plan and a result computed from local vault rows; an ambiguous or unsupported prompt asks for clarification before any vault reads; malformed Gemini output produces an error and never triggers a vault scan.

## Configuration

`GEMINI_API_KEY` is required for `POST /api/v1/query`. `GEMINI_MODEL` is optional and defaults to `gemini-2.5-flash`. `GEMINI_TIMEOUT` is optional and defaults to 90 seconds. Obsidian access is required to provide local schema metadata and query data.
