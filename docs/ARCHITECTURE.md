# Project architecture

```text
backend/
├── src/backend/
│   ├── api/endpoints/routes.py       # FastAPI endpoints and request/response models
│   ├── clients/gemini.py             # Structured query-plan generation
│   ├── schemas/query.py              # Typed Gemini plan contract
│   ├── services/
│   │   ├── local_vault.py            # Safe local folder and file access
│   │   ├── schema_catalog.py         # Sheet/header/type discovery and cache
│   │   ├── query_service.py          # Catalog → Gemini → validate → execute flow
│   │   ├── query_compiler.py         # Plan validation and parameterized SQL
│   │   └── query_executor.py         # In-memory DuckDB execution
│   ├── config.py                     # Environment and runtime settings
│   └── main.py                       # Local application entry point
├── pyproject.toml
└── uv.lock

frontend/
├── src/App.tsx                       # Settings, file browser, chat, dynamic results
└── src/App.css

docs/
└── MULTI_FILE_QUERY_PLAN.md          # Query contract and implementation plan/status
```

## Query path

1. The frontend sends one natural-language prompt to `POST /api/v1/query`.
2. The backend creates a local catalog for available Markdown tables and Excel sheets.
3. Gemini returns a strict structured query plan using exact file, sheet, and column names.
4. The compiler validates the plan and builds parameterized SQL; it does not accept SQL from Gemini.
5. The executor loads only planned sources into an in-memory DuckDB database and runs one step or a two-source union/join.
6. The API returns generic column metadata and row dictionaries for frontend rendering.

Vault rows remain on the user's computer. The current implementation supports at most two query steps and two source files per request.
