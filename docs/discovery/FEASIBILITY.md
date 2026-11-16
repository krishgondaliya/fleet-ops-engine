# M0 Feasibility and Evidence Report

**Status:** discovery output. It is not an architecture and not an implementation plan.
**Evidence gathered:** 2026-11-16 02:47–03:07 UTC.

Labels:
- **V** verified, meaning observed in a real payload or page this session.
- **SS** source-stated.
- **R** reasoned.
- **U** unknown.

Companion docs:
- [SOURCES_AND_POLICY.md](SOURCES_AND_POLICY.md)
- [DATA_DICTIONARY_DRAFT.md](DATA_DICTIONARY_DRAFT.md)
- [ASSUMPTIONS_AND_RISKS.md](ASSUMPTIONS_AND_RISKS.md)

Evidence scripts are in [evidence/](evidence/).

> Independent analysis of public data. This is not an official Citi Bike service and has no affiliation with Lyft, Bikeshare, or Citigroup.

## 1. Go / no-go

**GO** for M1 (status collector) and M2 (trip ingestion and station identity), with conditions.

| Condition | Status |
|---|---|
| Live GBFS 2.3 feeds reachable via the discovery document | **V** (200 OK; 2,519 stations) |
| Field names, `ttl`, and timestamp types known | **V** (`ttl`=60; POSIX ints) |
| Trip-file station IDs join to live feed | **V** for JC/Hoboken: 100% match on `short_name`, 0% on `station_id`. **U** for NYC files |
| License compatible with polling at `ttl` with private retention | **R**: likely yes. Clause 2(e) leaves some ambiguity; see SOURCES_AND_POLICY |
| Leak-free weather archive exists | **V**: IEM MOS archive (public domain) returns past runs as issued |
| Historical availability labels | **Unavailable**. Labels must be collected from now on; there is no archive |

**Truly blocking decisions** (for the user):
1. **Where the collector runs (M1).** It must be always-on. A laptop collector leaves gaps, and gaps destroy labels.
2. **Public name (M9).** "Citi Bike" is a named mark under clause 2(h). Keep the working title internal.

Optional, at any time: a short note describing the project to bike-data@lyft.com (R).

## 2. Recommended MVP problem statement (smallest defensible first task)

> For the ~40 installed docked stations of **cluster C (Jersey City + Hoboken)**, at each issue time *t*, predict whether a station that is **currently serviceable** will be observed with **zero available bikes (with `is_renting`=1)** or **zero available docks (with `is_returning`=1)** at any fresh snapshot in **(t, t+30 min]**. Compare against persistence/threshold and time-of-week climatology on a chronologically held-out window. The earliest valid evaluation is the collector start date **+ 28 days**, in a winter regime.

Why cluster C first (R):
- Its trip files are small: about 4.6 MB/month compared with about 1 GB/month for NYC.
- Its join key is proven (V).
- The Hudson gives it a natural geographic boundary.
- The weekday commute profile is visible in the trips (V: peaks at 08 and 17 local).

The final cluster choice can still wait until M3. Collect the **whole system** regardless; one request returns every station (V).

Why "transition within 30 min" rather than "state at t+30" (R): already-empty stations make state-at-t+30 trivially predictable by persistence. Keep the state target as secondary and report already-empty and serviceable stations separately.

## 3. Feasibility of product claims

| Claim / capability | Class | Basis |
|---|---|---|
| Current bikes, docks, and service flags with freshness | **Feasible now** | V: fields present. Per-station `last_reported` exists, but 48 stations carry a placeholder value (86400) |
| Station time history | **Feasible after collection** | Starts when the collector starts. No prior archive (SS, Comptroller report) |
| Trip-flow diagnostics with join coverage | **Feasible now** | V: `short_name` join is 100% for JC |
| 30-min empty/full forecast, *produced* | **Feasible now** | Baselines and inventory-style model from trip rates. The forecasts would be unvalidated |
| 30-min forecast, *validated* | **After ≥28 days of snapshots** | Needs observed labels. Positive-event counts in winter are U |
| Weather-feature ablation | **Requires optional source** | V: IEM MOS archive usable. Availability lag must be modeled (R) |
| Evidence-grounded agent over recorded data | **Feasible after M2/M3** | Depends on clean datasets and tools. Requires API budget approval |
| Hidden causes (operator moves, unmet demand) | **Not defensible** | Not observable in public data (SS/R) |
| Simulated rebalancing comparison | **Feasible**, labeled simulated | Note: 58/2519 live stations already violate the capacity invariant (V). Initial-state rules are needed |
| Public branded deployment under the "Citi Bike" name | **Blocked by policy** | Clause 2(h) requires written permission |

