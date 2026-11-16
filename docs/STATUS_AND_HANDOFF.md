# Project state and next-session handoff

> **SCOPE CHANGE (2026-11-16): offline prototype.**
> - No continuous polling and no collector. GBFS is used only as one-off, manually triggered snapshots.
> - `context/ARCHITECT_PROPOSAL.md` is **superseded where it conflicts**: always-on collector and M1, snapshot-accumulation label gates, VM deployment, and the bronze/silver polling layout.
> - Consequence: forecast **validation against observed empty/full labels is not possible** in this scope, because there is no status history. Any forecast built later must be labeled unvalidated, or evaluated only on proxy tasks derived from trips.

| Item | Value |
|---|---|
| Last updated (UTC) | 2026-11-16 ~03:45 |
| Latest git commit | 530d006. All work below is **not committed** (per instruction) |
| Branch | `m0-discovery` |
| Architecture decision version | None approved. Offline scope per this file and the `CLAUDE.md` header |
| Source/policy verification last checked | 2026-11-16 (`docs/discovery/SOURCES_AND_POLICY.md`) |
| External resources currently running | **None** |

## Current outcome
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
| S2 | Day-ahead hourly forecast (grid, baselines, LightGBM, metrics, charts, leakage tests) | **verified done** | Commands and results below |
| ~~M1~~ | Collector live | **cancelled** (scope change) | — |

## Exact verification evidence
| Command | Time (UTC) | Observed outcome |
|---|---|---|
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
| Public name | requires-user-decision | Neutral name before any public artifact |
| Complete arrivals (cross-river) | requires-user-decision | Optionally download NYC months (about 1 GB each) and filter to trips ending in JC/Hoboken |

## Next ready ticket
- **Ticket:** step 3, decided by the user. Candidates:
  - an untouched holdout: Nov 2026 trips, once published, to evaluate the frozen model and the "drop month" variant;
  - a station-identity crosswalk for retired IDs;
  - an ablation of the lag features.
- **Commands for a fresh session:**
  - `.venv/Scripts/python.exe -m pytest -q`
  - `.venv/Scripts/python.exe -m fleetdata.build`
  - `.venv/Scripts/python.exe -m fleetdata.forecast` (re-running re-predicts October; treat any rerun as non-blind)

## How a fresh session should resume
1. Read `CLAUDE.md` (scope header), this file and `docs/discovery/DATA_DICTIONARY_DRAFT.md`.
2. Run `git status`, then the two commands above.
3. Follow `prompts/05_RESUME_SESSION.md`.
