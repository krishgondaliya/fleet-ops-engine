"""Download raw inputs for the offline prototype.

- Jersey City (JC-prefixed) monthly trip zips for the most recent N months -> data/raw/trips/
- ONE snapshot each of GBFS station_information and station_status -> data/raw/gbfs/
  (with fetch metadata in data/raw/gbfs/fetch_meta.json)

Files that already exist are skipped. Trip zips are re-downloaded only if the local size
differs from the bucket listing. GBFS is re-fetched only with --refresh-gbfs.
This is a one-shot script. It does not poll.

Usage:  python -m fleetdata.download [--months 12] [--refresh-gbfs]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import xml.etree.ElementTree as ET

import requests

BUCKET = "https://s3.amazonaws.com/tripdata/"
DISCOVERY = "https://gbfs.citibikenyc.com/gbfs/2.3/gbfs.json"
GBFS_FEEDS = ("station_information", "station_status")
HEADERS = {"User-Agent": "independent-research-offline-prototype/0.1"}
JC_KEY = re.compile(r"^JC-(\d{6})-citibike-tripdata(\.csv)?\.zip$")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def list_bucket(session: requests.Session) -> list[dict]:
    """All objects in the public trip bucket (handles S3 v1 pagination)."""
    objects, marker = [], ""
    while True:
        r = session.get(BUCKET, params={"marker": marker} if marker else None, timeout=60)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"s": root.tag.split("}")[0].strip("{")}
        for c in root.findall("s:Contents", ns):
            objects.append({
                "key": c.find("s:Key", ns).text,
                "size": int(c.find("s:Size", ns).text),
                "last_modified": c.find("s:LastModified", ns).text,
                "etag": (c.find("s:ETag", ns).text or "").strip('"'),
            })
        if root.find("s:IsTruncated", ns).text != "true":
            return objects
        marker = objects[-1]["key"]


def latest_jc(objects: list[dict], months: int) -> list[dict]:
    """Most recent `months` JC monthly files. If one month has two key variants, keep the newest upload."""
    by_month: dict[str, dict] = {}
    for o in objects:
        m = JC_KEY.match(o["key"])
        if not m:
            continue
        ym = m.group(1)
        if ym not in by_month or o["last_modified"] > by_month[ym]["last_modified"]:
            by_month[ym] = dict(o, yyyymm=ym)
    return [by_month[ym] for ym in sorted(by_month, reverse=True)[:months]]


def download_trips(session: requests.Session, out_dir: pathlib.Path, months: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for o in latest_jc(list_bucket(session), months):
        dest = out_dir / o["key"]
        if dest.exists() and dest.stat().st_size == o["size"]:
            print(f"skip   {o['key']} (already downloaded)")
            continue
        print(f"fetch  {o['key']} ({o['size']:,} B)")
        part = dest.with_suffix(dest.suffix + ".part")
        with session.get(BUCKET + o["key"], stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        if part.stat().st_size != o["size"]:
            raise IOError(f"size mismatch for {o['key']}: got {part.stat().st_size}, expected {o['size']}")
        part.replace(dest)
        manifest[o["key"]] = {"url": BUCKET + o["key"], "downloaded_at_utc": utc_now(), "size": o["size"],
                              "etag": o["etag"], "bucket_last_modified": o["last_modified"]}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def fetch_gbfs(session: requests.Session, out_dir: pathlib.Path, refresh: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "fetch_meta.json"
    if not refresh and meta_path.exists() and all((out_dir / f"{f}.json").exists() for f in GBFS_FEEDS):
        print("skip   GBFS snapshot (already downloaded; use --refresh-gbfs to replace)")
        return
    # Resolve feed URLs from discovery at runtime; never hardcode them.
    disc = session.get(DISCOVERY, timeout=60)
    disc.raise_for_status()
    feeds = {f["name"]: f["url"] for f in disc.json()["data"]["en"]["feeds"]}
    meta = {"discovery": {"url": DISCOVERY, "fetched_at_utc": utc_now()}}
    for name in GBFS_FEEDS:
        fetched_at = utc_now()
        r = session.get(feeds[name], timeout=60)
        r.raise_for_status()
        (out_dir / f"{name}.json").write_bytes(r.content)  # untouched payload
        meta[name] = {"url": feeds[name], "fetched_at_utc": fetched_at, "http_status": r.status_code,
                      "bytes": len(r.content), "etag": r.headers.get("ETag"),
                      "last_modified": r.headers.get("Last-Modified")}
        print(f"fetch  {name} at {fetched_at} ({len(r.content):,} B)")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="data/raw", type=pathlib.Path)
    ap.add_argument("--months", default=12, type=int)
    ap.add_argument("--refresh-gbfs", action="store_true", help="re-fetch the GBFS snapshot even if present")
    args = ap.parse_args()
    with requests.Session() as s:
        s.headers.update(HEADERS)
        download_trips(s, args.data_dir / "trips", args.months)
        fetch_gbfs(s, args.data_dir / "gbfs", args.refresh_gbfs)


if __name__ == "__main__":
    main()
