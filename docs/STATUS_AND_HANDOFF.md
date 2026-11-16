# Project state and next-session handoff

> **SCOPE CHANGE (2026-11-16): offline prototype.**
> - No continuous polling and no collector. GBFS is used only as one-off, manually triggered snapshots.
> - `context/ARCHITECT_PROPOSAL.md` is **superseded where it conflicts**: always-on collector and M1, snapshot-accumulation label gates, VM deployment, and the bronze/silver polling layout.
> - Consequence: forecast **validation against observed empty/full labels is not possible** in this scope, because there is no status history. Any forecast built later must be labeled unvalidated, or evaluated only on proxy tasks derived from trips.

| Item | Value |
|---|---|
| Last updated (UTC) | see the newest step section below |
| Latest git commit | see `git log` (steps 1–2 committed in df65560; each later step is committed locally, never pushed) |
| Branch | `main` (local only) |
| Architecture decision version | None approved. Offline scope per this file and the `CLAUDE.md` header |
| Source/policy verification last checked | 2026-11-16 (`docs/discovery/SOURCES_AND_POLICY.md`) |
| External resources currently running | **None** |

## Current outcome
**Independent audit after steps 3–5 (auditor subagent, 2026-11-16):** no high-severity findings. It reproduced 134 passing tests and the replay 10/10, and matched every claimed simulator, forecast and app number against the database. No data or secrets are in git history.

Fixed after the audit:
- **M2, app exposure.** `.streamlit/config.toml` binds the app to 127.0.0.1. Before this fix, the README command listened on all interfaces, so anyone on the local network could spend API credit.
- **M1, number check** (`fleetdata/agent.py`):
  - Numbers in model arguments, notes and failed calls are no longer evidence.
  - A signed number must match its sign.
  - Sums and differences count only within one result row or totals block.
  - Dates are no longer split into numbers.
  - New tests cover the audit's laundering and sign cases.
  - Remaining limit: small integers such as hours 0–23 can still match a returned value by coincidence.
- **M3, grader, partly fixed.** Signs are now enforced, and an answer listing more than 3×expected+10 numbers fails. **Still open:** Q8 and Q9 (simulated) and Q5 and Q7 (forecast) take their expected values from the same pipeline tables the tools read, so they test retrieval, not an independent recomputation. Only Q1–Q4 and Q6 are checked against base tables.
- **L2, CI scope.** The simulator CI covers seed-to-seed randomness only. This is now stated in the README.
- **L3, README.** It now says `forecast_predictions` holds the test month only.

Left open (low severity):
- **L1, DST fall-back leakage.** On 2025-11-02 (25 local hours), one training row's `lag24` reads the forecast day's first hour. This affects training only; the October test month has no DST change. A fix needs a forecast code change, and step 2 is frozen, so it is recorded instead.
- **L4, simulator gaps.**
  - A station-hour missing from the forecast table would silently get rate 0. Today the grid is complete (105×744).
  - `truck.count > 1` would share one truck position.
  - `over_capacity_clipped` counts stations, not bikes clipped.
- **L5, agent limits.** The token cap is checked before each request, so one request can overshoot it. Prompt injection via station names is mitigated (labelled untrusted, read-only tools) but untested live.
- **L6, app.** The query cache has no TTL, so restart the app after rerunning the simulator.

Verification after the fixes: `.venv/Scripts/python.exe -m pytest -q` → **136 passed in 15.12s**. `python -m fleetdata.agent_eval --mode replay` → 10/10.

**Step 5, the app (`app.py`, "Dock Balance Lab"), runs locally.**
- Command: `.venv/Scripts/streamlit run app.py`. It reads the database read-only and is bound to 127.0.0.1 by `.streamlit/config.toml` (added after the audit). Nothing is deployed.
- **Views:**
  - Station map: snapshot bikes and docks for 105 installed stations.
  - Forecast vs actual: station, target and October 2026 date range, with an optional baseline and MAE/WAPE.
  - Policy simulation: paired differences with CI, an hourly chart and the assumptions.
  - Ask the agent: the answer, any unverified numbers, and each tool call with its label and JSON result.
