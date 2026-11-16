# Data dictionary (draft, from real payloads)

Labels: **V** verified · **SS** source-stated · **R** reasoned · **U** unknown.
Inventory source: GBFS fetch 1 (2026-11-16 02:47:36 UTC) and JC-202610 trip file. Scripts: `evidence/m0_evidence_pass.py`, `evidence/m0_cluster_refinement.py`.

## 1. GBFS (version 2.3, system `lyft_nyc`, timezone America/New_York)

### Envelope (both feeds, V)
| Field | Type | Value seen |
|---|---|---|
| `version` | str | `"2.3"` |
| `ttl` | int | **60** |
| `last_updated` | int (POSIX seconds) | e.g. 1794797216 |
| `data.stations` | list | 2,519 stations |

HTTP (V): no `Cache-Control`. `ETag` and `Last-Modified` are present. Served by S3 + CloudFront. **No `Content-Encoding`**: the payload is uncompressed on the wire even with `Accept-Encoding: gzip`. Sizes: information 801,371 B (gzip 115,331), status 1,081,690 B (gzip 69,216).

### station_information (n = 2,519, V)
| Field | Type | Missing/null |
|---|---|---|
| `station_id` | str. **Mixed formats:** UUID (e.g. `66dc292c-0aca-11e7-…`) and 19-digit numeric string (e.g. `2218569564729174336`) | 0% |
| `short_name` | str. NYC `####.##`, Jersey City `JC###`, Hoboken `HB###` | 0% |
| `name` | str (untrusted display text) | 0% |
| `lat`, `lon` | float | 0% |
| `capacity` | int | 0% |
| `region_id` | str (`70` JC, `71` NYC, `311` Hoboken) | **0.48% (12)** |
| `rental_uris` | dict {android, ios} | 0% |
| `is_charging` | bool | 0% |

Not present: `station_type`, `address`, `post_code`.

### station_status (n = 2,519, V)
| Field | Type | Missing/null | Notes |
|---|---|---|---|
| `station_id` | str | 0% | Joins to station_information 2,519/2,519 |
| `num_bikes_available` | int | 0% | Includes e-bikes (R, from GBFS semantics) |
| `num_ebikes_available` | int | 0% | **Non-standard extension** |
| `num_bikes_disabled` | int | 0% | |
| `num_docks_available` | int | 0% | |
| `num_docks_disabled` | int | 0% | |
| `num_scooters_available` | int | **2.50% (63)** | Non-standard; field absent for some stations |
| `num_scooters_unavailable` | int | **2.50% (63)** | Non-standard |
| `vehicle_types_available` | list[{vehicle_type_id: str, count: int}] | 0% | IDs "1" and "2" seen. Mapping via `vehicle_types.json` not fetched (U) |
| `is_installed` | **int 0/1** | 0% | GBFS 2.3 requires JSON boolean, so this deviates |
| `is_renting` | **int 0/1** | 0% | Same deviation |
| `is_returning` | **int 0/1** | 0% | Same deviation |
| `last_reported` | int (POSIX) | 0% | **48 stations have the placeholder value 86400 (<1e6)** |

### Required presence checks (V)
| Field | Exists | Feed |
|---|---|---|
| `short_name` | yes | information |
| `capacity` | yes | information |
| `num_ebikes_available` | yes | status |
| `vehicle_types_available` | yes | status |
| `num_bikes_disabled` | yes | status |
| `num_docks_disabled` | yes | status |
| `is_installed` | yes | status |
| `is_renting` | yes | status |
| `is_returning` | yes | status |

### Snapshot quality at 02:47 UTC (V)
| Measure | Value |
|---|---|
| Station age (`last_updated − last_reported`): min / median / p90 | 17 s / 56 s / 124 s |
| Stations stale > 1 h | 82 |
| Stations stale > 1 day (includes placeholders) | 70 |
| `is_installed`=0 | 51 |
| `is_renting`=0 | 85 |
| `is_returning`=0 | 85 |
| `num_bikes_available`=0 | 180 |
| `num_docks_available`=0 | 200 |
| bikes + docks + bikes_disabled + docks_disabled **> capacity** | **58 / 2,519** |
| Example record | installed=1, renting=0, returning=0, 0 bikes, 24 bikes disabled, last_reported about 3.6 days old |

