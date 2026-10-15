# Multi-file Gemini query plan

## Purpose

This document describes the multi-file implementation of `POST /api/v1/query`. A user sends one natural-language prompt. The backend gives Gemini a catalog of local file schemas, Gemini returns a validated plan with one or two query steps, and Python runs those steps against local Excel and Markdown data.

The backend now uses a `MultiFileQueryPlan` instead of the former single-operation `QueryPlan`. The initial implementation supports one source or two independent sources combined by `union` or `join`. More complex chains of dependent steps are future work.

## Design rules

- Keep the endpoint request simple: `{"prompt": "..."}`.
- Read file contents and execute all calculations locally. Send Gemini the prompt and a compact schema catalog, never workbook rows or full file contents.
- Give Gemini structured operations and filters, not permission to write arbitrary SQL.
- Validate every file, sheet, column, operator, aggregation, and step reference against the local catalog before execution.
- Build SQL in Python using DuckDB and quoted identifiers. Bind user values as parameters.
- Return the actual result columns and rows. Do not hard-code fields such as `products`, `sellers`, or `revenue` in the response contract.
- Ask for clarification when the requested column, date range, source, or relationship between files cannot be determined reliably.

## Request flow

1. Receive the user's prompt at `POST /api/v1/query`.
2. Read the selected folder's supported files and build or refresh a schema catalog.
3. Narrow the catalog to relevant files using file names, sheet names, headers, inferred types, aliases, and prompt terms. If needed, ask Gemini to choose from a compact catalog rather than sending every workbook's full schema at once.
4. Send the prompt, current date, and relevant catalog to Gemini. Request JSON matching the query-plan contract below.
5. Validate the plan locally. Reject or clarify unknown paths, sheets, columns, invalid types, unsupported operations, bad step references, ambiguous joins, and excessive row limits.
6. Load only the files and sheets required by the accepted plan into in-memory DuckDB relations.
7. Compile the structured plan into parameterized SQL and execute each step in order.
8. Apply any supported combine operation to step results, then return display metadata and dynamic result data.

## Schema catalog

Build catalog entries from actual workbooks and Markdown tables. Each sheet should include:

```json
{
  "file_path": "Sales/October.xlsx",
  "sheet_name": "Orders",
  "columns": [
    { "name": "Ngày bán", "type": "date", "aliases": ["date", "order date"] },
    {
      "name": "Nhân viên",
      "type": "text",
      "aliases": ["seller", "salesperson"]
    },
    {
      "name": "Doanh thu",
      "type": "number",
      "aliases": ["revenue", "sales amount"]
    }
  ],
  "row_count": 6927
}
```

Column names are authoritative. Aliases and inferred types help Gemini map the prompt, but the executor must resolve every requested column back to the exact source header. Sample values can improve mapping, but should be optional, small, and reviewed for sensitive data before being sent to Gemini.

Cache the catalog using file path, modification time, and size as its invalidation key. Re-read a file when the signature changes. Do not cache row data beyond the lifetime needed for a request in the first version.

## Query-plan JSON contract

Gemini returns a plan, not SQL text. One prompt can create several steps. Each step points to one concrete file and sheet, describes the operation, fields, filters, grouping, ordering, and result limit.

Example prompt: “Tổng doanh thu theo nhân viên trong tháng 10, rồi đối chiếu với phòng ban của họ trong file nhân sự.”

```json
{
  "status": "ready",
  "steps": [
    {
      "id": "sales_by_person",
      "source": {
        "file_path": "Sales/October.xlsx",
        "sheet_name": "Orders"
      },
      "operation": "aggregate",
      "select": [
        { "column": "Nhân viên", "role": "group_by", "as": "Nhân viên" },
        {
          "column": "Doanh thu",
          "role": "aggregate",
          "function": "sum",
          "as": "Tổng doanh thu"
        }
      ],
      "filters": [
        {
          "column": "Ngày bán",
          "operator": "between",
          "value": ["2026-10-01", "2026-10-31"]
        }
      ],
      "order_by": [{ "column": "Tổng doanh thu", "direction": "desc" }],
      "limit": 500
    },
    {
      "id": "employee_departments",
      "source": {
        "file_path": "HR/Employees.xlsx",
        "sheet_name": "Staff"
      },
      "operation": "select",
      "select": [
        { "column": "Tên", "role": "value", "as": "Tên" },
        { "column": "Phòng ban", "role": "value", "as": "Phòng ban" }
      ],
      "filters": [],
      "order_by": [],
      "limit": 5000
    }
  ],
  "combine": {
    "operation": "join",
    "left_step": "sales_by_person",
    "right_step": "employee_departments",
    "left_column": "Nhân viên",
    "right_column": "Tên",
    "join_type": "left"
  },
  "display": {
    "title": "Doanh thu theo nhân viên và phòng ban",
    "summary": "Tổng hợp doanh thu tháng 10 và ghép thông tin phòng ban.",
    "columns": ["Nhân viên", "Tổng doanh thu", "Phòng ban"],
    "visualization": "table"
  },
  "clarification_needed": false,
  "clarification_question": null
}
```

