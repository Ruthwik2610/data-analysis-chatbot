# CSV Intelligence Chat

A local Streamlit chatbot for querying `/Users/rajasekharbandreddy/Downloads/sourcedata.csv` with high accuracy and low token use.

The app uses Gemini for intent understanding and concise answer wording, while DuckDB performs every calculation locally. It builds a persistent cache on first run so the 228 MB CSV does not need to be reparsed for every chat turn.

## Setup

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `GEMINI_API_KEY`. The app also works in a limited offline heuristic mode without the key.

Default model routing is Gemini 3 Flash first, then Gemini 2.5 Flash if the Gemini 3 call fails:

- `GEMINI_DEFAULT_MODEL=gemini-3-flash-preview`
- `GEMINI_FALLBACK_MODEL=gemini-2.5-flash`

## Run

```bash
source .venv/bin/activate
streamlit run app.py
```

The first run creates `.cache/chatbot/orders.duckdb`. Rebuild happens only when the source CSV path, size, mtime, schema hash, or cache version changes.

## Input Routes

The sidebar supports four input routes:

- `Upload`: upload CSV, XLSX, XLS, JSON, DuckDB, or DB files from the main chat surface.
- `Connector`: connect to an API endpoint, an MCP/exported file path, or a local terminal command that returns JSON or CSV.
- `Local path`: point to a file available on this machine.

Each source can use either `Analyze directly` for in-memory querying or `Convert to SQL cache` to materialize the source into a local DuckDB table. Uploaded DuckDB files are queried directly.

## Safety And Accuracy

- Raw CSV rows are never sent to Gemini.
- Dynamic prompt content is XML-escaped.
- Gemini must return structured JSON intent.
- DuckDB executes validated read-only SQL.
- Raw errors are logged in `logs/` and replaced with safe user-facing messages.
- A "How I answered" panel shows the model, query ID, filters, display choice, and optional SQL.

## Visualization Defaults

- Top 3 style questions render as compact tables/cards by default.
- Bar charts are used for larger rankings.
- Line charts are used for time trends.
- Pie charts are used for share or distribution questions with a small category count.
