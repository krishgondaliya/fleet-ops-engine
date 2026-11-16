# Real-world data dossier: verified facts, unknowns, and due diligence

**Checked on 2026-11-15 for source publication and discovery only.** This is **not** a claim that all downstream APIs currently work or that their schema is already validated.

## Official references

1. **Citi Bike system data**: https://citibikenyc.com/system-data  
   Published historical trip downloads and system information. The site lists ride ID, rideable type, start/end timestamps, start/end station details, start/end coordinates and member/casual classification. **Published trips are completed rides.** Formats may differ across vintages.
2. **Citi Bike data sharing policy**: https://citibikenyc.com/data-sharing-policy  
   Terms govern data access/use. Verify before any public release or automated collection. Policy explicitly prohibits treating the data as a stand-alone distributable dataset, unauthorized interfaces/extraction, customer reidentification, implied endorsement, and trademark use without written permission. The license grants broad but *conditional* data use; do not infer that public use of brand marks is cleared.
3. **Citi Bike GBFS discovery URL**: https://gbfs.citibikenyc.com/gbfs/2.3/gbfs.json  
   As checked, returned a GBFS **2.3** discovery document with language feed lists, including `station_information`, `station_status`, `system_information`, alerts and others. English status URL discovered at that instant: `https://gbfs.lyft.com/gbfs/2.3/bkn/en/station_status.json`. This URL is illustrative of discovery; **resolve from discovery at runtime instead of hardcoding**. Downstream feed reachability and payload structure were **not independently verified**.
4. **GBFS specification/reference**: https://gbfs.org/documentation/reference/  
   GBFS defines the meaning of status flags, `last_updated`, `ttl` and station `last_reported`. **Important:** currently published GBFS reference includes newer versions. Check the actual version-specific specification before assuming fields like `num_vehicles_available` or timestamp representations; GBFS 2.x can use `num_bikes_available`.
5. **Optional National Weather Service API**: https://www.weather.gov/documentation/services-web-api  
   Optional later; no-weather baseline first. Live forecast ≠ retrospectively known forecast archive.

## What is available in principle vs. what remains to verify

| Information | Source | Verification needed by Opus |
|---|---|---|
| Trip timestamps, station identifiers, ride types | Monthly trip files | Pick dates, sample actual CSVs, validate columns/types/null rate and station mapping |
| Station IDs, coordinates, capacities | `station_information` | Verify fields for actual feed version; version metadata changes |
| Bike/dock counts, service state | `station_status` | Verify real response, count field names, `ttl`, timestamps, station identifiers |
| Collection cadence | Feed `ttl` + provider terms | Determine fair polling behavior; don't assume 30 sec or 5 min fixed cadence |
| Historic availability time series | Not supplied here | Must accumulate live observations over time, if allowed; cannot reconstruct from trips alone |
| Historical weather as-of-forecast | Not assured | Find a reliable archived source or omit weather from leak-free backtesting |
| Operator truck movements / unmet customer demand | Not public here | Do **not** invent or identify these from simple count changes |
| Brand/logo rights | Provider policy | Seek permission/choose alternative public-facing brand; don't imply endorsement |

## Essential data traps

**1. Censored demand**  
Completed rides do not measure attempted rides that failed because no bikes/docks were available. Demand estimators must disclose this.

**2. Missing status history**  
The GBFS feed reports publisher's *current* view. A daily/monthly trip dataset is not equivalent to an availability history. Only observed collected status snapshots (or another verified archive) can support honest retrospective zero/full labels.

**3. Service status is not demand**  
Separate a station closed for maintenance (`is_renting`/`is_returning` false) from a normal empty/full outcome. Zero count is not automatically a shortage event.

**4. Event time vs. ingestion time**  
Keep feed freshness and station last-report time distinct from collection time. Handle stale/repeated snapshots, reordering and clock issues.

**5. Identifiers and geography**  
Don't silently join by station display name or assume stable capacity, coordinates or station IDs across years. Report matched/unmatched join coverage.

**6. Prediction leakage**  
Do not compute features from trips or weather that occurred after prediction issuance. Evaluation should follow actual information availability, not merely data-file timestamps.

**7. Counterfactual simulation limits**  
Station count changes reflect some combination of actual riding, maintenance and possible rebalancing. No public data here gives a complete causal picture. Simulated intervention impact is not an observed treatment effect.

**8. Public release/branding**  
Data license may permit analysis but still restrict marks, data redistribution, and use methods. Keep raw downloads out of git and public artifacts. Record exact policy clauses and any permission obtained.

## Data verification request for Opus

Before architecture or production collector code, obtain a *small, permitted* sample and produce a source evidence memo that includes:

- Each source URL, retrieval date/time, status, and relevant policy/terms notes.
- Feed version, exact field names, `ttl`, `last_updated`, station report timestamp representation, example field types and nullable cases.
- One verified example of station/status join coverage and basic missing-field rates (no broad bulk harvesting for discovery).
- Historical trip-file schema for a specified time period and whether station identifiers align with live feeds.
- Known gaps, data volume implications, feasibility of 30-minute labels and the earliest date evaluation could be valid.
- An explicit distinction between **confirmed**, **inferred**, **planned to validate**, and **unavailable** facts.

If internet access fails, report that transparently and do not fabricate samples or observations.
