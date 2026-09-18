# Agent Handoff — Interrupted Refactor

## Important Warning

This refactor was started by Claude Sonnet and was interrupted before completion.

The project is now tracked with Git.

Do NOT:

- restart the refactor from scratch
- redesign the architecture without a clear technical reason
- discard or overwrite existing changes
- reset/revert files unless explicitly instructed
- remove partially migrated code before verifying all callers
- modify unrelated files
- force-push or rewrite Git history

The current code has NOT been fully run or validated yet.

Existing changes may be:

- complete
- partially implemented
- inconsistent
- temporarily broken during migration

Treat the current working tree and commit history as the source of truth.

---

## First Steps

Before editing anything:

1. Read `PLAN.md`.
2. Read this file completely.
3. Run:

   ```bash
   git status
   git diff --stat
   git diff
   git log --oneline -10
   ```
