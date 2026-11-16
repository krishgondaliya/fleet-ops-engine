# Project state and next-session handoff

| Item | Value |
|---|---|
| Last updated (UTC) | 2026-11-16 ~03:15 |
| Latest git commit | 530d006. M0 outputs below are **not committed** |
| Branch / working tree | `m0-discovery`. New untracked files: `docs/`, `tests/fixtures/gbfs/` |
| Architecture decision version | None approved. `context/ARCHITECT_PROPOSAL.md` is a proposal; M0 challenges are in `docs/discovery/ASSUMPTIONS_AND_RISKS.md` §1 |
| Source/policy verification last checked | 2026-11-16 (see `docs/discovery/SOURCES_AND_POLICY.md`) |
| External resources currently running | **None.** No polling, services, or deployments |

## Current outcome
M0 discovery is complete as **documentation only**. No application code was written. What exists:
- Four discovery documents built from real payloads.
- Three evidence scripts.
- Real 10-station GBFS fixtures with provenance.

Recommendation: **GO** for M1/M2. The collector host must be chosen first.

## Ticket status
| ID | Scope | State | Evidence |
|---|---|---|---|
| M0 | Feasibility and evidence memo | **verified done** (docs) | `docs/discovery/*.md`, verification table below |
| M1 | Collector live | not started, **blocked** | Host decision and polling approval |
| M2 | Trips and station identity | not started (ready) | — |

## Exact verification evidence
| Command/test | Timestamp (UTC) | Observed outcome | Notes |
|---|---|---|---|
| `python -` (in-memory script, now `docs/discovery/evidence/m0_evidence_pass.py`) | 02:47 | GBFS 2.3, ttl 60, 2,519 stations. JC-202610: 111,446 rows. short_name join 100% | First fetch of each GBFS URL |
| `python -` (now `docs/discovery/evidence/m0_cluster_refinement.py`) | 02:49 | 3 clusters × 40 stations; capacity 2,703 / 1,326 / 827 | Second (final budgeted) fetch |
| `python docs/discovery/evidence/make_gbfs_fixtures.py` | 03:06 | Wrote 3 files in `tests/fixtures/gbfs/`. 10 stations selected | User-approved third fetch |
| Inline fixture check (10 stations per feed, matching IDs, provenance contains "REAL") | ~03:08 | `fixture checks OK` | — |
| `git ls-files \| grep -E '\.(csv\|zip\|parquet)$'` | ~03:15 | No output (exit 1). The same check on untracked files also printed nothing | No raw data present |

Rerunning the evidence scripts fetches live data again. Respect the fetch policy before doing so.

## Data and model state
- **GBFS:** version 2.3. Endpoints `https://gbfs.lyft.com/gbfs/2.3/bkn/en/{station_information,station_status}.json`, resolved from discovery.
- **Trip sample:** JC-202610 (Oct 2026), 13 columns, analyzed in memory and **not stored**.
- **Snapshot collection:** not started.
- **Labels, evaluation, agent, simulation:** not run.

## Decisions and deviations
- Fetch budget: 2 per GBFS URL, plus 1 user-approved extra fetch of station_information and station_status for fixtures.
- Raw payloads were analyzed in memory only. The only stored provider data is the 10-station fixture subset.
- In plan mode, the evidence scripts were run from the plan file because a long heredoc failed to parse.

## Blockers / approvals
| Blocker | Class | Exact unblock action |
|---|---|---|
| Collector host | requires-user-decision | Choose an always-on VM or home machine |
| Start continuous polling | requires-user-decision | Explicit approval (CLAUDE.md #7) |
| Public name | requires-user-decision | Neutral name before any public artifact |
| NYC join coverage | requires-source-verification | Sample one NYC month in M2 |

## Next ready ticket
- **Ticket:** prompt 01, the architecture review. It challenges `ARCHITECT_PROPOSAL.md` with the M0 evidence, then M1 or M2.
- **Why it's ready:** feed schema, ttl, join key and volume are known.
- **Acceptance proof:** an architecture decision record that addresses every item in `ASSUMPTIONS_AND_RISKS.md` §1.
- **Risks / preapproval:** no polling until the host is chosen and polling is approved.

## How a fresh session should resume
1. Read `CLAUDE.md`, this file and `docs/discovery/FEASIBILITY.md`.
2. Run `git status`.
3. Re-run the fixture check without network access: load `tests/fixtures/gbfs/*.json` and assert 10 matching stations.
4. Follow `prompts/05_RESUME_SESSION.md`.
