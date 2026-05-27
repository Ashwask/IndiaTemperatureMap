#!/usr/bin/env python3
"""Fetch India temperature-reporting stations from OpenAQ v3.

Requires a free API key from https://openaq.org/explore (export OPENAQ_API_KEY).
Saves to stations_openaq.json — picked up automatically by index.html.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.openaq.org/v3"
ROOT = Path(__file__).parent
OUT = ROOT / "stations_openaq.json"

API_KEY = os.environ.get("OPENAQ_API_KEY", "").strip()
if not API_KEY:
    print(
        "OPENAQ_API_KEY not set. Get a free key from https://explore.openaq.org/register",
        file=sys.stderr,
    )
    sys.exit(2)


def req(path: str, params: dict | None = None) -> dict:
    qs = "?" + urllib.parse.urlencode(params) if params else ""
    r = urllib.request.Request(
        f"{API}{path}{qs}",
        headers={"X-API-Key": API_KEY, "Accept": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read())


def find_temperature_parameter_id() -> int:
    data = req("/parameters", {"limit": 200})
    for p in data.get("results", []):
        if p.get("name", "").lower() in ("temperature", "temperature_c", "temperature_celsius"):
            return p["id"]
    raise RuntimeError("could not locate a temperature parameter id in OpenAQ")


def find_india_country_id() -> int:
    data = req("/countries", {"limit": 300})
    for c in data.get("results", []):
        if c.get("code") == "IN":
            return c["id"]
    raise RuntimeError("could not locate India country id in OpenAQ")


def fetch_india_temp_locations(country_id: int, param_id: int) -> list[dict]:
    out = []
    page = 1
    while True:
        data = req("/locations", {
            "countries_id": country_id,
            "parameters_id": param_id,
            "limit": 1000,
            "page": page,
        })
        results = data.get("results", [])
        out.extend(results)
        meta = data.get("meta", {})
        if len(results) < meta.get("limit", 1000) or len(out) >= meta.get("found", 0):
            break
        page += 1
        time.sleep(0.5)
    return out


def latest_value(location_id: int, sensor_ids: list[int]) -> dict | None:
    try:
        data = req(f"/locations/{location_id}/latest")
    except urllib.error.HTTPError:
        return None
    results = data.get("results", [])
    if not results:
        return None
    # Prefer the temperature sensor reading
    for rec in results:
        if rec.get("sensorsId") in sensor_ids:
            return {
                "value": rec.get("value"),
                "datetime": (rec.get("datetime") or {}).get("utc"),
            }
    return None


def main() -> int:
    print("resolving India + temperature ids...", file=sys.stderr)
    country_id = find_india_country_id()
    param_id = find_temperature_parameter_id()
    print(f"  country_id={country_id}  temperature parameter_id={param_id}", file=sys.stderr)

    locs = fetch_india_temp_locations(country_id, param_id)
    print(f"fetched {len(locs)} India locations reporting temperature", file=sys.stderr)

    stations = []
    for i, loc in enumerate(locs, 1):
        coords = loc.get("coordinates") or {}
        if coords.get("latitude") is None or coords.get("longitude") is None:
            continue
        temp_sensor_ids = [
            s["id"] for s in loc.get("sensors", [])
            if (s.get("parameter") or {}).get("id") == param_id
        ]
        latest = latest_value(loc["id"], temp_sensor_ids) if temp_sensor_ids else None
        stations.append({
            "id": loc["id"],
            "name": loc.get("name") or loc.get("locality") or f"loc-{loc['id']}",
            "city": loc.get("locality"),
            "lat": coords["latitude"],
            "lon": coords["longitude"],
            "provider": (loc.get("provider") or {}).get("name"),
            "temperature_c": latest["value"] if latest else None,
            "observed_at": latest["datetime"] if latest else None,
        })
        if i % 25 == 0:
            print(f"  {i}/{len(locs)} latest values pulled", file=sys.stderr)
        time.sleep(0.15)

    OUT.write_text(json.dumps({
        "source": "OpenAQ v3 — locations with temperature in India",
        "country_id": country_id,
        "parameter_id": param_id,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "stations": stations,
    }, indent=2))
    with_values = sum(1 for s in stations if s["temperature_c"] is not None)
    print(f"saved {len(stations)} stations ({with_values} with current temperature) → {OUT.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
