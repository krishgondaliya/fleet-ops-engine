"""M0 evidence script: build 10-station GBFS fixtures from ONE real fetch of each feed.

Provenance: real provider data subset, NOT synthetic. Writes only tests/fixtures/gbfs/*.
Selection rule (deterministic, no hand-typed names):
  - 8 stations: installed+docked stations in regions {70 JC, 311 Hoboken}, nearest to seed (40.7190, -74.0400)  [cluster C]
  - 1 edge case: is_installed=1 and is_renting=0 (first by station_id), if present
  - 1 edge case: last_reported < 1e6 (placeholder-like), first by station_id, if present
  Missing edge cases are back-filled with the next-nearest cluster-C stations.
Usage (from repo root):  python docs/discovery/evidence/make_gbfs_fixtures.py
"""
import datetime
import json
import math
import pathlib

import requests

DISCOVERY = "https://gbfs.citibikenyc.com/gbfs/2.3/gbfs.json"
UA = {"User-Agent": "independent-research-feasibility-check/0.1"}
OUT = pathlib.Path("tests/fixtures/gbfs")
SEED = (40.7190, -74.0400)
REGIONS = {"70", "311"}


def hav(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(x))


def fetch(url):
    t = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    meta = {"url": url, "fetched_at_utc": t, "http_status": r.status_code, "bytes": len(r.content),
            "etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified"),
            "cache_control": r.headers.get("Cache-Control"), "content_encoding": r.headers.get("Content-Encoding")}
    return r.json(), meta


def main():
    # Feed URLs come from the discovery document. They are not hardcoded.
    # This run fetches the discovery document a second time, which is within budget.
    disc, disc_meta = fetch(DISCOVERY)
    feeds = {f["name"]: f["url"] for f in disc["data"]["en"]["feeds"]}
    info, info_meta = fetch(feeds["station_information"])
    status, status_meta = fetch(feeds["station_status"])

    inf = info["data"]["stations"]
    st = {s["station_id"]: s for s in status["data"]["stations"]}
    by_id = {s["station_id"]: s for s in inf}

    cluster = sorted(
        (s for s in inf if s.get("capacity") and s.get("region_id") in REGIONS
         and st.get(s["station_id"], {}).get("is_installed") == 1),
        key=lambda s: hav(SEED[0], SEED[1], s["lat"], s["lon"]))
    chosen = [s["station_id"] for s in cluster[:8]]
    reasons = {sid: "cluster_C_nearest" for sid in chosen}

    def first(pred):
        for sid in sorted(st):
            if sid in by_id and sid not in chosen and pred(st[sid]):
                return sid
        return None

    edge_rules = {
        "edge_installed_not_renting": lambda s: s.get("is_installed") == 1 and s.get("is_renting") == 0,
        "edge_placeholder_last_reported": lambda s: isinstance(s.get("last_reported"), int) and s["last_reported"] < 10**6,
    }
    for reason, pred in edge_rules.items():
        sid = first(pred)
        if sid:
            chosen.append(sid)
            reasons[sid] = reason
    for s in cluster[8:]:
        if len(chosen) >= 10:
            break
        if s["station_id"] not in chosen:
            chosen.append(s["station_id"])
            reasons[s["station_id"]] = "cluster_C_backfill"

    keep = set(chosen)
    info_fx = dict(info, data={"stations": [s for s in inf if s["station_id"] in keep]})
    status_fx = dict(status, data={"stations": [s for s in status["data"]["stations"] if s["station_id"] in keep]})

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "station_information.json").write_text(json.dumps(info_fx, indent=2), encoding="utf-8")
    (OUT / "station_status.json").write_text(json.dumps(status_fx, indent=2), encoding="utf-8")
    prov = {
        "provenance": "REAL provider data subset (not synthetic). 10 stations filtered from one live fetch per feed; envelope fields unchanged.",
        "license_note": "Citi Bike Data License Agreement https://citibikenyc.com/data-sharing-policy . Test fixture only; not a stand-alone dataset. Re-review before making the repo public.",
        "discovery": disc_meta,
        "station_information": dict(info_meta, original_station_count=len(inf)),
        "station_status": dict(status_meta, original_station_count=len(status["data"]["stations"])),
        "selection_rule": __doc__.split("Selection rule")[1].split("Usage")[0].strip(),
        "selected": [{"station_id": sid, "short_name": by_id[sid].get("short_name"), "reason": reasons[sid]} for sid in chosen],
    }
    (OUT / "PROVENANCE.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    print(json.dumps({k: prov[k] for k in ("station_information", "station_status", "selected")}, indent=1))


if __name__ == "__main__":
    main()
