# Sources, fetch ledger, and policy

Labels: **V** verified · **SS** source-stated · **R** reasoned · **U** unknown. All times are UTC on 2026-11-16 unless stated.

## 1. Source registry

| Source | URL | Retrieved | Status | Notes |
|---|---|---|---|---|
| GBFS discovery | https://gbfs.citibikenyc.com/gbfs/2.3/gbfs.json | 02:47:35, 03:06:49 | 200 | Version 2.3. Languages en/fr/es. 12 feeds. ETag `242f5932…` |
| station_information | https://gbfs.lyft.com/gbfs/2.3/bkn/en/station_information.json | 02:47:36, 02:49:36, 03:06:49 | 200 | 801,371 B every time. ETags changed each fetch |
| station_status | https://gbfs.lyft.com/gbfs/2.3/bkn/en/station_status.json | 02:47:36, 02:49:37, 03:06:50 | 200 | 1,081,690 / 1,081,697 / 1,081,770 B |
| system_information | https://gbfs.lyft.com/gbfs/2.3/bkn/en/system_information.json | 02:47:36 | 200 | `timezone` America/New_York. Operator Lyft |
| system_regions | https://gbfs.lyft.com/gbfs/2.3/bkn/en/system_regions.json | 02:49:37 | 200 | 70 JC District, 71 NYC District, 311 Hoboken District, plus 158, 185, 189, 190 ("testzone") |
| Trip bucket index | https://s3.amazonaws.com/tripdata/ | 02:47:37 | 200 | 180 keys |
| JC trip file | https://s3.amazonaws.com/tripdata/JC-202610-citibike-tripdata.zip | 02:47:37 | 200 | 4,599,971 B. ETag `32000f83…`. Analyzed in memory only; **not stored** |
| Data license | https://citibikenyc.com/data-sharing-policy | 02:48:04 | 200 | Text quoted in §3 |
| Data license (alternate URL cited in proposal) | https://ride.citibikenyc.com/data-sharing-policy | ~02:52 | **503** | Use the canonical URL above |
| System data page | https://citibikenyc.com/system-data | ~02:48 | 200 | Links GBFS as the real-time feed. States no timestamp timezone |
| GBFS v2.3 spec | https://github.com/MobilityData/gbfs/blob/v2.3/gbfs.md (read via raw.githubusercontent) | ~02:55 | 200 | Freshness, Boolean, and Timestamp definitions (§4) |
| IEM MOS archive | https://mesonet.agron.iastate.edu/mos/ and https://mesonet.agron.iastate.edu/api/1/mos.json | ~02:52 | 200 | Two queries (KLGA, LAV and NBS, run time 2026-10-15T12Z) |
| IEM disclaimer | https://mesonet.agron.iastate.edu/disclaimer.php | ~02:52 | 200 | Public domain |
| Open-Meteo Previous Runs | https://open-meteo.com/en/docs/previous-runs-api, https://open-meteo.com/en/terms | ~02:51 | 200 | Docs read only; no data calls |
| NYC Comptroller, *Riding Forward* | https://comptroller.nyc.gov/reports/riding-forward-overhauling-citi-bikes-contract-for-better-more-equitable-service/ | ~02:53 | 200 | See §5 |
| MDPI SBRM paper | https://www.mdpi.com/2673-7590/6/4/143 | ~02:53 | **403** | Bibliographic details from a mirror (citedrive) |
| Raviv & Kolka 2013 | https://ideas.repec.org/a/taf/uiiexx/v45y2013i10p1077-1093.html | ~02:55 | search | Bibliography V; abstract-level content |
| O'Mahony & Shmoys 2015 | https://ojs.aaai.org/index.php/AAAI/article/view/9245 | ~02:55 | listing V; PDF blocked | — |

## 2. Fetch ledger and budget

The user's budget was **at most two fetches of each GBFS URL**. The user later approved **one extra fetch** of station_information and station_status, to build the test fixtures.

