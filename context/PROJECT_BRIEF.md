# Project brief: intent and problem (not an architecture)

## Working title
**Citi Bike: Agentic Fleet Forecasting & Optimization Engine**

Independent portfolio / applied-AI project using publicly published bike-share records. **Not** a contracted, endorsed, or operational Citi Bike application. Do not treat the title as permission for public use of protected trademarks.

## Why this project exists
The developer is a recent Computer Science and Data Science graduate targeting **Forward Deployed Engineer (FDE)** and applied-AI engineering roles. They want to demonstrate both:

1. **Production-minded engineering:** messy real-world data integration, API/backend competence, reliability, practical workflows, troubleshooting, usable tooling and explicit tradeoffs.
2. **AI capability exploration:** controlled evidence about whether modeling, reasoning, retrieval, tool use, planning, and optimization actually improve a well-defined operational task.

Do not turn the project into either a generic chatbot or a research-only benchmark divorced from the operator problem.

## The real-world problem
A docked bike-share service faces shifting supply of bikes and free docks across a city. Availability can vary with commuting patterns, weather, station constraints, and unobserved operator moves. A customer needs a bike to depart and an open dock to return. A useful analyst should understand what is actually happening, forecast short-term shortages, and examine hypothetical countermeasures without claiming access to real dispatch.

## Target users / reviewers
- **Primary hypothetical user:** an urban mobility operations analyst investigating recurring shortage risks and comparing possible rebalancing responses.
- **Secondary user:** a technical reviewer evaluating how evidence, data quality, baselines, guardrails and operational tradeoffs were handled.
- **Hiring reviewer:** an FDE interviewer assessing problem decomposition, integration, AI judgment, execution, and communication.

These are *hypothetical personas*, not claims of an existing customer.

## Initial problem boundary (may be revised only with explicit justification)
- One compact NYC station cluster, initially approximately **30–50 docked stations** selected using real coordinates.
- A **30-minute forecast horizon** for bike-empty and dock-full risk (or a documented alternative if data makes this unworkable).
- Actual **published historical trips** + actually collected **timestamped live status**; optional genuinely available context (e.g., weather) after baseline.
- Read-only, auditable AI investigation; **counterfactual simulation** of rebalancing, not dispatch.
- A small, convincing operator-oriented demo; avoid enterprise features unrelated to the core task.

## Expected questions to support
- Which stations in the region have few bikes/free docks **now**? How fresh is that information?
- Which stations may become empty or full in the next 30 minutes? What is the model's observed quality?
- Is a recurring morning risk associated with past departures, arrivals, capacity, location, and calendar patterns?
- What evidence *contradicts* the proposed explanation?
- What happens to forecast/analysis quality if we remove certain features, switch models, or restrict agent tools?
- Under stated hypothetical truck/capacity constraints, how do two rebalancing policies compare in the **same simulation**?

## Design freedom retained for Opus
Opus must research and decide architecture, technology choices, storage, deployment, schemas, model selection, evaluation implementation, code structure, task order and effort. The original Obsidian document includes examples and proposals; treat them as options, not commands.

## Non-goals
- No controlling Citi Bike infrastructure, authenticating into operator tools, moving bikes, or creating dispatch orders.
- No pretend internal ERP, personnel, driver, truck routing or maintenance records.
- No foundation-model training, giant agent platform, multi-tenant SaaS, or deep learning solely for resume keywords.
- No manufactured accuracy metrics, claimed customer adoption, or causal operational improvements.
- No polished UI in place of data reliability and evaluated model behavior.

## Success story to be earned, not claimed in advance
"We worked from limited public data, discovered and handled its real constraints, built a functioning pipeline and decision-support interface, compared simple and advanced methods fairly, and openly distinguished predictive value from hypotheses and simulated interventions."
