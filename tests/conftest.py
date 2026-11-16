"""Tests are offline: any attempt to open a network connection fails the test.

fixture_db: the REAL 10-station GBFS fixture (stations, snapshot) + SYNTHETIC trips, plus SYNTHETIC demand_grid,
forecast and metrics tables generated here; the simulator is run on it to produce sim_* tables (SIMULATED).
"""
import pathlib
import socket

import duckdb
import numpy as np
import pandas as pd
import pytest

from fleetdata import build as B
from fleetdata import sim as S

FIX = pathlib.Path(__file__).parent / "fixtures"


LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Block every outbound connection. Loopback is allowed: asyncio on Windows (used by streamlit's AppTest)
    builds its self-pipe from a 127.0.0.1 socket pair."""
    real_connect = socket.socket.connect

    def connect(self, address, *a, **kw):
        if isinstance(address, tuple) and address and address[0] in LOOPBACK:
            return real_connect(self, address, *a, **kw)
        raise RuntimeError(f"network access attempted in an offline test: {address!r}")

    def create_connection(address, *a, **kw):
        raise RuntimeError(f"network access attempted in an offline test: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    # The claude_code backend runs the Claude Code CLI in a subprocess, which the socket guard cannot see. Point it
    # at a path that does not exist so an unpatched call fails fast instead of reaching the network.
    monkeypatch.setenv("CLAUDE_CLI", str(pathlib.Path(__file__).parent / "no-such-claude-cli.exe"))


@pytest.fixture(scope="session")
def fixture_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("agent") / "test.duckdb"
    B.build(path, FIX / "gbfs", [FIX / "trips" / "SYNTHETIC_trips.csv"])
    rng = np.random.default_rng(0)
    hours = pd.date_range("2026-09-01", "2026-10-31 23:00", freq="h")
    stations = ["JC115", "JC014", "JC006"]
    grid = pd.concat([pd.DataFrame({"short_name": s, "hour_local": hours}) for s in stations], ignore_index=True)
    grid["hour_utc"] = grid.hour_local + pd.Timedelta(hours=4)
    grid["departures"], grid["arrivals"] = rng.poisson(2, len(grid)), rng.poisson(2, len(grid))
    oct_ = grid[grid.hour_local >= "2026-10-01"]
    preds = pd.concat([oct_.assign(target=t, actual=oct_[t], pred_lightgbm=2.0, pred_last_week=1.0, pred_avg_4w=3.0,
                                   in_eval_set=True) for t in ("departures", "arrivals")], ignore_index=True)
    metrics = pd.DataFrame([dict(target=t, split="test", method=m, n_rows=10, excluded_rows=0, mean_actual=2.0, mae=0.8, wape=0.6)
                            for t in ("departures", "arrivals") for m in ("lightgbm", "avg_4w")])
    with duckdb.connect(str(path)) as con:
        for name, df in {"demand_grid": grid[["short_name", "hour_utc", "hour_local", "departures", "arrivals"]],
                         "forecast_predictions": preds.drop(columns=["departures", "arrivals"]),
                         "forecast_metrics": metrics}.items():
            con.register("t", df)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM t")
            con.unregister("t")
        con.execute("CREATE TABLE forecast_bootstrap AS SELECT 'departures' AS target, 'lightgbm - avg_4w' AS comparison, "
                    "-0.03 AS mae_diff, -0.04 AS ci95_lo, -0.02 AS ci95_hi")
        con.execute("CREATE TABLE forecast_metrics_by_hour AS SELECT 'departures' AS target, 'lightgbm' AS method, "
                    "8 AS hour_local, 10 AS n_rows, 0.9 AS mae, 0.5 AS wape")
        con.execute("""CREATE TABLE forecast_metrics_by_station AS SELECT 'arrivals' AS target, 'JC115' AS short_name,
                       500 AS actual_total, 1.0 AS mae_lightgbm, 1.2 AS mae_last_week, 1.1 AS mae_avg_4w,
                       0.4 AS wape_lightgbm, 0.5 AS wape_last_week, 0.45 AS wape_avg_4w""")
    cfg = S.load_config(pathlib.Path(__file__).parents[1] / "config" / "sim.json")
    S.run(path, cfg)
    return path
