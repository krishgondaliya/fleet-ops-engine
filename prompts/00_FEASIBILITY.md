# Prompt 00 — Independent feasibility and evidence audit

Act as a skeptical senior data engineer, applied AI researcher, and FDE. You are **not** implementing an application yet.

1. Read `CLAUDE.md`, all `context/*.md`, and `source/ORIGINAL_OBSIDIAN_SPEC.md` completely. Call out contradictions and assumptions that are unverified, especially in the earlier source document.
2. Independently check official current sources: Citi Bike system data, the data-sharing policy, GBFS discovery and *actual* advertised station-info/status schemas if reachable, and the matching GBFS version's field semantics. Use the least invasive permitted reads; do not start continuous polling or bulk downloads. Record exact source URLs and verification timestamp.
3. Inspect a **small** historical trip sample only if accessible and permitted. Report verified fields/types and actual station-ID join feasibility; if not accessible, clearly say `not verified`.
4. Identify dataset gaps and leakage risks, especially: historical trips ≠ status history; attempted demand is censored; future empty/full labels require observed station snapshots; bike-count changes do not uniquely identify operator relocations.
5. Evaluate the *feasibility* of the product claims and scientific experiments. Mark each as feasible now, feasible after collecting enough snapshots, requiring an optional source, not defensible, or blocked by data/policy.
6. Flag trademark and licensing constraints before a public-facing name or portfolio deployment. Treat the working title as internal until resolved.
7. Generate a **feasibility/evidence report**, not a final architecture or implementation plan. Include a source registry, source status, field inventory, highest-risk assumptions, important questions, and a small recommended MVP problem statement.
8. Where several possible scopes exist, recommend the least costly scientifically defensible first task. Explain why; do not dictate frameworks or microservices yet.

**Outputs requested:** present (and, when file writing is approved, save under `docs/discovery/`): `FEASIBILITY.md`, `SOURCES_AND_POLICY.md`, `DATA_DICTIONARY_DRAFT.md`, `ASSUMPTIONS_AND_RISKS.md`.

**Output quality:** Label all claims `verified`, `source-stated`, `reasoned`, or `unknown`. Cite links and sample inspections. State what you **could not verify**. Do not claim programmatic calls succeeded if they did not. Do not write application code, create database resources, deploy, start polling, subscribe to services, or incur costs.

**Finish with:** a concise go/no-go assessment and the smallest set of truly blocking questions, if any. Other uncertainties should become explicit assumptions for the architecture stage.
