"""Step 3: one-day hourly inventory SIMULATOR for Jersey City + Hoboken stations. Every output is SIMULATED.

Offline. Reads data/fleet.duckdb (stations, snapshot, forecast_predictions). Assumptions live in config/sim.json.
Writes SIMULATED results back to the database:
  sim_runs     one row per (seed, policy): lost rentals, failed returns, truck activity
  sim_summary  paired differences (greedy - no_action) over seeds, with a 95% bootstrap interval
  sim_hourly   mean per local hour and policy;  sim_station  mean per station and policy
  sim_moves    every truck move;  sim_meta  config + scope as JSON

Model
  Start      bikes = snapshot num_bikes_available clipped to [0, capacity]; stations not installed are skipped
  Demand     per station and local hour, departures ~ Poisson(lambda_dep), arrivals ~ Poisson(lambda_arr), where
             lambda = mean step-2 LightGBM prediction for that station-hour over Oct 2026 non-holiday weekdays
             (PREDICTED completed trips, used here as SIMULATED demand). Arrivals are drawn independently of
             departures, so rider trips do not conserve bikes; only truck moves are tested for conservation.
  Order      within an hour, departure and arrival events are shuffled into a random order
  Outcomes   departure at an empty station = lost rental; arrival at a full station = failed return
  Policies   no_action; greedy = one truck that at the start of each operating hour moves bikes from the fullest
             reachable station to the emptiest station within the travel budget (config/sim.json)
  Pairing    demand for a seed is drawn once and replayed for both policies (common random numbers)

Usage:  python -m fleetdata.sim
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib

import duckdb
import numpy as np
import pandas as pd

from fleetdata.forecast import REGIONS

POLICIES = ("no_action", "greedy")
LABEL = "SIMULATED"
EARTH_KM = 6371.0088


@dataclasses.dataclass
class Network:
    short_name: list[str]
    capacity: np.ndarray        # int, docks
    inv0: np.ndarray            # int, starting bikes (clipped)
    dist_km: np.ndarray         # road km between stations (haversine x circuity)
    dep_rate: np.ndarray        # [24, n] expected departures per local hour
    arr_rate: np.ndarray        # [24, n] expected arrivals per local hour


@dataclasses.dataclass
class Demand:
    """Pre-drawn events for one seed: for each hour, station indices and is_departure flags in event order."""
    stations: list[np.ndarray]
    is_dep: list[np.ndarray]


def load_config(path: pathlib.Path = pathlib.Path("config/sim.json")) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def haversine_km(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    la, lo = np.radians(lat)[:, None], np.radians(lon)[:, None]
    a = np.sin((la - la.T) / 2) ** 2 + np.cos(la) * np.cos(la.T) * np.sin((lo - lo.T) / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


def clip_inventory(bikes, capacity) -> np.ndarray:
    return np.clip(np.nan_to_num(np.asarray(bikes, float)), 0, np.asarray(capacity)).astype(int)


# ---------------- inputs from the database ----------------
def load_network(con, cfg: dict) -> tuple[Network, dict]:
    st = con.execute(f"""SELECT st.short_name, st.capacity, st.lat, st.lon, sn.num_bikes_available,
                                sn.over_capacity, sn.is_stale, sn.is_renting, sn.is_returning, sn.fetched_at_utc
                         FROM stations st JOIN snapshot sn USING (short_name)
                         WHERE st.region_id IN {REGIONS} AND sn.is_installed AND st.capacity > 0
                         ORDER BY st.short_name""").df()
    sc = cfg["scenario"]
    rates = con.execute("""SELECT short_name, target, hour(hour_local) AS h, avg(pred_lightgbm) AS rate,
                                  count(DISTINCT CAST(hour_local AS DATE)) AS n_days
                           FROM forecast_predictions
                           WHERE hour_local >= CAST(? AS TIMESTAMP) AND hour_local < CAST(? AS TIMESTAMP)
                             AND isodow(hour_local) <= 5 AND NOT list_contains(CAST(? AS DATE[]), CAST(hour_local AS DATE))
                           GROUP BY ALL""", [sc["month_start_local"], sc["month_end_local"], sc["exclude_dates_local"]]).df()
    no_forecast = sorted(set(st.short_name) - set(rates.short_name))
    st = st[st.short_name.isin(rates.short_name)].reset_index(drop=True)   # stations with no forecast are skipped
    idx = {s: i for i, s in enumerate(st.short_name)}
    dep, arr = np.zeros((24, len(st))), np.zeros((24, len(st)))
    for r in rates[rates.short_name.isin(idx)].itertuples():
        (dep if r.target == "departures" else arr)[r.h, idx[r.short_name]] = r.rate
    cap = st.capacity.to_numpy(int)
    net = Network(list(st.short_name), cap, clip_inventory(st.num_bikes_available, cap),
                  haversine_km(st.lat.to_numpy(), st.lon.to_numpy()) * cfg["truck"]["road_circuity"], dep, arr)
    info = dict(stations=len(st), skipped_no_forecast=no_forecast,
                snapshot_fetched_at_utc=str(st.fetched_at_utc.iloc[0]),
                start_bikes_raw=int(st.num_bikes_available.sum()), start_bikes_clipped=int(net.inv0.sum()),
                docks=int(cap.sum()), over_capacity_clipped=int(st.over_capacity.sum()),
                stale_stations_used=int(st.is_stale.sum()), not_renting_or_returning=int((~st.is_renting | ~st.is_returning).sum()),
                scenario_days=int(rates.n_days.max()) if len(rates) else 0,
                expected_departures=float(dep.sum()), expected_arrivals=float(arr.sum()))
    return net, info


# ---------------- simulation core (pure; tested) ----------------
def draw_demand(net: Network, seed: int) -> Demand:
    """All randomness for a seed, drawn before and independently of any policy."""
    rng = np.random.default_rng(seed)
    stations, is_dep = [], []
    for h in range(24):
        d, a = rng.poisson(net.dep_rate[h]), rng.poisson(net.arr_rate[h])
        s = np.concatenate([np.repeat(np.arange(len(d)), d), np.repeat(np.arange(len(a)), a)])
        f = np.concatenate([np.ones(d.sum(), bool), np.zeros(a.sum(), bool)])
        order = rng.permutation(len(s))
        stations.append(s[order])
        is_dep.append(f[order])
    return Demand(stations, is_dep)


def greedy_move(inv: np.ndarray, cap: np.ndarray, dist: np.ndarray, pos: int | None, t: dict):
    """One truck move: (src, dst, qty, km) or None. Fullest reachable source first; for it, the emptiest
    destination such that km(pos->src) + km(src->dst) <= budget. Never makes a station exceed capacity."""
    fill = inv / cap
    surplus = inv - np.ceil(t["target_fill"] * cap).astype(int)       # bikes above target
    deficit = np.floor(t["target_fill"] * cap).astype(int) - inv       # space below target
    to_src = np.zeros(len(inv)) if pos is None else dist[pos]
    budget = t["travel_budget_km_per_hour"]
    for src in np.argsort(-fill, kind="stable"):
        if surplus[src] <= 0:
            break
        if to_src[src] > budget:
            continue
        ok = (deficit > 0) & (to_src[src] + dist[src] <= budget) & (fill[src] - fill >= t["min_fill_gap"])
        ok[src] = False
        if ok.any():
            cand = np.flatnonzero(ok)
            dst = cand[np.argmin(fill[cand])]          # ties -> lowest index (cand is sorted)
            qty = int(min(t["capacity_bikes"], surplus[src], deficit[dst]))
            return int(src), int(dst), qty, float(to_src[src] + dist[src, dst])
    return None


def simulate(net: Network, demand: Demand, policy: str, truck: dict) -> dict:
    """Run one SIMULATED day. Returns totals, per-hour and per-station counts, moves, and the inventory trace."""
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    n = len(net.capacity)
    inv = net.inv0.copy()
    lost, failed = np.zeros((24, n), int), np.zeros((24, n), int)
    trace, moves, pos = [inv.copy()], [], None
    lo, hi = truck["operating_hours_local"]
    for h in range(24):
        if policy == "greedy" and lo <= h < hi:
            for _ in range(truck["moves_per_hour"] * truck["count"]):
                m = greedy_move(inv, net.capacity, net.dist_km, pos, truck)
                if m is None:
                    break
                src, dst, qty, km = m
                inv[src] -= qty
                inv[dst] += qty
                pos = dst
                moves.append(dict(hour_local=h, src=net.short_name[src], dst=net.short_name[dst], bikes=qty, km=km))
        for s, dep in zip(demand.stations[h], demand.is_dep[h]):
            if dep:
                if inv[s] == 0:
                    lost[h, s] += 1
                else:
                    inv[s] -= 1
            elif inv[s] >= net.capacity[s]:
                failed[h, s] += 1
            else:
                inv[s] += 1
        trace.append(inv.copy())
    return dict(lost=lost, failed=failed, moves=moves, trace=np.array(trace),
                departures_drawn=int(sum(d.sum() for d in demand.is_dep)),
                arrivals_drawn=int(sum((~d).sum() for d in demand.is_dep)))


def paired_summary(runs: pd.DataFrame, n_boot: int = 10_000, seed: int = 7) -> pd.DataFrame:
    """Per metric: mean over seeds for each policy, and mean paired difference greedy - no_action with a
    95% percentile bootstrap interval (resampling seeds)."""
    w = runs.pivot(index="seed", columns="policy")
    rng = np.random.default_rng(seed)
    out = []
    for metric in ("lost_rentals", "failed_returns", "unserved_total"):
        d = (w[(metric, "greedy")] - w[(metric, "no_action")]).to_numpy(float)
        boots = d[rng.integers(0, len(d), size=(n_boot, len(d)))].mean(axis=1)
        out.append(dict(label=LABEL, metric=metric, n_seeds=len(d),
                        mean_no_action=float(w[(metric, "no_action")].mean()), mean_greedy=float(w[(metric, "greedy")].mean()),
                        mean_diff=float(d.mean()), ci95_lo=float(np.percentile(boots, 2.5)),
                        ci95_hi=float(np.percentile(boots, 97.5)), seeds_greedy_better=int((d < 0).sum()),
                        seeds_greedy_worse=int((d > 0).sum())))
    return pd.DataFrame(out)


# ---------------- run ----------------
def run(db_path: pathlib.Path, cfg: dict) -> dict:
    with duckdb.connect(str(db_path), read_only=True) as con:
        net, info = load_network(con, cfg)
    runs, hourly, station, moves = [], [], [], []
    for seed in cfg["seeds"]:
        demand = draw_demand(net, seed)
        for policy in POLICIES:
            r = simulate(net, demand, policy, cfg["truck"])
            L, Fr = int(r["lost"].sum()), int(r["failed"].sum())
            runs.append(dict(label=LABEL, seed=seed, policy=policy, lost_rentals=L, failed_returns=Fr, unserved_total=L + Fr,
                             departures_drawn=r["departures_drawn"], arrivals_drawn=r["arrivals_drawn"],
                             truck_moves=len(r["moves"]), bikes_moved=sum(m["bikes"] for m in r["moves"]),
                             truck_km=sum(m["km"] for m in r["moves"]), end_bikes=int(r["trace"][-1].sum()),
                             empty_station_hours=int((r["trace"][1:] == 0).sum()),
                             full_station_hours=int((r["trace"][1:] == net.capacity).sum())))
            hourly.append(pd.DataFrame({"seed": seed, "policy": policy, "hour_local": range(24),
                                        "lost_rentals": r["lost"].sum(1), "failed_returns": r["failed"].sum(1)}))
            station.append(pd.DataFrame({"seed": seed, "policy": policy, "short_name": net.short_name,
                                         "lost_rentals": r["lost"].sum(0), "failed_returns": r["failed"].sum(0)}))
            moves += [dict(m, seed=seed, policy=policy) for m in r["moves"]]
    runs = pd.DataFrame(runs)
    mean = lambda df, k: df.groupby(["policy", k], as_index=False)[["lost_rentals", "failed_returns"]].mean().assign(label=LABEL)
    st_mean = mean(pd.concat(station), "short_name").merge(
        pd.DataFrame({"short_name": net.short_name, "capacity": net.capacity, "start_bikes": net.inv0,
                      "expected_departures": net.dep_rate.sum(0), "expected_arrivals": net.arr_rate.sum(0)}), on="short_name")
    out = dict(runs=runs, summary=paired_summary(runs), hourly=mean(pd.concat(hourly), "hour_local"), station=st_mean,
               moves=pd.DataFrame(moves, columns=["seed", "policy", "hour_local", "src", "dst", "bikes", "km"]).assign(label=LABEL),
               meta=dict(label=LABEL, config=cfg, scope=info))
    with duckdb.connect(str(db_path)) as con:
        tables = dict(sim_runs=out["runs"], sim_summary=out["summary"], sim_hourly=out["hourly"],
                      sim_station=out["station"], sim_moves=out["moves"],
                      sim_meta=pd.DataFrame([{"label": LABEL, "meta_json": json.dumps(out["meta"], default=str)}]))
        for name, df in tables.items():
            con.register("tmp_df", df)
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
            con.unregister("tmp_df")
    return out


def print_report(out: dict) -> None:
    s = out["meta"]["scope"]
    print(f"\n=== SIMULATED one-day results ({LABEL}; not observed outcomes) ===")
    print(f"Scope: {s['stations']} installed JC/Hoboken stations; {s['docks']:,} docks; start bikes "
          f"{s['start_bikes_clipped']:,} after clipping ({s['start_bikes_raw']:,} raw; {s['over_capacity_clipped']} over-capacity "
          f"stations; {s['stale_stations_used']} stale reports used as-is). Snapshot fetched {s['snapshot_fetched_at_utc']} UTC")
    print(f"Scenario: typical Oct 2026 weekday from {s['scenario_days']} days of step-2 predictions; expected "
          f"departures {s['expected_departures']:.0f}, arrivals {s['expected_arrivals']:.0f} per day")
    r = out["runs"].groupby("policy")[["departures_drawn", "lost_rentals", "failed_returns", "truck_moves", "bikes_moved",
                                       "truck_km", "empty_station_hours", "full_station_hours"]].mean()
    print("\nMean per SIMULATED day over seeds:")
    print(r.to_string(float_format=lambda v: f"{v:.1f}"))
    print(f"\nPaired difference greedy - no_action over {out['summary'].n_seeds.iloc[0]} seeds (SIMULATED; 95% bootstrap CI):")
    for _, x in out["summary"].iterrows():
        print(f"  {x.metric:<15} no_action {x.mean_no_action:7.1f}  greedy {x.mean_greedy:7.1f}  diff {x.mean_diff:+7.1f} "
              f"[{x.ci95_lo:+.1f}, {x.ci95_hi:+.1f}]  greedy better in {x.seeds_greedy_better}/{x.n_seeds} seeds")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/fleet.duckdb", type=pathlib.Path)
    ap.add_argument("--config", default="config/sim.json", type=pathlib.Path)
    a = ap.parse_args()
    print_report(run(a.db, load_config(a.config)))


if __name__ == "__main__":
    main()
