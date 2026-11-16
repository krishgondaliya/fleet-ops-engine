# fleet-ops-engine (offline prototype)

Independent analysis of public bike-share data. This is **not** an official Citi Bike service and has no affiliation with Lyft, Bikeshare or Citigroup. The data is used under the [Citi Bike Data License Agreement](https://citibikenyc.com/data-sharing-policy). Raw data stays in `data/`, which is git-ignored, and is never redistributed.

Scope: an **offline prototype**. There is no continuous polling and no collector. See the header of `CLAUDE.md` and `docs/STATUS_AND_HANDOFF.md`.

## Setup (Python 3.11)

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows (Git Bash). On macOS/Linux use .venv/bin/pip
```

## Run the data layer

```bash
# 1. Download (one-shot; already-downloaded files are skipped)
#    - the 12 most recent Jersey City (JC-*) monthly trip zips   -> data/raw/trips/  (+ MANIFEST.json)
#    - one snapshot each of GBFS station_information/status      -> data/raw/gbfs/   (+ fetch_meta.json with fetch times)
.venv/Scripts/python -m fleetdata.download                # options: --months 12  --refresh-gbfs

# 2. Build data/fleet.duckdb and print a summary (offline)
.venv/Scripts/python -m fleetdata.build

# 3. Tests (offline: GBFS fixtures + a SYNTHETIC trips CSV; network is blocked)
.venv/Scripts/python -m pytest -v
```

The download is about 35 MB of trip zips plus about 1.9 MB of GBFS JSON. The build takes about 25 s for about 980k trips.

## Tables in `data/fleet.duckdb`

| Table | Grain | Notes |
|---|---|---|
| `stations` | one row per GBFS station, key `short_name` | Coordinates, capacity, region, fetch time |
| `snapshot` | one row per station from the single `station_status` fetch | 0/1 flags coerced to BOOLEAN. `is_stale` and `stale_reason` cover a placeholder or missing `last_reported`, or a report >900 s older than the feed. `over_capacity` is also flagged |
| `trips` | one row per completed trip (deduplicated on `ride_id`) | `*_at_local` (America/New_York) and `*_at_utc`. `*_tz_flag` marks the ambiguous fall-back or nonexistent spring-forward hour. `start_matched`/`end_matched` show whether the join to `stations.short_name` succeeded; unmatched trips are kept |
| `hourly_flow` | station × UTC hour (sparse) | `departures` and `arrivals`. Hours with no activity are absent |
| `build_log` | — | Build-time counts, e.g. duplicate rides removed |

Caveats:
- Trips are **completed trips, not demand**.
- JC files contain only trips that **start** in Jersey City/Hoboken, so arrivals from NYC-origin trips are missing.
- Stations retired since a trip occurred do not match today's GBFS feed. They are reported by the build summary.

## Step 2: day-ahead hourly forecast

```bash
.venv/Scripts/python -m fleetdata.forecast     # about 2.5 min. Prints the metrics and writes tables, models and charts
```

- **Scope:** Jersey City and Hoboken stations (regions 70 and 311) that are installed in the current GBFS snapshot.
- **Targets:** hourly departures and arrivals per station.
- **Issue time:** forecasts for a local day are issued at local midnight. Features are hour, day of week, month, US federal holiday, station, the 24-hour and 168-hour lags, and the four-week same-hour average. No lag is shorter than 24 h.
- **Split:** train through Aug 2026, validate on Sep 2026, test on Oct 2026. The test month is predicted once.
- **Comparison:** LightGBM (Poisson objective) against "same hour last week" and the "4-week same-hour average".

Outputs:
- **Tables:** `demand_grid`, `forecast_predictions` (test month only), `forecast_metrics`, `forecast_metrics_by_hour`, `forecast_metrics_by_station`, `forecast_bootstrap` and `forecast_runs`.
- **Models:** `data/models/lgbm_{departures,arrivals}.txt` and `forecast_run.json`.
- **Charts:** `reports/error_by_hour.png` and `reports/busiest_station_week.png`.

## Limits

- **These are completed rides, not demand.** A station that was empty could not serve departures, and a full station could not accept arrivals. Demand at those times is undercounted. The models learn and forecast *served* trips, and they inherit this bias.
- **Zero-filled hours mix "nobody rode" with "the station could not serve"**, for example a closure or outage. The data has no record of station status over time, so the two cannot be told apart. For example, station JC115 shows exactly zero trips from about 15:00 Saturday 10 Oct 2026 to midday Sunday.
- **Arrivals exclude trips that started in NYC.** Those trips are in the NYC trip files, which are not downloaded.
- **"Known at midnight" is a simulation.** In reality trip files are published about 5 days after the end of each month. A ride that starts before midnight but ends after it would not yet be recorded.
- **Station scope and capacity come from today's snapshot.** Stations retired during the year are excluded, which is survivorship. Capacity is treated as constant.
- **Results cover one test month (Oct 2026)** and one validation month. They are not seasonal estimates.

Discovery notes and data dictionary: `docs/discovery/`.

## Step 3: one-day simulator (all outputs SIMULATED)

```bash
.venv/Scripts/python -m fleetdata.sim          # about 1 s. Reads stations, snapshot, forecast_predictions
```

- **Start:** bikes from the GBFS snapshot for installed JC/Hoboken stations, clipped to `[0, capacity]`.
- **Scenario:** one day, hour by hour. Departures and arrivals per station-hour are Poisson draws whose rates are the mean step-2 forecast for a non-holiday October 2026 weekday. A departure at an empty station is a lost rental; an arrival at a full station is a failed return.
- **Policies:** `no_action`, and `greedy`: one truck that each operating hour moves bikes from the fullest reachable station to the emptiest within a travel budget. Every truck assumption is in `config/sim.json`.
- **Comparison:** 30 seeds; each seed's demand is drawn once and replayed for both policies. Results are paired differences with a 95% bootstrap interval. The interval covers **only seed-to-seed randomness**, not forecast error, truck-parameter uncertainty or the start-state assumption.
- **Tables:** `sim_runs`, `sim_summary`, `sim_hourly`, `sim_station`, `sim_moves`, `sim_meta` (every row carries `label = 'SIMULATED'`).
- **Limits:** riders do not carry bikes between stations in the model (arrivals are independent draws), rates are completed trips rather than demand, and the truck parameters are assumptions. Results compare policies under identical simulated scenarios; they are not operational evidence.

## Step 4: investigation agent

Settings go in `.env` (git-ignored) and are loaded at runtime:

```
AGENT_BACKEND=claude_code         # claude_code (default) or api
AGENT_MODEL=claude-sonnet-5-5     # optional; this is the default
ANTHROPIC_API_KEY=...             # only needed for AGENT_BACKEND=api
```

```bash
.venv/Scripts/python -m fleetdata.agent "What was the LightGBM test MAE for departures?"   # [--backend api|claude_code]
.venv/Scripts/python -m fleetdata.agent_eval --mode replay   # offline: scripted tool calls, checks tools + grader
.venv/Scripts/python -m fleetdata.agent_eval --mode live     # the selected backend answers the 10 questions
```

**Two backends, same tools, same checks.**
- `claude_code` (default): runs the Claude Code CLI non-interactively (`claude -p`) once per question, under your logged-in Claude subscription. No API key is needed. The five tools are served by a local MCP server over stdio (`fleetdata/agent_mcp.py`), which calls the same `run_tool` code as the API path. Every built-in Claude Code tool (file, shell, web) is disabled, and only the five `mcp__fleet__*` tools are allowed. The turn limit is 9 (8 tool calls plus the answer), and the MCP server also refuses a 9th call. The child process gets the environment **without** `ANTHROPIC_API_KEY`. Each run checks that Claude Code reported `apiKeySource: none` and that no other tools were available, and refuses the answer otherwise. The exact flags are listed in `fleetdata/agent_claude_code.py`.
- `api`: the original tool-use loop on the Anthropic API with `ANTHROPIC_API_KEY`. It is billed per token.

**Limits of the claude_code backend.**
- **Local only:** it needs the `claude` CLI installed and logged in on the same machine.
- **Plan allowance:** each question uses your subscription's allowance, about 7,000 tokens in the eval.
- **Token cap:** the 80,000-token cap is not enforced mid-run; tokens are only reported afterwards. The tool-call and turn limits still apply.
- **Public use:** a public or shared deployment must use `AGENT_BACKEND=api`. A subscription login is for personal use and must not serve other people.

- **One tool-use loop** over five read-only tools: `station_lookup`, `hourly_flow`, `forecast_vs_actual`, `model_metrics` and `simulation_results`. Arguments are validated, SQL is fixed and parameterized, and results are capped at 200 rows. The model cannot run its own SQL.
- **Limits per question:** 8 tool calls and an 80,000-token cap.
- **Numbers:** each number in an answer is checked against the values the tools returned. Arguments, notes and failed calls do not count, and a signed number must match the sign. Unmatched numbers are flagged as unverified. The check is a guard, not a proof: small numbers such as hours 0–23 often match some returned value by coincidence. The list of tool calls is appended to every answer.
- **Eval:** 10 questions whose answers are computed directly with SQL. Results are written to `reports/agent_eval.json`.

## Step 5: the app (Dock Balance Lab)

```bash
# prerequisites: steps 1-3 have built data/fleet.duckdb (build, forecast, sim)
.venv/Scripts/streamlit run app.py            # http://127.0.0.1:8501 (bound to loopback by .streamlit/config.toml)
# options: FLEET_DB=path/to.duckdb (default data/fleet.duckdb), FLEET_ENV_FILE=path/to/.env (default .env)
```

Four views, each value badged **Observed**, **Predicted** or **Simulated**:
1. **Station map:** installed JC/Hoboken stations with bikes and docks from the single GBFS snapshot.
2. **Forecast vs actual:** pick a station, a target and October 2026 dates. Shows hourly actual against the LightGBM forecast, with an optional baseline, and MAE/WAPE.
3. **Policy simulation:** no action vs the greedy truck, as paired differences with a 95% CI, an hourly chart and the assumptions. All of it is simulated.
4. **Ask the agent:** answers from the step-4 agent, with every tool call and its result, and the backend that answered. With the default `AGENT_BACKEND=claude_code` it uses your local Claude Code login and plan allowance. With `api` it needs `ANTHROPIC_API_KEY` and calls the paid API.

The app is local only and reads the database read-only. It shows a banner stating that this is independent analysis, not affiliated with the operator.
