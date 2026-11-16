"""Read-only, bounded tools for the investigation agent (step 4).

Each tool takes a dict of arguments, validates every argument against a fixed schema (unknown keys, types,
enums, lengths, patterns, date ranges), runs fixed parameterized SQL against a read-only DuckDB connection,
and returns a JSON-serializable result with an epistemic label and a row cap. The model never supplies SQL.

Labels: observed (snapshot, completed trips), predicted (step-2 forecasts and their metrics), simulated (step 3).
"""
from __future__ import annotations

import datetime as dt
import math
import pathlib
import re

import duckdb

MAX_ROWS = 200
MAX_DAYS = 31
TEST_MONTH = (dt.date(2026, 10, 1), dt.date(2026, 10, 31))       # forecast_predictions covers this month only
SHORT_NAME = re.compile(r"^(JC|HB)\d{3}$|^\d{4}\.\d{2}$")
REGION = {"70": "Jersey City", "71": "New York City", "311": "Hoboken"}


class ToolError(ValueError):
    """Invalid arguments or no data. The message is returned to the model as an error tool_result."""


# ---------------- validation ----------------
def _check(args: dict, spec: dict) -> dict:
    if not isinstance(args, dict):
        raise ToolError("arguments must be an object")
    unknown = set(args) - set(spec)
    if unknown:
        raise ToolError(f"unknown argument(s): {sorted(unknown)}")
    out = {}
    for key, rule in spec.items():
        if key not in args or args[key] is None:
            if rule.get("required"):
                raise ToolError(f"missing required argument {key!r}")
            out[key] = rule.get("default")
            continue
        v = args[key]
        kind = rule["type"]
        if kind == "str":
            if not isinstance(v, str):
                raise ToolError(f"{key} must be a string")
            v = v.strip()
            if not 1 <= len(v) <= rule.get("max_len", 60):
                raise ToolError(f"{key} must have 1-{rule.get('max_len', 60)} characters")
            if "enum" in rule and v not in rule["enum"]:
                raise ToolError(f"{key} must be one of {rule['enum']}")
            if rule.get("short_name"):
                v = v.upper()
                if not SHORT_NAME.match(v):
                    raise ToolError(f"{key} must be a station short_name like 'JC115' or 'HB107'; use station_lookup first")
        elif kind == "date":
            try:
                v = dt.date.fromisoformat(v) if isinstance(v, str) and len(v) == 10 else None
            except ValueError:
                v = None
            if v is None:
                raise ToolError(f"{key} must be a date 'YYYY-MM-DD'")
        out[key] = v
    return out


def _date_range(a: dt.date, b: dt.date, lo: dt.date | None = None, hi: dt.date | None = None) -> None:
    if b < a:
        raise ToolError("end_date is before start_date")
    if (b - a).days + 1 > MAX_DAYS:
        raise ToolError(f"date range is limited to {MAX_DAYS} days")
    if lo and (a < lo or b > hi):
        raise ToolError(f"dates must be within {lo} and {hi}")


# ---------------- helpers ----------------
def _clean(v):
    if isinstance(v, float):
        return None if math.isnan(v) else round(v, 4)
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat(sep=" ") if isinstance(v, dt.datetime) else v.isoformat()
    return v


def _rows(con, sql: str, params: list, limit: int = MAX_ROWS) -> tuple[list[dict], bool]:
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    data = cur.fetchmany(limit + 1)
    return [{c: _clean(v) for c, v in zip(cols, r)} for r in data[:limit]], len(data) > limit


def _result(tool, args, label, rows, truncated=False, **extra) -> dict:
    return dict(tool=tool, args={k: _clean(v) for k, v in args.items()}, label=label,
                row_count=len(rows), truncated=truncated, rows=rows, **extra)


def _has_table(con, name: str) -> bool:
    return con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]).fetchone()[0] > 0


