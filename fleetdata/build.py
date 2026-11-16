"""Build data/fleet.duckdb from raw downloads. Offline; makes no network calls.

Tables
  stations     one row per GBFS station, keyed on short_name (the trip-file station ID)
  snapshot     the single station_status fetch; 0/1 flags coerced to BOOLEAN; stale stations flagged
  trips        completed trips; America/New_York naive local times converted to UTC;
               DST fall-back (ambiguous) and spring-forward (nonexistent) hours flagged;
               joined to stations on short_name (unmatched trips are kept, never dropped)
  hourly_flow  departures and arrivals per station per UTC hour (sparse: hours with no activity are absent)

Epistemic notes: snapshot = observed (one instant); trips = observed completed trips, not demand.

Usage:  python -m fleetdata.build [--db data/fleet.duckdb] [--gbfs-dir data/raw/gbfs] [--trips-dir data/raw/trips]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import tempfile
import zipfile
from zoneinfo import ZoneInfo

import duckdb

NY = ZoneInfo("America/New_York")
STALE_SECONDS = 900          # station report older than 15 min (vs feed last_updated) counts as stale
PLACEHOLDER_MAX = 10**6      # last_reported below this is a placeholder (observed value: 86400)
JC_HB_REGIONS = ("70", "311")
TRIP_COLUMNS = {"ride_id", "rideable_type", "started_at", "ended_at", "start_station_name", "start_station_id",
                "end_station_name", "end_station_id", "start_lat", "start_lng", "end_lat", "end_lng",
                "member_casual"}


# ---------- helpers ----------
def as_bool(v):
    """Coerce GBFS flags. The live feed sends 0/1 ints (GBFS 2.3 says JSON booleans)."""
    if v is None or isinstance(v, bool):
        return v
    if type(v) is int and v in (0, 1):
        return bool(v)
    raise ValueError(f"unexpected flag value {v!r}")


def posix_to_utc(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).replace(tzinfo=None) if ts is not None else None


def iso_to_utc(s):
    return dt.datetime.fromisoformat(s).astimezone(dt.timezone.utc).replace(tzinfo=None)


def load_fetch_meta(gbfs_dir: pathlib.Path) -> dict:
    """fetch_meta.json (download script) or PROVENANCE.json (test fixtures); same per-feed keys."""
    for name in ("fetch_meta.json", "PROVENANCE.json"):
        p = gbfs_dir / name
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"no fetch_meta.json or PROVENANCE.json in {gbfs_dir}")


def sql_list(paths) -> str:
    return "[" + ",".join("'" + pathlib.Path(p).as_posix().replace("'", "''") + "'" for p in paths) + "]"


def local_hour_rows(start: dt.datetime, end: dt.datetime):
    """(local_hour, utc_offset_minutes, tz_flag) for every naive local hour in [start, end].
    Ambiguous fall-back hours resolve to the FIRST occurrence (fold=0, daylight time) and are flagged.
    Nonexistent spring-forward hours use the pre-transition offset (fold=0) and are flagged."""
    h = start.replace(minute=0, second=0, microsecond=0)
    while h <= end:
        probe = h.replace(minute=30)
        a, b = probe.replace(tzinfo=NY, fold=0), probe.replace(tzinfo=NY, fold=1)
        roundtrip = a.astimezone(dt.timezone.utc).astimezone(NY).replace(tzinfo=None)
        if roundtrip != probe:
            flag = "nonexistent_spring_forward"
        elif a.utcoffset() != b.utcoffset():
            flag = "ambiguous_fall_back"
        else:
            flag = None
        yield h, int(a.utcoffset().total_seconds() // 60), flag
        h += dt.timedelta(hours=1)


# ---------- loaders ----------
def load_stations(con, gbfs_dir: pathlib.Path, meta: dict) -> None:
    info = json.loads((gbfs_dir / "station_information.json").read_text(encoding="utf-8"))
    rows, seen, dups = [], set(), set()
    for s in info["data"]["stations"]:
        sn = s.get("short_name")
        if sn in seen:
            dups.add(sn)
        seen.add(sn)
        rows.append((sn, s["station_id"], s.get("name"), s.get("lat"), s.get("lon"), s.get("capacity"),
                     s.get("region_id")))
    if dups or None in seen:
        raise ValueError(f"short_name is not a usable key: duplicates={sorted(map(str, dups))[:10]}, null={None in seen}")
    con.execute("""CREATE TABLE stations (
        short_name VARCHAR PRIMARY KEY, station_id VARCHAR NOT NULL UNIQUE, name VARCHAR,
        lat DOUBLE, lon DOUBLE, capacity INTEGER, region_id VARCHAR,
        info_last_updated_utc TIMESTAMP, info_fetched_at_utc TIMESTAMP)""")
    lu, fa = posix_to_utc(info["last_updated"]), iso_to_utc(meta["station_information"]["fetched_at_utc"])
    con.executemany("INSERT INTO stations VALUES (?,?,?,?,?,?,?,?,?)", [r + (lu, fa) for r in rows])


def load_snapshot(con, gbfs_dir: pathlib.Path, meta: dict) -> None:
    status = json.loads((gbfs_dir / "station_status.json").read_text(encoding="utf-8"))
    feed_lu = status["last_updated"]
    fetched = iso_to_utc(meta["station_status"]["fetched_at_utc"])
    key = dict(con.execute("SELECT station_id, short_name FROM stations").fetchall())
    cap = dict(con.execute("SELECT station_id, capacity FROM stations").fetchall())
    rows = []
    for s in status["data"]["stations"]:
        lr = s.get("last_reported")
        if lr is None:
            reason, lr_utc, age = "missing_last_reported", None, None
        elif lr < PLACEHOLDER_MAX:
            reason, lr_utc, age = "placeholder_last_reported", None, None
        else:
            age = feed_lu - lr
            reason, lr_utc = ("age_gt_%ds" % STALE_SECONDS if age > STALE_SECONDS else None), posix_to_utc(lr)
        counts = [s.get(k) for k in ("num_bikes_available", "num_ebikes_available", "num_bikes_disabled",
                                     "num_docks_available", "num_docks_disabled")]
        c = cap.get(s["station_id"])
        over = None if c is None or None in (counts[0], counts[2], counts[3], counts[4]) \
            else counts[0] + counts[2] + counts[3] + counts[4] > c
        rows.append((key.get(s["station_id"]), s["station_id"], *counts,
                     as_bool(s.get("is_installed")), as_bool(s.get("is_renting")), as_bool(s.get("is_returning")),
                     lr_utc, age, reason is not None, reason, over, posix_to_utc(feed_lu), fetched))
    con.execute("""CREATE TABLE snapshot (
        short_name VARCHAR, station_id VARCHAR NOT NULL,
        num_bikes_available INTEGER, num_ebikes_available INTEGER, num_bikes_disabled INTEGER,
        num_docks_available INTEGER, num_docks_disabled INTEGER,
        is_installed BOOLEAN, is_renting BOOLEAN, is_returning BOOLEAN,
        last_reported_utc TIMESTAMP, report_age_seconds BIGINT, is_stale BOOLEAN, stale_reason VARCHAR,
        over_capacity BOOLEAN, feed_last_updated_utc TIMESTAMP, fetched_at_utc TIMESTAMP)""")
    con.executemany("INSERT INTO snapshot VALUES (" + ",".join("?" * 17) + ")", rows)


def load_trips(con, csv_paths: list[pathlib.Path]) -> None:
    con.execute(f"""CREATE TEMP TABLE trips_raw AS SELECT * FROM read_csv({sql_list(csv_paths)},
                    header=true, all_varchar=true, union_by_name=true, filename=true)""")
    cols = {r[0] for r in con.execute("DESCRIBE trips_raw").fetchall()}
    missing = TRIP_COLUMNS - cols
    if missing:
        raise ValueError(f"trip files lack expected columns {sorted(missing)}; older schema not supported")
    con.execute(r"""CREATE TEMP TABLE trips_parsed AS SELECT
        ride_id, rideable_type, member_casual,
        TRY_CAST(started_at AS TIMESTAMP) AS started_local, TRY_CAST(ended_at AS TIMESTAMP) AS ended_local,
        NULLIF(trim(start_station_id), '') AS start_short_name, NULLIF(trim(end_station_id), '') AS end_short_name,
        NULLIF(start_station_name, '') AS start_station_name, NULLIF(end_station_name, '') AS end_station_name,
        TRY_CAST(NULLIF(start_lat, '') AS DOUBLE) AS start_lat, TRY_CAST(NULLIF(start_lng, '') AS DOUBLE) AS start_lng,
        TRY_CAST(NULLIF(end_lat, '') AS DOUBLE) AS end_lat, TRY_CAST(NULLIF(end_lng, '') AS DOUBLE) AS end_lng,
        regexp_extract(replace(filename, '\', '/'), '[^/]+$') AS source_file
        FROM trips_raw""")
    # Monthly files overlap at boundaries (observed: identical rides in both JC-202604 and JC-202605).
    # Keep one row per ride_id (first by source_file) and record how many were removed and whether any differed.
    con.execute("""CREATE TEMP TABLE dedup_report AS SELECT
        count(*) - count(DISTINCT ride_id) AS removed,
        (SELECT count(*) FROM (SELECT ride_id FROM trips_parsed GROUP BY ride_id
            HAVING count(DISTINCT (started_local, ended_local, start_short_name, end_short_name, rideable_type)) > 1)) AS conflicting
        FROM trips_parsed""")
    con.execute("""CREATE OR REPLACE TEMP TABLE trips_parsed AS SELECT * FROM trips_parsed
                   QUALIFY row_number() OVER (PARTITION BY ride_id ORDER BY source_file) = 1""")
    con.execute("CREATE TABLE build_log AS SELECT 'duplicate_ride_ids_removed' AS item, removed AS value FROM dedup_report "
                "UNION ALL SELECT 'duplicate_ride_ids_with_conflicting_content', conflicting FROM dedup_report")
    lo, hi = con.execute("SELECT least(min(started_local), min(ended_local)), "
                         "greatest(max(started_local), max(ended_local)) FROM trips_parsed").fetchone()
    con.execute("CREATE TEMP TABLE local_hours (local_hour TIMESTAMP PRIMARY KEY, utc_offset_minutes INTEGER, tz_flag VARCHAR)")
    if lo is not None:
        con.executemany("INSERT INTO local_hours VALUES (?,?,?)", list(local_hour_rows(lo, hi)))
    con.execute("""CREATE TABLE trips AS SELECT
        p.ride_id, p.rideable_type, p.member_casual,
        p.started_local AS started_at_local, p.ended_local AS ended_at_local,
        p.started_local - to_minutes(hs.utc_offset_minutes) AS started_at_utc,
        p.ended_local   - to_minutes(he.utc_offset_minutes) AS ended_at_utc,
        hs.tz_flag AS started_tz_flag, he.tz_flag AS ended_tz_flag,
        p.start_short_name, p.end_short_name,
        ss.short_name IS NOT NULL AS start_matched,
        CASE WHEN p.end_short_name IS NULL THEN NULL ELSE es.short_name IS NOT NULL END AS end_matched,
        p.start_station_name, p.end_station_name, p.start_lat, p.start_lng, p.end_lat, p.end_lng, p.source_file
      FROM trips_parsed p
      LEFT JOIN local_hours hs ON hs.local_hour = date_trunc('hour', p.started_local)
      LEFT JOIN local_hours he ON he.local_hour = date_trunc('hour', p.ended_local)
      LEFT JOIN stations ss ON ss.short_name = p.start_short_name
      LEFT JOIN stations es ON es.short_name = p.end_short_name""")


def build_hourly_flow(con) -> None:
    con.execute("""CREATE TABLE hourly_flow AS
      WITH d AS (SELECT start_short_name AS short_name, date_trunc('hour', started_at_utc) AS hour_utc, count(*) AS n
                 FROM trips WHERE start_short_name IS NOT NULL AND started_at_utc IS NOT NULL GROUP BY ALL),
           a AS (SELECT end_short_name AS short_name, date_trunc('hour', ended_at_utc) AS hour_utc, count(*) AS n
                 FROM trips WHERE end_short_name IS NOT NULL AND ended_at_utc IS NOT NULL GROUP BY ALL)
      SELECT coalesce(d.short_name, a.short_name) AS short_name, coalesce(d.hour_utc, a.hour_utc) AS hour_utc,
             coalesce(d.n, 0)::INTEGER AS departures, coalesce(a.n, 0)::INTEGER AS arrivals,
             coalesce(d.short_name, a.short_name) IN (SELECT short_name FROM stations) AS station_matched
      FROM d FULL OUTER JOIN a ON d.short_name = a.short_name AND d.hour_utc = a.hour_utc
      ORDER BY short_name, hour_utc""")


# ---------- build + summary ----------
def extract_trip_csvs(trips_dir: pathlib.Path, tmp: pathlib.Path) -> list[pathlib.Path]:
    out = []
    for z in sorted(trips_dir.glob("*.zip")):
        with zipfile.ZipFile(z) as zf:
            for m in zf.infolist():
                name = pathlib.PurePosixPath(m.filename)
                if m.is_dir() or name.suffix.lower() != ".csv" or "__MACOSX" in name.parts or name.name.startswith("._"):
                    continue
                dest = tmp / name.name
                with zf.open(m) as src, open(dest, "wb") as dst:
                    dst.write(src.read())
                out.append(dest)
    return out


def build(db_path: pathlib.Path, gbfs_dir: pathlib.Path, trip_csvs: list[pathlib.Path]) -> None:
    """Build the database atomically: write to a temp file, then replace db_path."""
    if not trip_csvs:
        raise FileNotFoundError("no trip CSVs found; run `python -m fleetdata.download` first")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_db = db_path.with_suffix(".building.duckdb")
    tmp_db.unlink(missing_ok=True)
    meta = load_fetch_meta(gbfs_dir)
    with duckdb.connect(str(tmp_db)) as con:
        load_stations(con, gbfs_dir, meta)
        load_snapshot(con, gbfs_dir, meta)
        load_trips(con, trip_csvs)
        build_hourly_flow(con)
    os.replace(tmp_db, db_path)


def summary(con) -> dict:
    q = lambda sql: con.execute(sql).fetchall()
    one = lambda sql: con.execute(sql).fetchone()
    s = {"row_counts": {t: one(f"SELECT count(*) FROM {t}")[0] for t in ("stations", "snapshot", "trips", "hourly_flow")}}
    s["trip_range_local"] = one("SELECT min(started_at_local), max(started_at_local) FROM trips")
    s["trip_range_utc"] = one("SELECT min(started_at_utc), max(started_at_utc) FROM trips")
    s["source_files"] = [r[0] for r in q("SELECT DISTINCT source_file FROM trips ORDER BY 1")]
    s["unparsed_timestamps"] = one("SELECT count(*) FILTER (started_at_local IS NULL), count(*) FILTER (ended_at_local IS NULL) FROM trips")
    s["tz_flags"] = q("""SELECT flag, count(*) FROM (SELECT started_tz_flag AS flag FROM trips UNION ALL
                         SELECT ended_tz_flag FROM trips) WHERE flag IS NOT NULL GROUP BY 1 ORDER BY 1""")
    s["duplicate_ride_ids"] = one("SELECT count(*) - count(DISTINCT ride_id) FROM trips")[0]
    s["build_log"] = dict(q("SELECT item, value FROM build_log"))
    s["join_start"] = one("""SELECT avg(start_matched::INT) * 100, count(DISTINCT start_short_name) FILTER (start_matched),
                             count(DISTINCT start_short_name) FROM trips""")
    s["join_end"] = one("""SELECT avg(end_matched::INT) * 100, count(DISTINCT end_short_name) FILTER (end_matched),
                           count(DISTINCT end_short_name), count(*) FILTER (end_short_name IS NULL) FROM trips""")
    s["unmatched_ids"] = q("""SELECT id, count(*) FROM (SELECT start_short_name AS id FROM trips WHERE NOT start_matched
                              UNION ALL SELECT end_short_name FROM trips WHERE end_matched = false)
                              GROUP BY 1 ORDER BY 2 DESC LIMIT 10""")
    s["snapshot_quality"] = one("""SELECT count(*) FILTER (is_stale), count(*) FILTER (stale_reason = 'placeholder_last_reported'),
        count(*) FILTER (NOT is_installed), count(*) FILTER (NOT is_renting), count(*) FILTER (over_capacity),
        any_value(fetched_at_utc), any_value(feed_last_updated_utc) FROM snapshot""")
    no_trips = """FROM snapshot sn JOIN stations st USING (short_name)
                  WHERE short_name NOT IN (SELECT start_short_name FROM trips WHERE start_short_name IS NOT NULL
                                           UNION SELECT end_short_name FROM trips WHERE end_short_name IS NOT NULL)"""
    s["no_trips_all"] = one(f"SELECT count(*) {no_trips}")[0]
    s["no_trips_jc_hb"] = q(f"""SELECT short_name, st.region_id, sn.is_installed {no_trips}
                                AND st.region_id IN {JC_HB_REGIONS} ORDER BY short_name""")
    # Name from GBFS when matched; otherwise the most common trip-file name (station retired/renumbered).
    s["top10_departures"] = q("""SELECT t.start_short_name, coalesce(any_value(st.name), mode(t.start_station_name)),
                                 count(*) AS departures, bool_or(t.start_matched) FROM trips t
                                 LEFT JOIN stations st ON st.short_name = t.start_short_name
                                 GROUP BY 1 ORDER BY departures DESC, 1 LIMIT 10""")
    s["match_by_file"] = q("""SELECT source_file, avg(start_matched::INT) * 100, count(*) FROM trips GROUP BY 1 ORDER BY 1""")
    return s


def print_summary(s: dict) -> None:
    print("\n=== fleet.duckdb summary ===")
    print("Row counts:", ", ".join(f"{k}={v:,}" for k, v in s["row_counts"].items()))
    print(f"Trip files ({len(s['source_files'])}): {s['source_files'][0]} .. {s['source_files'][-1]}")
    print("Trip start range (local NY):", *s["trip_range_local"], sep="  ")
    print("Trip start range (UTC):     ", *s["trip_range_utc"], sep="  ")
    bl = s["build_log"]
    print("Unparsed timestamps (start, end):", s["unparsed_timestamps"],
          f" Duplicate ride_ids removed: {bl['duplicate_ride_ids_removed']} "
          f"(conflicting content: {bl['duplicate_ride_ids_with_conflicting_content']}); remaining: {s['duplicate_ride_ids']}")
    print("DST-flagged timestamps:", s["tz_flags"] or "none")
    js, je = s["join_start"], s["join_end"]
    print(f"Join start_station_id -> stations.short_name: {js[0]:.2f}% of trips; {js[1]}/{js[2]} distinct IDs")
    print(f"Join end_station_id   -> stations.short_name: {je[0]:.2f}% of trips with an end ID; "
          f"{je[1]}/{je[2]} distinct IDs; {je[3]:,} trips have no end ID")
    print("Top unmatched IDs (id, trip refs):", s["unmatched_ids"] or "none")
    print("Start-station match rate by file:",
          ", ".join(f"{f[3:9]} {pct:.1f}%" for f, pct, _ in s["match_by_file"]))
    sq = s["snapshot_quality"]
    print(f"Snapshot fetched {sq[5]} UTC (feed last_updated {sq[6]}): stale={sq[0]} (placeholder={sq[1]}), "
          f"not_installed={sq[2]}, not_renting={sq[3]}, over_capacity={sq[4]}")
    print(f"Snapshot stations with no trips: {s['no_trips_all']:,} system-wide "
          f"(expected: JC files only contain trips starting in JC/Hoboken)")
    print(f"  of which in JC/Hoboken regions: {len(s['no_trips_jc_hb'])}",
          [f"{r[0]}{'' if r[2] else ' (not installed)'}" for r in s["no_trips_jc_hb"]])
    print("Top 10 stations by departures (* = not in current GBFS; name from trip file):")
    for sn, name, n, matched in s["top10_departures"]:
        print(f"  {sn:<8}{' ' if matched else '*'} {n:>7,}  {name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/fleet.duckdb", type=pathlib.Path)
    ap.add_argument("--gbfs-dir", default="data/raw/gbfs", type=pathlib.Path)
    ap.add_argument("--trips-dir", default="data/raw/trips", type=pathlib.Path)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        build(args.db, args.gbfs_dir, extract_trip_csvs(args.trips_dir, pathlib.Path(tmp)))
    with duckdb.connect(str(args.db), read_only=True) as con:
        print_summary(summary(con))


if __name__ == "__main__":
    main()
