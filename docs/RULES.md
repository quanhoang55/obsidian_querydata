# Technical Rules & Security Guidelines

## 1. Security & Local Privacy

- **Prompt Privacy:** The user prompt, current date, and file names/sheet names/column headers may be sent to Google Gemini to interpret the request. Never send file rows, file contents, or chat history. Read and aggregate files locally.
- **Path Sanitization:** The selected directory is the workspace root. Resolve every file path under that root and reject traversal or symlinks that escape it.

## 2. Backend Rules (FastAPI / Python)

- **Asynchronous Handlers:** Use `async def` for endpoints that perform file I/O operations where applicable.
- **Robust Error Handling:** Return clear HTTP status codes (400 for malformed queries, 404 if vault path is invalid, 500 for parsing crashes) with descriptive JSON error payloads.
- **Data Parsing Fallback:** If an Excel file lacks standard column headers, fallback to scanning raw cell values or row strings.

## 3. Frontend Rules (TypeScript)

- **Strict Typing:** Avoid `any` types. Define clear TypeScript interfaces for API payloads, chat messages, and query responses.
- **CORS Configuration:** FastAPI backend must explicitly enable CORS middleware to allow communication from the TypeScript frontend development server.
- **State Management:** Keep local state for chat history clean and render messages efficiently using safe DOM manipulation or lightweight template rendering.
