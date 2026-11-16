# Plan for steps 3–5 (user instruction, saved verbatim on 2026-11-15)

Step 2 is final. Do not retune the forecast model or re-score it on October 2026.

Finish the prototype without waiting for me between steps. Before writing anything, orient yourself:
- Read CLAUDE.md, docs/STATUS_AND_HANDOFF.md, the README, and docs/discovery/DATA_DICTIONARY_DRAFT.md and ASSUMPTIONS_AND_RISKS.md for the known data quirks.
- Survey the existing code and tests from steps 1 and 2, and list the tables in data/fleet.duckdb with their columns by running a query. Reuse the existing modules, table names and test patterns. Do not duplicate logic that already exists.
- Treat source/ORIGINAL_OBSIDIAN_SPEC.md and context/ARCHITECT_PROPOSAL.md as background only. Where they conflict with the offline prototype scope, the prototype scope wins. Do not build anything from them that is not in the steps below.
Then tell me in five lines or fewer what you found and will reuse, save this message as docs/PLAN.md, and do steps 3, 4 and 5 in order.

Rules for every step: keep it small, run the tests, write results to docs/STATUS_AND_HANDOFF.md, then git commit locally with a clear message and move on. Never push. Never commit anything under data/. Stop and ask me only if tests still fail after two fix attempts, or you need a secret, a paid service, or a decision that changes scope. Label every simulated number as simulated in code, output and UI.

STEP 3, simulator.
- Start inventory from the GBFS snapshot for the Jersey City and Hoboken stations, clipped to capacity. Skip stations that are not installed.
- Simulate one day hour by hour. Draw departures and arrivals from Poisson distributions using the step 2 forecast for a typical October weekday. A departure at an empty station is a lost rental. An arrival at a full station is a failed return.
- Two policies: no action, and a greedy rule with one truck of capacity 20 that each hour moves bikes from the fullest station to the emptiest within a stated travel budget. Put all truck assumptions in one config file.
- Run 30 seeds, the same seeds for both policies. Report lost rentals and failed returns as paired differences with a confidence interval.
- Tests: inventory never below zero or above capacity, bikes conserved by truck moves, same seed gives same result.

STEP 4, investigation agent.
- A single tool-use loop on the Anthropic API. Model name from an AGENT_MODEL variable in .env, default claude-sonnet-5-5. Key from ANTHROPIC_API_KEY in .env, loaded by the app at runtime. Do not read or print .env yourself. If a live call fails for lack of a key, build everything else, test with recorded responses, and tell me at the end.
- Read-only tools over data/fleet.duckdb with validated arguments and row limits: station lookup, hourly flow for a station and date range, forecast vs actual, model metrics, simulation results. No free-form SQL from the model.
- Limit of 8 tool calls and a token cap per question. Every number in an answer must come from a tool result, and the answer lists which tool calls it used. If the data does not support an answer, it says so.
- Write 10 test questions whose correct numbers you compute directly with SQL, and report how many the agent gets right.

STEP 5, app.
- One Streamlit app with four views: station map with snapshot bikes and docks, forecast vs actual for a chosen station, the two-policy simulation comparison, and an ask-the-agent box that shows the tool calls behind each answer.
- Badge every value as Observed, Predicted or Simulated. Show a banner: independent analysis of public bike-share data, not affiliated with the operator. Use a neutral app name with no operator brand.
- Add run instructions to the README.

When all three are done: use the auditor subagent to review the whole repo, fix anything it rates high severity, then give me a summary: what works, the measured numbers, what is simulated, and anything you could not finish.
