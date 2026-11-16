"""Offline tests for the day-ahead forecast (fleetdata.forecast). All inputs are SYNTHETIC, generated in-test."""
import numpy as np
import pandas as pd
import pytest

from fleetdata import forecast as F


def synthetic_grid(days=45, seed=0):
    """SYNTHETIC dense grid: two stations, random Poisson counts, starting 2026-02-20 local (crosses the March DST change)."""
    rng = np.random.default_rng(seed)
    hours = pd.date_range(F.local_to_utc("2026-02-20"), periods=days * 24, freq="h")
    g = pd.concat([pd.DataFrame({"short_name": sn, "hour_utc": hours}) for sn in ("S1", "S2")], ignore_index=True)
    g["departures"] = rng.poisson(3, len(g))
    g["arrivals"] = rng.poisson(3, len(g))
    g["capacity"] = 20
    return g


def same(a: pd.Series, b: pd.Series) -> bool:
    return all((x == y) or (pd.isna(x) and pd.isna(y)) for x, y in zip(a.to_numpy(), b.to_numpy()))


# ---- leakage ----
def test_declared_lags_are_at_least_24_hours():
    assert min(F.LAG_HOURS_USED) >= 24


@pytest.mark.parametrize("target", F.TARGETS)
def test_no_feature_uses_data_less_than_24h_before_t(target):
    """For hour t, perturb every hour bucket that starts later than t-24h (i.e. data from within the last 24 hours,
    the hour t itself, and the future). Features at t must not change. The bucket starting exactly at t-24h is the
    lag-24 source and is allowed (it ends at t-23h, at or before local midnight of t's day)."""
    g = synthetic_grid()
    base = F.make_features(g, target)
    rng = np.random.default_rng(1)
    for i in rng.choice(np.flatnonzero(g.short_name == "S1"), size=25, replace=False):
        t = g.hour_utc[i]
        g2 = g.copy()
        recent = g2.hour_utc > t - pd.Timedelta(hours=24)
        g2.loc[recent, list(F.TARGETS)] = rng.integers(1000, 2000, size=(recent.sum(), 2))
        assert same(F.make_features(g2, target).loc[i], base.loc[i]), f"feature at {t} changed"


@pytest.mark.parametrize("target", F.TARGETS)
def test_day_ahead_features_ignore_the_forecast_day(target):
    """Forecasts for local day D are issued at local midnight of D: data from D onward must not affect any row of D."""
    g = synthetic_grid()
    base = F.make_features(g, target)
    local_day = F.to_local(g.hour_utc).dt.tz_localize(None).dt.normalize()
    for day in ("2026-03-08", "2026-03-20", "2026-04-01"):     # includes the spring-forward day
        D = pd.Timestamp(day)
        g2 = g.copy()
        g2.loc[local_day >= D, list(F.TARGETS)] = 999
        rows = local_day == D
        pd.testing.assert_frame_equal(F.make_features(g2, target)[rows], base[rows])


def test_lag_values_are_real_hours_back_and_nan_before_history():
    g = synthetic_grid()
    X = F.make_features(g, "departures")
    s1 = g[g.short_name == "S1"].reset_index()
    i = 24 * 30   # 30 days in: crosses the 2026-03-08 DST change, lags still count real (UTC) hours
    assert X.loc[s1.loc[i, "index"], "lag24"] == s1.loc[i - 24, "departures"]
    assert X.loc[s1.loc[i, "index"], "lag168"] == s1.loc[i - 168, "departures"]
    assert X.loc[s1.loc[i, "index"], "avg4w"] == pytest.approx(np.mean([s1.loc[i - k, "departures"] for k in F.AVG4W_LAGS]))
    assert np.isnan(X.loc[s1.loc[10, "index"], "lag24"])      # no history yet: unknown, not zero
    assert np.isnan(X.loc[s1.loc[24 * 20, "index"], "avg4w"])  # fewer than four prior weeks


# ---- grid ----
def test_densify_zero_fills_and_starts_at_first_trip():
    lo, hi = pd.Timestamp("2026-01-01 05:00"), pd.Timestamp("2026-01-02 05:00")
    flow = pd.DataFrame({"short_name": ["A", "A", "B", "Z"],
                         "hour_utc": pd.to_datetime(["2026-01-01 10:00", "2026-01-01 13:00", "2026-01-01 20:00", "2026-01-01 10:00"]),
                         "departures": [2, 0, 1, 5], "arrivals": [0, 1, 0, 5]})
    scope = pd.DataFrame({"short_name": ["A", "B", "C"], "capacity": [10, 20, 30]})   # Z out of scope; C has no trips
    g = F.densify(flow, scope, lo, hi)
    assert set(g.short_name) == {"A", "B"}
    a = g[g.short_name == "A"]
    assert a.hour_utc.min() == pd.Timestamp("2026-01-01 10:00") and a.hour_utc.max() == hi - pd.Timedelta(hours=1)
    assert len(a) == 19 and a.departures.sum() == 2 and a.arrivals.sum() == 1
    assert (a.set_index("hour_utc").loc["2026-01-01 11:00", ["departures", "arrivals"]] == 0).all()
    assert g[g.short_name == "B"].hour_utc.min() == pd.Timestamp("2026-01-01 20:00")


def test_holiday_flag_uses_local_date():
    g = pd.DataFrame({"short_name": "S", "capacity": 10, "departures": 0, "arrivals": 0,
                      "hour_utc": pd.to_datetime(["2025-12-25 15:00", "2025-12-26 15:00", "2025-12-26 04:30"])})
    # 2025-12-26 04:30 UTC is 2025-12-25 23:30 local, still Christmas
    assert F.make_features(g, "departures").is_holiday.tolist() == [1, 0, 1]


def test_metrics():
    assert F.mae([1, 2, 3], [1, 2, 6]) == 1.0
    assert F.wape([1, 2, 3], [1, 2, 6]) == 0.5
