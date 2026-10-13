# FastAPI Backend Architecture & Obsidian Integration

This document outlines the complete backend architecture designed with **FastAPI (Python)**. It handles natural language queries from the TypeScript frontend, communicates with the local **Obsidian Local REST API**, and aggregates data (such as sales performance and date-ranged summaries).

---

## 1. Environment Configuration (`.env`)

The backend environment has been configured with local Obsidian vault connection credentials. Ensure your `.env` file contains the following keys:

```env
OBSIDIAN_URL=https://127.0.0.1:27124
OBSIDIAN_KEY=your_actual_api_key_here
PORT=8000
```

---

## 2. FastAPI Backend Design (`main.py`)

### A. Project Structure

```text
backend/
├── main.py              # FastAPI application entry point & routes
├── services.py          # Obsidian API client & Query parsing logic
├── requirements.txt     # fastapi, uvicorn, httpx, pydantic, python-dotenv
└── .env                 # Environment variables
```

### B. Core Endpoints Design

1. **`GET /health`**
   - **Description:** Check if the FastAPI backend and connection to Obsidian Local REST API are alive.
   - **Response:** `200 OK` with connection status.

2. **`POST /api/v1/query`**
   - **Description:** Receives the user's natural language prompt from the TypeScript frontend, parses parameters (e.g., salesperson name, date range), queries Obsidian via Local REST API, and returns an aggregated summary.
   - **Request Body (JSON):**
     ```json
     {
       "prompt": "Tổng doanh số của Nam từ ngày 01/05/2026 đến 10/05/2026"
     }
     ```
   - **Response Body (JSON):**
     ```json
     {
       "status": "success",
       "query": "Tổng doanh số của Nam từ ngày 01/05/2026 đến 10/05/2026",
       "answer": "Tổng doanh số của Nam từ ngày 01/05/2026 đến 10/05/2026 là 45.000.000 VNĐ (từ 3 file ghi chú).",
       "details": []
     }
     ```

### C. Implementation Logic (`services.py` core concept)

- **HTTP Client:** Uses `httpx` with `verify=False` to securely bypass local self-signed certificate warnings from Obsidian's REST API.
- **Query Parser:** Uses Regex to extract targets (`salesperson` and `date_range`) from conversational input.
- **Data Fetcher:** Calls Obsidian's `/search/simple/` or `/vault/` endpoints to retrieve relevant notes or spreadsheet data.

---

## 3. Appendix: Obsidian Local REST API Reference

### REST API

```sh
# Check the server is running (no auth required)
curl -k https://127.0.0.1:27124/

# List files at the root of your vault
curl -k -H "Authorization: Bearer <your-api-key>" \
  https://127.0.0.1:27124/vault/

# Read a note
curl -k -H "Authorization: Bearer <your-api-key>" \
  https://127.0.0.1:27124/vault/path/to/note.md

# Read a specific heading (URL-embedded target)
curl -k -H "Authorization: Bearer <your-api-key>" \
  https://127.0.0.1:27124/vault/path/to/note.md/heading/My%20Section

# Append a line to a specific heading (PATCH with a JSON instruction)
curl -k -X PATCH \
  -H "Authorization: Bearer <your-api-key>" \
  -H "Content-Type: application/json" \
  --data '{"targetType":"heading","target":["My Section"],"operation":"append","content":"New line of content"}' \
  https://127.0.0.1:27124/vault/path/to/note.md
```

To avoid certificate warnings, you can download the plugin's certificate authority from `https://127.0.0.1:27124/obsidian-local-rest-api.crt` and trust it in your OS or browser, or point your HTTP client at it directly (for example `curl --cacert obsidian-local-rest-api.crt ...`). The plugin generates its own certificate authority on first run and serves a server certificate signed by it, so the download is a CA certificate rather than the server certificate itself. That CA is name-constrained: it can only vouch for `127.0.0.1`, `localhost`, your configured binding host, and the hostnames you list under **Subject alternative names**, so trusting it does not let it (or anyone who obtains its key) impersonate other sites.

### MCP clients

The MCP server runs at `https://127.0.0.1:27124/mcp/` and requires that you provide your bearer token for authentication via an `Authorization` header (i.e. `Authorization: Bearer <your-api-key>`). Because the plugin uses a locally generated certificate authority, you may need to either trust that certificate in your OS/client, or use the plain HTTP endpoint at `http://127.0.0.1:27123/mcp/` (enable it under **Settings → Local REST API → Enable HTTP server**).

#### Claude Code

Claude Code has native HTTP MCP support. The quickest way to add the server is via the CLI:

```sh
claude mcp add --transport http obsidian https://127.0.0.1:27124/mcp/ \
  --header "Authorization: Bearer <your-api-key>"
```

Or add it manually to `.mcp.json` in your project root (project-scoped) or configure it user-wide via `claude mcp add --scope user`:

```json
{
  "mcpServers": {
    "obsidian": {
      "type": "http",
      "url": "https://127.0.0.1:27124/mcp/",
      "headers": {
        "Authorization": "Bearer <your-api-key>"
      }
    }
  }
}
```

#### Claude Desktop

Claude Desktop does not natively support remote HTTP MCP servers, but you can bridge it with [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) (requires Node.js). Add the following to `claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "npx",
      "args": [
        "mcp-remote@latest",
        "https://127.0.0.1:27124/mcp/",
        "--header",
        "Authorization: Bearer <your-api-key>"
      ]
    }
  }
}
```

Restart Claude Desktop after saving the file.

#### Cursor

Cursor supports the Streamable HTTP MCP transport. Add the following to `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project-specific):

```json
{
  "mcpServers": {
    "obsidian": {
      "url": "https://127.0.0.1:27124/mcp/",
      "headers": {
        "Authorization": "Bearer <your-api-key>"
      }
    }
  }
}
```

#### Other clients

Any MCP client that supports the Streamable HTTP transport can connect to `https://127.0.0.1:27124/mcp/` with an `Authorization: Bearer <your-api-key>` header. Consult your client's documentation for the exact configuration format.

## API overview

| Endpoint                 | Methods                   | Description                                                                    |
| ------------------------ | ------------------------- | ------------------------------------------------------------------------------ |
| `/vault/{path}`          | GET PUT PATCH POST DELETE | Read, write, or delete any file in your vault                                  |
| `/active/`               | GET PUT PATCH POST DELETE | Operate on the currently open file                                             |
| `/search/simple/`        | POST                      | Full-text search across all notes                                              |
| `/search/`               | POST                      | Structured search via JsonLogic                                                |
| `/commands/`             | GET                       | List available Obsidian commands                                               |
| `/commands/{commandId}/` | POST                      | Execute a command                                                              |
| `/tags/`                 | GET                       | List all tags with usage counts                                                |
| `/open/{path}`           | POST                      | Open a file in the Obsidian UI                                                 |
| `/`                      | GET                       | Server status and authentication check                                         |
| `/mcp/`                  | GET POST                  | MCP (Model Context Protocol) server — connect AI agents directly to your vault |
