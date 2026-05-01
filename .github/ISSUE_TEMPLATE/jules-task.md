---
name: Jules task
about: Give Jules a focused async coding task
title: "[Jules] "
labels: jules
assignees: ""
---

## Goal

Describe the one focused outcome Jules should produce.

## Scope

- Area:
- Files or features likely involved:
- Out of scope:

## Constraints

- Do not touch secrets, `.env*`, `mcp_connectors.json`, VPS/systemd/nginx config, or production credentials.
- Do not deploy to the VPS.
- Keep the diff focused.

## Verification

Run the relevant checks and include exact command output summary in the PR:

- `./.venv/bin/pytest -q`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

## PR Expectations

- Summary of changes.
- Tests/builds run.
- Known gaps or assumptions.
