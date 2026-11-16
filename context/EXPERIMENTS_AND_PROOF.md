# Capability experiments and evidence requirements

**This file describes questions worth answering and standards of proof. It is NOT a selected modeling stack, research plan, or architecture.** Opus should choose the smallest experiments that support a compelling FDE system, justify their order, and reject experiments with poor ROI.

## Forecast / operations questions

- **F1 — Short-horizon prediction:** Can availability-history features predict a station being empty or full at a 30-minute horizon better than persistence and a simple threshold/time-of-week baseline?
- **F2 — Actionable transitions:** Can we predict stations that are currently serviceable but will become short of bikes/docks soon? Distinguish transition prediction from trivial persistence of already-empty stations.
- **F3 — Extra context:** Does adding historical completed-trip flow improve over station-status-only features? Is any claimed lift robust to realistic feature-availability assumptions?
- **F4 — Spatial/weather context:** Do neighboring stations and weather signals provide measurable improvement without leakage and excessive complexity?
- **F5 — Uncertainty:** Are probabilities calibrated well enough for alert decisions? What fraction of alerts is actionable at a fixed operator alert budget?

**Candidate measures to choose from:** PR-AUC; recall/precision at fixed alert volume; Brier score/calibration; false alerts per station/day; latency; data missingness; performance by station, daypart and horizon; confidence intervals where meaningful. Accuracy alone is not an adequate primary metric for rare stockouts.

## Agent capability questions

- **A1 — Tool use:** Does a bounded agent with read-only analytical tools produce more factually grounded answers than a direct-prompt/no-tool baseline or deterministic report?
- **A2 — Evidence:** Can an independent checker map every important numeric claim to a specific tool result, interval and station?
- **A3 — Failure recovery:** Does the agent handle stale data, a missing station, a broken feed, conflicting observations, or a tool timeout by surfacing uncertainty rather than fabricating a conclusion?
- **A4 — Efficiency:** Do extra planning/reflection steps improve grounded task success enough to justify higher latency and cost?
- **A5 — Safety:** Can adversarial content in untrusted station names/descriptions induce the model to overstep its tool authorization? **Do not include real secret keys in tests.**

**Candidate measures:** grounded fact accuracy; evidence ID validity; correct tool-call rate; unsupported causal assertions; appropriate abstention; step count; token cost; latency; test-case pass rate. Create a fixed, human-reviewed question set with answer criteria and deliberately difficult/negative cases.

## Optimization and simulator questions

- **O1 — Better than no action?** Under a clearly described *simulation*, how do policies affect predicted/simulated empty/full minutes?
- **O2 — Better than a heuristic?** Does a constrained solver beat a simple greedy rule when both receive the same information and budgets?
- **O3 — Robust to modeling error?** Do results survive perturbations to demand, forecast error, transfer time and hypothetical fleet capacity?

**Candidate measures:** simulated shortage-minutes, modeled unmet demand, number of moves, route cost, feasibility violations, solver runtime, robustness across common seeds. Never label these as measured Citi Bike outcomes.

## Experiments must be falsifiable

For each experiment Opus should create a record with:

```text
Question / hypothesis
Baseline(s) and why fair
Data provenance / date window / station population
Feature availability at decision time
Definitions and exclusions
Chronological train/validation/test and contamination checks
Metric, denominator, uncertainty / variance
Code/config/model/data versions and seeds
Actual measured result (or NOT RUN / INSUFFICIENT DATA)
Interesting failures and opposing evidence
A decision: ship, reject, defer, or rerun
```

## Hard evidence gates

- Never state "ML is better" without an explicit fair comparison to a named baseline on held-out time.
- Never use future station snapshots as features for prior predictions; future snapshots only for labels and post-hoc evaluation.
- Do not train and test on the same temporal regimes without reporting limitations.
- Do not trust single stochastic agent runs as robust evidence. Measure repeated runs and judge on fixed test cases when feasible.
- Do not rank agent approaches solely by subjective LLM-as-judge scores; include deterministic trace checks and human spot review.
- Do not declare a simulator realistic by assumption. Expose limitations and run sensitivity checks.
- Where the external world cannot be observed (missed riders, fleet actions), state what remains unidentified.

## Strong public portfolio outputs

- A 2–3-minute demo showing actual current data, evidence-grounded analysis, and visibly simulated comparisons.
- A concise technical case study showing the ambiguous user problem, data discovery, rejected assumptions, chosen tradeoffs, and true limitations.
- A reproducible experiment notebook/report with baseline comparison and at least two failure analyses.
- A runnable local setup, honest test output, and a clear disclaimer of independent analysis.
- Resume bullets only with measured, attributable outcomes. The title/branding must be reviewed against the data policy before public use.
