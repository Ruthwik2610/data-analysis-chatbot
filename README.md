# DataChat

DataChat is a conversational workspace for exploring data from files, databases, APIs, and MCP connections. A Next.js interface manages sources and conversations, a FastAPI service handles requests, and DuckDB performs tabular queries. An optional model provider helps interpret questions and explain results.

## Contents

- [Capabilities](#capabilities)
- [How analysis works](#how-analysis-works)
- [Architecture](#architecture)
- [Local development](#local-development)
- [Verification](#verification)
- [Security and operating notes](#security-and-operating-notes)
- [Limitations](#limitations)
- [Contributing and support](#contributing-and-support)
- [License](#license)

## Capabilities

- Upload CSV, Excel, JSON, PDF tables, archives, and DuckDB files, or connect approved API and MCP sources.
- Select one or more sources for a conversation. Cross-source questions use a chat-scoped DuckDB workspace for joins and follow-up analysis.
- Review tables, charts, and the available query/source details behind an answer.
- Organize work into chats and projects with source selections and project instructions.
- Use administrator views for testing, feedback, query-loop metrics, and optional observability integrations.

The application asks for clarification when a cross-source relationship is unclear. It constrains generated SQL to read-only queries and blocks private or internal API destinations by default. These checks reduce risk; users should still review AI-assisted answers before relying on them.

## How analysis works

1. Upload a file or configure an approved source.
2. Select the sources for a conversation.
3. Ask a question, such as “Compare monthly sales in this CSV with the connected forecast API.”
4. Review the answer together with its available table, chart, query, and source details.

## Architecture

| Component | Role |
| --- | --- |
| `frontend/` | Next.js and React interface |
| `backend/server.py` | FastAPI routes for accounts, sources, chats, projects, and queries |
| `backend/storage.py` | Application persistence |
| DuckDB | Local tabular query execution |
| MCP and model connections | Optional external sources and language-model planning |

## Local development

Use Python 3.12, `uv`, and Node.js compatible with `frontend/package.json`. Start from the repository root.

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
```

Replace the example `DATA_PATH` with a path on your machine if using it. Set your own `OPENROUTER_API_KEY` in the untracked `.env` file if you want model-assisted queries. Leave credentials out of Git and screenshots. Start the API:

```bash
uvicorn backend.server:app --host 127.0.0.1 --port 8000 --reload
```

In a second terminal, start the web app:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. The frontend defaults to `http://127.0.0.1:8000` for the API; set `NEXT_PUBLIC_API_BASE` for another address. You can upload a small test file or connect a source through the interface. External connectors require their own credentials and network access.

## Verification

```bash
python -m pytest -q
cd frontend
npm test
npm run build
```

## Security and operating notes

- Keep `.env` files, connector credentials, and uploaded data out of the repository.
- Set `API_KEY` and a separate `JWT_SECRET` before exposing the API beyond localhost. The web app uses user login tokens for protected requests; do not put server secrets in `NEXT_PUBLIC_` variables.
- API and MCP URLs reject private or internal addresses unless a trusted local-development setting explicitly allows them.
- Model-assisted questions depend on provider availability; local tabular work uses DuckDB.
- Cloud sandbox code execution is optional and requires a separately managed E2B credential. No sandbox credential belongs in source code or Git history.

## Limitations

- Model planning, API sources, MCP bridges, tracing, and cloud sandbox features depend on separately configured services.
- Check generated joins against the original data, especially when keys or units are ambiguous.
- Read-only SQL validation does not replace data access review or privacy controls.

## Contributing and support

Open an issue with reproducible steps, expected and observed behavior, and a sanitized sample when possible. For changes, include the affected data-source or chat workflow and the checks you ran. Never include real datasets, credentials, or raw provider responses in an issue.

## License

No license file is currently included. Public visibility alone does not grant permission to reuse or redistribute this code; the repository owner should add an explicit license before inviting external reuse.
