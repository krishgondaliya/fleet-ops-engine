# Citi Bike FDE Engine: Execution Architecture and Phased Plan

Nov 15, 2026 · @Albert Einstein

## Bottom line

The project is a go, and the critical path is the calendar, not the code. No forecast can be honestly evaluated until we have collected our own station snapshots, so the collector ships first and everything else gets built while it runs.

**The system in one paragraph.** A polite GBFS collector writes immutable raw snapshots to Parquet. SQL transforms (dbt on DuckDB) turn raw feeds and monthly trip files into clean, tested datasets. A small code-defined ontology sits on top, and every property carries an epistemic tag: observed, derived, predicted, or simulated. A FastAPI service exposes the ontology, and the agent's tools are generated from it, so the LLM can only read what the ontology allows. Forecasts come from a ladder of models that starts with a classical station inventory model and climbs to gradient boosting only if it wins on held-out time. An optimizer proposes simulated truck moves, a human approves or rejects them in the operator app, and that decision is logged.

**What I changed from the kit and the original spec:**

1. **Collector first, on an always-on host.** The spec puts it in Week 1 next to six other tasks with no hosting plan. A laptop collector has gaps, and gaps destroy labels.
2. **Collect the whole system, analyze one cluster.** One GBFS request returns every station, so scoping collection to 30 to 50 stations saves nothing and throws away neighbor and boundary context.
3. **DuckDB plus Parquet instead of Postgres.** Cheaper, faster on trip analytics, and a reviewer can reproduce it with one command.
4. **A station inventory model as the day-one forecaster.** It works from trip history before any labels exist, and its cost curve is the principled input to the optimizer. The spec jumps from heuristics to LightGBM and bolts on a generic min-cost flow.
5. **An ontology with human-approved actions.** The spec has flat tables and a chat panel. That is a dashboard, not an FDE workflow.
6. **Transition prediction is the primary target.** "Empty at t+30" is mostly persistence. The operational question is which serviceable stations will run out.
7. **A React operator app instead of Streamlit.** The alert to investigation to decision workflow needs real UI state.
8. **Opus attacks this proposal instead of designing from blank.** Prompt 01 in the kit gets this doc as a candidate to challenge against M0 evidence.

## Evidence check

I verified the license text today, but I could not reach the live feeds or the trip bucket from my workspace, so every payload-level fact below is still open until Milestone 0 runs on your machine.

