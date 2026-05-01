# Jules + Codex Lifecycle

This repo can use Google Jules as an async cloud contributor while Codex remains the local review and VPS release operator.

## Roles

- Jules: GitHub issues, scheduled tasks, cloud branches, and PRs.
- Codex: local review, test/build verification, follow-up fixes, GitHub push, and VPS deploys when explicitly requested.
- Human: approves scope, merge/deploy policy, and any production-sensitive decision.

## Daily Background Loop

1. Jules scheduled task runs in Google Cloud against the GitHub repo.
2. Jules opens or updates a branch/PR with a focused change.
3. Codex nightly automation checks for Jules-authored branches/PRs.
4. Codex reviews the diff and runs the relevant checks.
5. If the change is safe but needs cleanup, Codex commits and pushes follow-up fixes to the same branch when permitted.
6. If the change is unsafe, too broad, or needs secrets/production access, Codex leaves a clear review summary and does not push.

## Suggested Jules Scheduled Prompt

Use this as the recurring Jules task prompt:

```text
You are working on the data analysis chatbot repo. Act as a careful async contributor.

Daily task:
- Review one small, high-value area for bugs, missing tests, stale docs, or simple maintainability issues.
- Prefer backend/frontend tests, docs, or narrowly scoped bug fixes.
- Keep the diff focused and avoid architecture rewrites.
- Do not touch secrets, .env files, mcp_connectors.json, deployment credentials, nginx/systemd config, or production/VPS operations.
- Do not run long-lived dev servers.
- Run the relevant checks and include exact commands and output summary in the PR.
- Open a GitHub PR with a clear title, summary, touched files, test evidence, and known gaps.

Project checks:
- Backend: ./.venv/bin/pytest -q
- Frontend tests: cd frontend && npm test -- --run
- Frontend build: cd frontend && npm run build
```

## Good Jules Task Examples

- Add regression tests for PDF/ZIP/7z upload behavior.
- Review project source add/remove behavior and add frontend coverage.
- Check connector UI state handling for obvious regressions.
- Update docs when source-ingestion behavior changes.
- Reduce duplicated helpers in one module with tests.

## Bad Jules Task Examples

- Deploy this to the VPS.
- Fix production MCP credentials.
- Rewrite the full chat architecture.
- Change nginx/systemd settings.
- Connect directly to the production database.

## Codex Nightly Review Rules

Codex may push follow-up commits only when:

- The branch/PR is clearly from Jules or labeled for Jules review.
- The diff is small enough to review in one pass.
- No secrets or production-only files are touched.
- Required checks pass after Codex changes.

Codex must stop and leave a summary when:

- The PR changes credentials, deployment config, or remote-service behavior.
- The fix requires production data or manual account access.
- Tests fail for reasons that are not clearly caused by the PR.
- The PR is too broad to review safely in the automation window.

## Production Deploy Boundary

Jules does not deploy. Codex deploys only when asked:

```bash
rsync -az --stats --exclude-from=/tmp/datachat-rsync-excludes \
  -e "ssh -F /Users/rajasekharbandreddy/.ssh/config" \
  ./ datachat-vps:/opt/datachat/
ssh datachat-vps 'cd /opt/datachat/frontend && npm run build'
ssh datachat-vps systemctl restart datachat-backend.service datachat-frontend.service
ssh datachat-vps 'curl -fsS http://127.0.0.1:8000/health && curl -fsSI http://127.0.0.1:3000'
```
