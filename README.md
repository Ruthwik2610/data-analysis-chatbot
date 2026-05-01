# Data Analysis Chatbot

A local FastAPI + Next.js chatbot for asking plain-English questions over uploaded files, API responses, and connected MCP data bridges. DuckDB performs the tabular work locally; OpenRouter-backed models handle intent parsing, multi-step planning, and concise answer wording.

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

## Sources

The app supports:

- CSV uploads
- Excel uploads (`.xlsx`, `.xls`)
- PDF table uploads (`.pdf`)
- ZIP uploads containing PDF tables (`.zip`)
- 7z uploads containing PDF tables (`.7z`)
- JSON uploads
- DuckDB database files
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