| Claim | Status | Source |
| --- | --- | --- |
| License allows access, analysis, modification and use for any lawful purpose, including distribution inside your own product | Verified 2026-11-15 | [Data License Agreement](https://ride.citibikenyc.com/data-sharing-policy) |
| 2(b): no hosting or publishing the data as a standalone dataset. Non-commercial analyses and reports may use it as source material | Verified | [Data License Agreement](https://ride.citibikenyc.com/data-sharing-policy) |
| 2(c) and 2(e): access only through the provided interface, and no data mining or extraction methods on the website or the data | Verified | [Data License Agreement](https://ride.citibikenyc.com/data-sharing-policy) |
| 2(g) and 2(h): no implied affiliation, no CITI BIKE mark or logo without written permission | Verified | [Data License Agreement](https://ride.citibikenyc.com/data-sharing-policy) |
| No attribution clause. License can be revoked at any time by notice | Verified | [Data License Agreement](https://ride.citibikenyc.com/data-sharing-policy) |
| Trip files list ride ID, rideable type, start and end time, station names and IDs, coordinates, member or casual | Source-stated | [System Data](https://citibikenyc.com/system-data) |
| GBFS 2.3 says status feeds should never be more than 5 minutes stale, with cadence set by `ttl` | Spec-stated | [GBFS v2.3](https://github.com/MobilityData/gbfs/blob/v2.3/gbfs.md) |
| Files prefixed `JC` are Jersey City, a small sample to validate schema cheaply | Source-stated | [data.gov catalog](https://catalog.data.gov/dataset/citi-bike-system-data) |
| Trip-file station IDs match GBFS `short_name`, not GBFS `station_id` | Third-party report, must verify | [DisPatch70 dataset card](https://huggingface.co/datasets/hulnegy/DisPatch70) |
| Live `station_status` and `station_information` field names, `ttl`, e-bike count fields | Not verified | M0 |
| Trip timestamps are naive local time (a DST trap if true) | Unknown, suspected | M0 |
| An archived-forecast weather source exists for leak-free backtests | Unknown | M0 |

**My policy reading (reasoned, not legal advice).** Polling the published GBFS endpoint is using the provided interface. Clause 2(e) is broadly worded, so we stay conservative: poll no faster than the feed's `ttl`, send an identifying User-Agent with a contact address, never touch the website, keep raw data out of git and out of the public app, and ship under a neutral public name. The license names bike-data@lyft.com for permission requests. A short note describing the project is optional and cheap.

## Challenged assumptions

Twelve spec assumptions do not survive contact with the data or the goal, and each has a replacement decision.

| Spec assumption | Problem | Decision |
| --- | --- | --- |
| Collect 30 to 50 stations | The feed returns all stations per request. Narrow collection loses neighbors and cannot be undone later | Store every station raw. Scope analysis, models and UI to one cluster |
| PostgreSQL, maybe TimescaleDB | A server to run and pay for, slow on tens of millions of trip rows, nothing here needs concurrent writers | Parquet plus DuckDB for data, SQLite for app state. Postgres only if a trigger fires |
| Label is "empty at t+30" | Dominated by stations already empty. High scores, no operational value | Primary: first passage to empty or full within 30 minutes, among currently serviceable stations. State-at-t+30 kept as secondary |
| Zero bikes available means empty | Ignores classic vs e-bike mix and service flags | Label on rentable bikes with `is_renting` true. Preregister threshold 0, report sensitivity at 2 or fewer. Split by bike type only if the feed supports it |
| The ML model is LightGBM | Skips the classical method this domain already has | Ladder: persistence, time-of-week rates, inventory model, logistic regression, then LightGBM. Each rung must beat the one below |
| Optimizer minimizes an unspecified shortage penalty | No link between forecast and objective | Per-station expected unmet demand as a function of starting inventory, from the inventory model. That curve is the objective |
| Seven hand-written agent tools, including run simulation | Tool surface drifts from the data model. Simulation is expensive and unbounded | Tools generated from the ontology. Simulation runs are bounded and cached. The only write is a proposal a human must approve |
| Streamlit or lightweight React | Streamlit reruns the script on every click and cannot hold an alert to decision workflow | React, TypeScript, MapLibre, served by the API |
| Four one-week phases | Labels need about four weeks minimum after the collector starts, and the window crosses the holidays | Nine milestones over 8 to 10 weeks, forecast evaluation gated on real label counts, winter regime disclosed |
| Weather from the NWS API | NWS serves live forecasts, not what was forecast last month | Weather is an ablation only, and only with an archived-forecast source verified in M0 |
| Join trips to status on station ID | Two ID namespaces. Stations move, rename and resize | Versioned station dimension with a crosswalk, join coverage reported as a metric |
| Opus designs the architecture from blank (kit prompt 01) | Wastes this work and removes a concrete target to attack | This doc goes in the repo as a proposal. Opus must challenge it against M0 evidence |

## System architecture

One Python codebase, one small VM, four layers: datasets, ontology, intelligence, operator app. Nothing is a separate service until a measured trigger says so.

&#91;embedded content: system layers · sources to operator workflow\]

Read it top down: data flows into datasets, the ontology is the only door, and the three intelligence components and the app never query raw data directly.

| Layer | Choice | Rejected, and why | Upgrade trigger |
| --- | --- | --- | --- |
| Language and tooling | Python 3.12, uv, ruff, pyright, pytest, hypothesis | Poetry and mypy work too, uv and pyright are faster | None |
| Collector | One long-running process, httpx, discovery resolved at runtime, systemd restart | Queue or Kafka: one producer, one consumer, about one request per minute | More than one feed provider |
| Raw storage | Immutable gzipped JSON per fetch, compacted daily to Parquet | Writing straight to a database: loses the original payload and the ability to reparse | Never |
| Transforms | dbt-core with dbt-duckdb: staging, clean, ontology marts, with data tests | Hand-rolled SQL runner: no lineage graph, no test framework. Spark: absurd at this size | dbt fights the incremental snapshot model |
| Query engine | DuckDB over Parquet, read-only in the API | Postgres plus Timescale: server cost and ops for no concurrency need | Multi-user writes or managed hosting that requires it |
| App state | SQLite in WAL mode: proposals, decisions, agent runs, traces | DuckDB for this: single-writer rules clash with the API | Same trigger as above |
| Orchestration | cron plus `just` targets | Airflow, Dagster, Prefect: a scheduler to babysit for three jobs | More than about ten scheduled jobs or cross-job retries |
| Ontology | Python registry (Pydantic) that generates API schemas, agent tools and UI metadata | Graph database: the relationships are few and fixed | Ad hoc multi-hop queries become a real need |
| Forecasting | numpy and scipy inventory model, scikit-learn, LightGBM | Deep or graph models: no evidence tabular loses, and too little data | LightGBM clearly beats baselines and spatial ablation shows lift |
| Optimization | OR-Tools CP-SAT plus a greedy heuristic | Reinforcement learning: no environment worth trusting | Robust or stochastic variants after sensitivity results |
| Agent | Anthropic API tool-use loop written directly, single agent | LangChain or multi-agent: hides the loop we need to measure and bound | An experiment shows planner plus executor wins |
| API | FastAPI, Pydantic v2, generated OpenAPI client | Separate services per domain | Independent scaling need |
| Operator app | React, TypeScript, Vite, MapLibre GL | Streamlit: no workflow state. Next.js: no need for SSR | None |
| Observability | structlog JSON logs, a collector health table, `/healthz`, agent traces in SQLite | Full OpenTelemetry stack: more infrastructure than product | A second host |
| Deployment | Docker Compose on one small VM, Caddy for TLS | Kubernetes, serverless: the collector must be long-lived | Never at this scale |
| CI | GitHub Actions: lint, types, tests, dbt build on fixtures | None | None |

The second credible option was Postgres for everything. It wins on familiarity and concurrent writes. It loses on cost, on trip-analytics speed, and on reviewer reproducibility, which matter more here.

## Ontology

Ten object types model the operation, and each property declares whether it is observed, derived, predicted or simulated. That tag travels through the API, the agent's evidence and the UI badges, so a simulated number cannot be displayed as a measurement.

| Object | Key | What it holds | Epistemic class | Backed by |
| --- | --- | --- | --- | --- |
| Station | internal station key | Name, coordinates, capacity, external IDs, valid-from and valid-to | Observed | `station_information`, versioned |
| StationState | station, source timestamp | Bikes, docks, service flags, fetch time, staleness | Observed | `station_status` snapshots |
| TripFlow | station, time bucket | Departures and arrivals from completed trips | Observed, censored | Monthly trip files |
| ServiceInterval | station, start | A contiguous run of empty, full, closed or serviceable | Derived | StationState |
| DataQualityIssue | id | Gap, stale feed, schema drift, failed join, impossible value | Derived | Collector and tests |
| Forecast | run, station, target time | Probability of empty and of full, model version, issue time | Predicted | Model runs |
| Alert | id | A forecast that crossed a validated threshold, with status | Predicted | Forecast |
| Investigation | id | Question, tool trace, evidence IDs, claims with verdicts | Mixed, tagged per claim | Agent runs |
| RebalancingProposal | id | Moves, policy, scenario, simulated effect, assumptions | Simulated | Optimizer and simulator |
| Decision | id | Human approve or reject, reason, timestamp | Observed (about us, not the fleet) | Operator app |

**Links.** Station has many StationStates, TripFlows, ServiceIntervals and Forecasts. Station is near Station (distance-ranked). Alert is raised from a Forecast, Investigation concerns Stations and Alerts, RebalancingProposal responds to Alerts, Decision resolves a RebalancingProposal.

**Actions.** There are four, all internal to our system: acknowledge an alert, open an investigation, propose a rebalancing plan, record a decision. No action touches anything outside our database. The agent may call only the first three, and a proposal stays inert until a human records a decision.

**Enforcement.**

1. The registry is the single source: API response models, agent tool schemas and UI column metadata are generated from it, and a CI test fails if they drift.
2. Every object returned to the agent or UI carries `evidence_id`, `source`, `as_of` and its epistemic class.
3. Lineage is the dbt graph for datasets plus `evidence_id` for individual facts, so any number on screen traces to a model, a dataset and a fetch.
4. Missing is a value. A station with no fresh snapshot has state "unknown", never zero.

## Data integration

Four sources feed three dataset tiers, and the hard problem is reconciling station identity across them, not moving bytes.

| Source | Cadence | What it gives | Known trap |
| --- | --- | --- | --- |
| GBFS `station_status` | At feed `ttl`, never faster | Live bikes, docks, service flags | No history. Stale and repeated payloads |
| GBFS `station_information` | Every few hours, plus on change | Identity, coordinates, capacity | Stations move, rename, resize |
| Monthly trip files | Monthly, about a month behind | Completed trips | Censored demand, different station IDs, possibly local timestamps |
| Weather (optional) | Deferred | Forecasts as issued | Only usable with an archive of past forecasts |

**Collector rules.**

1. Resolve feed URLs from the discovery document on start and daily. Never hardcode them.
2. Sleep for the payload's `ttl` between fetches, with a floor of 60 seconds. Use conditional requests where the server supports them.
3. Write the untouched response body, HTTP status and three clocks: our fetch time, feed `last_updated`, per-station `last_reported`.
4. Skip parsing duplicates by `last_updated`, but record that the fetch happened. A gap in fetches and an unchanged feed are different facts.
5. Back off exponentially on errors with a cap, and write a DataQualityIssue instead of retrying forever.
6. Parse with tolerant Pydantic models: required fields strict, unknown fields kept and logged as schema drift.
7. Send a User-Agent naming the project and a contact address.

**Storage layout.**

```text
data/                      # never in git
  bronze/gbfs/station_status/dt=YYYY-MM-DD/*.json.gz    # exact payloads
  bronze/gbfs/station_information/dt=YYYY-MM-DD/*.json.gz
  bronze/trips/YYYYMM/*.csv.zip                         # as downloaded, with checksums
  silver/station_state/dt=YYYY-MM-DD/*.parquet          # typed, deduped, UTC
  silver/station_dim.parquet                            # versioned identity + crosswalk
  silver/trips/month=YYYY-MM/*.parquet
  gold/                                                 # ontology marts, features, labels
  app.sqlite                                            # proposals, decisions, agent traces
```

**Reconciliation.** The station dimension is slowly changing: a new version row whenever name, coordinates or capacity change. Trips join through a crosswalk from the trip-file station ID to the GBFS station, expected to be `short_name` but unproven until M0. Every join publishes matched and unmatched counts by month, and unmatched trips are kept, not dropped. All timestamps are stored in UTC, with New York local time derived only for calendar features, and a DST test covers both transitions.

**Volume.** Size per day is unknown until M1 measures it. The plan assumes tens of megabytes per day compressed and sets an alert if the real number is ten times that.

## Forecasting and evaluation

The primary task is predicting which currently serviceable stations will hit empty or full within 30 minutes, and no model is promoted unless it beats the rung below it on held-out time.

**Targets, fixed before any training.**

- **Primary (transition):** station is serviceable at issue time `t`, and any observed snapshot in `(t, t+30 min]` shows zero rentable bikes with renting enabled. Same for docks.
- **Secondary (state):** empty or full at `t+30`, reported separately for already-empty and serviceable stations.
- **Excluded, and counted:** closed stations, stale snapshots, windows with fetch gaps. Exclusion rates are reported next to every metric.

**The model ladder.**

1. **Persistence and threshold:** alert if bikes are at or below k.
2. **Time-of-week climatology:** historical transition rate for this station and hour.
3. **Inventory model:** departure and arrival rates per station and time bucket from trip history, then the probability a finite-capacity birth-death process hits zero or capacity within 30 minutes from the current count. This is the standard operations-research treatment of bike-share stations (Raviv and Kolka 2013, O'Mahony and Shmoys 2015, citations from memory, to be confirmed in M0). It needs no snapshot labels to produce a forecast.
4. **Logistic regression** on lagged status features.
5. **LightGBM** on the same features plus trip-flow, neighbor and calendar features.

**Leakage controls.** Features use only snapshots with fetch time at or before `t`. Trip-derived rates use only months published before `t`, because trip files arrive about a month late. Splits are chronological with a 30-minute gap. The final test window is frozen before tuning. Uncertainty comes from a block bootstrap by day.

**Metrics.** PR-AUC, precision and recall at a fixed alert budget (top 5 alerts per hour across the cluster), lead time before the event, Brier score and reliability curve, results by station and daypart. Accuracy is never reported alone.

| ID | Question | Compared against | Ship rule | Earliest valid |
| --- | --- | --- | --- | --- |
| F0 | Does the inventory model rank risky stations at all? | Climatology | Reported as pending until labels exist | Day 1 forecast, evaluation at 4 weeks |
| F1 | Do status-history features beat persistence and climatology? | Rungs 1 and 2 | PR-AUC interval excludes zero, calibration not worse | 4 weeks of snapshots |
| F2 | Same question on transitions only | Rungs 1 to 3 | Same | 4 weeks |
| F3 | Does trip flow add lift over status only? | Status-only model | Same, with publication lag enforced | 4 weeks |
| F4 | Do neighbors or weather add lift? | F3 winner | Same. Weather only with archived forecasts | 8 weeks |
| F5 | Are probabilities calibrated enough to alert on? | Reliability curve | Alert thresholds chosen on validation only | 8 weeks |

**Label sufficiency gate.** Evaluation runs only with at least 28 days of collection, at least 95% fetch coverage, and at least 200 positive transition events per target in the test window. If the gate fails, the experiment is recorded as INSUFFICIENT DATA and the UI shows the best ungated rung with a "not yet validated" badge.

**Known limits, stated up front.** Collection starts in late November, so the first evaluation covers a low-demand, holiday-affected regime. Trip-based rates are biased low wherever stations were empty. Count changes mix riders with unobserved operator moves.

## Agent design and AI capability experiments

One bounded agent investigates with read-only ontology tools, and a deterministic verifier checks every numeric claim against the evidence it cites. The LLM never forecasts, never does arithmetic that matters, and never writes SQL.

**Tools, generated from the ontology.**

| Tool | Returns | Bound |
| --- | --- | --- |
| `get_station`, `list_stations_near` | Identity, capacity, neighbors | Cluster allowlist |
| `get_current_state` | Latest StationState with staleness | 50 stations per call |
| `get_state_history` | Pre-aggregated time series | 14 days, 5-minute buckets minimum |
| `get_service_intervals` | Empty, full and closed runs | 14 days |
| `get_trip_flow` | Departures and arrivals by bucket | 60 days, hourly minimum |
| `get_forecast`, `get_model_card` | Probabilities plus the model's measured quality | Latest run or a named run |
| `get_data_quality` | Gaps, stale periods, join coverage | 14 days |
| `compare_periods` | Deterministic deltas between two windows | Same limits |
| `run_scenario` | Cached simulated policy comparison | Preset scenarios only |
| `propose_rebalancing` | Creates a proposal awaiting human decision | One per investigation |

**How the bounds are enforced, outside the prompt.** The tool layer owns a read-only DuckDB connection and runs parameterized queries only. Arguments are validated by Pydantic before execution. A run stops at 12 tool calls, 60 seconds or its token cap, whichever comes first. The single write path inserts a row with status "pending human" and can do nothing else.

**Answer contract.** The agent returns claims, each typed as observation, association, hypothesis or unknown, each citing evidence IDs. The verifier confirms that every number, station and time window in an observation matches the cited tool result. Unverified claims are shown flagged, not hidden. Station names and other feed text reach the model as quoted data fields.

**Evaluation set.** Forty hand-written cases frozen against a recorded data snapshot, so correct answers are computable: 10 lookups, 8 comparisons, 6 explanations where the evidence contradicts the obvious story, 8 data-quality traps (stale feed, closed station, missing window), 4 invalid premises, 4 prompt injections planted in station names. Each case runs three times. API responses are recorded so CI replays them for free.

| ID | Question | Arms | Measure |
| --- | --- | --- | --- |
| A1 | Do tools improve grounded accuracy? | No-tool prompt, deterministic report, tool agent | Verified-claim rate, exact numeric match |
| A2 | Can every number be traced? | Tool agent | Evidence-ID validity from the verifier |
| A3 | Does it abstain when data is bad? | Tool agent on trap cases | Correct abstention rate, fabricated-claim count |
| A4 | Is planning worth its cost? | Direct loop, plan-then-act, verifier-retry | Success per dollar and per second |
| A5 | Can injected text widen its authority? | Tool agent on injection cases | Out-of-policy tool calls (target: zero, enforced by code) |
| A6 | Which model tier is enough? | Small, mid and large Claude tiers on the same cases | Success, cost, latency, variance across runs |

Scoring is deterministic first. An LLM judge is used only for explanation quality, with ten traces reviewed by hand. Multi-agent is rejected for now: it adds cost and makes failures harder to attribute, and A4 is the experiment that could overturn that.

## Simulation and optimization

Four rebalancing policies are compared inside one stochastic simulator with shared random seeds, and every output is labeled simulated. Nothing here measures the real fleet.

**Simulator.** Discrete-event, seeded, cluster-scoped. Rental demand arrives per station as a time-varying Poisson process with rates from trip history. Destinations are drawn from the observed origin-destination mix, with one external node for trips that cross the cluster boundary. A rental at an empty station is counted as lost. A return to a full station is redirected to the nearest station with a dock and counted as a failed return. Runs start from a real observed snapshot.

**Hypothetical fleet.** Truck count, capacity, load time per bike and travel speed live in a scenario file and are shown in the UI as assumptions. Travel time is straight-line distance times a detour factor. A routing engine is rejected as extra infrastructure for a number we would still be guessing.

| Policy | Logic | Purpose |
| --- | --- | --- |
| P0 No action | Let the system run | Baseline |
| P1 Threshold | Move bikes from stations above 80% full to stations below 20% | What a simple rulebook does |
| P2 Greedy forecast-aware | Rank moves by reduction in expected unmet demand per truck-minute, using the inventory model's cost curve | Strong cheap heuristic |
| P3 CP-SAT | Pickup-and-delivery plan under capacity and time budget, same cost curves, rolling 30-minute horizon | The solver that must earn its complexity |

**Fair comparison.** Same initial state, same demand draws, same fleet and same information for every policy. At least 30 seeds per scenario, with results as paired differences and confidence intervals.

**Invariants, tested with property-based tests.** Inventory stays between zero and capacity. Bikes are conserved inside the cluster except through the external node. No move exceeds truck capacity or the time budget. Identical seeds give identical outputs.

| ID | Question | Claim rule |
| --- | --- | --- |
| O1 | Does any policy beat no action in simulation? | Paired interval excludes zero in the base scenario |
| O2 | Does CP-SAT beat greedy? | Same, and the sign holds across most sensitivity cells. Otherwise ship greedy and say so |
| O3 | Do results survive wrong assumptions? | Demand inflated 1.2x and 1.5x for censoring, travel time 0.7x and 1.3x, forecast noise added, truck capacity halved |
| O4 | How wrong is the simulator? | With no action, compare simulated empty and full minutes to observed snapshots on held-out days, and publish the gap |

O4 is the honesty check. The gap will not be zero, because real operators rebalance and we cannot see it. That gap gets published, not tuned away.

## Operator app, observability, security, deployment

The app is one workflow, alert to investigation to proposal to decision, on one small VM that costs about as much as a coffee per month.

**Screens.**

1. **Live map:** station fill, freshness and risk for the cluster, with feed age and collector health in the header.
2. **Alert inbox:** forecasts over the validated threshold, sortable by lead time and confidence.
3. **Station detail:** state history, service intervals, forecast with its model card.
4. **Investigation:** the question, the tool trace, and each claim with its evidence chip and verifier verdict.
5. **Scenario and proposal review:** policy comparison under stated assumptions, then approve or reject with a reason.
6. **Data health and lineage:** fetch coverage, gaps, join rates, schema drift, link to the dbt lineage graph.
7. **Experiments:** the latest measured result for every registered experiment, or PENDING.

Every value carries an Observed, Predicted or Simulated badge. A permanent banner states that this is independent analysis of public data with no affiliation.

**Observability.** JSON logs with a run ID on every fetch, forecast and agent call. A health table records each fetch attempt. An alert fires if no fetch succeeds for 10 minutes. Agent traces store tool arguments, result references, tokens, cost and latency.

**Security.** Secrets live in environment variables and never reach the browser or the model. The public demo serves recorded investigations by default, and live agent calls sit behind a passcode and a daily spend cap. There is no bulk export endpoint. Raw data stays off git and off the web. CI runs a dependency audit.

**Deployment in two stages.**

- **Stage A, at M1:** the VM runs only the collector, with a nightly copy of raw data to a second location.
- **Stage B, at M9:** Docker Compose adds the API, the built UI and Caddy for TLS on the same VM.

**Cost.** One small VM in the roughly 5 to 7 dollars per month class (confirm the price at purchase), an optional domain, and LLM API spend under a hard cap you set. Nothing is bought without your approval.

## Phased roadmap

Ten milestones, and only M7 waits on the calendar: it opens 28 days after the collector starts, so M2 through M6 are built while labels accumulate.

| Milestone | Outcome | Depends on | Exit gate | Claude Code sessions |
| --- | --- | --- | --- | --- |
| M0 Discovery | Evidence memo from real payloads | Nothing | Feed fields and `ttl` recorded, join key proven on a sample, three cluster candidates, go or no-go | 1 to 2 |
| M1 Collector live | The data clock starts | M0, host decision | 48 hours unattended at 95% or better fetch coverage, survives a restart, alert fires on a forced outage, bytes per day measured | 2 to 3 |
| M2 Trips and station identity | Clean, tested datasets | M0 | dbt build green, join coverage published, DST tests pass | 3 |
| M3 Ontology, API, live map | First operator-visible slice | M1, M2 | Map shows real state with freshness, unknown is never rendered as zero, ontology drift test in CI | 3 to 4 |
| M4 Risk v0 | Baselines, inventory model, evaluation harness | M2, M3 | Forecasts served with a "not yet validated" badge, harness runs end to end on fixtures, experiments registered | 3 |
| M5 Agent v1 | Grounded investigations with an eval | M3, M4, API budget | 40 cases run three times, A1 to A6 recorded, zero out-of-policy tool calls | 4 |
| M6 Simulator and optimizer | Fair policy comparison | M4 | Invariant tests pass, O1 to O4 recorded | 4 |
| M7 Forecast evaluation | Real results on real labels | M1 plus 28 days, M4 | F1 to F3 recorded as measured or INSUFFICIENT DATA, promotion decision written. Rerun at 8 weeks for F4 and F5 | 2 to 3 |
| M8 Workflow and hardening | Alert to decision, end to end | M5, M6 | Full demo path works, independent audit (kit prompt 04) findings closed | 3 |
| M9 Deploy and case study | Public, honest portfolio piece | M8, your approval | Live under a neutral name, runbook, case study separating measured, simulated and unverified | 2 |

**Rules for every milestone.** One ticket per Claude Code session, using kit prompt 03. Each session ends with exact test commands and outputs in `docs/STATUS_AND_HANDOFF.md`. You bring me that file and I review it before the next ticket. Every third milestone gets the adversarial audit.

**What you can demo honestly at each point.** After M3: live fleet state with provenance. After M5: grounded investigations over real data. After M6: simulated policy comparisons. After M7: measured forecast quality. Nothing is shown as validated before its gate.

## Milestone 0 runbook

Run these five steps now. M0 writes no application code and costs nothing.

**Step 1. Create the repo and unpack the kit at its root.**

```bash
mkdir fleet-ops-engine && cd fleet-ops-engine
git init -b main
unzip ~/Downloads/Citi_Bike_Claude_Code_Opus_Handoff_Kit.zip -d .
printf 'data/\n.env\n.venv/\n__pycache__/\n*.duckdb\n*.sqlite\n*.parquet\n*.csv\n*.zip\n' > .gitignore
git add -A && git commit -m "Add handoff kit"
```

**Step 2. Add this proposal to the repo.** Export this doc as Markdown, save it as `context/ARCHITECT_PROPOSAL.md`, add that path to the "Read first" list in `CLAUDE.md`, and commit.

**Step 3. Start Claude Code in Plan mode.** Run `claude` in the repo, pick Opus with `/model`, and press Shift+Tab until Plan mode is on.

**Step 4. Paste this prompt.**

```text
You are acting as the lead engineer and applied AI experiment designer for this repository. First read CLAUDE.md, every file in context/, and source/ORIGINAL_OBSIDIAN_SPEC.md. The source spec and context/ARCHITECT_PROPOSAL.md are proposals, not approved architecture. Then follow all instructions in prompts/00_FEASIBILITY.md. Do not implement application code, run recurring polling, deploy services, incur paid API charges, or publish anything in this phase. Be skeptical of unsupported assumptions. Record source URLs and uncertainty. Only ask for decisions that are truly blocking.

In addition, answer these with evidence. Fetch each GBFS URL at most twice in total.

1. Resolve station_information and station_status from the discovery document and fetch each once. Record: GBFS version, ttl, the type of last_updated and last_reported, every per-station field name with type and null rate, response size in bytes, and any Cache-Control or ETag headers. State explicitly whether these exist: short_name, capacity, num_ebikes_available, vehicle_types_available, num_bikes_disabled, num_docks_disabled, is_installed, is_renting, is_returning.
2. List the trip-data bucket index. Download only the most recent Jersey City file (JC prefix). Record columns, types, null rates and timestamp format. Determine whether timestamps are local time or UTC and say how you know. Test whether start_station_id matches station_information.short_name, station_id, or neither, and report the match rate.
3. Quote license clauses 2(b), 2(c), 2(e), 2(g) and 2(h) exactly. State whether polling at the feed ttl with private local retention is consistent with them. Label this reasoned, not legal advice.
4. Check whether any free weather source archives forecasts as they were issued, and its terms. If none is usable, say so.
5. From station_information coordinates, propose three candidate clusters of 30 to 50 stations with different demand character. For each give station count, bounding box and total capacity. Do not hand-type station names.
6. Estimate bytes per day for whole-system collection at the observed ttl.
7. List every claim in context/ARCHITECT_PROPOSAL.md that your evidence contradicts or cannot support.
8. Confirm or correct the two citations in the forecasting section of the proposal.
```

**Step 5. Approve documentation writes only.** When Opus presents its findings, reply:

```text
Approved: write the four discovery documents under docs/discovery/ and a 10-station fixture of each GBFS feed under tests/fixtures/gbfs/, each fixture marked with its source URL and retrieval time. Write nothing else. Then show me git status.
```

**Verify before you call M0 done.**

- [ ] `ls docs/discovery/` shows FEASIBILITY.md, SOURCES\_AND\_POLICY.md, DATA\_DICTIONARY\_DRAFT.md, ASSUMPTIONS\_AND\_RISKS.md
- [ ] The field inventory comes from a real payload, with a retrieval timestamp
- [ ] There is a number for `ttl`, a number for the join match rate, and a number for bytes per day
- [ ] `git ls-files | grep -E '\.(csv|zip|parquet)$'` prints nothing
- [ ] Every claim is labeled verified, source-stated, reasoned or unknown

**Hand back to me:** paste FEASIBILITY.md's go or no-go section, the field inventory, and the answer to question 7. The M1 collector prompt depends on the real `ttl` and field names, so I write it after I see them.

## Decisions needed and open risks

One decision blocks M1 and the rest can wait for their milestone.

| Decision | My recommendation | Needed by |
| --- | --- | --- |
| Where the collector runs | A small rented VM. A home machine that is always on also works. A laptop does not | M1 |
| Repo visibility while building | Private until the M8 audit passes | M0 |
| Analysis cluster | Pick from the three candidates M0 produces | M3 |
| LLM API budget | A hard cap, starting at 30 dollars, revised once M5 measures tokens per case | M5 |
| Public name | A neutral name with a factual line such as "built on public NYC bike-share data". Keep the current title internal | M9 |
| Note to bike-data@lyft.com | Send a short description of the project. Optional | Any time |

**Risks I am carrying.**

- **The license is revocable and the feed can change.** Mitigation: raw payloads are kept, parsing is tolerant, fixtures let everything run offline.
- **Winter and holiday data.** The first evaluation may have few shortage events and will not represent summer. The label gate and the write-up say so.
- **Censored demand.** Trip-based rates understate demand at empty stations. Sensitivity runs inflate demand, and nothing claims to measure unmet riders.
- **Simulator realism.** Experiment O4 measures the gap and publishes it.
- **Scope.** Ten milestones is a lot for one person. If time runs short, M6 shrinks to P0 through P2 and CP-SAT is cut first.

## Sources

- [Citi Bike Data License Agreement](https://ride.citibikenyc.com/data-sharing-policy), read 2026-11-15
- [Citi Bike System Data](https://citibikenyc.com/system-data), column list from search result, page not opened
- [GBFS v2.3 specification](https://github.com/MobilityData/gbfs/blob/v2.3/gbfs.md), from search result, page not opened
- [data.gov: Citi Bike System Data](https://catalog.data.gov/dataset/citi-bike-system-data), from search result
- [DisPatch70 dataset card](https://huggingface.co/datasets/hulnegy/DisPatch70), third-party, from search result
- The handoff kit: all 16 files read in full
