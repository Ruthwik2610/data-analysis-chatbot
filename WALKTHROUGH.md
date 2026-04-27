# Data Chat — Walkthrough

A local chat UI over your CSVs / Excel files / DuckDB databases / APIs / shell commands. Frontend is Next.js 16; backend is FastAPI wrapping the existing Python data + LLM modules. DuckDB runs every query; Gemini classifies intent and writes the streamed answer.

---

## 1. Run it

In two terminals:

```bash
# terminal 1 — backend
cd "data analysis chatbot"
.venv/bin/python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000

# terminal 2 — frontend
cd "data analysis chatbot/frontend"
npm run dev -- --port 3000
```

Open **http://localhost:3000**. The frontend talks to the backend at `http://127.0.0.1:8000`. Override with `NEXT_PUBLIC_API_BASE` if needed.

---

## 2. Attach a source

Click **📎** in the input bar (or **🔌** in the topbar). The dialog has five tabs:

| Tab | Input | Notes |
|---|---|---|
| **CSV** | local file path | Optional *Build DuckDB cache* checkbox for files >100 MB. |
| **Excel** | local file path + sheet name | First load reads the sheet directly; switch to a SQL cache later if you want. |
| **DuckDB** | local `.duckdb` path + table name | Read-only. |
| **API** | URL + optional bearer token | Tick *Save connector* to remember it. |
| **Terminal** | shell command outputting JSON or CSV | Local-only, runs `subprocess.run(shell=True)`. Trust your input. |

A successful attach drops the source into the **Knowledge base** panel at the bottom of the sidebar with a colored dot (green = CSV/Excel, orange = DuckDB, blue = API/Terminal).

---

## 3. Switch the active source

The query always runs against the **active** KB entry — the one with a filled colored dot and bold name. Click any other entry in the sidebar to switch. The topbar source pill updates immediately.

Click `×` next to a KB entry to remove it (frees memory; doesn't touch the original file).

---

## 4. Ask a question

Type into the input at the bottom and press Enter (Shift+Enter for newline). The flow:

1. **Backend** classifies intent via Gemini (or a heuristic if `GEMINI_API_KEY` is missing).
2. **Backend** turns the intent into a single read-only `SELECT` plan, validates it against a forbidden-token list, executes it against DuckDB.
3. **Backend** streams over Server-Sent Events: `meta` → `result` → `text` deltas → `done`.
4. **Frontend** renders the source pill on `meta`, the result block on `result`, and types out the LLM answer character-by-character via `text` deltas.

The result block shows the title, row count, query elapsed in ms, the chosen visualization (mini horizontal bars for `bar`/`pie`, inline SVG line for `line`, table fallback), a CSV download button, a Chart/Table toggle, and a collapsible *How I answered* with the SQL.

---

## 5. Recent chats

Every assistant reply auto-persists the chat to SQLite at `.cache/chatbot/app.sqlite`. The sidebar **Recents** list shows them most-recent-first. Click a chat → restore. Click `×` → delete. The current chat is highlighted.

Restored chats display the answer text + result block (columns, rows, viz). The DataFrame is rehydrated from the persisted payload; you don't need to re-run the query.

---

## 6. Saved connectors

In the attach dialog, ticking *Save connector* on an API or Terminal entry stores the configuration in SQLite. Reopen the dialog and a **Saved connectors** section at the bottom lists them with `Use` and trash buttons. `Use` re-runs the connector and adds the result to the knowledge base.

---

## 7. Architecture

```
backend/
  server.py     ← FastAPI app, SSE /query, source/chat/connector CRUD
  storage.py    ← SQLite schema + CRUD
src/            ← shared Python modules (re-used as-is)
  config.py, data_sources.py, ingest.py, model_router.py,
  prompting.py, query_engine.py, visualization.py, utils.py,
  logging_config.py
frontend/
  src/app/{layout,page}.tsx, globals.css
  src/components/{Sidebar,Topbar,MessageList,InputBar,
                  AttachDialog,ResultBlock,InlineQuestion}.tsx
  src/lib/{api,types}.ts
```

State of record:
- **Sources** (in-memory `DataSource`) live in the backend process; metadata persists to SQLite. Restart the backend → in-memory CSVs need re-attach (path-based attaches re-load instantly from origin).
- **Chats + messages** persist to SQLite.
- **Connectors** persist to SQLite.

---

## 8. Environment

`.env` (optional — without `GEMINI_API_KEY` the app uses heuristic intents):

```
GEMINI_API_KEY=...
DATA_PATH=/abs/path/to/sourcedata.csv
CACHE_DIR=.cache/chatbot
PROMPT_CHAR_BUDGET=24000
```

---

## 9. Things to try

- Attach `sourcedata.csv` via local-path with *Build DuckDB cache* on. Ask: *"top 5 categories by revenue"* (mini bars), *"monthly revenue trend"* (line chart), *"orders for ORD-12345"* (lookup table).
- Attach `https://jsonplaceholder.typicode.com/users` and tick *Save connector*. Ask: *"how many users in each city?"* Reload the page; reopen the dialog; the connector is still there.
- Attach a Terminal source with `curl -s http://localhost:3000/api/whatever` (or any local JSON-emitting command).
- Open a second tab — your sources and chats are visible in both because they're in SQLite.

---

## 10. Stop everything

```bash
pkill -f "uvicorn backend"
pkill -f "next dev"
```