### Allowed values

- `status`: `ready` or `clarification_required`.
- `operation`: initially `select`, `distinct`, `aggregate`, and `inspect`.
- Select roles: `value`, `group_by`, or `aggregate`.
- Aggregations: initially `sum`, `count`, `average`, `min`, and `max`.
- Filter operators: `equals`, `not_equals`, `contains`, `in`, `between`, `greater_than`, `greater_or_equal`, `less_than`, `less_or_equal`, `is_empty`, and `is_not_empty`.
- Sort direction: `asc` or `desc`.
- Combine operation: initially `none`, `union`, or `join`.
- Join types: `inner`, `left`, and `full` only when supported by the SQL engine and the request.
- Visualization hints: `text`, `table`, `bar`, `line`, or `number`. These are presentation hints; the frontend must still render generic columns and rows.

Require unique step IDs. The first implementation allows at most two steps and two source files. A step may only refer to a source present in the catalog. Aggregate columns must be numeric where the operation requires numbers; date filters must use validated ISO dates. Set safe per-step and final row limits in backend configuration or constants, not at Gemini's discretion.

## SQL execution

Python maps each validated source to a generated internal relation name, such as `source_0`. Read the workbook sheet with the existing spreadsheet parser, normalize supported values, and register its rows as an in-memory DuckDB relation. Do not use a user supplied file path or header directly as a SQL identifier without catalog resolution and proper quoting.

Compile `select`, filters, grouping, ordering, and limits from the validated fields. Bind filter values as SQL parameters. Compile joins only from validated step outputs and requested key columns. When files have no clear shared key, do not guess a join: return a clarification question. Keep each result associated with its source step for diagnostics.

`union` requires compatible output columns and types. If the columns cannot be aligned by exact names or an explicit mapping in the plan, ask for clarification. Do not silently combine unrelated tables.

## API response

The endpoint returns the prompt, a concise answer, the validated plan, and generic result data. The response columns vary with the prompt and source files.

```json
{
  "status": "success",
  "query": "Tổng doanh thu theo nhân viên trong tháng 10, rồi đối chiếu với phòng ban của họ trong file nhân sự.",
  "answer": "Lan đạt 12.500.000; Minh đạt 9.800.000.",
  "plan": { "steps": [], "combine": { "operation": "join" } },
  "result": {
    "columns": [
      { "name": "Nhân viên", "type": "text" },
      { "name": "Tổng doanh thu", "type": "number" },
      { "name": "Phòng ban", "type": "text" }
    ],
    "rows": [
      {
        "Nhân viên": "Lan",
        "Tổng doanh thu": 12500000,
        "Phòng ban": "Kinh doanh"
      },
      {
        "Nhân viên": "Minh",
        "Tổng doanh thu": 9800000,
        "Phòng ban": "Kinh doanh"
      }
    ],
    "row_count": 2
  },
  "sources": ["Sales/October.xlsx#Orders", "HR/Employees.xlsx#Staff"],
  "warnings": []
}
```

For a clarification, return `status: "clarification_required"`, the question in `answer`, and no fabricated result rows. For no matches, return `status: "no_results"` and an empty result with the planned output columns when known. Preserve warnings per file or query step so a partial result is explicit.

The frontend renders `result.columns` and each row's values dynamically. It can use `display.title`, `display.summary`, and `display.visualization` to choose a heading or chart style, while preserving a readable table fallback. Do not make one response component for a specific sales field.