- **Labels:** every metric label carries [Observed], [Predicted] or [Simulated], plus a section badge. A banner says the app is independent analysis and not affiliated with the operator. The app name contains no operator brand (tested).
- **Chart colors:** blue `#2a78d6` and orange `#eb6834` passed the palette validator (CVD ΔE 24.7, normal ΔE 33.6, contrast ≥ 3:1 on a light surface). Observed actuals are drawn in dark ink. Dark mode was not separately validated.
- **Not done:** charts were rendered headless (AppTest) and the server health check passed, but nobody looked at the page in a browser.
- The agent view cannot answer live until the API credit issue (step 4) is resolved. Without a key it shows an error instead of calling the API (tested).

**Step 4, the investigation agent, is built and tested offline. It has NOT been measured live.**
- **Live API calls fail:** HTTP 400 `invalid_request_error`, "Your credit balance is too low to access the Anthropic API" (request `req_011Ch5wjYDkTAkE6RdRPTiqL`, 2026-11-15). The key loads from `.env` (contents not read or printed). **The live agent score is unmeasured: 0 of 10 questions scored.**
- Code: `fleetdata/agent_tools.py` (5 read-only tools), `fleetdata/agent.py` (one manual tool-use loop), `fleetdata/agent_eval.py` (10 questions + grader). Tests: `tests/test_agent.py`.
- **Tools:** `station_lookup`, `hourly_flow`, `forecast_vs_actual`, `model_metrics`, `simulation_results`.
  - Every argument is validated: unknown keys are rejected, plus enums, the short_name pattern, ISO dates, at most 31 days, forecasts limited to Oct 2026, and 1–60 character strings.
  - SQL is fixed and parameterized, the connection is read-only, and results are capped at 200 rows with a `truncated` flag.
  - Each result carries an observed, predicted or simulated label. The model never writes SQL.