## 4. Feasibility of experiments (EXPERIMENTS_AND_PROOF / proposal IDs)

| ID | Class | Note |
|---|---|---|
| F1, F2 (status features vs persistence/climatology; transitions) | After 28+ days of snapshots | The proposal's ≥200 positives gate is unmeasured for 40 stations in winter (U) |
| F3 (trip-flow lift) | After 28+ days | Trip files are published about 5 days after month end (V: Oct file on Nov 5). Enforce the publication lag |
| F4 (neighbors/weather) | After about 8 weeks plus IEM MOS | Weather features use run time plus a conservative lag |
| F5 (calibration / alert budget) | After about 8 weeks | — |
| A1–A6 (agent) | After M3/M4 plus API budget | Use deterministic verifier-first scoring |
| O1–O3 (policies, robustness) | Feasible in simulation | Results are simulated only |
| O4 (simulator vs observed) | After collection | The gap is expected because rebalancing is unobserved |

## 5. Highest-risk assumptions (details in ASSUMPTIONS_AND_RISKS)

1. **Label scarcity in winter.** Prevalence of transitions into empty or full in cluster C is unmeasured.
2. **Per-station staleness.** A fresh feed does not mean every station is fresh: 82 stations were more than 1 h stale and 48 had a placeholder value (V).
3. **Trip timestamps are naive local time** (inferred, strong). The fall-back hour is ambiguous.
4. **Feed deviates from GBFS 2.3.** Booleans are sent as 0/1 ints, there are non-standard fields, and `station_id` formats are mixed (UUID and 19-digit numeric) (V).
5. **Volume.** About 1.56 GB/day of transfer and about 100 MB/day of gzipped raw data at `ttl`=60 (V inputs, R projection). That is about 10× the proposal's assumption.
6. **License clause 2(e) ambiguity** for automated retrieval (R).
7. **NYC `202610` trip zip is about 315 MB**, compared with about 1 GB for prior months (U: partial or repackaged?).

## 6. Important questions (non-blocking; become architecture-stage assumptions)

- Poll cadence: 60 s (`ttl`) or 120 s? 120 s halves volume. Whether it costs label resolution is reasoned only, and it should be decided at M1 using the transition-duration distribution.
- Should `num_bikes_available` include e-bikes for the empty label? The feed exposes `num_ebikes_available` and `vehicle_types_available`, so a classic/e-bike split is possible.
- What to do with stations where available + disabled > capacity in the simulator's initial state.
- NYC trip-file join coverage, to check in M2 before any NYC cluster is chosen.

## 7. What could NOT be verified

- NYC trip-file schema and join coverage. Only the JC file was downloaded, per instruction.
- Whether the server returns 304 to conditional GETs.
- IEM rate limits and the exact dissemination latency of MOS runs.
- The O'Mahony & Shmoys 2015 full text (bot wall). The MDPI page returned 403 (bibliographic details came from a mirror).
- `ride.citibikenyc.com/data-sharing-policy` returned 503. The canonical `citibikenyc.com` URL worked.
- VM pricing.

## 8. Answers to the M0 question list (summary)

| # | Answer |
|---|---|
| 1 | GBFS 2.3, `ttl` 60, `last_updated` and `last_reported` are ints. Full inventory is in DATA_DICTIONARY §1. No `Cache-Control`. `ETag` and `Last-Modified` present. All nine named fields exist |
| 2 | JC-202610: 13 columns, 111,446 rows. Naive local timestamps (inferred). `start_station_id` = `short_name` (100%) |
| 3 | Clauses quoted exactly in SOURCES_AND_POLICY §3. Polling at `ttl` with private retention is likely consistent (R, not legal advice) |
| 4 | Yes: IEM MOS archive (public domain). Open-Meteo Previous Runs is partial (non-commercial, fixed lead offsets) |
| 5 | Three clusters in DATA_DICTIONARY §4 (capacity 2,703 / 1,326 / 827) |
| 6 | Status: about 1.56 GB/day transfer, about 100 MB/day gzipped |
| 7 | ASSUMPTIONS_AND_RISKS §1 |
| 8 | Both citations exist. Raviv & Kolka's content is mischaracterized (dissatisfaction function, not first-passage probability). O'Mahony & Shmoys' modeling detail is U. See SOURCES_AND_POLICY §5 |
