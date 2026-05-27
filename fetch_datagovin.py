#!/usr/bin/env python3
"""Fetch CPCB CAAQMS realtime stations from data.gov.in.

Requires a free API key from https://data.gov.in/help/how-use-datasets-apis
(export DATAGOVIN_API_KEY). Saves to stations_cpcb.json — index.html loads it
if present.

The CPCB realtime dataset includes temperature for many but not all stations.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"  # CPCB CAAQMS Real-time
API = "https://api.data.gov.in/resource"
ROOT = Path(__file__).parent
OUT = ROOT / "stations_cpcb.json"

KEY = os.environ.get("DATAGOVIN_API_KEY", "").strip()
if not KEY:
    print(
        "DATAGOVIN_API_KEY not set. Register at https://data.gov.in/user/register",
        file=sys.stderr,
    )
    sys.exit(2)


def fetch_all(page_size: int = 1000) -> list[dict]:
    records = []
    offset = 0
    while True:
        q = urllib.parse.urlencode({
            "api-key": KEY,
            "format": "json",
            "limit": page_size,
            "offset": offset,
        })
        url = f"{API}/{RESOURCE_ID}?{q}"
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
        recs = data.get("records", [])
        records.extend(recs)
        if len(recs) < page_size:
            break
        offset += page_size
        time.sleep(0.5)
    return records


def main() -> int:
    print("fetching CPCB CAAQMS realtime records...", file=sys.stderr)
    records = fetch_all()
    print(f"  raw records: {len(records)}", file=sys.stderr)

    # CPCB realtime dataset reports one row per (station × pollutant). Group by station,
    # take the temperature row when present.
    stations: dict[str, dict] = {}
    for rec in records:
        sid = rec.get("station") or rec.get("station_id") or rec.get("id")
        if not sid:
            continue
        s = stations.setdefault(sid, {
            "id": sid,
            "name": rec.get("station") or rec.get("station_name"),
            "city": rec.get("city"),
            "state": rec.get("state"),
            "lat": _tofloat(rec.get("latitude")),
            "lon": _tofloat(rec.get("longitude")),
            "last_update": rec.get("last_update"),
            "temperature_c": None,
            "pollutants": {},
        })
        pid = (rec.get("pollutant_id") or "").lower()
        avg = _tofloat(rec.get("pollutant_avg") or rec.get("avg_value"))
        if pid in ("temperature", "temp", "at"):
            s["temperature_c"] = avg
        elif pid:
            s["pollutants"][pid] = avg

    stations_list = [s for s in stations.values() if s["lat"] is not None and s["lon"] is not None]
    with_temp = [s for s in stations_list if s["temperature_c"] is not None]
    OUT.write_text(json.dumps({
        "source": "data.gov.in / CPCB CAAQMS realtime",
        "resource_id": RESOURCE_ID,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "stations": stations_list,
    }, indent=2))
    print(
        f"saved {len(stations_list)} stations ({len(with_temp)} with temperature) → {OUT.name}",
        file=sys.stderr,
    )
    return 0


def _tofloat(v):
    if v in (None, "", "NA", "N/A", "-"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    sys.exit(main())
