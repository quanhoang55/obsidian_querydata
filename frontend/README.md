# Querydata frontend

Minimal local demo UI for the Querydata backend.

## Run the demo

Start the backend on port `8000`, then run:

```sh
npm install
npm run dev
```

Open the Vite URL shown in the terminal (usually `http://localhost:5173`). During development, Vite proxies `/health` and `/api/*` to `http://127.0.0.1:8000`.

The UI uses the health, config, query, vault file list/read, and vault search endpoints. Obsidian URL and key can be set from the connection settings screen; the key is held by the backend process and is never returned to the browser. Gemini credentials remain in the backend `.env` file.

To use a different backend origin, set `VITE_API_BASE_URL` before starting Vite.
