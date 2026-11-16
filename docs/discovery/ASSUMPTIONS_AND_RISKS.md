# Assumptions and risks

Labels: **V** verified · **SS** source-stated · **R** reasoned · **U** unknown.
Blocked-item classes follow `context/OPEN_DECISIONS.md`.

## 1. ARCHITECT_PROPOSAL claims that the evidence contradicts or cannot support (Q7)

`context/ARCHITECT_PROPOSAL.md` is a proposal, not approved architecture. Each item gives the claim, then the evidence.

### Contradicted or corrected
1. **Volume: "assumes tens of megabytes per day compressed; alert at 10×".** Measured raw gzip is **≈100 MB/day** for status alone at `ttl` 60, already at the top of the alert band. Transfer is **≈1.56 GB/day** because responses are not compressed (V inputs). Revise the expectation, or store a deduplicated, columnar silver layer and keep raw for a bounded window.
2. **"Use conditional requests where the server supports them"; "station_information … plus on change".** ETags exist (V), but station_status changes about every 60 s, and the station_information ETag changed across three fetches about 2 and 17 minutes apart while its byte size stayed identical (V). ETag-based change detection will fire spuriously. Detect change by hashing normalized identity, coordinate, and capacity fields.
3. **"Parse with tolerant Pydantic models: required fields strict".** `is_installed`, `is_renting`, and `is_returning` arrive as **0/1 integers**, not the JSON booleans GBFS 2.3 mandates (V). A strict bool parser rejects every record. Coerce explicitly and log a drift issue.
4. **Simulator: "Runs start from a real observed snapshot" plus the invariant "inventory stays between zero and capacity".** **58/2,519** live stations have available + disabled > capacity (V). Define the initial-state rule (for example, clip with a logged DataQualityIssue, or use effective capacity) before the property tests are written.
5. **Label: "zero rentable bikes with renting enabled", with GBFS's 5-minute freshness rule implying fresh data.** A fresh feed does not mean every station is fresh. **48 stations report the placeholder `last_reported`=86400**, 70 are more than 1 day stale, and 82 more than 1 hour (V). Staleness must be judged per station using `last_reported`, and placeholders must be treated as missing.
6. **"Files prefixed `JC` are Jersey City".** They contain Jersey City **and Hoboken** (`HB###`) stations (V).
7. **License URL `https://ride.citibikenyc.com/data-sharing-policy`.** It returned **HTTP 503**. The canonical `https://citibikenyc.com/data-sharing-policy` returned 200 (V). The proposal's clause summaries match the canonical text.
8. **Rung 3: "the probability a finite-capacity birth-death process hits zero or capacity within 30 minutes … the standard OR treatment (Raviv and Kolka 2013, O'Mahony and Shmoys 2015)".** Both papers exist. Raviv & Kolka define an **expected dissatisfaction function over a horizon**, not a first-passage probability (SS). The O'Mahony & Shmoys modeling detail is U. Describe rung 3 as an adaptation.
9. **Station identity: "station_id" implicitly treated as a uniform key.** `station_id` formats are **mixed**: UUIDs and 19-digit numeric strings (V, e.g. JC149 → `2218569564729174336`). Treat it as an opaque string and never cast it to a number.

### Cannot be supported yet (U)
10. "At least 200 positive transition events per target in the test window" may not be reachable for about 40 stations in a late-November-to-December window. Prevalence is unmeasured.
11. "Stations move, rename and resize". Plausible, but it cannot be observed from snapshots taken over 20 minutes.
12. "One small VM in the roughly 5 to 7 dollars per month class". Not checked.
13. "Trip files arrive about a month late". October 2026 files were published on Nov 5 (V), about 5 days after month end, which is consistent. But NYC `202610` is about 315 MB compared with about 1 GB for prior months, which is unexplained.
14. "Python 3.12". This machine has Python 3.11.9 (V). This is minor and is a tooling decision for the user.

### Resolved by evidence (no longer open)
- GBFS field names, `ttl` (60), and e-bike fields: V.
- Join on `short_name`: V for JC, 100%.
- Naive local trip timestamps: inferred, strong.
- Archived-forecast weather source: V (IEM MOS).
- GBFS 2.3 "never more than 5 minutes out-of-date" wording: V.

## 2. Data gaps and leakage risks

| Risk | Detail | Mitigation (proposed, not built) |
|---|---|---|
| **Censored demand** | Completed trips miss rentals that failed because no bike or dock was available (SS/R) | Never call trip counts demand. Run sensitivity inflation in the simulator. Disclose the bias at empty stations |
| **No status history** | GBFS is live-only (V; Comptroller report says the same) | Labels exist only from collector start. Evaluation is gated on ≥28 days |
| **Trip publication lag** | Month M is published about 5 days after month end (V) | When building features for issue time *t*, use only trip files published before *t* |
| **DST ambiguity** | Trip timestamps are naive local (inferred). The 01:00–01:59 hour repeats on fall-back days | Explicit ambiguity policy plus tests covering both transitions |
| **Per-station staleness** | Placeholder and days-old `last_reported` values (V) | Staleness by station. Unknown is never zero |
| **Closures vs shortages** | `is_renting`/`is_returning` = 0 for 85 stations (V) | Exclude closures from shortage labels and count them separately |
| **Capacity inconsistency** | 58 stations exceed capacity (V) | Logged data-quality issue. Simulator initial-state rule |
| **Unobserved rebalancing** | Count changes mix riders, maintenance and operator moves (R) | No causal attribution. Publish the simulator-versus-observed gap (O4) |
| **Weather leakage** | Using realized weather, or forecasts before they were available | IEM MOS by run time plus a conservative availability lag |
| **Station ID drift** | Mixed `station_id` formats. Metadata may change over time | Versioned station dimension. Report join coverage by month |
| **Seasonal regime** | Collection starts in winter (R) | Disclose it. Re-evaluate later. Do not generalize to summer |
| **Untrusted text** | Station `name` reaches the UI and the model | Treat it as quoted data. Include prompt-injection tests |

## 3. Assumptions carried into the architecture stage (non-blocking)

- Collect the whole system and analyze one cluster (cluster C is provisional).
- Poll no faster than `ttl` (60 s). Whether 120 s is enough depends on the transition durations measured in M1.
- `num_bikes_available` includes e-bikes. A classic/e-bike split is possible but deferred.
- The trip-file station ID equals GBFS `short_name` for NYC as well. Must be verified in M2 before any NYC cluster is chosen.

## 4. Blocked items

| Item | Class | Unblock action |
|---|---|---|
| Collector host (always-on) | `requires-user-decision` | User chooses a VM or always-on home machine before M1 |
| Continuous polling | `requires-user-decision` | Explicit approval to start, per CLAUDE.md invariant 7 |
| Public name and branding | `requires-user-decision` | Choose a neutral name. Optionally contact bike-data@lyft.com |
| Validated forecast results | `requires-more-real-data` | ≥28 days of snapshots with ≥95% fetch coverage |
| NYC trip join coverage | `requires-source-verification` | Sample one NYC month in M2 |
| LLM API usage (agent) | `requires-cost-approval` | User sets a hard spend cap before M5 |
| O'Mahony & Shmoys model detail | `requires-source-verification` | Read the full PDF |