- **Loop limits:** at most 8 tool calls (after that, `tool_choice: none` forces an answer), an 80,000-token cap per question (input + output), and 4,000 `max_tokens` per response.
  - The model is `AGENT_MODEL` (default `claude-sonnet-5-5`), at effort `medium`, with server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`) for models that support it.
- **Grounding:** the system prompt requires every number to come from a tool result, with [#n] citations. Code then checks every number in the answer against the tool results; unmatched numbers are shown as "Unverified numbers".
  - The tool-call list is appended by code, not by the model.
  - Unanswerable questions must start with "Not supported by the data:".
- **Eval (`python -m fleetdata.agent_eval`):** 10 questions. Expected numbers are computed by direct SQL on `trips`, `snapshot`, `forecast_predictions`, `sim_runs` and `sim_summary`, independently of the tool code. One question (Q10) is unanswerable by design.
  - **SCRIPTED replay: 10/10.** A fixed tool sequence per question, with the answer written from the tool results. This shows that the tools return the right numbers and that the loop, the number check and the grader work. **It is not a measure of the model.**
  - **LIVE: not scored** (credit error above). Rerun `python -m fleetdata.agent_eval --mode live` after adding credit. Output goes to `reports/agent_eval.json`.

| Q | Question (short) | Expected (direct SQL) |
|---|---|---|
| Q1 | bikes, docks at "Grove St PATH" (snapshot) | 14, 26 (observed) |
| Q2 | departures JC115 on 2026-10-05 | 178 (observed) |
| Q3 | arrivals HB107 2026-09-01..07 | 685 (observed) |
| Q4 | peak departure hour JC115 on 2026-10-07 | hour 17, 55 trips (observed) |
| Q5 | test MAE departures, LightGBM vs 4-week avg | 0.838, 0.867 (predicted vs observed) |
| Q6 | JC115 2026-10-06 actual vs LightGBM total | 182 vs 159.9 |
| Q7 | LightGBM WAPE arrivals HB107 (test) | 0.425 |
| Q8 | mean lost rentals/day no_action vs greedy | 236.0, 209.2 (SIMULATED) |
| Q9 | paired diff failed returns, 95% CI | −40.0 [−43.8, −36.3] (SIMULATED) |
| Q10 | real lost rentals JC115 on 2026-10-05 | must say unsupported (no status history) |

**Step 3, a one-day SIMULATOR, runs on real inputs.** Every number in this section is **SIMULATED**.
- Command: `.venv/Scripts/python.exe -m fleetdata.sim` (about 1 s). Assumptions: `config/sim.json`. Code: `fleetdata/sim.py`. Tests: `tests/test_sim.py`.
- Start state (observed): 105 installed JC/Hoboken stations, 2,004 docks, 902 bikes from the snapshot fetched 2026-11-16 03:20:48 UTC. Clipping to capacity changed no counts (the 3 `over_capacity` stations are over because of disabled bikes/docks, not available bikes). 3 stale station reports are used as-is.
- Demand (predicted → simulated): Poisson rates = mean step-2 LightGBM prediction per station and local hour over the 21 non-holiday Oct 2026 weekdays. Expected 2,655 departures and 2,604 arrivals per day. Predictions are only read; the model is not refit or re-scored.
- Policies: `no_action` and `greedy` (1 truck, 20 bikes, 1 move per hour from 06 to 22 local, 6 road-km per hour, circuity 1.3, target fill 0.5, minimum fill gap 0.25).
- 30 seeds; demand for each seed is drawn once and replayed for both policies (common random numbers).

| SIMULATED, mean per day | no_action | greedy | paired diff (greedy − no_action) | 95% bootstrap CI | seeds where greedy better |
|---|---|---|---|---|---|
| lost rentals | 236.0 | 209.2 | −26.8 | [−31.7, −21.7] | 29/30 |
| failed returns | 178.5 | 138.6 | −40.0 | [−43.8, −36.3] | 30/30 |
| total unserved | 414.5 | 347.7 | −66.8 | [−74.5, −59.3] | 30/30 |

Greedy truck activity (SIMULATED mean): 16 moves, 122 bikes, 66 km per day.

Limits of the simulator (stated assumptions, not findings):
- Arrivals are drawn independently of departures, so riders do not carry bikes between stations. A lost rental does not reduce later arrivals, and a failed return does not reroute the rider.
- Rates are **completed trips**, not demand, and arrivals miss NYC-origin trips (step 1). Simulated lost rentals are therefore a lower bound on the scenario's own shortfall, not a forecast of real stockouts.
- The start state is a late-evening November snapshot used as the start of an October weekday.
- Stations not renting or not returning in the snapshot (3) are simulated as open.
- The truck's travel budget, speed and circuity are assumptions, not operator data. The results compare two policies under identical simulated scenarios; they are not evidence about real operations.

**Step 2, a day-ahead hourly forecast, is measured on the October 2026 test month.**
- LightGBM (Poisson) beats both baselines for departures and arrivals. Paired day-block bootstrap 95% intervals exclude zero.
- Against the 4-week same-hour average the margin is small: about 3% relative MAE (WAPE 0.620 vs 0.642 for departures, 0.619 vs 0.636 for arrivals).
- These are forecasts of **completed trips, not demand** (predicted values; see README "Limits").

**Step 1, the data layer, works on real data.**
- `python -m fleetdata.download` fetched 12 JC monthly trip zips (2025-11 to 2026-10) and one GBFS snapshot.
- `python -m fleetdata.build` builds `data/fleet.duckdb` with four tables: `stations`, `snapshot`, `trips` and `hourly_flow`, plus a `build_log`.
- 14 offline tests pass.

## Ticket status
| ID | Scope | State | Evidence |
|---|---|---|---|
| M0 | Feasibility and evidence memo | verified done (docs) | `docs/discovery/*.md` |
| S1 | Offline data layer (download, build, summary, tests) | **verified done** | Commands and results below |
| S2 | Day-ahead hourly forecast (grid, baselines, LightGBM, metrics, charts, leakage tests) | **verified done**; final, not to be retuned | Commands and results below |
| S3 | One-day simulator, two policies, 30 paired seeds | **verified done** | Commands and results below |
| S5 | Streamlit app, 4 views, badges, banner | **done; headless-tested** (not visually inspected in a browser) | Commands and results below |
| S4 | Investigation agent: tools, loop, 10-question eval | **built; offline-tested; live score not measured** (API credit) | Commands and results below |
| ~~M1~~ | Collector live | **cancelled** (scope change) | — |

## Exact verification evidence
| Command | Time (UTC) | Observed outcome |
|---|---|---|
| `.venv/Scripts/python.exe -m pytest -q` (step 5) | 2026-11-15 | **134 passed in 15.56s** (128 earlier + 5 app (AppTest) + 1 network-guard). The guard now allows loopback only, which asyncio's self-pipe on Windows needs |
| AppTest of `app.py` against the real `data/fleet.duckdb` | 2026-11-15 | No exceptions. Metrics: 105 stations, 902 bikes, 921 docks, 3 empty [Observed]; greedy lost rentals 209.2, failed returns 138.6 [Simulated] |
| `streamlit run app.py --server.address 127.0.0.1 --server.port 8599` + `curl /_stcore/health` | 2026-11-15 | `ok`; server then stopped |
| `.venv/Scripts/python.exe -m pytest -q` (step 4) | 2026-11-15 | **128 passed in 12.64s** (91 earlier + 37 agent; offline, scripted client) |
| `.venv/Scripts/python.exe -m fleetdata.agent_eval --mode both` | 2026-11-15 | Replay **10/10**; live **0 scored**: the first call returned HTTP 400 "credit balance is too low", and the remaining 9 were not sent |
| `.venv/Scripts/python.exe -m pytest -q` (step 3) | 2026-11-15 | **91 passed in 7.34s** (23 earlier + 68 simulator; offline) |
| Simulator mutation check: (a) treat an empty station as able to rent, (b) truck drops off one extra bike | 2026-11-15 | (a) 41 failed, (b) 20 failed (bounds/counting and conservation tests detect them); restored code: 68 passed |
| `.venv/Scripts/python.exe -m fleetdata.sim` | 2026-11-15 | Results table above (SIMULATED). Writes `sim_runs`, `sim_summary`, `sim_hourly`, `sim_station`, `sim_moves`, `sim_meta` |
| `.venv/Scripts/python.exe -m pytest -v` | ~03:44 | **23 passed in 7.41s** (14 data layer + 9 forecast; offline) |
| Leakage-test mutation check: inject `lag(23)` into a copy of `make_features` | ~03:40 | Both leakage tests **FAIL** on the mutant (they detect the leak) and pass on the real code |
| `.venv/Scripts/python.exe -m fleetdata.forecast` | ~03:41 | 105 stations, 882,003 grid rows (train 728,283 / valid 75,600 / test 78,120). Test metrics below. About 2 min 24 s |
| `.venv/Scripts/python.exe -m pytest -v` (step 1) | ~03:28 | 14 passed in 4.95s |
| `.venv/Scripts/python.exe -m fleetdata.download` | 03:20 | 12 trip zips downloaded (958,731–4,599,971 B each). station_information (801,371 B) and station_status (1,081,781 B) fetched at 03:20:48 |
| `.venv/Scripts/python.exe -m fleetdata.build` | ~03:29 | stations 2,519 · snapshot 2,519 · trips 979,315 · hourly_flow 487,628. Start-ID match 96.96%. 18 duplicate ride_ids removed. 178 ambiguous fall-back timestamps flagged. About 23 s |
| M0 rows (evidence pass, cluster refinement, fixture build) | 02:47–03:08 | See `docs/discovery/SOURCES_AND_POLICY.md` §2 |

## Step 2 results (test = Oct 2026; 78,120 station-hours; none excluded)
| Target | Method | MAE | WAPE |
|---|---|---|---|
| departures | same hour last week | 1.0135 | 0.7498 |
| departures | 4-week same-hour avg | 0.8670 | 0.6415 |
| departures | **LightGBM** | **0.8380** | **0.6200** |
| arrivals | same hour last week | 0.9996 | 0.7461 |
| arrivals | 4-week same-hour avg | 0.8525 | 0.6363 |
| arrivals | **LightGBM** | **0.8294** | **0.6191** |

MAE difference for LightGBM minus baseline, with 95% CI:

| Target | vs last week | vs 4-week average |
|---|---|---|
| departures | −0.175 [−0.195, −0.156] | −0.029 [−0.041, −0.017] |
| arrivals | −0.170 [−0.190, −0.149] | −0.023 [−0.036, −0.011] |

Observations:
- **Where the model does not help.** At the evening peak (local 17–18 h) LightGBM is slightly *worse* than the 4-week average. At 04–07 h it is roughly equal.
- **Volume and error.** The busiest stations (JC115, HB107) have the lowest WAPE, about 0.36–0.43. Low-volume stations have WAPE above 1.1, which is worse than predicting zero would be on a WAPE basis.
- **The `month` feature hurt on validation.** Removing it lowered validation MAE (0.889 → 0.865 departures, 0.879 → 0.850 arrivals). Months 9 and 10 never occur in training. The feature was **kept** because it was in the specified feature set, and the test month has already been used. Evaluating "drop month" must use a fresh month (Nov 2026, once published), **not** October again.
- **Tuning.** Selected config: num_leaves 15, min_data_in_leaf 50. Departures stopped at iteration 993 of a 1,000 cap, so early stopping did not trigger and more rounds may help (validation only).
- **Zero-filled outages (V).** JC115 has exactly zero trips from about 15:00 on 10 Oct to midday on 11 Oct, which looks like an outage. The zero-filled grid treats it as zero demand.
- **Interpretation of the leakage rule.** The 24 h lag reads the hour bucket starting at t−24h. That bucket ends at t−23h, at or before local midnight of t's day. "No data from t−24h or later" is enforced as "no hour bucket starting after t−24h". The day-ahead rule is tested separately.

## Data state and findings from step 1
- **Join (V).** 96.96% of trips match a current GBFS `short_name` (108 of 114 distinct start IDs).
  - Matching is 100% for Aug–Oct 2026 and 94–97% for earlier months.
  - Unmatched IDs are stations absent from today's feed, i.e. retired or renumbered. The largest is `HB106` "River St & Newark St", with 22,827 departures through 2026-07-31.
  - Unmatched trips are kept with `start_matched = false`.
- **Duplicates (V).** 18 rides appear in both the JC-202604 and JC-202605 files with identical content. They are deduplicated and logged in `build_log`.
- **File boundaries (V).** JC-202511 contains rides that started on 2025-10-31. Monthly files are not cleanly partitioned by start time.
- **ride_id format (V).** It changed from 16-character hex in older months to a 19-digit number (Oct 2026). It is stored as a string.
- **DST (V).** 178 timestamps fall in the ambiguous 2025-11-02 01:00–01:59 hour. They are resolved to the first occurrence (EDT) and flagged. There are no spring-forward hits.
- **Arrival undercount (R).** JC files contain trips that **start** in JC/Hoboken. Arrivals at JC stations from trips that started in NYC are in the NYC files, which were not downloaded. `hourly_flow.arrivals` therefore undercounts inbound cross-river trips. NYC stations appear only as destinations.
- **Snapshot (V).** 83 stale stations, 48 of them with the placeholder `last_reported`. 51 not installed, 85 not renting, 50 over capacity. In the JC/Hoboken regions, the only station with no trips is JC141, which is not installed.
- **Epistemic status:** `snapshot` is observed at one instant. `trips` and `hourly_flow` are observed completed trips, **not demand**.

## Decisions and deviations
- Ambiguous fall-back times resolve to the first occurrence (fold=0) and are flagged. Nonexistent spring-forward times use the pre-transition offset and are flagged.
- Stale means `last_reported` is missing or a placeholder (<1e6), or the station report is more than 900 s older than the feed's `last_updated`.
- Python `zoneinfo` + `tzdata` handle the conversion, not DuckDB ICU, so the rules are explicit and testable.
- `.gitignore` gained an exception, `!tests/fixtures/**/*.csv`, so the synthetic test CSV is not ignored.
- Root `README.md` was created with run instructions. The kit's `README_START_HERE.md` was left unchanged.

## Blockers / approvals
| Blocker | Class | Exact unblock action |
|---|---|---|
| Live agent evaluation | requires-cost-approval | Add Anthropic API credit; then `python -m fleetdata.agent_eval --mode live` (10 questions, a few cents to tens of cents at Sonnet prices; not measured) |
| Public name | requires-user-decision | Neutral name before any public artifact |
| Complete arrivals (cross-river) | requires-user-decision | Optionally download NYC months (about 1 GB each) and filter to trips ending in JC/Hoboken |

## Next ready ticket
- **Ticket:** none queued. Steps 3–5 of `docs/PLAN.md` are done. Open items: add API credit, then run `python -m fleetdata.agent_eval --mode live`; inspect the app visually in a browser; choose the public name.
- **Commands for a fresh session:**
  - `.venv/Scripts/python.exe -m pytest -q`
  - `.venv/Scripts/python.exe -m fleetdata.build`
  - `.venv/Scripts/python.exe -m fleetdata.forecast` (do **not** rerun: step 2 is final; rerunning re-predicts October)
  - `.venv/Scripts/python.exe -m fleetdata.sim`

## How a fresh session should resume
1. Read `CLAUDE.md` (scope header), this file and `docs/discovery/DATA_DICTIONARY_DRAFT.md`.
2. Run `git status`, then the two commands above.
3. Follow `prompts/05_RESUME_SESSION.md`.
