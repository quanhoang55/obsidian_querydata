# Querydata frontend

Local React interface for choosing a folder and querying Markdown and Excel files through the FastAPI backend.

The chat reads the query endpoint's generic `result.columns` and `result.rows` fields and displays the columns returned for each request; it does not assume a fixed sales schema.

## Run

Start the backend from backend/:

    uv sync
    uv run python -m backend.main

Then start the frontend from frontend/:

    npm install
    npm run dev

Open the Vite URL shown in the terminal. The development server proxies API calls to http://127.0.0.1:8000. Use Choose folder… in the interface to select an Obsidian vault or any folder containing supported .md and .xlsx files.

The backend requires GEMINI_API_KEY, GEMINI_MODEL, and GEMINI_TIMEOUT in its .env. The folder choice is stored in memory until the backend restarts.
