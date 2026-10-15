# ObsidianQuery

A local app for querying Markdown and Excel files inside a folder selected by the user. The backend reads files locally and uses Gemini online to interpret prompts from the available column headers.

`POST /api/v1/query` sends Gemini the prompt and relevant file/sheet/column metadata. Gemini returns a validated one- or two-step plan. The backend compiles that plan into parameterized SQL and executes it in an in-memory DuckDB database. Workbook rows stay local. Results use generic `result.columns` and `result.rows` fields so the UI can display different schemas without field-specific code.

## Environment

The backend .env uses only these variables:

    GEMINI_API_KEY=your_gemini_api_key
    GEMINI_MODEL=your_gemini_model
    GEMINI_TIMEOUT=90

## Run locally

In one terminal:

    cd backend
    uv sync
    uv run python -m backend.main

In another terminal:

    cd frontend
    npm install
    npm run dev

Open the Vite URL printed in the terminal and choose the folder that contains your local Markdown or Excel files.

## Desktop installers

The desktop app bundles the React interface and a private local FastAPI process. File data remains on the computer; Gemini receives the user prompt and workbook schema metadata. The Gemini API key, model, and selected folder are configured from the app's **Cài đặt** screen and stored with the operating system credential/configuration services.

Requirements for local packaging:

- macOS Sequoia 15 or newer for the DMG build
- Windows 10 or newer for the EXE build
- Node.js 22, Rust, Python 3.12, and `uv`

Build an unsigned macOS DMG on macOS:

    ./scripts/build-desktop-macos.sh

Build an unsigned Windows NSIS installer in PowerShell on Windows:

    ./scripts/build-desktop-windows.ps1

Installers are written under `frontend/src-tauri/target/release/bundle/`. Since these test builds are unsigned, macOS Gatekeeper and Windows SmartScreen may require the user to explicitly allow the app.

To build both operating-system packages without maintaining both machines, run the **Build desktop installers** workflow manually in GitHub Actions and download its two artifacts.
