# Project state and next-session handoff

> **Template only.** During implementation maintain the live version at `docs/STATUS_AND_HANDOFF.md`. Treat the repo and test outputs as source of truth.

Last updated (UTC): [date/time]
Latest git commit: [SHA or not committed]
Branch / working-tree status: [details]
Architecture decision version: [doc/link]
Source/policy verification last checked: [date/link]
External resources currently running: [none / exact names + ownership]

## Current outcome
[One paragraph describing what demonstrably works today.]

## Ticket status
| ID | Scope | State (`verified done`, `implemented unverified`, `blocked`, `not started`) | Evidence |
|---|---|---|---|
| ... | ... | ... | ... |

## Exact verification evidence
| Command/test | Timestamp | Observed outcome | Notes |
|---|---|---|---|
| ... | ... | ... | ... |

## Data and model state
- GBFS version + endpoints actually inspected:
- Trip sample dates + columns actually inspected:
- Snapshot collection start, if approved/active:
- Label sufficiency (actual counts/windows):
- Evaluation windows and verified metrics (or not run):
- Agent eval case count/results (or not run):
- Simulation case count/results (or not run):

## Decisions and deviations
- [What changed and why; link decision record]

## Blockers / approvals
| Blocker | Class | Exact unblock action |
|---|---|---|
| ... | ... | ... |

## Next ready ticket
- Ticket:
- Why it's ready:
- Acceptance proof:
- Commands to run:
- Risks / preapproval:

## How a fresh Opus session should resume
1. Read `CLAUDE.md` and this file.
2. Inspect git status and last changed files.
3. Re-run [specific smoke checks].
4. Follow `prompts/05_RESUME_SESSION.md`, then `prompts/03_IMPLEMENT_ONE_SLICE.md` after user approval.
