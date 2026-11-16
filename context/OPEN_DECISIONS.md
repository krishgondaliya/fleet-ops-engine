# Questions Opus must resolve, not assumptions this kit resolves

This exists to prevent premature technical decisions. Investigate with documentation and small validated samples; make reasonable low-cost assumptions where blocked; surface only truly consequential user approvals.

## Source feasibility / policy
- Can the currently advertised station feeds be fetched reliably from the documented discovery entry point? Which exact GBFS version and fields do they use now?
- Does the provider's policy permit the proposed polling, retention, derived outputs and deployment? What cadence is compatible with source TTL and stated restrictions?
- What may be called "Citi Bike" publicly? Do we need permission to use the mark as a product title/domain/logo? If uncertain, choose an unbranded public presentation and escalate.
- Which trip-file date range is recent, available and small enough to begin with? Do live station IDs join to historic files with sufficient coverage?

## User-value / experimental validity
- Is the best first measurable task predicting `empty/full at t+30` or `transition into empty/full by t+30`, given feasible collection cadence and event prevalence?
- How much recorded snapshot history is required before comparisons mean anything? What can be **honestly demonstrated immediately** while collection runs?
- What quantitative threshold, if any, makes an alert operationally worthwhile versus naive thresholds?
- Can completed-trip flow help without misleading estimates of unserved latent demand?
- What can an investigation agent answer from public data without inventing internal causes?

## Engineering architecture / execution
- What is the smallest resilient design and stack for a single developer that still demonstrates FDE engineering quality?
- Which components should be deterministic, ML-based, LLM-driven, or optimizer-based? What is the evidence for each choice?
- What single deployment target and operational footprint best balances cost, reliability and portfolio demoability?
- What tests can run offline using clearly marked fixtures, and what tests require permitted live endpoints?
- How will the agent's tool permissions be enforced rather than relying on instructions alone?
- How should state/progress survive fresh Claude Code sessions without inferring unfinished features from files alone?
- What does "production quality" mean at this scale? Avoid scaling features for imaginary traffic.

## Budget / permissions / operator decisions
- User has not supplied a cloud/GPU/API budget, paid model provider/key, preferred hosting service, or permissions for public launch. **Do not invent these.** Offer a low-cost/default local option and show costs/tradeoffs; ask before charges, account actions, or deployment.
- User has not authorized real Citi Bike data redistribution, any direct station management actions, or use of protected brand assets.
- User wants end-to-end development using Claude Code Opus, but initial instructions are to **plan and design first**, then implement with verification gates.

## When something is blocked
Classify it as: `requires-user-decision`, `requires-source-verification`, `requires-more-real-data`, `requires-cost-approval`, or `requires-technical-fix`. State the specific unblock action. Don't fabricate status or force a convenient substitute without labeling it.
