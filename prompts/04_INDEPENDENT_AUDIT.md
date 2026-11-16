# Prompt 04 — Adversarial independent quality audit

Act as a skeptical independent reviewer rather than the implementing engineer. Inspect repository code, docs, experiments, changed files, and actual test output. Don't treat docs/checkmarks as proof.

Audit, with severity-ranked findings:
- **External data truthfulness:** permitted source access, exact GBFS version and field semantics, TTL/staleness handling, timestamps, source provenance, duplicates, station-ID joins, nulls, station closures, missing historical labels, release/branding constraints.
- **Prediction quality:** label definitions, chronological splits, leakage, persistence baseline, class imbalance, already-empty/full separation, calibration, held-out reliability and whether any quality claims are reproducible.
- **Agent:** tight typed/read-only tool boundaries, permission enforcement outside prompts, adversarial input handling, bounded calls/cost, evidence traceability, unsupported causality, robust abstention and tool failures.
- **Optimization:** physical feasibility, conservation, common simulation assumptions, determinism, fair no-action/heuristic baselines, uncertainty analysis and all results labeled simulated.
- **Operations/security:** minimal secrets surface, reproducible environment, CI, migration/rollback strategy, errors, logging, documentation, service health, cost controls and deployment boundary.
- **Portfolio honesty:** actual user data vs fixtures, independent affiliation disclaimer, no fabricated usage or measured external business outcomes, explanation of limitations.

For each issue provide: evidence (file/line/test), impact, a minimal suggested fix, and a test that would prove it. Distinguish `observed failure`, `potential issue`, `untested risk`, and `missing requirement`.

**Run the available automated checks and record the commands.** Don't claim a test pass based on a README. Produce `docs/reviews/AUDIT_YYYY-MM-DD.md` when writing is authorized. Propose an ordered fix list; **don't silently rewrite the whole project** during audit.
