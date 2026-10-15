# Querydata backend

The FastAPI backend reads Markdown and Excel files directly from a folder chosen by the user. For `POST /api/v1/query`, it sends the prompt and relevant local file/sheet/column metadata to Gemini. Gemini returns a typed query plan with up to two steps; Python validates it, compiles safe parameterized SQL, and executes it in an in-memory DuckDB database. File contents and calculations stay local.

## Environment

The backend .env contains only GEMINI_API_KEY, GEMINI_MODEL, and GEMINI_TIMEOUT.

Example values:

    GEMINI_API_KEY=your_gemini_api_key
    GEMINI_MODEL=your_gemini_model
    GEMINI_TIMEOUT=90

## Run locally

From this directory, run uv sync and then uv run python -m backend.main.

Run the frontend from frontend/ with npm install and npm run dev. The UI connects to the backend through the Vite development proxy.

## Folder selection

Choose folder… in the frontend opens the native folder picker on the computer running the backend. The PUT /api/v1/config endpoint can also select a directory by receiving a JSON body with an absolute vault_path.

The selection is held in backend memory and must be selected again after restarting the backend. File endpoints support .md and .xlsx files below the selected root. Hidden files and folders are skipped.

## Endpoints

- GET /health
- GET /api/v1/config
- PUT /api/v1/config
- GET /api/v1/settings
- PUT /api/v1/settings
- POST /api/v1/vault/select
- GET /api/v1/vault/files
- GET /api/v1/vault/files/{path}
- POST /api/v1/vault/search
- POST /api/v1/query
- GET /api/v1/query/examples
- GET /api/v1/tags

Gemini settings can be changed through `PUT /api/v1/settings` without editing `.env`. The API key is saved in macOS Keychain or Windows Credential Manager. The model and timeout are saved in the current user's application settings directory. `GET /api/v1/settings` only returns whether a key is configured; it never returns the key value.

`POST /api/v1/query` still accepts `{"prompt":"..."}`. Successful results return a generic `result` object containing column metadata, row dictionaries, row count, and truncation status. The `plan`, `display`, `sources`, `step_results`, and `warnings` fields describe how the data was queried without exposing generated SQL.
