# Backend core

This prototype contains configuration, an async client for the Obsidian Local REST API, and the first FastAPI endpoints.

## Configuration

Copy `.env.example` to `.env` and set your Local REST API URL and API key. The existing `backend/.env` is loaded automatically; shell environment variables override it.

```env
OBSIDIAN_URL=https://127.0.0.1:27124
OBSIDIAN_KEY=your_local_rest_api_key
PORT=8000
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TIMEOUT=90
```

`GEMINI_API_KEY` is required for `POST /api/v1/query`. The backend reads vault files locally, extracts only file names, sheet names, and column headers, then sends that schema metadata with the prompt and current date to Gemini. Workbook rows and chat history stay local. `GEMINI_MODEL` is optional and defaults to `gemini-2.5-flash`; `GEMINI_TIMEOUT` is optional and defaults to 90 seconds.

Gemini connection errors identify a network failure; provider errors include the HTTP status and provider message. The API key is redacted from error messages.

`PORT` controls the local API server. The Obsidian client currently disables TLS verification to support Obsidian's default self-signed local certificate. Keep the REST API bound to your local machine, or configure a trusted CA before exposing it elsewhere.

## Core usage

```python
from backend.clients.obsidian import ObsidianClient

async with ObsidianClient() as obsidian:
    status = await obsidian.health()
    matches = await obsidian.search("sales report")
    note = await obsidian.read_file("Reports/May.md")
```

The client rejects parent-directory path segments when reading a note. Install the package dependencies with `uv sync` from this directory.

## Run the API

```sh
uv run python -m backend.main
```

`GET /health` returns `{"status":"ok"}` when the backend is responding. It does not contact Obsidian, so it remains useful when the vault API is offline. The development frontend origins `localhost:5173` and `127.0.0.1:5173` are allowed by CORS.

## Current API

- `GET /api/v1/config` returns `obsidian_url`, `obsidian_key_configured`, `gemini_api_key_configured`, and `port`. It never returns either API key.
- `PUT /api/v1/config` accepts `obsidian_url` and/or `obsidian_key`. Updates apply to the running process only and are not written to `.env`. URL updates must point to `localhost` or a loopback IP.
- `GET /api/v1/vault/files` recursively lists `.md` and `.xlsx` vault paths.
- `GET /api/v1/vault/files/{path}` returns Markdown as text or an Excel workbook as sheet names and row data. Example path: `/api/v1/vault/files/Reports/May.xlsx`.
- `POST /api/v1/vault/search` accepts `{"query":"sales report","context_length":100}` and returns Obsidian full-text matches.
- `POST /api/v1/query` accepts `{"prompt":"Tổng doanh số của Nam từ ngày 01/05/2026 đến 10/05/2026"}`. It supplies Gemini with the prompt and available table headers, then totals matching rows from Markdown tables and Excel sheets locally.
- `GET /api/v1/query/examples` returns sample prompts supported by the query parser.
- `GET /api/v1/tags` returns tag names and usage counts from Obsidian.

The query flow uses Gemini to convert the prompt into a validated JSON plan with a metric, date range, salesperson, and grouping. The backend then reads supported Markdown and Excel files from Obsidian and executes the plan locally. The response includes the interpreted plan and matching source rows for review. Sales sums, counts, averages, and grouped result breakdowns are supported.

If the Obsidian settings are absent from `.env`, use `PUT /api/v1/config` before calling either vault endpoint:

```json
{
  "obsidian_url": "https://127.0.0.1:27124",
  "obsidian_key": "your_local_rest_api_key"
}
```
