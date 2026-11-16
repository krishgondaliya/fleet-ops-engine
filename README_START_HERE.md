# Claude Code / Opus handoff kit

**Project working name:** Citi Bike: Agentic Fleet Forecasting & Optimization Engine  
**Purpose of this kit:** Supply *inputs and instructions* so Claude Opus can independently perform discovery, challenge the original proposal, design the architecture, produce an execution plan, implement the system, and prepare a defensible FDE portfolio handoff.

**This kit does not prescribe an architecture, stack, directory structure, work breakdown, or finished implementation.** Those are outputs to ask Opus to produce and justify.

## 1. What's inside

| File | Role |
|---|---|
| `CLAUDE.md` | Short, persistent project rules Claude Code reads on startup |
| `context/PROJECT_BRIEF.md` | Product/problem framing, goals, non-goals, real-world operator scenarios |
| `context/REQUIREMENTS_AND_BOUNDARIES.md` | Required behaviors, constraints, and honest project boundaries |
| `context/DATA_SOURCE_DOSSIER.md` | Official source links, known facts, unverified fields, policy checks, data traps |
| `context/EXPERIMENTS_AND_PROOF.md` | Capability experiments, quality metrics, independent validation expectations |
| `context/OPEN_DECISIONS.md` | What Opus should decide, verify, or escalate; not pre-decided architecture |
| `source/ORIGINAL_OBSIDIAN_SPEC.md` | Unedited original detailed project idea; a reference, **not** an implementation mandate |
| `prompts/00_FEASIBILITY.md` | First prompt: research and verify before designing |
| `prompts/01_ARCHITECTURE.md` | Second prompt: independent architecture and tradeoff evaluation |
| `prompts/02_EXECUTION_HANDOFF.md` | Third prompt: executable work plan and session handoff documents |
| `prompts/03_IMPLEMENT_ONE_SLICE.md` | Repeatable implementation prompt, one verified milestone at a time |
| `prompts/04_INDEPENDENT_AUDIT.md` | Rigorous quality/security/reproducibility review |
| `prompts/05_RESUME_SESSION.md` | Start a new Claude Code session without losing progress |
| `templates/STATUS_AND_HANDOFF.md` | Template for Claude to maintain the *actual* repo's state |
| `templates/DECISION_RECORD.md` | Reusable architectural / research decision record |

## 2. How to use with Claude Code

1. **Create a fresh git repository** for the actual project and unzip this kit **at repository root**. Keep these handoff files available to Claude. The `source/` file is your original Obsidian specification, copied verbatim.
2. Open that directory in Claude Code; select **Opus** via the model selector (`/model` if supported by your installed version). Confirm the selected model in Claude Code rather than relying on an unverified CLI flag.
3. Use **Plan mode** for the first three prompts. In the CLI, the current UI can switch modes with `Shift+Tab`; verify your installed version. Plan mode is read-only with respect to normal code modification. If Opus needs to persist planning documents while Plan mode forbids writing, ask it to present them for approval, then explicitly approve writing docs only, or switch to an appropriate permission mode.
4. Paste the body of `prompts/00_FEASIBILITY.md` as your first Claude Code prompt. Let Opus read files and check authoritative sources. **Do not ask it to write application code yet.**
5. Inspect the feasibility result. Then give `prompts/01_ARCHITECTURE.md`. Review chosen alternatives and unresolved issues.
6. Then give `prompts/02_EXECUTION_HANDOFF.md`. This should create an implementation backlog and durable project-state files, not begin writing the whole application.
7. Move out of Plan mode only after the plan is approved. Repeatedly issue `prompts/03_IMPLEMENT_ONE_SLICE.md` with a specific ticket or "next ready ticket". Review each set of tests and evidence before accepting it.
8. Periodically run `prompts/04_INDEPENDENT_AUDIT.md`. At the start of new Claude Code sessions, use `prompts/05_RESUME_SESSION.md`.

**Suggested first message (copy exactly):**

> You are acting as the lead engineer and applied AI experiment designer for this repository. First read `CLAUDE.md`, every file in `context/`, and `source/ORIGINAL_OBSIDIAN_SPEC.md`. The source spec is background, not an approved architecture. Then follow all instructions in `prompts/00_FEASIBILITY.md`. Do not implement application code, run recurring polling, deploy services, incur paid API charges, or publish anything in this phase. Be skeptical of unsupported assumptions. Record source URLs and uncertainty. Only ask for decisions that are truly blocking.

## 3. Project principles, condensed

- The working project name is the user's choice. **Do not assume permission to use the Citi Bike mark in a public brand/logo/domain.** Public naming needs a policy review, potentially written permission. Never suggest official affiliation.
- Real historical completed trips and *current* GBFS status are different kinds of evidence. **Do not invent past station stockout labels.** A collector must accumulate future station snapshots if permitted.
- An LLM is a bounded evidence-grounded investigator, not an unvalidated time-series forecaster, unconstrained SQL engine, or real fleet controller.
- Every forecast must be compared to a simple baseline under chronological evaluation. Every claimed operational improvement from rebalancing must be labeled *simulated*.
- Prioritize a working vertical slice over speculative infrastructure. Explain when a proposed technology is unnecessary.
- Maintain budget, uncertainty, test evidence, source provenance, and a durable handoff after every implementation session.

## 4. What "complete" means

"Complete" is not "Claude produced a lot of files." It means a new developer can:

1. Set up and run the documented system with non-secret configuration.
2. Inspect actual data provenance and freshness, and see missing-data conditions rather than invented zeros.
3. Run the project tests and reproduce the data/forecast/agent/simulation evaluations to the extent permitted by data availability.
4. Trace predictions and agent claims to specific inputs and tool results.
5. Inspect simulation assumptions and compare baselines fairly.
6. Read an honest technical report distinguishing measured, simulated, and unverified outcomes.

Some of these may remain blocked until enough *new* station snapshots have accumulated. Opus must label them pending instead of faking completion.

## 5. Authoritative references

- Citi Bike system data: https://citibikenyc.com/system-data
- Citi Bike data-sharing policy: https://citibikenyc.com/data-sharing-policy
- Citi Bike GBFS discovery (2.3 entry point, subject to change): https://gbfs.citibikenyc.com/gbfs/2.3/gbfs.json
- MobilityData GBFS reference: https://gbfs.org/documentation/reference/
- Claude Code memory / `CLAUDE.md`: https://code.claude.com/docs/en/memory
- Claude Code permission modes: https://code.claude.com/docs/en/permission-modes
- Claude Code best practices: https://code.claude.com/docs/en/best-practices

**Verification note:** As of 2026-11-15, the discovery feed returned GBFS 2.3 with English `station_status` and `station_information` endpoints under `https://gbfs.lyft.com/gbfs/2.3/bkn/en/`. We verified **the discovery document**, not live reachability or exact payload schemas of those downstream endpoints. Opus must verify those independently. GBFS 3.x examples must not be blindly imposed on a GBFS 2.3 feed.
