"""Step 4 evaluation: 10 questions whose correct numbers are computed directly with SQL on the base tables
(trips, snapshot, forecast_predictions, sim_runs, sim_summary), independently of the agent's tool code.

Modes
  live     ask the real agent (needs ANTHROPIC_API_KEY with API credit). Measures the agent.
  replay   a SCRIPTED client replays a fixed sequence of tool calls per question and writes the answer from the
           tool results. It measures whether the tools can supply the right numbers and whether the loop, the
           number check and the grader work. It does NOT measure the model.

Usage:  python -m fleetdata.agent_eval [--mode live|replay|both]   (writes reports/agent_eval.json)
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import types

import duckdb

from fleetdata import agent as A

# ---------------- questions + independent SQL ----------------
QUESTIONS = [
    dict(id="Q1", question="How many bikes and how many docks were available at the station named 'Grove St PATH' in the snapshot?",
         sql="SELECT num_bikes_available, num_docks_available FROM snapshot WHERE short_name = 'JC115'",
         replay=[[("station_lookup", {"query": "Grove St PATH"})]],
         answer=lambda r: f"Observed in the snapshot [#1]: {r[0]['rows'][0]['num_bikes_available']} bikes and "
                          f"{r[0]['rows'][0]['num_docks_available']} docks available at JC115."),
    dict(id="Q2", question="How many trips started at station JC115 on 2026-10-05 (local date)?",
         sql="SELECT count(*) FROM trips WHERE start_short_name = 'JC115' AND CAST(started_at_local AS DATE) = '2026-10-05'",
         replay=[[("hourly_flow", {"short_name": "JC115", "start_date": "2026-10-05", "end_date": "2026-10-05"})]],
         answer=lambda r: f"Observed: {r[0]['totals']['departures']} completed departures [#1]."),
    dict(id="Q3", question="How many completed trips ended at station HB107 between 2026-09-01 and 2026-09-07 inclusive?",
         sql="""SELECT count(*) FROM trips WHERE end_short_name = 'HB107'
                AND CAST(ended_at_local AS DATE) BETWEEN '2026-09-01' AND '2026-09-07'""",
         replay=[[("hourly_flow", {"short_name": "HB107", "start_date": "2026-09-01", "end_date": "2026-09-07"})]],
         answer=lambda r: f"Observed: {r[0]['totals']['arrivals']} arrivals [#1]."),
    dict(id="Q4", question="At station JC115 on 2026-10-07, which local hour had the most departures, and how many were there?",
         sql="""SELECT hour(started_at_local), count(*) FROM trips WHERE start_short_name = 'JC115'
                AND CAST(started_at_local AS DATE) = '2026-10-07' GROUP BY 1 ORDER BY 2 DESC LIMIT 1""",
         replay=[[("hourly_flow", {"short_name": "JC115", "start_date": "2026-10-07", "end_date": "2026-10-07", "granularity": "hour"})]],
         answer=lambda r: (lambda top: f"Observed: hour {int(top['hour_local'][11:13])} had {top['departures']} departures [#1].")(
             max(r[0]["rows"], key=lambda x: x["departures"]))),
    dict(id="Q5", question="On the October 2026 test month, what was the MAE of the LightGBM forecast for departures, and of the 4-week average baseline?",
         sql="""SELECT avg(abs(actual - pred_lightgbm)), avg(abs(actual - pred_avg_4w)) FROM forecast_predictions
                WHERE target = 'departures' AND in_eval_set""",
         replay=[[("model_metrics", {"view": "overall", "target": "departures"})]],
         answer=lambda r: (lambda m: f"Predicted-vs-observed, test month [#1]: LightGBM MAE {m['lightgbm']:.4f}, "
                                     f"4-week average MAE {m['avg_4w']:.4f}.")(
             {x["method"]: x["mae"] for x in r[0]["rows"] if x["split"] == "test"})),
    dict(id="Q6", question="For station JC115 on 2026-10-06, how many departures actually happened and what total did the LightGBM forecast predict?",
         sql="""SELECT (SELECT count(*) FROM trips WHERE start_short_name = 'JC115' AND CAST(started_at_local AS DATE) = '2026-10-06'),
                       (SELECT sum(pred_lightgbm) FROM forecast_predictions WHERE short_name = 'JC115' AND target = 'departures'
                        AND CAST(hour_local AS DATE) = '2026-10-06')""",
         replay=[[("forecast_vs_actual", {"short_name": "JC115", "start_date": "2026-10-06", "end_date": "2026-10-06"})]],
         answer=lambda r: f"Observed {r[0]['totals']['actual_total']} departures; LightGBM predicted "
                          f"{r[0]['totals']['pred_lightgbm_total']:.1f} [#1]."),
    dict(id="Q7", question="What was the LightGBM WAPE for arrivals at station HB107 in the October 2026 test month?",
         sql="""SELECT sum(abs(actual - pred_lightgbm)) / sum(actual) FROM forecast_predictions
                WHERE short_name = 'HB107' AND target = 'arrivals' AND in_eval_set""",
         replay=[[("model_metrics", {"view": "by_station", "short_name": "HB107", "target": "arrivals"})]],
         answer=lambda r: f"Predicted-vs-observed: WAPE {r[0]['rows'][0]['wape_lightgbm']:.3f} [#1]."),
    dict(id="Q8", question="In the simulation, what were the mean lost rentals per day under no action and under the greedy truck policy?",
         sql="""SELECT avg(lost_rentals) FILTER (policy = 'no_action'), avg(lost_rentals) FILTER (policy = 'greedy') FROM sim_runs""",
         replay=[[("simulation_results", {"view": "summary"})]],
         answer=lambda r: (lambda m: f"Simulated [#1]: no action {m['no_action']:.1f}, greedy {m['greedy']:.1f} lost rentals per day.")(
             {x["policy"]: x["lost_rentals"] for x in r[0]["mean_per_day_by_policy"]})),
    dict(id="Q9", question="In the simulation, what is the paired difference in failed returns (greedy minus no action), with its 95% confidence interval?",
         sql="""SELECT (SELECT avg(g.failed_returns - n.failed_returns) FROM sim_runs g JOIN sim_runs n USING (seed)
                        WHERE g.policy = 'greedy' AND n.policy = 'no_action'),
                       ci95_lo, ci95_hi FROM sim_summary WHERE metric = 'failed_returns'""",
         replay=[[("simulation_results", {"view": "summary"})]],
         answer=lambda r: (lambda s: f"Simulated [#1]: {s['mean_diff_greedy_minus_no_action']:.1f} failed returns per day, "
                                     f"95% CI {s['ci95_lo']:.1f} to {s['ci95_hi']:.1f}.")(
             next(x for x in r[0]["rows"] if x["metric"] == "failed_returns"))),
    dict(id="Q10", question="How many rentals were actually lost at station JC115 on 2026-10-05 because the station had no bikes?",
         sql=None, unsupported=True,
         replay=[[("hourly_flow", {"short_name": "JC115", "start_date": "2026-10-05", "end_date": "2026-10-05"})]],
         answer=lambda r: f"{A.UNSUPPORTED_PREFIX} the data has completed trips only and no station-status history, "
                          "so lost rentals on a real day cannot be observed [#1]."),
]


def expected_values(db_path: pathlib.Path) -> dict[str, list[float]]:
    with duckdb.connect(str(db_path), read_only=True) as con:
        return {q["id"]: [float(v) for v in con.execute(q["sql"]).fetchone()] for q in QUESTIONS if q["sql"]}


# ---------------- grading ----------------
def matches(expected: float, tok: str) -> bool:
    """The answer number (with d decimals) equals the expected value rounded to d decimals, and d is precise enough
    that rounding error is at most 5% of the value. Percentages (x100) are also accepted."""
    x = A._to_float(tok)
    if tok.lstrip()[0] not in "-−":          # an unsigned number may state a magnitude ("40 fewer")
        x, expected = abs(x), abs(expected)
    d = len(tok.split(".")[1]) if "." in tok else 0
    step = 10 ** -d
    for v in (expected, expected * 100):
        if abs(x - v) <= 0.5 * step + 1e-9 and (v == round(v) or step <= 0.05 * abs(v)):
            return True
    return False


def grade(q: dict, answer: str, expected: list[float] | None) -> tuple[bool, str]:
    if q.get("unsupported"):
        ok = answer.strip().startswith(A.UNSUPPORTED_PREFIX)
        return ok, "says unsupported" if ok else "did not decline"
    toks = A.numbers_in(answer)
    if len(toks) > 3 * len(expected) + 10:      # a dump of many numbers cannot earn credit by containing the right one
        return False, f"too many numbers in the answer ({len(toks)})"
    missing = [v for v in expected if not any(matches(v, t) for t in toks)]
    return not missing, "all expected numbers present" if not missing else f"missing {missing}"


# ---------------- scripted (replay) client ----------------
def _block(**kw):
    return types.SimpleNamespace(**kw)


class ScriptedClient:
    """SCRIPTED stand-in for anthropic.Anthropic. Each step is a list of (tool, args) to request, or an answer
    function that receives the parsed tool results so far. Responses mimic the SDK's shape."""

    def __init__(self, steps: list, answer=None, input_tokens: int = 1000, output_tokens: int = 100):
        self.steps, self.answer, self.calls = list(steps), answer, []
        self.usage = types.SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
        self.messages = types.SimpleNamespace(create=self._create)
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        if self.steps and kw.get("tool_choice", {}).get("type") != "none":
            step = self.steps.pop(0)
            uses = [_block(type="tool_use", id=f"tu_{len(self.calls)}_{i}", name=n, input=a) for i, (n, a) in enumerate(step)]
            return _block(content=uses, stop_reason="tool_use", usage=self.usage)
        results = []
        for m in kw["messages"]:
            if m["role"] == "user" and isinstance(m["content"], list):
                results += [json.loads(r["content"]) for r in m["content"] if not r.get("is_error")]
        text = self.answer(results) if callable(self.answer) else (self.answer or "")
        return _block(content=[_block(type="text", text=text)], stop_reason="end_turn", usage=self.usage)


