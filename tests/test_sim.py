"""Offline tests for the SIMULATOR (fleetdata.sim). All networks and demand are SYNTHETIC, generated in-test."""
import pathlib

import numpy as np
import pandas as pd
import pytest

from fleetdata import sim as S

CFG = S.load_config(pathlib.Path(__file__).parents[1] / "config" / "sim.json")
TRUCK = CFG["truck"]


def synthetic_network(n=12, seed=0, rate=2.0) -> S.Network:
    """SYNTHETIC: random capacities, inventories at both extremes, stations within ~2 km, unbalanced rates."""
    rng = np.random.default_rng(seed)
    cap = rng.integers(5, 30, n)
    inv0 = np.where(np.arange(n) % 3 == 0, 0, np.where(np.arange(n) % 3 == 1, cap, cap // 2))
    lat, lon = 40.72 + rng.uniform(0, 0.01, n), -74.04 + rng.uniform(0, 0.01, n)
    dep = rng.uniform(0, rate * 2, (24, n))
    arr = rng.uniform(0, rate * 2, (24, n))
    return S.Network([f"S{i}" for i in range(n)], cap, inv0.astype(int), S.haversine_km(lat, lon) * 1.3, dep, arr)


@pytest.mark.parametrize("policy", S.POLICIES)
@pytest.mark.parametrize("seed", range(20))
def test_inventory_stays_within_zero_and_capacity(policy, seed):
    net = synthetic_network(seed=seed, rate=4.0)
    r = S.simulate(net, S.draw_demand(net, seed), policy, TRUCK)
    assert (r["trace"] >= 0).all() and (r["trace"] <= net.capacity).all()


def test_clip_inventory():
    assert S.clip_inventory([-1, 5, 40, np.nan], [10, 10, 30, 10]).tolist() == [0, 5, 30, 0]


@pytest.mark.parametrize("seed", range(20))
def test_truck_moves_conserve_bikes(seed):
    """Replay with zero demand: the only inventory changes are truck moves, so the total must never change,
    and each move must be within truck capacity, never overfill, and respect the travel budget."""
    net = synthetic_network(seed=seed)
    net.dep_rate[:] = 0
    net.arr_rate[:] = 0
    r = S.simulate(net, S.draw_demand(net, seed), "greedy", TRUCK)
    assert r["moves"], "expected the greedy truck to act on an unbalanced network"
    assert (r["trace"].sum(axis=1) == net.inv0.sum()).all()
    for m in r["moves"]:
        assert 0 < m["bikes"] <= TRUCK["capacity_bikes"] and m["km"] <= TRUCK["travel_budget_km_per_hour"]
        assert TRUCK["operating_hours_local"][0] <= m["hour_local"] < TRUCK["operating_hours_local"][1]


def test_greedy_move_direction_and_budget():
    cap = np.array([20, 20, 20, 20])
    inv = np.array([20, 0, 10, 2])
    dist = np.array([[0, 1, 1, 9], [1, 0, 1, 9], [1, 1, 0, 9], [9, 9, 9, 0]], float)
    src, dst, qty, km = S.greedy_move(inv, cap, dist, None, TRUCK)
    assert (src, dst, qty) == (0, 1, 10)          # fullest -> emptiest, down/up to target fill 0.5
    # From station 3's location every source is 9 km away, beyond the 6 km budget: no move
    assert S.greedy_move(inv, cap, dist, 3, TRUCK) is None


@pytest.mark.parametrize("policy", S.POLICIES)
def test_same_seed_gives_same_result(policy):
    net = synthetic_network(seed=3)
    a = S.simulate(net, S.draw_demand(net, 11), policy, TRUCK)
    b = S.simulate(net, S.draw_demand(net, 11), policy, TRUCK)
    assert (a["lost"] == b["lost"]).all() and (a["failed"] == b["failed"]).all() and a["moves"] == b["moves"]
    assert (a["trace"] == b["trace"]).all()
    c = S.simulate(net, S.draw_demand(net, 12), policy, TRUCK)
    assert not (a["trace"] == c["trace"]).all()


def test_policies_face_identical_demand():
    """Common random numbers: demand is drawn before policy, so both policies see the same events."""
    net = synthetic_network(seed=4)
    d = S.draw_demand(net, 5)
    a, b = S.simulate(net, d, "no_action", TRUCK), S.simulate(net, d, "greedy", TRUCK)
    assert a["departures_drawn"] == b["departures_drawn"] and a["arrivals_drawn"] == b["arrivals_drawn"]


def test_lost_rental_and_failed_return_counting():
    """Hand-built events: station 0 empty, station 1 full (capacity 2)."""
    net = S.Network(["E", "F"], np.array([2, 2]), np.array([0, 2]), np.zeros((2, 2)), np.zeros((24, 2)), np.zeros((24, 2)))
    empty = lambda: np.array([], int)
    st = [empty() for _ in range(24)]
    dep = [np.array([], bool) for _ in range(24)]
    st[8], dep[8] = np.array([0, 1, 1, 0, 0]), np.array([True, False, True, False, True])
    r = S.simulate(net, S.Demand(st, dep), "no_action", TRUCK)
    # E: depart (lost), arrive (0->1), depart (1->0).  F: arrive (full -> failed), depart (2->1)
    assert r["lost"].sum() == 1 and r["failed"].sum() == 1
    assert r["trace"][-1].tolist() == [0, 1]


def test_paired_summary_signs():
    runs = pd.DataFrame([dict(seed=s, policy=p, lost_rentals=10 - 2 * (p == "greedy"), failed_returns=5,
                              unserved_total=15 - 2 * (p == "greedy")) for s in range(5) for p in S.POLICIES])
    s = S.paired_summary(runs).set_index("metric")
    assert s.loc["lost_rentals", "mean_diff"] == -2 and s.loc["lost_rentals", "ci95_hi"] == -2
    assert s.loc["failed_returns", "mean_diff"] == 0
    assert (s.label == "SIMULATED").all()


def test_config_is_the_single_source_of_truck_assumptions():
    keys = {"capacity_bikes", "count", "moves_per_hour", "operating_hours_local", "travel_budget_km_per_hour",
            "road_circuity", "target_fill", "min_fill_gap"}
    assert keys <= set(TRUCK) and TRUCK["capacity_bikes"] == 20 and TRUCK["count"] == 1
    assert len(CFG["seeds"]) == 30 == len(set(CFG["seeds"]))
