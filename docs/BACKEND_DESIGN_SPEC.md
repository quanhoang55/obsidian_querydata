# Backend design

## Purpose

The local FastAPI backend reads Markdown and Excel files from one user-selected directory. Gemini interprets a natural-language prompt into a validated query plan. It receives the prompt, current date, and only file/sheet/column names; the backend reads and computes over file contents locally.

`POST /api/v1/query` uses a schema catalog and a typed one- or two-step `MultiFileQueryPlan`. The backend validates file/sheet/column references and compiles parameterized SQL for in-memory DuckDB. The response uses dynamic columns and row dictionaries instead of sales-specific fields. See [MULTI_FILE_QUERY_PLAN.md](MULTI_FILE_QUERY_PLAN.md) for the query contract, execution limits, and implementation status.

## Configuration

Backend .env fields:

- GEMINI_API_KEY
- GEMINI_MODEL
- GEMINI_TIMEOUT

The selected directory is chosen in the UI and held in backend memory. It is not an environment variable and is cleared when the backend restarts.

Gemini settings can also be changed through GET/PUT `/api/v1/settings`. The API key is stored in the operating system credential store; the model and timeout are saved in the user's application settings directory. The API never returns the key value.

## File access

Only .md and .xlsx files under the selected root are listed and read. Hidden files and folders are skipped. Relative file paths are resolved and checked against the selected root before access.

## API

- GET /health
- GET /api/v1/config
- PUT /api/v1/config — set an existing folder path
- GET /api/v1/settings — read Gemini model, timeout, and whether a key is configured
- PUT /api/v1/settings — update Gemini preferences and optionally set or clear its key
- POST /api/v1/vault/select — open a native folder chooser on the computer running the backend
- GET /api/v1/vault/files
- GET /api/v1/vault/files/{path}
- POST /api/v1/vault/search
- POST /api/v1/query
- GET /api/v1/query/examples
- GET /api/v1/tags

## Local development

Start the backend from backend/ with uv sync and uv run python -m backend.main. Start the React frontend from frontend/ with npm run dev. The Vite dev server proxies API calls to the local backend.