## 2. Trip file: JC-202610-citibike-tripdata.zip (V)
4,599,971 B zip containing one CSV (`JC-202610-citibike-tripdata.csv`, 24,401,585 B) with **111,446 rows**. Every value was read as a string; no implicit NA conversion.

| Column | Inferred type | Empty | Distinct | Example |
|---|---|---|---|---|
| `ride_id` | numeric-looking string (keep as str) | 0% | 111,446 | `6239929685212553526` |
| `rideable_type` | enum | 0% | 2 | `electric_bike`, `classic_bike` |
| `started_at` | naive timestamp text | 0% | — | `2026-10-20 22:01:47.295` |
| `ended_at` | naive timestamp text | 0% | — | `2026-10-20 22:06:44.476` |
| `start_station_name` | str | 0% | 108 | — |
| `start_station_id` | str (`JC###`/`HB###`) | 0% | 108 | `JC110` |
| `end_station_name` | str | 0.301% (336) | 217 | — |
| `end_station_id` | str | 0.354% (394) | 216 | — |
| `start_lat`, `start_lng` | float, variable precision | 0% | 108 | `40.71539114317` |
| `end_lat`, `end_lng` | float | 0.352% (392) | 219 | — |
| `member_casual` | enum | 0% | 2 | `member`, `casual` |

The empty counts for end name, ID, and coordinates differ slightly. Their row-level relationship is U.

- **Timestamp format (V):** `YYYY-MM-DD HH:MM:SS.fff`, always 23 characters, with no `Z` and no offset.
- **Range (V):** `started_at` runs from 2026-10-01 00:01:33 to 2026-10-31 23:59:54. `ended_at` reaches 2026-11-01 23:59:30.
- **Durations (V):** median 379 s, 0 negative, 33 longer than 1 day.

**Local time or UTC: naive America/New_York local time.** This is *inferred (strong)*, not source-stated.
- Weekday start-hour counts peak at **08:00 (6,945)** and **17:00 (9,851)**, with the minimum at 03:00 (95).
- In UTC those peaks would correspond to 04:00 and 13:00 EDT, which does not fit commuting.
- The weekend profile is flat from 11 to 16.
- Neither the system-data page nor the CSV states a timezone.

**DST hazard:** DST ended 2026-11-01 at 02:00 local. Naive times from 01:00 to 01:59 that day are ambiguous, and the file contains rides ending on that date. Convert to UTC with an explicit ambiguity policy and add a test.

### Station ID join (V)
| Trip column | → GBFS `short_name` | → GBFS `station_id` |
|---|---|---|
| `start_station_id` | **100.00% of trips; 108/108 distinct** | 0% |
| `end_station_id` (non-empty) | **100.00%; 216/216 distinct** | 0% |

JC files include Hoboken (`HB`) stations. Some end stations are NYC stations, and all of those matched as well. Join coverage for NYC trip files is U.

## 3. Bucket index (V, 02:47 UTC)
- 180 keys: 134 `JC-*` (2015-09 to 2026-10) and 45 NYC files plus `index.html`.
- Naming drift: older files end `-citibike-tripdata.csv.zip`; JC-202610 ends `-citibike-tripdata.zip`.
- NYC `202610-citibike-tripdata.zip` is 314,905,579 B. Prior months were about 0.97–1.05 GB, so this one may be partial (U).

## 4. Candidate clusters (V; GBFS fetch 2, 02:49 UTC)
- Rule: installed docked stations (`is_installed`=1, `capacity`>0), filtered by region, then the 40 nearest by haversine distance to a coordinate seed. No station names were typed.
- A version without the region filter put 2 Manhattan stations into C, across the Hudson. The filter was added for that reason.
- Demand-character labels are R, except C's commute profile, which is V from the JC trips.

