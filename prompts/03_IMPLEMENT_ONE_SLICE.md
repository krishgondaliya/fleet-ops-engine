# Prompt 03 — Implement exactly one verified slice (repeat as needed)

Implement **[TICKET_ID or "the next unblocked, highest-priority ticket"]** from the approved `docs/planning/BACKLOG.md`.

Before editing:
- Read `CLAUDE.md`, `docs/STATUS_AND_HANDOFF.md`, ticket prerequisites, actual code/tests and relevant design artifacts. Verify prerequisites in the repository; do not assume status files are correct.
- Briefly state the concrete behavior to deliver, acceptance tests, likely files and explicit external actions. If a required action needs budget, legal/policy clarification, long-lived polling, secret access or deployment approval, stop for that authorization; continue with safe offline work if possible.
- State how to run a minimal proving check. Keep scope to one coherent vertical slice and don't refactor unrelated subsystems.

During execution:
- Implement production-minded error handling, typed interfaces where appropriate, explicit data provenance, deterministic test fixtures, and documented constraints.
- Run focused unit/integration tests and relevant lint/typecheck. If applicable, run bounded integration reads against the approved official provider endpoint and record exact observed output metadata (not sensitive raw bulk data). Do not start unauthorized repeated polling.
- On ML/agent/simulator tickets, prove quality against a baseline/fixtures/held-out data where available. If real labels or credentials are unavailable, label the validation pending and do not substitute fictional metrics.
- Fix failures that are in scope; don't claim success if tests are still failing or unrun.
- Record important implementation choices and the reason; add a regression test for every discovered bug when practical.

Before ending:
1. Show a concise diff/file summary and what user-visible behavior is now demonstrated.
2. Show **exact test commands and outcomes** with any skipped tests and reasons.
3. Update `docs/STATUS_AND_HANDOFF.md` with verified status, changed files, evidence, decisions, remaining blockers, next ready task and reproducible resume commands.
4. Update ticket/experiment status honestly: `verified done`, `implemented not verified`, `blocked`, or `not started`.
5. Flag any changes that alter data meaning, model claims, provider policy interpretation, or deployment cost.

**Do not** say the whole project is completed when a slice is complete. Do not start a second ticket unless it is a small necessary dependency and documented in the handoff.
