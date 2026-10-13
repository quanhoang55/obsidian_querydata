# Project Architecture & File Structure

## 1. Directory Tree

```text
obsidian-query-app/
├── SYSTEM.md
├── RULES.md
├── ARCHITECTURE.md
├── backend/
│   ├── requirements.txt         # fastapi, uvicorn, pandas, openpyxl
│   ├── main.py                  # FastAPI app entry point, CORS, routes
│   └── services/
│       ├── vault_scanner.py     # Local file system traversal (.md, .xlsx)
│       └── query_engine.py      # Regex extraction & data aggregation logic
└── frontend/
    ├── package.json             # typescript, vite
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── main.ts              # Entry point & DOM initialization
        ├── api.ts               # Fetch client wrapper for FastAPI backend
        └── styles.css           # Chat dashboard styling
```