- Fetch 1 (02:47) was a full in-memory evidence pass: `evidence/m0_evidence_pass.py`.
- Fetch 2 (02:49) refined the clusters: `evidence/m0_cluster_refinement.py`.
- Fetch 3 (03:06) built the fixtures: `evidence/make_gbfs_fixtures.py`, which writes only the 10-station subsets.

The discovery document was fetched twice in total. No polling loop was ever run. The script `User-Agent` was `independent-research-feasibility-check/0.1`; it contained no personal contact details.

The raw payloads and the trip CSV were **not written to disk**; they were analyzed in memory. The only provider data stored in the repo is the 10-station fixture subset under `tests/fixtures/gbfs/`, with `PROVENANCE.json`.

## 3. Data License Agreement: exact clauses (V)

Source: https://citibikenyc.com/data-sharing-policy, retrieved 02:48:04 UTC. "Section 2" is the "Prohibited Conduct" list. The rendered text has no section numerals; the numbering is inferred from section order (License, then Prohibited Conduct). Curly apostrophes were restored where the HTML decoding garbled them.

- **2(b)** "Host, stream, publish, distribute, sublicense, or sell the Data as a stand-alone dataset; provided, however, you may include the Data as source material, as applicable, in analyses, reports, or studies published or distributed for non-commercial purposes;"
- **2(c)** "Access the Data by means other than the interface Bikeshare provides or authorizes for that purpose;"
- **2(e)** "Use data mining or other extraction methods in connection with Bikeshare’s website or the Data;"
- **2(g)** "State or imply that you are affiliated, approved, endorsed, or sponsored by Bikeshare."
- **2(h)** "Use or authorize others to use, without the written permission of the applicable owners, the trademarks or trade names of Lyft Bikes and Scooters, LLC, or Citigroup, Inc., (sponsor of the Citi Bike service). These marks include, but are not limited to CITI BIKE, and the CITI BIKE logo."

Other relevant text (V):
- The grant: "access, reproduce, analyze, copy, modify, distribute in your product or service and use the Data for any lawful purpose".
- There is no attribution clause.
- "Bikeshare may modify or cease providing any or all of the Data at any time".
- The agreement is terminable at any time by notice.
- Trademark permission requests go to bike-data@lyft.com.

### Assessment: polling at the feed `ttl` with private local retention (R, NOT legal advice)

Overall: **likely consistent**, with residual ambiguity in 2(e).

| Clause | Reading |
|---|---|
| 2(c) | Consistent. The official system-data page links the GBFS feed as the real-time data source, so polling it uses the interface Bikeshare provides. Scraping the website would not. |
| 2(b) | Consistent. Private local retention is not hosting, publishing, or distributing a stand-alone dataset. Public outputs should be analyses and derived results. Published reports may include data as source material for **non-commercial** purposes. Whether a job-search portfolio counts as non-commercial is not settled (R: probably, but unconfirmed). |
| 2(e) | **Ambiguous.** "Other extraction methods in connection with … the Data" could be read broadly. Against that reading: the license grants access and copying, GBFS is a machine-readable feed designed for automated consumption, and polling at `ttl` matches the publisher's own refresh hint. Mitigations: never poll faster than `ttl`, never touch the website, keep raw data private, and optionally notify bike-data@lyft.com. |
| 2(g), 2(h) | Collection does not touch these. The risk is in **naming and branding**: the working title contains the CITI BIKE mark. Use a neutral public name and a factual line such as "built on public NYC bike-share data", plus an explicit no-affiliation notice. |

Fixtures: a 10-station subset kept as a test fixture in a private repo is not a "stand-alone dataset" (R). Re-review before the repo becomes public.

## 4. GBFS v2.3 specification excerpts (V via spec text)

- Freshness (station_status): "Data returned SHOULD be as close to realtime as possible, but in no case should it be more than 5 minutes out-of-date."
- `ttl`: "Number of seconds before the data in the feed will be updated again (0 if the data should always be refreshed)."
- Boolean: "Boolean values MUST be JSON booleans, not strings". The values are `true` or `false`. **The live feed sends 0/1 integers instead (V).**
- Timestamp: "MUST be represented as integers in POSIX time". The live feed complies (V).
- `last_reported`: REQUIRED, "The last time this station reported its status to the operator's backend."
- `vehicle_types_available`: v2.1+, REQUIRED if `vehicle_types.json` is defined. `num_ebikes_available` is **not** in the v2.3 spec, so it is an operator extension (V).

