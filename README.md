# Data Analysis Chatbot

A local FastAPI + Next.js chatbot for asking plain-English questions over uploaded files, API responses, external Databases, and connected MCP data bridges. DuckDB performs the tabular work locally; OpenRouter-backed models handle intent parsing, multi-step planning, and concise answer wording.

## Setup

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

```bash
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_PROVIDER_ORDER=DeepSeek
MODEL=openrouter/deepseek/deepseek-v4-pro
AGENT_MODEL=openrouter/deepseek/deepseek-v4-pro
```

`API_KEY` is optional for local-only use. If you set it, set the same value in the frontend as `NEXT_PUBLIC_API_KEY`.

## Production Readiness

- Run `cd frontend && npm test`, `cd frontend && npm run build`, and `.venv/bin/python -m pytest -q` before deploying.
- Keep `.env*` files and connector secrets untracked; only expose browser-safe values with `NEXT_PUBLIC_`.
- The VPS deploy path rebuilds `/opt/datachat/frontend` after rsync because `.next` is excluded from sync.
- Treat failed systemd status checks, frontend HTTP smoke failures, and Web Vitals regressions as release blockers.

## Run Locally

Backend:

```bash
source .venv/bin/activate
uvicorn backend.server:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## LLM Observability (Arize Phoenix)

This project integrates with **Arize Phoenix** for deep LLM tracing and evaluation. This provides visibility into "Chain of Thought" reasoning, intent detection, and SQL generation.

1. Create a free account at [app.phoenix.arize.com](https://app.phoenix.arize.com).
2. Create a project named `data-analysis-chatbot`.
3. Obtain your API key and add it to your `.env`:

```bash
PHOENIX_API_KEY=your_phoenix_api_key
PHOENIX_PROJECT_NAME=data-analysis-chatbot
PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com/v1/traces
```

The system will automatically capture:
- **Classify Intent:** How the LLM interpreted the user's natural language.
- **Build Query Plan:** The conversion of intent into DuckDB SQL logic.
- **Summarize Answer:** The final grounded response generation.

Access the **Observability** tab in the Admin Dashboard to view live traces and deep-link into Phoenix for debugging.

## Sources

The app supports:

- CSV uploads
- Excel uploads (`.xlsx`, `.xls`)
- PDF table uploads (`.pdf`)
- ZIP uploads containing PDF tables (`.zip`)
- 7z uploads containing PDF tables (`.7z`)
- JSON uploads
- DuckDB database files
- SQL Databases (MySQL, PostgreSQL, etc.) via project-scoped MCP bridges
- JSON APIs with optional bearer auth
- MCP bridges, such as BigQuery/Salesforce-style tool servers

Multiple sources can be selected in the sidebar. Single-source questions use the deterministic DuckDB query path. Multi-source or MCP-mixed questions use a per-chat DuckDB workspace so results can be joined, filtered, aggregated, and charted locally.

## Multi-Source Querying

For cross-source questions, select more than one source in the sidebar, then ask a question like:

- `Join customers.csv with orders.csv and show revenue by customer segment`
- `Compare uploaded sales with the API forecast by month`
- `Use the connected warehouse source and my CSV to find missing customer IDs`

Uploaded/API sources are copied into chat-scoped DuckDB workspace tables. MCP tool results are fetched live, and tabular results are cached into the same workspace for that chat so follow-up joins are faster.

When matching columns are obvious, the agent can join directly. If a join relationship is unclear, it should ask which columns relate before guessing.

## MCP Bridges

Use the plug button, open the `MCP Bridge` tab, and enter a bridge URL such as:

```text
https://example.com/mcp
```

Connected bridges appear in the source list as `mcp`. Select it to ask MCP-only questions, or select it alongside uploaded/API sources for mixed queries.

Troubleshooting:

- If a bridge shows `error`, use the reconnect button in the connector popover.
- If a question says no tools are available, confirm the bridge is connected and exposes tools.
- If no chart/table appears, the tool may have returned text instead of tabular JSON/CSV.
- If the model is unavailable, MCP and multi-source agent queries cannot run until OpenRouter is reachable.

## Safety And Accuracy

- Raw rows are queried locally with DuckDB wherever possible.
- Prompt content is XML-escaped.
- Generated SQL is constrained to read-only `SELECT` statements.
- Upload filenames are normalized before writing to disk.
- API and MCP bridge URLs reject private/internal addresses by default; set `ALLOW_PRIVATE_API_URLS=1` only for trusted local/internal development.
- The “How I answered” panel shows source, model, SQL, display choice, and query details when available.

## Verification

Backend:

```bash
source .venv/bin/activate
python -m unittest discover -s tests -p 'test*.py' -v
python -m pytest -q
```

Frontend:

```bash
cd frontend
npm run build
```
