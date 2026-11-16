"""Step 2: day-ahead hourly demand forecast (departures and arrivals) for Jersey City + Hoboken stations.

Offline. Reads data/fleet.duckdb (built by fleetdata.build). Writes back to it:
  demand_grid, forecast_predictions, forecast_metrics, forecast_metrics_by_hour,
  forecast_metrics_by_station, forecast_bootstrap, forecast_runs
Also writes data/models/lgbm_<target>.txt + forecast_run.json, and reports/*.png.

Setup
  Scope    stations in regions 70 (JC) / 311 (Hoboken) that are installed in the current GBFS snapshot
  Grid     one row per station per UTC hour, zero-filled, from the station's first observed trip to the window end
  Targets  completed-trip departures and arrivals per hour. These are observed completed rides, NOT demand
  Issue    forecasts for local day D are issued at local midnight of D. Every feature uses only hour-buckets
           that ended at or before that midnight, and no lag is shorter than 24 hours
  Split    train < 2026-09-01 <= valid < 2026-10-01 <= test < 2026-11-01 (local). Tuning uses valid only;
           the test month is predicted once
Usage:  python -m fleetdata.forecast
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

import duckdb
import numpy as np
import pandas as pd

TZ = "America/New_York"
REGIONS = ("70", "311")
WINDOW_LOCAL = ("2025-11-01", "2026-11-01")          # [start, end) local midnights
SPLITS_LOCAL = {"train": ("2025-11-01", "2026-09-01"),
                "valid": ("2026-09-01", "2026-10-01"),
                "test": ("2026-10-01", "2026-11-01")}
TARGETS = ("departures", "arrivals")
AVG4W_LAGS = (168, 336, 504, 672)                    # same hour-of-week, prior four weeks
LAG_HOURS_USED = (24, 168) + AVG4W_LAGS
MIN_LAG_HOURS = 24
assert min(LAG_HOURS_USED) >= MIN_LAG_HOURS, "day-ahead rule: no lag shorter than 24 hours"
FEATURES = ["hour", "dow", "month", "is_holiday", "station", "lag24", "lag168", "avg4w", "capacity"]
METHODS = {"last_week": "lag168", "avg_4w": "avg4w"}  # baselines = these feature columns
MIN_STATION_VOLUME = 100                             # station ranking only for stations with >=100 test-month trips
SEED = 7
BASE_PARAMS = dict(objective="poisson", learning_rate=0.1, feature_fraction=0.9, bagging_fraction=0.8,
                   bagging_freq=1, seed=SEED, deterministic=True, force_row_wise=True, num_threads=4, verbose=-1)
CONFIGS = [dict(num_leaves=15, min_data_in_leaf=50), dict(num_leaves=31, min_data_in_leaf=200),
           dict(num_leaves=63, min_data_in_leaf=50), dict(num_leaves=127, min_data_in_leaf=100)]


def local_to_utc(day: str) -> pd.Timestamp:
    return pd.Timestamp(day).tz_localize(TZ).tz_convert("UTC").tz_localize(None)


def to_local(hour_utc: pd.Series) -> pd.Series:
    return hour_utc.dt.tz_localize("UTC").dt.tz_convert(TZ)


# ---------------- grid ----------------
def densify(flow: pd.DataFrame, scope: pd.DataFrame, lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DataFrame:
    """Dense station x UTC-hour grid over [first observed trip, hi). Hours without rides are 0.
    Stations in scope with no trips in the window get no rows."""
    flow = flow[(flow.hour_utc >= lo) & (flow.hour_utc < hi) & flow.short_name.isin(scope.short_name)]
    first = flow[(flow.departures + flow.arrivals) > 0].groupby("short_name").hour_utc.min()
    parts = [pd.DataFrame({"short_name": sn, "hour_utc": pd.date_range(start, hi - pd.Timedelta(hours=1), freq="h")})
             for sn, start in first.items()]
    grid = pd.concat(parts, ignore_index=True)
    grid = grid.merge(flow[["short_name", "hour_utc", "departures", "arrivals"]], on=["short_name", "hour_utc"], how="left")
    grid[list(TARGETS)] = grid[list(TARGETS)].fillna(0).astype("int64")
    grid = grid.merge(scope[["short_name", "capacity"]], on="short_name", how="left")
    return grid.sort_values(["short_name", "hour_utc"], ignore_index=True)


# ---------------- features (pure function of the grid; leakage-tested) ----------------
def make_features(grid: pd.DataFrame, target: str) -> pd.DataFrame:
    """Features for each grid row. Calendar fields depend only on the row's own timestamp.
    Lags read the target at hour_utc - k for k in LAG_HOURS_USED (all >= 24 h); missing history -> NaN."""
    s = grid.set_index(["short_name", "hour_utc"])[target]

    def lag(k: int) -> np.ndarray:
        idx = pd.MultiIndex.from_arrays([grid["short_name"], grid["hour_utc"] - pd.Timedelta(hours=k)])
        return s.reindex(idx).to_numpy(dtype="float64")

    local = to_local(grid["hour_utc"])
    from pandas.tseries.holiday import USFederalHolidayCalendar
    days = local.dt.tz_localize(None).dt.normalize()
    hol = USFederalHolidayCalendar().holidays(days.min(), days.max())
    out = pd.DataFrame(index=grid.index)
    out["hour"] = local.dt.hour.astype("int64")
    out["dow"] = local.dt.day_of_week.astype("int64")
    out["month"] = local.dt.month.astype("int64")
    out["is_holiday"] = days.isin(hol).astype("int64")
    out["station"] = pd.Categorical(grid["short_name"], categories=sorted(grid["short_name"].unique()))
    out["lag24"] = lag(24)
    out["lag168"] = lag(168)
    out["avg4w"] = np.vstack([lag(k) for k in AVG4W_LAGS]).mean(axis=0)   # NaN unless all four weeks exist
    out["capacity"] = grid["capacity"].astype("float64")
    return out[FEATURES]


def split_masks(grid: pd.DataFrame) -> dict[str, pd.Series]:
    return {name: (grid.hour_utc >= local_to_utc(a)) & (grid.hour_utc < local_to_utc(b))
            for name, (a, b) in SPLITS_LOCAL.items()}


# ---------------- metrics ----------------
def mae(y, p) -> float:
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))


def wape(y, p) -> float:
    y = np.asarray(y, float)
    return float(np.sum(np.abs(y - np.asarray(p, float))) / np.sum(y)) if np.sum(y) > 0 else float("nan")


def bootstrap_mae_diff(df: pd.DataFrame, a: str, b: str, n: int = 2000) -> tuple[float, float, float]:
    """Paired block bootstrap by local day: MAE(a) - MAE(b), with a 95% percentile interval."""
    g = df.assign(ea=(df.actual - df[a]).abs(), eb=(df.actual - df[b]).abs()).groupby("local_date")
    d = g[["ea", "eb"]].sum().assign(n=g.size())
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(d), size=(n, len(d)))
    ea, eb, cnt = d.ea.to_numpy()[idx].sum(1), d.eb.to_numpy()[idx].sum(1), d.n.to_numpy()[idx].sum(1)
    diffs = (ea - eb) / cnt
    point = (d.ea.sum() - d.eb.sum()) / d.n.sum()
    return float(point), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


# ---------------- training ----------------
def fit(X_tr, y_tr, X_va, y_va, params):
    import lightgbm as lgb
    dtr = lgb.Dataset(X_tr, y_tr, free_raw_data=False)
    dva = lgb.Dataset(X_va, y_va, reference=dtr, free_raw_data=False)
    return lgb.train(dict(BASE_PARAMS, **params), dtr, num_boost_round=1000, valid_sets=[dva],
                     callbacks=[lgb.early_stopping(50, verbose=False)])


def tune(X, y, m) -> tuple[dict, object, list[dict]]:
    """Select the config by validation MAE (early stopping also on validation). Test rows are never used."""
    trials, best = [], None
    for cfg in CONFIGS:
        bst = fit(X[m["train"]], y[m["train"]], X[m["valid"]], y[m["valid"]], cfg)
        v = mae(y[m["valid"]], bst.predict(X[m["valid"]], num_iteration=bst.best_iteration))
        trials.append(dict(cfg, best_iteration=bst.best_iteration, valid_mae=v))
        if best is None or v < best[2]:
            best = (cfg, bst, v)
    return best[0], best[1], trials


# ---------------- run ----------------
def run(db_path: pathlib.Path, models_dir: pathlib.Path, reports_dir: pathlib.Path) -> dict:
    lo, hi = local_to_utc(WINDOW_LOCAL[0]), local_to_utc(WINDOW_LOCAL[1])
    with duckdb.connect(str(db_path), read_only=True) as con:
        scope = con.execute(f"""SELECT st.short_name, st.capacity FROM stations st JOIN snapshot sn USING (short_name)
                                WHERE st.region_id IN {REGIONS} AND sn.is_installed""").df()
        flow = con.execute("SELECT short_name, hour_utc, departures, arrivals FROM hourly_flow").df()
    grid = densify(flow, scope, lo, hi)
    local = to_local(grid.hour_utc)
    grid["hour_local"] = local.dt.tz_localize(None)
    grid["local_date"] = grid["hour_local"].dt.normalize()
    m = split_masks(grid)
    info = {"scope_stations": len(scope), "grid_stations": grid.short_name.nunique(),
            "grid_rows": len(grid), "rows_by_split": {k: int(v.sum()) for k, v in m.items()},
            "stations_without_train_rows": sorted(set(grid.short_name) - set(grid.short_name[m["train"]]))}

    preds, metrics, by_hour, by_station, boots, run_meta = [], [], [], [], [], {}
    for target in TARGETS:
        X, y = make_features(grid, target), grid[target]
        cfg, bst, trials = tune(X, y, m)
        # Validation-only check of the month feature (month 9/10 never occur in training).
        no_month = fit(X.loc[m["train"]].drop(columns="month"), y[m["train"]],
                       X.loc[m["valid"]].drop(columns="month"), y[m["valid"]], cfg)
        v_no_month = mae(y[m["valid"]], no_month.predict(X.loc[m["valid"]].drop(columns="month"),
                                                         num_iteration=no_month.best_iteration))
        for split in ("valid", "test"):          # the test month is predicted exactly once, here
            sel = m[split]
            p = grid.loc[sel, ["short_name", "hour_utc", "hour_local", "local_date"]].copy()
            p["target"], p["actual"] = target, y[sel].to_numpy()
            p["pred_lightgbm"] = bst.predict(X[sel], num_iteration=bst.best_iteration)
            p["pred_last_week"], p["pred_avg_4w"] = X.loc[sel, "lag168"].to_numpy(), X.loc[sel, "avg4w"].to_numpy()
            p["in_eval_set"] = X.loc[sel, ["lag24", "lag168", "avg4w"]].notna().all(axis=1).to_numpy()
            e = p[p.in_eval_set]
            for meth in ("last_week", "avg_4w", "lightgbm"):
                metrics.append(dict(target=target, split=split, method=meth, n_rows=len(e),
                                    excluded_rows=int((~p.in_eval_set).sum()), mean_actual=float(e.actual.mean()),
                                    mae=mae(e.actual, e["pred_" + meth]), wape=wape(e.actual, e["pred_" + meth])))
            if split != "test":
                continue
            preds.append(p)
            for meth in ("last_week", "avg_4w", "lightgbm"):
                for h, g in e.groupby(e.hour_local.dt.hour):
                    by_hour.append(dict(target=target, method=meth, hour_local=int(h), n_rows=len(g),
                                        mae=mae(g.actual, g["pred_" + meth]), wape=wape(g.actual, g["pred_" + meth])))
            for sn, g in e.groupby("short_name"):
                by_station.append(dict(target=target, short_name=sn, actual_total=int(g.actual.sum()), n_rows=len(g),
                                       **{f"mae_{k}": mae(g.actual, g["pred_" + k]) for k in ("last_week", "avg_4w", "lightgbm")},
                                       **{f"wape_{k}": wape(g.actual, g["pred_" + k]) for k in ("last_week", "avg_4w", "lightgbm")}))
            for base in ("last_week", "avg_4w"):
                pt, a, b = bootstrap_mae_diff(e, "pred_lightgbm", "pred_" + base)
                boots.append(dict(target=target, comparison=f"lightgbm - {base}", mae_diff=pt, ci95_lo=a, ci95_hi=b,
                                  model_better=bool(b < 0), baseline_better=bool(a > 0)))
        models_dir.mkdir(parents=True, exist_ok=True)
        bst.save_model(str(models_dir / f"lgbm_{target}.txt"), num_iteration=bst.best_iteration)
        run_meta[target] = dict(selected=cfg, best_iteration=bst.best_iteration, trials=trials,
                                valid_mae_without_month=v_no_month,
                                feature_importance_gain=dict(zip(bst.feature_name(),
                                                                 map(float, bst.feature_importance("gain")))))

    meta = dict(created_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), features=FEATURES,
                lags_used_hours=LAG_HOURS_USED, base_params=BASE_PARAMS, splits_local=SPLITS_LOCAL,
                window_local=WINDOW_LOCAL, scope=dict(regions=REGIONS, installed_in_snapshot=True), **info,
                models=run_meta, note="Targets are completed trips (not demand). Day-ahead issue at local midnight.")
    (models_dir / "forecast_run.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

    out = {"metrics": pd.DataFrame(metrics), "by_hour": pd.DataFrame(by_hour), "by_station": pd.DataFrame(by_station),
           "bootstrap": pd.DataFrame(boots), "preds": pd.concat(preds, ignore_index=True), "meta": meta}
    with duckdb.connect(str(db_path)) as con:
        tables = {"demand_grid": grid[["short_name", "hour_utc", "hour_local", "departures", "arrivals"]],
                  "forecast_predictions": out["preds"].drop(columns="local_date"),
                  "forecast_metrics": out["metrics"], "forecast_metrics_by_hour": out["by_hour"],
                  "forecast_metrics_by_station": out["by_station"], "forecast_bootstrap": out["bootstrap"],
                  "forecast_runs": pd.DataFrame([{"created_utc": meta["created_utc"], "meta_json": json.dumps(meta, default=str)}])}
        for name, df in tables.items():
            con.register("tmp_df", df)
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
            con.unregister("tmp_df")
    charts(out, grid, reports_dir)
    return out


# ---------------- charts ----------------
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SERIES = {"lightgbm": ("#2a78d6", "-", "LightGBM"), "last_week": ("#eb6834", "--", "Same hour last week"),
          "avg_4w": ("#1baf7a", ":", "4-week same-hour avg")}


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def charts(out: dict, grid: pd.DataFrame, reports_dir: pathlib.Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    reports_dir.mkdir(parents=True, exist_ok=True)
    bh = out["by_hour"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), facecolor=SURFACE)
    for ax, target in zip(axes, TARGETS):
        _style(ax)
        for meth, (color, ls, label) in SERIES.items():
            d = bh[(bh.target == target) & (bh.method == meth)].sort_values("hour_local")
            ax.plot(d.hour_local, d.mae, color=color, linestyle=ls, linewidth=2, label=label)
            ax.annotate(label, (d.hour_local.iloc[-1], d.mae.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                        va="center", fontsize=8, color=INK2)
        ax.set_title(f"Hourly {target}: mean absolute error by local hour (test: Oct 2026)", fontsize=10, color=INK, loc="left")
        ax.set_xlabel("Hour of day (America/New_York)", fontsize=9, color=INK2)
        ax.set_ylabel("MAE (trips per station-hour)", fontsize=9, color=INK2)
        ax.set_xticks(range(0, 24, 3))
        ax.set_xlim(0, 27.5)
        ax.set_ylim(bottom=0)
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.text(0.01, 0.01, "Completed trips (not demand); JC/Hoboken stations; arrivals exclude trips that started in NYC.",
             fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(reports_dir / "error_by_hour.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)

    p = out["preds"]
    busiest = (p[p.target == "departures"].groupby("short_name").actual.sum().idxmax())
    week = (pd.Timestamp("2026-10-05"), pd.Timestamp("2026-10-12"))   # Mon..Sun, local
    fig, axes = plt.subplots(2, 1, figsize=(12, 6.4), sharex=True, facecolor=SURFACE)
    for ax, target in zip(axes, TARGETS):
        _style(ax)
        d = p[(p.target == target) & (p.short_name == busiest) & (p.hour_local >= week[0]) & (p.hour_local < week[1])]
        d = d.sort_values("hour_local")
        ax.plot(d.hour_local, d.actual, color=INK2, linewidth=1.6, label="Actual (observed completed trips)")
        ax.plot(d.hour_local, d.pred_lightgbm, color=SERIES["lightgbm"][0], linewidth=2, label="LightGBM day-ahead forecast")
        ax.set_title(f"Station {busiest}: hourly {target}, actual vs forecast, 5–11 Oct 2026 (local)",
                     fontsize=10, color=INK, loc="left")
        ax.set_ylabel(f"{target.capitalize()} per hour", fontsize=9, color=INK2)
        ax.set_ylim(bottom=0)
    axes[0].legend(frameon=False, fontsize=8, loc="upper left", ncol=2)
    axes[1].set_xlabel("Local time (America/New_York)", fontsize=9, color=INK2)
    fig.text(0.01, 0.01, "Forecast = predicted, issued at local midnight using data through the prior day. Actual = observed.",
             fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(reports_dir / "busiest_station_week.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)


# ---------------- report ----------------
def print_report(out: dict) -> None:
    pd.set_option("display.width", 160)
    mt, meta = out["metrics"], out["meta"]
    print(f"\nScope: {meta['grid_stations']} stations with trips (of {meta['scope_stations']} installed JC/Hoboken); "
          f"grid rows {meta['grid_rows']:,}; split rows {meta['rows_by_split']}")
    if meta["stations_without_train_rows"]:
        print("Stations with no training rows (first trip after Aug 2026):", meta["stations_without_train_rows"])
    for t in TARGETS:
        r = meta["models"][t]
        print(f"[{t}] selected {r['selected']} best_iteration={r['best_iteration']}; valid MAE by config: "
              + ", ".join(f"{x['num_leaves']}/{x['min_data_in_leaf']}={x['valid_mae']:.4f}" for x in r["trials"])
              + f"; without 'month' (validation only): {r['valid_mae_without_month']:.4f}")
    print("\n=== Metrics (MAE in trips per station-hour; WAPE = sum|error| / sum actual) ===")
    tbl = mt.pivot_table(index=["split", "target", "method"], values=["n_rows", "mean_actual", "mae", "wape"], aggfunc="first")
    tbl = tbl.reindex(columns=["n_rows", "mean_actual", "mae", "wape"])
    print(tbl.sort_index(level=[0, 1], ascending=[False, True]).to_string(float_format=lambda v: f"{v:.4f}"))
    print("\n=== Test month: LightGBM minus baseline, MAE difference (95% CI, day-block bootstrap) ===")
    for _, b in out["bootstrap"].iterrows():
        verdict = "model better" if b.model_better else ("BASELINE BETTER" if b.baseline_better else "no clear difference")
        print(f"  {b.target:<10} {b.comparison:<22} {b.mae_diff:+.4f}  [{b.ci95_lo:+.4f}, {b.ci95_hi:+.4f}]  -> {verdict}")
    bh = out["by_hour"].pivot_table(index="hour_local", columns=["target", "method"], values="mae")
    print("\n=== Test month MAE by local hour ===")
    print(bh.to_string(float_format=lambda v: f"{v:.3f}"))
    bs = out["by_station"]
    for t in TARGETS:
        d = bs[(bs.target == t) & (bs.actual_total >= MIN_STATION_VOLUME)].sort_values("wape_lightgbm")
        cols = ["short_name", "actual_total", "wape_lightgbm", "wape_last_week", "wape_avg_4w", "mae_lightgbm"]
        print(f"\n=== {t}: 10 best stations by LightGBM WAPE (stations with >= {MIN_STATION_VOLUME} test-month trips: "
              f"{len(d)} of {int((bs.target == t).sum())}) ===")
        print(d[cols].head(10).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
        print(f"=== {t}: 10 worst ===")
        print(d[cols].tail(10).iloc[::-1].to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/fleet.duckdb", type=pathlib.Path)
    ap.add_argument("--models-dir", default="data/models", type=pathlib.Path)
    ap.add_argument("--reports-dir", default="reports", type=pathlib.Path)
    a = ap.parse_args()
    print_report(run(a.db, a.models_dir, a.reports_dir))


if __name__ == "__main__":
    main()