## 5. Citations

### Forecasting section of ARCHITECT_PROPOSAL ("citations from memory")

1. **Raviv & Kolka 2013: CONFIRMED, with a content correction.**
   - Citation: T. Raviv and O. Kolka, "Optimal inventory management of a bike-sharing station," *IIE Transactions* 45(10):1077–1093, 2013. DOI 10.1080/0740817X.2013.770186.
   - Content: the paper defines a **user dissatisfaction function**, the expected shortages (unmet rentals and returns) over a horizon, as a convex function of the station's initial inventory. Rentals and returns are stochastic arrival processes.
   - Correction: it does **not** define "probability of hitting zero or capacity within 30 minutes". The proposal's rung 3 is a reasonable **adaptation** and should be described as one.
   - Evidence: bibliographic data V. Content is SS, from the abstract and secondary descriptions.
2. **O'Mahony & Shmoys 2015: CONFIRMED (bibliographic).**
   - Citation: E. O'Mahony and D. B. Shmoys, "Data Analysis and Optimization for (Citi)Bike Sharing," *Proc. AAAI-15*, pp. 687–694. DOI 10.1609/aaai.v29i1.9245.
   - Content: the abstract covers bike placement for usage, overnight rebalancing routing, and mid-rush clustering. The tools were in daily use at NYC Bike Share (SS).
   - Unverified: whether the paper uses a station birth-death inventory model. The full text was blocked, so this is U. Do not cite it for the first-passage model until the PDF is read.

### Source spec references (extra check)

- **NYC Comptroller, "Riding Forward: Overhauling Citi Bike's Contract for Better, More Equitable Service"** (Nov 15, 2023): **V**. Quote: "we created an automated tool that loaded these data every 15 minutes and stored the system status at that time", covering June–July 2023. The report notes "228 gaps of more than 30 minutes, accounting for 5 percent of samples" and that the data "are only available live, not historically."
- **"Citi Bike Station Behavioral Regime Model and Its Application in Rebalancing Operations"**, S. Chen, *Future Transportation* 6(4):143 (2026), DOI 10.3390/futuretransp6040143. Exists (SS via mirror; the MDPI page returned 403). The spec's description of "dataset alignment caveats" is U.

## 6. Weather archives (Q4)

| Source | As-issued archive? | Coverage | Terms | Verdict |
|---|---|---|---|---|
| **IEM MOS** (`/api/1/mos.json?station=KLGA&model=LAV&runtime=…`) | **Yes**. Selectable per run time. V: the 2026-10-15T12Z run returned 38 hourly LAV rows and 23 NBS rows | LAV (hourly GFS LAMP) from 2020-07-12; GFS MOS from 2003; NBS/NBE from 2018–2020, run times changed 2026-05-05 (SS) | "public domain and may be used freely by anyone for any lawful purpose". Attribution appreciated. No stated rate limits (U) | **Usable.** Treat each run as available at run time plus a conservative lag (R; exact latency U) |
| Open-Meteo Previous Runs API | Partially. Fixed lead offsets of 1–7 days (`_previous_dayN`), not per issuance | Most models from Jan 2024 (SS) | Free tier non-commercial only; <10,000 calls/day, 5,000/hour, 600/minute; CC BY 4.0 (SS) | Usable only for day-ahead features. Weaker for a 30-minute horizon |
| NWS api.weather.gov | No. Live forecasts only | — | — | Not usable for backtests |

## 7. Trademark and naming

- The working title "Citi Bike: Agentic Fleet Forecasting & Optimization Engine" is **internal only**.
- Public artifacts should use a neutral name, carry no logos, and include a permanent "independent analysis of public data; no affiliation" notice.
- Written permission from the mark owners (via bike-data@lyft.com) is required before any public use of the marks.