## Reliability and safety checks

- Constrain Gemini output with a JSON response schema and validate it again with Pydantic.
- Resolve aliases to exact schema columns before SQL compilation. If alias matching has multiple likely columns, ask the user.
- Refuse file paths outside the selected root and ignore any source not returned by the local catalog.
- Never execute Gemini-produced SQL, Python, formulas, macros, or file commands.
- Parameterize filter values, quote trusted identifiers, cap rows, and cap the number of steps and files per plan.
- Do not let Gemini instructions embedded in workbook cell text affect query planning; the catalog should normally contain headers and types only.
- Return per-step warnings for unsupported or unreadable files. A failed file should not silently appear as an empty successful result.
- Keep Gemini's answer grounded in the rows computed locally. For large outputs, ask Gemini only to summarize a bounded result if a natural-language summary is needed; do not send all source rows by default.

## Planned system changes

The endpoint request remains `{"prompt": "..."}`. The main change is the internal Gemini contract: Gemini will return a `MultiFileQueryPlan`, and the backend will validate and execute that exact plan. Do not send data rows to Gemini to make this work.

| Current component | Planned change |
| --- | --- |
| `backend/src/backend/schemas/query.py` | Replace or version the single `QueryPlan` with Pydantic models for `MultiFileQueryPlan`, `QueryStep`, `QuerySource`, `SelectItem`, `Filter`, `SortItem`, `CombinePlan`, and `DisplayPlan`. Set `extra="forbid"`, use enums for every operation/operator, require unique step IDs, and validate required fields by operation. Keep the Gemini-compatible JSON schema generation here or in a dedicated schema helper. |
| `backend/src/backend/clients/gemini.py` | Change `create_query_plan(prompt, available_files)` to return the typed multi-step plan. Include current date and a bounded schema catalog. Tell Gemini to return structured operations only, to use exact file/sheet/header names, and to ask for clarification when a mapping or join key is uncertain. Parse JSON and validate it before returning. Never accept generated SQL. |
| `backend/src/backend/services/query_service.py` | Keep this as the orchestration layer: load the selected folder, request the catalog, choose relevant catalog entries, call Gemini, validate the sources and columns, short-circuit clarification, execute the plan, and assemble the generic API response. Do not embed SQL generation in this service. |
| `backend/src/backend/services/query_engine.py` | Retain or move reusable table parsers, but stop treating the whole request as one sales operation. Parse Markdown/XLSX rows into typed tabular data while preserving original headers and source paths. |
| New `backend/src/backend/services/schema_catalog.py` | Build catalog entries per file and sheet with exact column names, inferred types, optional aliases, row counts, and file signatures. Cache schema metadata by root-relative path, size, and modified time; invalidate entries when the file changes. Return only relevant schemas to Gemini where possible. |
| New `backend/src/backend/services/query_compiler.py` | Validate plan references against the catalog and compile each structured step into SQL. Resolve aliases to exact columns before compiling. Quote only validated identifiers and bind all filter values as parameters. Reject unknown paths, sheet names, headers, operations, operators, aliases, limits, and step references. |
| New `backend/src/backend/services/query_executor.py` | Open a fresh in-memory DuckDB connection for the request. Load only referenced file/sheet tables, assign generated internal relation names, execute compiled statements in step order, and close the connection when the request ends. DuckDB is declared in `backend/pyproject.toml`; resolve it into `backend/uv.lock` with `uv sync` when package-index access is available. |
| `backend/src/backend/api/endpoints/routes.py` | Keep `QueryRequest.prompt` unchanged. Keep the route thin and map missing folder, Gemini timeout/provider failure, invalid Gemini plans, and local file errors to clear HTTP responses. Return the new generic response model. |
| `backend/tests/test_query_flow.py` | Replace single-plan mocks with multi-step plan fixtures. Add tests for schema-catalog construction, Gemini response validation, per-step execution, joins/unions, malformed plans, ambiguous mappings, and generic result serialization. |
| `frontend/src/App.tsx` | Update `QueryResponse` to consume `result.columns` and `result.rows` instead of assuming the current `data` format. Render column names and row values dynamically, show plan/source warnings when useful, and use display metadata for a title or chart hint with a table fallback. |

### Current implementation status