| Cluster | Seed | Regions | n | Lat range | Lon range | Total capacity (mean) | Radius |
|---|---|---|---|---|---|---|---|
| **A** Midtown CBD, commuter destination | 40.7540, −73.9840 | 71 | 40 | 40.74757–40.76171 | −73.99377 – −73.97499 | **2,703** (67.6) | 0.88 km |
| **B** Brooklyn residential, commuter origin | 40.6760, −73.9800 | 71 | 40 | 40.66813–40.68538 | −73.99037 – −73.96902 | **1,326** (33.1) | 1.07 km |
| **C** Jersey City + Hoboken | 40.7190, −74.0400 | 70, 311 | 40 | 40.71124–40.73755 | −74.06419 – −74.02837 | **827** (20.7) | 2.12 km |

Member `short_name`s (copied from script output, ordered by distance to seed):
- **A:** 6517.08, 6593.14, 6474.11, 6560.15, 6551.02, 6593.15, 6560.14, 6441.06, 6441.02, 6398.06, 6551.11, 6441.11, 6667.12, 6483.06, 6432.15, 6602.03, 6626.11, 6432.08, 6432.09, 6364.10, 6432.11, 6626.01, 6398.08, 6526.05, 6364.07, 6708.04, 6676.02, 6322.01, 6602.05, 6526.01, 6389.09, 6584.12, 6464.09, 6740.10, 6700.14, 6331.01, 6313.10, 6644.04, 6450.12, 6747.07
- **B:** 4134.06, 4060.09, 4019.06, 4175.15, 4101.18, 4208.01, 3946.07, 4175.14, 4051.01, 3987.06, 4028.04, 4166.08, 4143.04, 4217.06, 4217.02, 4125.07, 3874.01, 3905.15, 4281.08, 4028.03, 3978.13, 4143.02, 4322.06, 4010.13, 4290.06, 3834.10, 4010.15, 3996.01, 4184.07, 4354.07, 4083.13, 3803.09, 4199.12, 4157.15, 3955.05, 4010.01, 3842.08, 4395.07, 3865.05, 4362.04
- **C:** JC014, JC115, JC149, JC006, JC097, JC003, JC082, JC102, JC013, JC116, JC032, JC035, JC074, JC098, JC072, JC038, JC002, JC027, JC076, JC110, JC099, JC009, JC075, JC066, JC023, JC081, JC008, JC052, JC117, JC105, JC034, JC019, JC078, HB101, HB401, JC118, HB409, JC020, HB107, HB612

Membership depends on `is_installed` at fetch time. Re-derive it with the same rule and record the date. Do not hand-maintain the lists.

## 5. Volume at observed `ttl` (Q6)
| Item | Per poll | Per day (1,440 polls) | Per 30 days |
|---|---|---|---|
| station_status transfer (uncompressed on the wire) | 1,081,690 B | **≈1.56 GB** | ≈46.7 GB |
| station_status raw, gzipped at rest | 69,216 B | **≈99.7 MB** | ≈3.0 GB |
| station_information every 6 h, raw | 801,371 B | ≈3.2 MB | ≈96 MB |
| Normalized station-rows | 2,519 | ≈3.63 M | ≈109 M |

Inputs are V; projections are R. Conditional GET is unlikely to save much because content changes about every minute (R). Whether the server answers with 304 is U.

## 6. Fixtures
`tests/fixtures/gbfs/` holds **real** 10-station subsets from GBFS fetch 3 (03:06 UTC), with `PROVENANCE.json` giving URLs, fetch times, ETags, and the selection rule. The subset is 8 cluster-C stations plus 2 edge cases:
- installed but not renting (`short_name` 5129.01);
- placeholder `last_reported`=86400, which is also not installed (`short_name` 6545.07).