# ---------------- run ----------------
@dataclasses.dataclass
class Row:
    id: str
    question: str
    expected: list | str
    mode: str
    correct: bool | None
    detail: str
    answer: str = ""
    tool_calls: list = dataclasses.field(default_factory=list)
    unverified_numbers: list = dataclasses.field(default_factory=list)
    tokens: int = 0


def run_mode(mode: str, db_path: pathlib.Path, exp: dict) -> list[Row]:
    rows, client, model = [], None, A.DEFAULT_MODEL
    if mode == "live":
        s = A.load_settings()
        model = s["model"]
        if not s["has_key"]:
            return [Row(q["id"], q["question"], exp.get(q["id"], "unsupported"), mode, None, "no ANTHROPIC_API_KEY") for q in QUESTIONS]
        client = A.make_client()
    failed = None
    for q in QUESTIONS:
        e = exp.get(q["id"], "unsupported")
        if failed:                                     # do not keep calling an API that already refused
            rows.append(Row(q["id"], q["question"], e, mode, None, f"not run after earlier API failure: {failed}"))
            continue
        c = ScriptedClient(q["replay"], q["answer"]) if mode == "replay" else client
        try:
            r = A.ask(q["question"], c, db_path, model)
        except Exception as err:                       # live API failure: record it, do not score
            failed = f"{type(err).__name__}: {str(err)[:200]}"
            rows.append(Row(q["id"], q["question"], e, mode, None, f"API call failed: {failed}"))
            continue
        ok, detail = grade(q, r.answer, exp.get(q["id"]))
        rows.append(Row(q["id"], q["question"], e, mode, ok, detail, r.answer,
                        [dict(n=t.n, name=t.name, args=t.args, error=t.error) for t in r.tool_calls],
                        r.unverified_numbers, r.input_tokens + r.output_tokens))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/fleet.duckdb", type=pathlib.Path)
    ap.add_argument("--mode", default="both", choices=["live", "replay", "both"])
    ap.add_argument("--out", default="reports/agent_eval.json", type=pathlib.Path)
    a = ap.parse_args()
    exp = expected_values(a.db)
    rows = []
    for mode in (["replay", "live"] if a.mode == "both" else [a.mode]):
        rows += run_mode(mode, a.db, exp)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps([dataclasses.asdict(r) for r in rows], indent=2, default=str), encoding="utf-8")
    for mode in dict.fromkeys(r.mode for r in rows):
        m = [r for r in rows if r.mode == mode]
        scored = [r for r in m if r.correct is not None]
        label = "SCRIPTED replay (tools + loop + grader; not the model)" if mode == "replay" else "LIVE agent"
        print(f"\n=== {label}: {sum(r.correct for r in scored)}/{len(scored)} correct"
              f"{'' if len(scored) == len(m) else f' ({len(m) - len(scored)} not scored)'} ===")
        for r in m:
            print(f"  {r.id:<4} {('PASS' if r.correct else 'FAIL') if r.correct is not None else 'N/A '}  "
                  f"expected {r.expected}  {r.detail}  unverified={r.unverified_numbers}")


if __name__ == "__main__":
    main()
