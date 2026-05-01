---
name: Codex review Jules PR
about: Ask Codex to review a Jules branch or PR
title: "[Codex Review] Jules PR "
labels: codex-review,jules
assignees: ""
---

## Jules PR or Branch

Link the PR or name the branch.

## Review Focus

- Functional correctness:
- Tests/build:
- UI behavior:
- Deployment risk:

## Allowed Follow-Up

- [ ] Codex may push small cleanup commits to the Jules branch.
- [ ] Codex should only report findings.
- [ ] Codex may deploy after review if all checks pass.

## Required Checks

- `./.venv/bin/pytest -q`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`