- Implemented: typed multi-step Gemini response models, JSON response schema, schema catalog and file-signature cache, catalog-focused Gemini prompt, plan validation, parameterized DuckDB SQL compilation, in-memory query execution, generic API response, and dynamic frontend result table.
- Implemented in `backend/pyproject.toml`: DuckDB is a declared runtime dependency.
- Pending environment setup: `backend/uv.lock` could not be regenerated in this environment because PyPI DNS/network access failed. Run `uv sync` from `backend/` on a machine with package-index access to resolve the lockfile and install DuckDB before using `POST /api/v1/query`.
- Initial limit: the executor accepts one step or two steps with one final union/join. Arbitrary dependency chains and more than two sources are not implemented.

### Execution sequence

1. **Catalog first.** Add catalog types and read actual sheet/table headers and values needed for type inference. Keep paths relative to the selected root. Start without sample cell values in Gemini context; add small samples only if tests show header-only mapping is insufficient.
2. **Plan contract second.** Define strict Pydantic models for the JSON contract in this document. Test valid and invalid model outputs locally. Gemini's JSON schema should contain only fields supported by the Interactions API; strict validation stays in Pydantic.
3. **One step before many.** Implement and exercise `select`, `distinct`, `aggregate`, and `inspect` for a single file/sheet using DuckDB. This verifies header mapping, data type conversion, filters, sorting, and limits before adding multi-file behavior.
4. **Add step orchestration.** Execute independent steps in order and store each output under its unique step ID. A plan may refer to a prior output only where the schema explicitly allows it; reject cycles, missing IDs, and references to steps that have not completed.
5. **Add combines.** Implement `union` for matching result schemas, then `join` with explicit validated columns. Do not infer a join from similar sounding headers alone. If there are multiple plausible keys or incompatible types, return a clarification.
6. **Change response contract.** Return `result.columns` and `result.rows` as the generic user-facing data. Keep per-step row counts, source identifiers, and warnings in predictable metadata. Do not expose internal SQL or temporary relation names.
7. **Adapt frontend.** Switch to the generic response fields and test with distinct, aggregate, inspect, no-result, clarification, and multi-source responses. Unknown columns should still render without a code change.
8. **Remove legacy behavior.** Once the frontend and API use the new contract, remove the single-step sales-only assumptions and update the API docs and README examples. If a transition release must support both formats, use an explicit response version instead of guessing the payload shape.

### Resource limits and runtime behavior

- Use one in-memory DuckDB connection per query request; do not create a shared database file for the prototype.
- Set backend-owned maximums for plan steps, files per plan, output rows, and execution time. Reject or clamp requests before running SQL; never let Gemini choose unlimited work.
- Load only files/sheets referenced by the validated plan. Close workbooks and the DuckDB connection in `finally` blocks.
- Return one warning per unreadable or skipped source. A failed required source should make the affected step fail or produce an explicit partial-result status, not silently count as zero.
- Keep original headers in output. Internal aliases such as `source_0` are execution details and must not leak into response columns.

## Implementation phases

1. **Implemented:** typed Gemini plan, response schema, schema catalog, and source/column validation.
2. **Implemented:** one-file query operations for selection, distinct values, aggregates, and inspection.
3. **Implemented in code:** DuckDB in-memory executor; `uv.lock` resolution and package installation remain pending due to unavailable package-index access in this environment.
4. **Implemented with initial limits:** two-source `union` and explicit-key `join`; plans with more than two steps and dependency chains are rejected.
5. **Implemented:** generic `result.columns` and `result.rows` API response, status, sources, step counts, and warnings.
6. **Implemented:** dynamic frontend table rendering with display title, summary, source list, and warnings.
7. **Still to verify:** representative runtime queries after DuckDB is installed, including multiple schemas, joins/unions, invalid plans, no matches, and damaged workbooks.

## Acceptance criteria

- One prompt can request fields from a named file with its own schema and return exact source column names and values.
- A prompt can use multiple files when the plan names their sources and defines a valid combine operation.
- Every executed query is generated by Python from a validated plan; Gemini cannot submit executable SQL.
- The output schema remains generic when users add files with new column names.
- Ambiguous column mappings or joins lead to clarification instead of plausible but incorrect results.
- File contents remain local; only the prompt and minimal schema metadata are sent to Gemini by default.
