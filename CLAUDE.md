# Project instructions for Claude Code

Working title: **Citi Bike: Agentic Fleet Forecasting & Optimization Engine**. Independent analysis based on public data; NOT an official Citi Bike service or partnership.

## Read first
- `context/PROJECT_BRIEF.md`
- `context/REQUIREMENTS_AND_BOUNDARIES.md`
- `context/DATA_SOURCE_DOSSIER.md`
- `context/EXPERIMENTS_AND_PROOF.md`
- `context/OPEN_DECISIONS.md`
- `source/ORIGINAL_OBSIDIAN_SPEC.md` (background proposal, NOT binding architecture)
- Generated and current `docs/` artifacts, if they exist

## Invariants
1. Separate **observed**, **predicted**, **inferred**, and **simulated** statements in code, UI, documentation and metrics.
2. Never invent data, data-source availability, test passes, benchmark gains, or live operational outcomes.
3. Provider data policy and branding: do not redistribute stand-alone raw datasets, scrape unauthorized interfaces, imply affiliation, use protected logos/marks for public branding without written permission, or access customer data. Escalate unresolved policy questions.
4. Historical trips are completed trips, **not** observed attempted demand or historical station stockout labels. Live GBFS is a snapshot stream, not a retrospective archive. Respect feed TTL, service status, freshness and version differences.
5. Model-facing tools must be scoped, validated, bounded, least-privilege, and evidence-returning. No real fleet-control tools, unrestricted SQL, or irreversible actions.
6. No future-data leakage, random time splits, unsupported causal claims, or comparison of policies using unequal scenarios. Include simple baselines and reproducible evaluation.
7. Do not incur paid API/GPU/cloud costs, begin persistent high-volume polling, expose services publicly, delete user data, or publish/deploy without explicit user approval.
8. Favor the smallest robust implementation. Challenge unnecessary frameworks, model complexity, multi-agent systems, or microservices.
9. Run applicable tests and record **exact commands and results**. If tests cannot be run, say so. Never claim an untested task is finished.
10. Maintain `docs/STATUS_AND_HANDOFF.md` during implementation: completed work, files, verification evidence, blockers, next ticket. Distinguish proposals from committed code.

## Engineering behavior
- Before code: read current repository state and selected ticket; identify a verifiable outcome.
- Change one coherent vertical slice per session unless explicitly directed otherwise.
- When a source cannot be reached, record uncertainty and build an inspectable fallback/test fixture, **never pretend a fake sample came from the provider**.
- Preserve user edits; do not overwrite unrelated work. Use git for traceability. Ask before destructive commands.
- Prefer deterministic/unit tests, integration tests with fixtures, and frozen evaluation sets to impressions from demos.
- Explain consequential engineering tradeoffs and material assumptions, concisely.
