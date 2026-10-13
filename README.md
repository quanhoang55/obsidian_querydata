# Obsidian Querydata

A local first prototype for asking questions about an Obsidian vault. The frontend is a minimal interactive UI with demo replies. The backend provides health, configuration, vault file, search, query, example, and tag endpoints.

## Configure

The backend reads `backend/.env` (already present in this workspace) and lets shell environment variables override it. The expected keys are:

```env
OBSIDIAN_URL=https://127.0.0.1:27124
OBSIDIAN_KEY=your_local_rest_api_key
PORT=8000
```

Use `backend/.env.example` as a template. Keep `backend/.env` private; it is excluded from Git.

## Run the demo UI

```sh
cd frontend
npm install
npm run dev
```

## Run the backend

```sh
cd backend
uv sync
uv run python -m backend.main
```

The API listens on `127.0.0.1` using the `PORT` value from `backend/.env`.

codex resume 01a12e55-4005-70b3-a082-cde3c5c981a8
