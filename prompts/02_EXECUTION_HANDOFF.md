# Prompt 02 — Turn approved architecture into a rigorous execution handoff

Read the latest feasibility report, approved architecture/decisions, project requirements, and the actual repository. The goal is to create a plan that Claude Code Opus can execute across **many new sessions** without losing accuracy or pretending unfinished work is complete.

Generate and maintain durable, specific artifacts:

1. **End-to-end dependency-aware roadmap** separated into thin, demonstrable vertical slices. Prioritize reliable live data and proof of data quality; do not block all progress on collecting weeks of labels. Define how data collection and the rest of development may proceed in parallel *without* pretending labels exist.
2. **Ticket/backlog catalog** with stable IDs. For each ticket: objective, user-visible outcome, prerequisites, source inputs, expected files/interfaces, constraints, acceptance tests, reproducible commands, verification evidence, risks, estimated cost/effort range, and explicit definition of done. The estimates are planning aids, not guarantees.
3. **Quality and release gates** for data integrity, forecasting, agent groundedness, simulation validity, security, operations and portfolio publication. Define the fallback if an advanced method fails to beat baseline.
4. **Experiment register** with preregistered question, baseline, data window, metrics, no-leakage condition, reproducibility metadata and success/failure rule.
5. **Operational setup checklist** for local development, secrets, data provider usage, low-cost development, CI, test fixtures, reproducible evaluation and a possible deployment; do not actually deploy or incur costs.
6. **Uncertainty and blockers register**: owner, severity, verification route, effect on dependencies and honest unblocked work.
7. **Session handoff protocol**: a persistent current-state file (`docs/STATUS_AND_HANDOFF.md`) that lists completed, verified, partial, untested and not started work, last command results, decisions, next ready ticket and exact restart context. Base status on actual code/tests, not merely written plans.
8. **Acceptance/demo scenario**: what a hiring reviewer can run end to end, including cases when no snapshot history exists and when several weeks of real snapshots are available.
9. **Code review checklist** for every slice (correctness, data provenance, errors, test quality, cost/permissions, documents, honest claims).

**Requested deliverables:** `docs/planning/MASTER_PLAN.md`, `docs/planning/BACKLOG.md`, `docs/planning/QUALITY_GATES.md`, `docs/planning/EXPERIMENT_REGISTER.md`, `docs/planning/RELEASE_CHECKLIST.md`, and initialized `docs/STATUS_AND_HANDOFF.md`.

Use checkboxes where helpful. Avoid filler and giant speculative tickets. Where code is not written, status must be `not started`. Do not mark an evaluation complete before its real data and tests exist. Show dependencies between tickets and define the **first ready ticket**.

**Important:** Stop before implementing application code. Present the plan for architectural/permission review. Do not automatically approve paid models, live deployments, or persistent collectors.
