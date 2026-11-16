"""Offline tests for the data layer.

Inputs:
- tests/fixtures/gbfs/: a REAL 10-station subset of the GBFS feeds (see PROVENANCE.json)
- tests/fixtures/trips/SYNTHETIC_trips.csv: hand-made SYNTHETIC trips (see README.md there)
"""
import datetime as dt
import pathlib

import duckdb
import pytest

from fleetdata import build as B

FIX = pathlib.Path(__file__).parent / "fixtures"
GBFS = FIX / "gbfs"
SYN = FIX / "trips" / "SYNTHETIC_trips.csv"


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "test.duckdb"
    B.build(db, GBFS, [SYN])
    with duckdb.connect(str(db), read_only=True) as c:
        yield c


def trip(con, ride_id):
    cur = con.execute("SELECT * FROM trips WHERE ride_id = ?", [ride_id])
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, cur.fetchone()))


def test_stations_keyed_on_short_name(con):
    n, distinct, nulls = con.execute(
        "SELECT count(*), count(DISTINCT short_name), count(*) FILTER (capacity IS NULL OR lat IS NULL) FROM stations").fetchone()
    assert (n, distinct, nulls) == (10, 10, 0)


def test_snapshot_flags_are_coerced_booleans(con):
    types = {r[0]: r[1] for r in con.execute("DESCRIBE snapshot").fetchall()}
    assert types["is_installed"] == types["is_renting"] == types["is_returning"] == "BOOLEAN"
    # Real edge case from the fixture: installed but not renting (short_name 5129.01)
    assert con.execute("SELECT is_installed, is_renting FROM snapshot WHERE short_name = '5129.01'").fetchone() == (True, False)


def test_placeholder_last_reported_is_stale_and_missing_not_epoch(con):
    # Real edge case: last_reported = 86400 (placeholder) for short_name 6545.07
    row = con.execute("SELECT is_stale, stale_reason, last_reported_utc FROM snapshot WHERE short_name = '6545.07'").fetchone()
    assert row == (True, "placeholder_last_reported", None)


def test_every_snapshot_row_joins_to_a_station(con):
    assert con.execute("SELECT count(*) FROM snapshot WHERE short_name IS NULL").fetchone()[0] == 0


def test_as_bool_rejects_unexpected_values():
    assert B.as_bool(0) is False and B.as_bool(1) is True and B.as_bool(True) is True
    for bad in (2, "1", 1.0):
        with pytest.raises(ValueError):
            B.as_bool(bad)


@pytest.mark.parametrize("ride_id, utc, flag", [
    ("SYN01", dt.datetime(2025, 10, 15, 12, 0), None),                      # EDT (UTC-4)
    ("SYN02", dt.datetime(2025, 12, 15, 13, 0), None),                      # EST (UTC-5)
    ("SYN03", dt.datetime(2025, 11, 2, 5, 30), "ambiguous_fall_back"),      # first occurrence (EDT) chosen, flagged
    ("SYN04", dt.datetime(2026, 3, 8, 7, 30), "nonexistent_spring_forward"),
])
def test_local_to_utc_and_dst_flags(con, ride_id, utc, flag):
    t = trip(con, ride_id)
    assert t["started_at_utc"] == utc
    assert t["started_tz_flag"] == flag


def test_ambiguous_flag_applies_to_end_time_too(con):
    assert trip(con, "SYN03")["ended_tz_flag"] == "ambiguous_fall_back"


def test_join_keeps_unmatched_and_missing_end(con):
    assert con.execute("SELECT count(*) FROM trips").fetchone()[0] == 6   # nothing dropped
    t5, t6 = trip(con, "SYN05"), trip(con, "SYN06")
    assert t5["start_matched"] is False and t5["end_matched"] is True
    assert t6["end_short_name"] is None and t6["end_matched"] is None


def test_hourly_flow_counts(con):
    q = "SELECT departures, arrivals FROM hourly_flow WHERE short_name = ? AND hour_utc = ?"
    # JC014 at 12:00 UTC on 2025-10-15: departures SYN01 (12:00) and SYN06 (12:45); arrival SYN05 (12:40)
    assert con.execute(q, ["JC014", dt.datetime(2025, 10, 15, 12)]).fetchone() == (2, 1)
    assert con.execute(q, ["JC014", dt.datetime(2025, 12, 15, 13)]).fetchone() == (1, 0)
    assert con.execute(q, ["ZZ999", dt.datetime(2025, 10, 15, 12)]).fetchone() == (1, 0)
    assert con.execute("SELECT station_matched FROM hourly_flow WHERE short_name = 'ZZ999'").fetchone() == (False,)
    total_dep, total_arr = con.execute("SELECT sum(departures), sum(arrivals) FROM hourly_flow").fetchone()
    assert (total_dep, total_arr) == (6, 5)   # SYN06 has no end station


def test_duplicate_rides_across_files_are_removed_once(tmp_path):
    # Same SYNTHETIC file presented twice under different names (mimics the observed month-boundary overlap)
    copy = tmp_path / "SYNTHETIC_trips_copy.csv"
    copy.write_bytes(SYN.read_bytes())
    db = tmp_path / "dup.duckdb"
    B.build(db, GBFS, [SYN, copy])
    with duckdb.connect(str(db), read_only=True) as c:
        assert c.execute("SELECT count(*), count(DISTINCT ride_id) FROM trips").fetchone() == (6, 6)
        log = dict(c.execute("SELECT item, value FROM build_log").fetchall())
    assert log == {"duplicate_ride_ids_removed": 6, "duplicate_ride_ids_with_conflicting_content": 0}


def test_missing_trip_columns_fail_loudly(tmp_path):
    bad = tmp_path / "old_schema.csv"
    bad.write_text("tripduration,starttime\n60,2015-01-01 00:00:00\n")
    with pytest.raises(ValueError, match="expected columns"):
        B.build(tmp_path / "x.duckdb", GBFS, [bad])
