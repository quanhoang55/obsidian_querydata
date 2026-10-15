# Querydata system specification

## Objective

Querydata is a local web app with a Python FastAPI backend and a React frontend. It reads Markdown and Excel files below one user-selected folder. Gemini interprets the prompt using a header-only schema catalog; the backend queries local data and returns generic result columns and rows.

## Components

- **Local API:** FastAPI runs on the user's computer. `LocalVault` confines reads to the selected root and supports `.md` and `.xlsx` files.
- **Schema catalog:** The backend lists sheets and columns, infers simple types, and caches schema metadata by path, size, and modification time.
- **Gemini planner:** Gemini receives the prompt, current date, and relevant file/sheet/column metadata. It returns a typed one- or two-step `MultiFileQueryPlan`, not SQL.
- **Query engine:** Python validates file/sheet/column names and operators, compiles parameterized SQL, and runs it in an in-memory DuckDB database.
- **Frontend:** React provides settings, file browsing, and a chat interface. Query result tables render columns and row values dynamically from the API response.
- **Settings:** Gemini credentials are stored in the operating system credential store on macOS/Windows. Model and timeout preferences are stored in the user's application settings directory. The folder selection remains in backend memory.

## Query endpoint

`POST /api/v1/query` accepts:

```json
{"prompt": "Tổng doanh thu theo nhân viên trong tháng 10"}
```

The API returns a status, concise answer, validated plan, display metadata, dynamic `result.columns` and `result.rows`, sources, per-step counts, and warnings. One source can be queried directly; two sources can be joined or unioned when the schemas support it. Ambiguous file, column, or join mappings return a clarification instead of invented results.

## Privacy and execution

- Workbook rows stay local; the standard Gemini request contains the prompt and relevant schema metadata only.
- The backend does not execute model-generated SQL or code.
- The executor only reads sources in the catalog and inside the selected folder.
- Filter values are SQL parameters. Identifiers are resolved against actual headers and quoted by the compiler.
- Each query uses an in-memory DuckDB database and returns a bounded result.

See [MULTI_FILE_QUERY_PLAN.md](MULTI_FILE_QUERY_PLAN.md) for the schema contract, query operations, response shape, and current implementation limits.
