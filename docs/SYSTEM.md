# System Specification: Obsidian Local Chat & Query Assistant (FastAPI + TypeScript)

## 1. Core Objective

Build a decoupled local web application consisting of a Python FastAPI backend and a TypeScript frontend. The system acts as a conversational query engine that scans local Markdown and Excel files inside an Obsidian Vault directory to extract metrics like total sales and date-ranged summaries.

## 2. Architecture Overview

- **Backend Service:** FastAPI (Python) running locally. It exposes REST endpoints to ingest natural language queries, parse parameters using regex/NLP logic, scan the local file system (`pathlib`, `xlsx`), and return structured JSON aggregated data.
- **Frontend Client:** TypeScript-based interface (Vite + Vanilla TS or lightweight framework) providing a clean ChatGPT-like chat dashboard. It communicates with FastAPI via `fetch` API.
- **Storage Layer:** Local Obsidian Vault directory acting as the source of truth for `.md` and `.xlsx` files.

## 3. Core Functional Requirements

- **Vault Configuration Endpoint:** FastAPI endpoint to configure or read the target local Obsidian vault path.
- **Chat Query Endpoint (`POST /api/v1/query`):** Accepts user prompts, extracts entity (salesperson name) and time bounds (`start_date`, `end_date`), scans files, aggregates numbers, and returns formatted markdown responses.
- **TypeScript Chat UI:** Interactive chat bubble interface, Markdown renderer for incoming responses, and loading indicators during file scanning.
