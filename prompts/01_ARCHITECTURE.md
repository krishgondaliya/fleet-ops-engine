# Prompt 01 — Architecture generation by Opus (after feasibility)

The feasibility audit is complete. Read its written findings and all project-context files, then **independently design** this system. The architecture in the source Obsidian spec is just an earlier idea; do not copy it uncritically.

Act as the system architect and applied AI lead. Your job is to choose technology and tradeoffs appropriate for **one engineer building a strong, low-cost FDE portfolio project** using public data.

Produce the following, with diagrams where useful:

1. **Requirements reconciliation:** What is being built and why, which outcomes are observable now, which are data-gated, and which features should be rejected/deferred.
2. **At least two credible architecture approaches** (one minimally complex) with a scored/traced comparison: operational risk, data integrity, iteration speed, maintainability, cost, analytical rigor, testability, deployment difficulty. Select one and articulate why.
3. **Data lineage and interfaces:** provider discovery, respectful ingestion, raw/normalized provenance, time semantics, versioning, storage and data contracts, trip/status joins, missingness/retention. Use *observed* schema facts; flag proposed columns as design, not source.
4. **Forecasting strategy and experimental validity:** exact target(s), valid labels, feature-availability logic, simple baselines, evaluation and model promotion conditions, no-data-yet fallback. Distinguish already empty/full and transition prediction.
5. **Agent boundaries:** decide when to use LLM versus deterministic functions. Design read-only typed tools, scoped authorization, output evidence IDs, bounded execution, failure handling and reproducible agent evals. Explain why multi-agent is or isn't justified.
6. **Simulation/optimization design:** scope, demand/flow assumptions, constraints, no-action and heuristic comparisons, uncertainty and inability to claim actual service impact.
7. **User workflow and delivery experience:** minimum credible operator-facing interface; no design-heavy distraction. Include observability, setup, permissions, cost and deployment story.
8. **Failure scenarios and invariants:** stale feeds, wrong field names, moved/renamed stations, DST, bad joins, absent data, model performance worse than baseline, agent unsupported claims, unreachable API, secret leakage, capacity violations.
9. **Decision log:** key choices, serious alternatives, rejection reasons, costs and upgrade triggers. Explicitly document what remains unresolved and its consequences.

**Deliverables requested:** `docs/design/ARCHITECTURE.md`, `docs/design/DECISIONS.md`, `docs/design/DATA_CONTRACTS.md`, `docs/design/EVALUATION_DESIGN.md`, `docs/design/SECURITY_AND_OPERATIONS.md`. Create them when writing is authorized; otherwise present them for review.

**Constraints:** No application implementation yet. No fake code, no defaulting to a massive enterprise stack, no unsupported claims that a provider feed has a given field, no invented metrics. A diagram alone is insufficient. Make the design executable by a solo engineer and cost-conscious.

**Finish with:** a short architecture review checklist and any genuinely blocking user approvals. Identify the earliest vertical slice that would prove the proposed design works.