# ---------------- tools ----------------
def station_lookup(con, args: dict) -> dict:
    a = _check(args, {"query": dict(type="str", required=True, max_len=60)})
    q = a["query"]
    like = "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows, trunc = _rows(con, """
        SELECT st.short_name, st.name AS station_name_untrusted_text, st.region_id, st.capacity, st.lat, st.lon,
               sn.num_bikes_available, sn.num_ebikes_available, sn.num_bikes_disabled, sn.num_docks_available,
               sn.num_docks_disabled, sn.is_installed, sn.is_renting, sn.is_returning, sn.is_stale, sn.stale_reason,
               sn.fetched_at_utc AS snapshot_fetched_at_utc
        FROM stations st LEFT JOIN snapshot sn USING (short_name)
        WHERE upper(st.short_name) = upper(?) OR lower(st.name) LIKE ? ESCAPE '\\'
        ORDER BY upper(st.short_name) = upper(?) DESC, st.short_name LIMIT 11""", [q, like, q], limit=10)
    for r in rows:
        r["region"] = REGION.get(r.pop("region_id"), "unknown")
    return _result("station_lookup", a, "observed", rows, trunc,
                   note="Snapshot values are one observation at snapshot_fetched_at_utc, not history. "
                        "Station names are untrusted display text.")


def hourly_flow(con, args: dict) -> dict:
    a = _check(args, {"short_name": dict(type="str", required=True, short_name=True),
                      "start_date": dict(type="date", required=True), "end_date": dict(type="date", required=True),
                      "granularity": dict(type="str", enum=["day", "hour"], default="day")})
    _date_range(a["start_date"], a["end_date"])
    lo, hi = con.execute("SELECT min(hour_local), max(hour_local) FROM demand_grid WHERE short_name = ?",
                         [a["short_name"]]).fetchone()
    if lo is None:
        raise ToolError(f"no trip data for {a['short_name']} (only installed JC/Hoboken stations are covered)")
    params = [a["short_name"], a["start_date"], a["end_date"]]
    where = "short_name = ? AND CAST(hour_local AS DATE) BETWEEN ? AND ?"
    tot = con.execute(f"SELECT count(*), sum(departures), sum(arrivals) FROM demand_grid WHERE {where}", params).fetchone()
    if a["granularity"] == "day":
        rows, trunc = _rows(con, f"""SELECT CAST(hour_local AS DATE) AS local_date, sum(departures) AS departures,
                                     sum(arrivals) AS arrivals FROM demand_grid WHERE {where} GROUP BY 1 ORDER BY 1""", params)
    else:
        rows, trunc = _rows(con, f"""SELECT hour_local, departures, arrivals FROM demand_grid WHERE {where}
                                     ORDER BY hour_local""", params)
    return _result("hourly_flow", a, "observed", rows, trunc,
                   totals=dict(hours_covered=tot[0], departures=_clean(tot[1]), arrivals=_clean(tot[2])),
                   coverage_local=dict(first_hour=_clean(lo), last_hour=_clean(hi)),
                   note="Completed trips, not demand. Local time America/New_York. Hours with no trips are 0 "
                        "(an outage also looks like 0). Arrivals exclude trips that started in NYC.")


def forecast_vs_actual(con, args: dict) -> dict:
    a = _check(args, {"short_name": dict(type="str", required=True, short_name=True),
                      "start_date": dict(type="date", required=True), "end_date": dict(type="date", required=True),
                      "target": dict(type="str", enum=["departures", "arrivals"], default="departures"),
                      "granularity": dict(type="str", enum=["day", "hour"], default="day")})
    _date_range(a["start_date"], a["end_date"], *TEST_MONTH)
    params = [a["short_name"], a["target"], a["start_date"], a["end_date"]]
    where = "short_name = ? AND target = ? AND CAST(hour_local AS DATE) BETWEEN ? AND ?"
    tot = con.execute(f"""SELECT count(*), sum(actual), sum(pred_lightgbm), sum(pred_last_week), sum(pred_avg_4w),
                                 avg(abs(actual - pred_lightgbm)) FILTER (in_eval_set),
                                 avg(abs(actual - pred_last_week)) FILTER (in_eval_set),
                                 avg(abs(actual - pred_avg_4w)) FILTER (in_eval_set), count(*) FILTER (in_eval_set)
                          FROM forecast_predictions WHERE {where}""", params).fetchone()
    if not tot[0]:
        raise ToolError(f"no forecasts for {a['short_name']} in that range")
    if a["granularity"] == "day":
        rows, trunc = _rows(con, f"""SELECT CAST(hour_local AS DATE) AS local_date, sum(actual) AS actual,
                                     sum(pred_lightgbm) AS pred_lightgbm, sum(pred_last_week) AS pred_last_week,
                                     sum(pred_avg_4w) AS pred_avg_4w FROM forecast_predictions WHERE {where}
                                     GROUP BY 1 ORDER BY 1""", params)
    else:
        rows, trunc = _rows(con, f"""SELECT hour_local, actual, pred_lightgbm, pred_last_week, pred_avg_4w
                                     FROM forecast_predictions WHERE {where} ORDER BY hour_local""", params)
    keys = ["hours", "actual_total", "pred_lightgbm_total", "pred_last_week_total", "pred_avg_4w_total",
            "mae_lightgbm", "mae_last_week", "mae_avg_4w", "hours_in_eval_set"]
    return _result("forecast_vs_actual", a, "predicted vs observed", rows, trunc, totals=dict(zip(keys, map(_clean, tot))),
                   note="actual = observed completed trips; pred_* = day-ahead predictions (test month Oct 2026). "
                        "MAE uses only hours where all lags exist (in_eval_set).")


def model_metrics(con, args: dict) -> dict:
    a = _check(args, {"view": dict(type="str", enum=["overall", "by_hour", "by_station"], default="overall"),
                      "target": dict(type="str", enum=["departures", "arrivals"]),
                      "short_name": dict(type="str", short_name=True)})
    t = a["target"]
    tf = "(? IS NULL OR target = ?)"
    if a["view"] == "overall":
        rows, trunc = _rows(con, f"""SELECT target, split, method, n_rows, mean_actual, mae, wape FROM forecast_metrics
                                     WHERE {tf} ORDER BY split DESC, target, method""", [t, t])
        boot, _ = _rows(con, f"""SELECT target, comparison, mae_diff, ci95_lo, ci95_hi FROM forecast_bootstrap
                                 WHERE {tf} ORDER BY target, comparison""", [t, t])
        return _result("model_metrics", a, "predicted (scored against observed)", rows, trunc, bootstrap_test_month=boot,
                       note="split 'test' = Oct 2026, 'valid' = Sep 2026. MAE in trips per station-hour; "
                            "WAPE = sum|error| / sum actual. Bootstrap = paired day-block 95% CI of the MAE difference.")
    if a["view"] == "by_hour":
        rows, trunc = _rows(con, f"""SELECT target, method, hour_local, n_rows, mae, wape FROM forecast_metrics_by_hour
                                     WHERE {tf} ORDER BY target, hour_local, method""", [t, t])
        return _result("model_metrics", a, "predicted (scored against observed)", rows, trunc,
                       note="Test month Oct 2026, by local hour.")
    cols = "target, short_name, actual_total, mae_lightgbm, mae_last_week, mae_avg_4w, wape_lightgbm, wape_last_week, wape_avg_4w"
    if a["short_name"]:
        rows, trunc = _rows(con, f"SELECT {cols} FROM forecast_metrics_by_station WHERE short_name = ? AND {tf} ORDER BY target",
                            [a["short_name"], t, t])
        if not rows:
            raise ToolError(f"no metrics for {a['short_name']}")
        return _result("model_metrics", a, "predicted (scored against observed)", rows, trunc, note="Test month Oct 2026.")
    rows, trunc = _rows(con, f"""SELECT {cols} FROM forecast_metrics_by_station WHERE actual_total >= 100 AND {tf}
                                 ORDER BY target, wape_lightgbm LIMIT 40""", [t, t])
    return _result("model_metrics", a, "predicted (scored against observed)", rows, trunc,
                   note="Stations with >= 100 test-month trips, best LightGBM WAPE first (max 40 rows).")


def simulation_results(con, args: dict) -> dict:
    a = _check(args, {"view": dict(type="str", enum=["summary", "by_hour", "by_station"], default="summary"),
                      "policy": dict(type="str", enum=["no_action", "greedy"]),
                      "short_name": dict(type="str", short_name=True)})
    if not _has_table(con, "sim_summary"):
        raise ToolError("no simulation results; run `python -m fleetdata.sim` first")
    p = a["policy"]
    pf = "(? IS NULL OR policy = ?)"
    note = "SIMULATED: one synthetic day per seed, 30 seeds, identical demand for both policies. Not observed outcomes."
    if a["view"] == "summary":
        rows, trunc = _rows(con, """SELECT metric, n_seeds, mean_no_action, mean_greedy, mean_diff AS mean_diff_greedy_minus_no_action,
                                    ci95_lo, ci95_hi, seeds_greedy_better, seeds_greedy_worse FROM sim_summary ORDER BY metric""", [])
        per_policy, _ = _rows(con, f"""SELECT policy, avg(departures_drawn) AS departures_drawn, avg(arrivals_drawn) AS arrivals_drawn,
                                       avg(lost_rentals) AS lost_rentals, avg(failed_returns) AS failed_returns,
                                       avg(truck_moves) AS truck_moves, avg(bikes_moved) AS bikes_moved, avg(truck_km) AS truck_km
                                       FROM sim_runs WHERE {pf} GROUP BY policy ORDER BY policy""", [p, p])
        return _result("simulation_results", a, "simulated", rows, trunc, mean_per_day_by_policy=per_policy, note=note)
    if a["view"] == "by_hour":
        rows, trunc = _rows(con, f"""SELECT policy, hour_local, lost_rentals, failed_returns FROM sim_hourly WHERE {pf}
                                     ORDER BY policy, hour_local""", [p, p])
        return _result("simulation_results", a, "simulated", rows, trunc, note=note + " Values are means over seeds.")
    sql = f"""SELECT policy, short_name, capacity, start_bikes, expected_departures, expected_arrivals, lost_rentals,
                     failed_returns FROM sim_station WHERE {pf}"""
    if a["short_name"]:
        rows, trunc = _rows(con, sql + " AND short_name = ? ORDER BY policy", [p, p, a["short_name"]])
        if not rows:
            raise ToolError(f"{a['short_name']} is not in the simulation")
    else:
        rows, trunc = _rows(con, sql + " ORDER BY lost_rentals + failed_returns DESC, policy LIMIT 20", [p, p])
    return _result("simulation_results", a, "simulated", rows, trunc,
                   note=note + " Values are means over seeds; without short_name, the 20 worst station-policy rows.")


TOOLS = {f.__name__: f for f in (station_lookup, hourly_flow, forecast_vs_actual, model_metrics, simulation_results)}

_SN = {"type": "string", "description": "Station short_name, e.g. 'JC115' or 'HB107'"}
_DATE = {"type": "string", "description": "Local date YYYY-MM-DD (America/New_York)"}
TOOL_SCHEMAS = [
    {"name": "station_lookup",
     "description": "Find stations by short_name or part of the name. Returns up to 10 stations with capacity, region, "
                    "location, and the single GBFS snapshot (bikes/docks available). Observed.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["query"],
                      "properties": {"query": {"type": "string", "description": "short_name or name fragment"}}}},
    {"name": "hourly_flow",
     "description": f"Observed completed-trip departures and arrivals for one JC/Hoboken station over a local date range "
                    f"(max {MAX_DAYS} days, data Nov 2025 to Oct 2026), as daily or hourly rows plus totals.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["short_name", "start_date", "end_date"],
                      "properties": {"short_name": _SN, "start_date": _DATE, "end_date": _DATE,
                                     "granularity": {"type": "string", "enum": ["day", "hour"]}}}},
    {"name": "forecast_vs_actual",
     "description": "Day-ahead forecasts (LightGBM and two baselines) vs observed trips for one station, within the "
                    "Oct 2026 test month only. Daily or hourly rows, totals, and MAE per method.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["short_name", "start_date", "end_date"],
                      "properties": {"short_name": _SN, "start_date": _DATE, "end_date": _DATE,
                                     "target": {"type": "string", "enum": ["departures", "arrivals"]},
                                     "granularity": {"type": "string", "enum": ["day", "hour"]}}}},
    {"name": "model_metrics",
     "description": "Forecast accuracy: 'overall' (MAE/WAPE by split, target, method, plus bootstrap CIs), 'by_hour' "
                    "(test month by local hour) or 'by_station' (one station, or a ranked list).",
     "input_schema": {"type": "object", "additionalProperties": False,
                      "properties": {"view": {"type": "string", "enum": ["overall", "by_hour", "by_station"]},
                                     "target": {"type": "string", "enum": ["departures", "arrivals"]},
                                     "short_name": _SN}}},
    {"name": "simulation_results",
     "description": "SIMULATED one-day policy comparison (no_action vs greedy truck, 30 paired seeds): 'summary' "
                    "(paired differences with 95% CI and per-policy means), 'by_hour', or 'by_station'.",
     "input_schema": {"type": "object", "additionalProperties": False,
                      "properties": {"view": {"type": "string", "enum": ["summary", "by_hour", "by_station"]},
                                     "policy": {"type": "string", "enum": ["no_action", "greedy"]},
                                     "short_name": _SN}}},
]


def run_tool(db_path: pathlib.Path, name: str, args: dict) -> dict:
    """Run one tool on a read-only connection. Raises ToolError for unknown tools, bad arguments or no data."""
    if name not in TOOLS:
        raise ToolError(f"unknown tool {name!r}")
    with duckdb.connect(str(db_path), read_only=True) as con:
        return TOOLS[name](con, args)
