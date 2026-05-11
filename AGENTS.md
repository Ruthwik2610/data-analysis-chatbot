# Deploy

Production VPS for this project:

- **SSH alias:** `datachat-vps` (defined in `~/.ssh/config` → `root@66.116.235.156`)
- **SSH alias (DB):** `datachat-db` (defined in `~/.ssh/config` → `Rapiduser@66.116.235.156`)
- **Remote repo path:** `/opt/datachat/`
- **Backend service:** `datachat-backend.service` (systemd)
- **Frontend service:** `datachat-frontend.service` (systemd)
- **Nginx vhost:** `/etc/nginx/sites-available/datachat`
- **Rsync excludes file:** `/tmp/datachat-rsync-excludes` — excludes `.git`, `.venv`, `.cache`, `cache`, `logs`, `node_modules`, `.next`, `__pycache__`, `*.pyc`, `.env`, `.env.local`, `.env.production`, `mcp_connectors.json`, `.DS_Store`, `.streamlit/`, `app.py`

Standard deploy after editing files locally:

```bash
rsync -az --stats --exclude-from=/tmp/datachat-rsync-excludes \
  -e "ssh -F /Users/rajasekharbandreddy/.ssh/config" \
  ./ datachat-vps:/opt/datachat/
ssh datachat-vps systemctl restart datachat-backend.service
ssh datachat-vps systemctl status datachat-backend.service --no-pager
```

For frontend (Next.js) changes also restart `datachat-frontend.service`. `mcp_connectors.json` is excluded from rsync so the server's connected MCP bridges (BigQuery, etc.) survive deploys.

# Frontend UI Guardrails

Light mode must be treated as a first-class production surface. Do not hardcode white/black text or low-opacity white borders/backgrounds in admin or chat UI unless the component is explicitly on a fixed dark brand surface. Prefer theme tokens such as `var(--color-text-primary)`, `var(--color-text-secondary)`, `var(--color-background-elevated)`, and `var(--color-border-secondary)`.

When touching admin navigation, dashboards, cards, or shell layout:
- Verify the route in light mode and dark mode.
- Keep a visible theme toggle in the top shell.
- Add or update a focused frontend test if the change affects navigation, shell controls, visibility, or theme behavior.
- Avoid hardcoded `text-white`, `text-white/*`, `bg-white/*`, and `border-white/*` classes in admin components unless paired with a scoped theme-safe override.

# Model Routing

This project intentionally uses DeepSeek models through OpenRouter:

- **Flash mode:** `openrouter/deepseek/deepseek-v4-flash`
- **Pro mode:** `openrouter/deepseek/deepseek-v4-pro`
- **Provider order:** `DeepSeek`

Do not switch Flash mode to Gemini or another provider/model unless the user explicitly asks for that change. If model availability breaks, verify the OpenRouter model id and provider routing first before changing defaults.

# Jules + Codex Development Workflow

Jules is allowed to work on this repository only through GitHub branches, issues, and pull requests. Treat Jules as an async cloud contributor, not as a production deploy agent.

## Jules Scope

Good Jules tasks:

- Add or improve tests for a clearly named backend or frontend behavior.
- Review a contained feature area for regressions and open a focused PR.
- Update documentation when behavior has already changed.
- Make small bug fixes with a short diff and a clear test command.
- Refactor narrowly when the public behavior and tests stay the same.

Avoid Jules tasks that require:

- SSH access to `datachat-vps` or `datachat-db`.
- Reading or changing `.env`, `.env.local`, `.env.production`, `mcp_connectors.json`, production logs, or private credentials.
- Direct VPS deployment, systemd restarts, nginx changes, or database administration.
- Large architecture rewrites without a written plan and human approval.
- Long-running local servers or watch commands.

## Required Jules PR Notes

Every Jules PR should include:

- What changed.
- Why it changed.
- Files or features touched.
- Tests/builds run, with exact commands.
- Any known gaps, assumptions, or manual checks still needed.

## Codex Review After Jules

Codex should review Jules output before anything is merged or deployed:

1. Fetch the Jules branch or PR.
2. Inspect the diff for behavior changes, secret exposure, broad rewrites, and accidental deploy/config edits.
3. Run relevant local checks:
   - Backend: `./.venv/bin/pytest -q`
   - Frontend: `cd frontend && npm test -- --run` when tests changed or frontend behavior changed.
   - Frontend build: `cd frontend && npm run build` before deployment-sensitive UI changes.
4. Push only review fixes or follow-up commits that are backed by passing checks.
5. Leave production deployment to the normal VPS flow below.

## Nightly Automation Intent

Use Jules scheduled tasks for background code review or small maintenance PRs. Use Codex nightly automation to review completed Jules PRs in the early morning, run checks, and push safe follow-up fixes. Do not auto-deploy Jules output to production unless a separate user request explicitly asks for deployment.

# Data Sources

## MySQL (Remote)
- **Host:** `66.116.235.156`
- **User:** `Rapiduser`
- **Database:** `rapidai`
- **Port:** `3306`
- **MCP Server:** `@berthojoris/mcp-mysql-server` (stdio via `npx`)
