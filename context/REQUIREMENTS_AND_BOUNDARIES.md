# Behavior requirements and non-negotiable boundaries

**This is a requirements input, not an architecture, schema or ticket plan.** Ask Opus to translate each into tests and actionable architecture choices.

## Functional capabilities

**A. Data observability**
- Display current station bikes, free docks, service flags, source timestamp, retrieval timestamp and staleness / missing indicators.
- Capture timestamped station status if automated collection is permitted by source terms and cadence; detect duplicate/out-of-order/stale/malformed records.
- Integrate published trip history with explicit coverage diagnostics; support different station IDs, null fields and changing station metadata.
- Show at least one real station's time history once collected, or clearly label the lack of longitudinal observations.

**B. Measurable forecasting**
- Specify whether the target is "empty/full at t+30 min" or "first transition to empty/full within 30 min"; these are different tasks.
- Separate currently serviceable stations from already empty/full stations in evaluations.
- Compare at least one transparent baseline and one learned/statistical method **only when adequate labels exist**; if insufficient, report a pending evaluation and continue with honest proxy tasks.
- Expose forecast issuance time, horizon, model version, data freshness and appropriate uncertainty/validation limitations.

**C. Grounded investigation**
- A user can ask an operational question; an AI investigator may use **read-only, typed, bounded** analytical tools to retrieve evidence.
- Numeric claims must trace to returned tool evidence; distinguish observations, statistical association, hypotheses and unknowns.
- Show meaningful uncertainty and abstain if tools fail or evidence is missing; do not let the model perform unrestricted queries or operational actions.
- Preserve traces useful for judging tools and claims, with safeguards for credentials and untrusted text.

**D. Rebalancing analysis**
- Compare no-action and at least one constrained hypothetical policy; advanced optimization must demonstrate value over a simple heuristic.
- Enforce station capacity, conservation and documented simulated move/travel budgets.
- Use identical simulation conditions for fair comparisons and publish assumptions; quantify sensitivity to unknown/unobserved demand and interventions.
- Clearly label *all* proposed moves and improvements as simulated.

**E. Operator / portfolio interface**
- Show selected station geography, current state, alerts or forecasts, investigation evidence, and scenario comparisons where those components are actually implemented.
- Make source provenance, freshness, incomplete data and hypothetical results visible.
- Make reproducibility accessible to a reviewer without disclosing keys or copying prohibited raw datasets.
- Clearly state that this is independent public-data analysis, not an official service or affiliation.

## Quality requirements
- Reasonable local execution and deployment cost for a single-developer portfolio project.
- Repeatable setup, migration and testing; predictable failures and recovery; structured errors and traces.
- Data validation, timezone/DST handling (UTC canonical, local NY features only when appropriate), schema changes and station identifier drift.
- Offline testability with **explicitly identified fixtures**; no need for live internet in every test.
- Baseline/model/agent/simulator measurements on frozen, documented conditions.
- Strictly separate permitted public data from secrets and user-specific records.
- Clear operational runbook and technical decision trail.

## Constraints with real consequences
- **External data is not owned by the project.** The source can change, throttle, fail or disappear.
- **Data use**: provider forbids particular extraction methods, standalone dataset redistribution, customer reidentification, implied affiliation, and unpermitted trademark use. Recheck exact policy text rather than paraphrase-only reliance.
- **No existing historical status archive is supplied.** Retrospective availability labels cannot be manufactured from completed trips.
- **No internal Citi Bike operations visibility.** Rider demand, dispatch logistics and reasons for changes are partly hidden.
- **No approved cloud budget / API provider / paid model yet.** Identify options and projected costs; get approval before incurring charges.
- **No guaranteed snapshot retention window.** Plan for evaluation lag honestly.
- **Safety**: read-only analysis; irreversible external actions and public deployments require user approval.

## Explicitly disallowed shortcuts
- Claims of business impact based on simulator outcomes.
- Treating zeros caused by station closure or stale feeds as normal stockout events.
- Joining historical trips to GBFS status solely on names without coverage checks.
- Future data in training features, including weather realized after forecast issuance.
- Random shuffling of time-series evaluation data.
- Reporting high overall accuracy on imbalanced stockouts while missing useful early warnings.
- Agent-generated forecasts or arithmetic without traceable underlying analytics.
- Unbounded SQL, unbounded agent loops, uncontrolled API costs, or scraping unapproved websites.
- Adding complexity (Kafka, Kubernetes, multi-agent swarms, graph neural nets) just because the project sounds impressive.

## Potential scope tiers (not a plan)
**Essential demonstrable value:** truthful data ingestion + current-state view + baseline risk analysis + evidence-grounded investigation on recorded data.  
**Conditional capability:** independently validated t+30 shortage forecasting after enough snapshots.  
**Advanced:** fair hypothetical rebalancing with explicit model limitations, then richer AI experiments and deployment.

Ask Opus to decide sequencing and define the precise quality gates, including what is blocked on data accumulation.
