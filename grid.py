#!/usr/bin/env python3
"""Generate a lat/lon lattice over India and fetch Open-Meteo weather per cell.

Defaults to 0.25° (~25 km), which matches ERA5/GFS grid resolution and is what
Open-Meteo's underlying models actually serve. Drop to 0.1° if you want denser
sampling — note Open-Meteo will still interpolate from its native ~11 km grid.

Uses Natural Earth 50m country polygons to clip to India's landmass (mainland +
Andaman & Nicobar + Lakshadweep). Downloaded once and cached locally.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.open-meteo.com/v1/forecast"
ROOT = Path(__file__).parent
OUTLINE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_50m_admin_0_countries.geojson"
)
OUTLINE_CACHE = ROOT / "ne_50m_countries.geojson"
INDIA_POLY = ROOT / "india_polygon.json"
GRID_FILE = ROOT / "india_grid.json"
WEATHER_FILE = ROOT / "india_grid_weather.json"

PARTIAL_FILE = ROOT / "india_grid_weather.partial.jsonl"

INDIA_BBOX = (6.5, 37.5, 68.0, 97.5)  # min_lat, max_lat, min_lon, max_lon

CURRENT_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
]


def load_india_polygons() -> list:
    if INDIA_POLY.exists():
        return json.loads(INDIA_POLY.read_text())
    if not OUTLINE_CACHE.exists():
        print(f"downloading {OUTLINE_URL}", file=sys.stderr)
        with urllib.request.urlopen(OUTLINE_URL, timeout=60) as r:
            OUTLINE_CACHE.write_bytes(r.read())
    data = json.loads(OUTLINE_CACHE.read_text())
    for feat in data["features"]:
        props = feat.get("properties", {})
        if props.get("ADMIN") == "India" or props.get("NAME") == "India":
            geom = feat["geometry"]
            if geom["type"] == "Polygon":
                polygons = [geom["coordinates"]]
            elif geom["type"] == "MultiPolygon":
                polygons = geom["coordinates"]
            else:
                raise ValueError(f"unexpected geometry type: {geom['type']}")
            INDIA_POLY.write_text(json.dumps(polygons))
            return polygons
    raise RuntimeError("India not found in Natural Earth countries dataset")


def point_in_ring(lon: float, lat: float, ring: list) -> bool:
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi) + xi
        ):
            inside = not inside
        j = i
    return inside


def point_in_india(lon: float, lat: float, polygons: list) -> bool:
    for poly in polygons:
        outer = poly[0]
        if not point_in_ring(lon, lat, outer):
            continue
        for hole in poly[1:]:
            if point_in_ring(lon, lat, hole):
                break
        else:
            return True
    return False


def generate_grid(resolution: float, polygons: list) -> list[dict]:
    min_lat, max_lat, min_lon, max_lon = INDIA_BBOX
    points = []
    lat = min_lat
    while lat <= max_lat + 1e-9:
        lon = min_lon
        while lon <= max_lon + 1e-9:
            if point_in_india(lon, lat, polygons):
                points.append({"lat": round(lat, 4), "lon": round(lon, 4)})
            lon += resolution
        lat += resolution
    return points


def chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def fetch_with_backoff(url: str, max_retries: int = 6) -> dict | list:
    """Open-Meteo free tier: ~600 calls/min, 5k/hr, 10k/day; each location = 1 call.
    On 429, honor Retry-After header (or exponential backoff)."""
    delay = 8.0
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == max_retries - 1:
                raise
            ra = e.headers.get("Retry-After")
            wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else delay
            print(f"    429 — sleeping {wait:.0f}s (attempt {attempt + 1})", file=sys.stderr)
            time.sleep(wait)
            delay = min(delay * 2, 120)
    raise RuntimeError("unreachable")


def load_partial() -> tuple[list[dict], set[tuple[float, float]]]:
    """Read any prior partial results so a re-run can resume."""
    if not PARTIAL_FILE.exists():
        return [], set()
    done = []
    keys = set()
    for line in PARTIAL_FILE.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        done.append(rec)
        keys.add((rec["lat"], rec["lon"]))
    return done, keys


def fetch_grid(points: list[dict], chunk_size: int, sleep: float) -> list[dict]:
    done, fetched_keys = load_partial()
    if done:
        print(f"resuming: {len(done)} cells already in {PARTIAL_FILE.name}", file=sys.stderr)
    remaining = [p for p in points if (p["lat"], p["lon"]) not in fetched_keys]
    total = (len(remaining) + chunk_size - 1) // chunk_size
    if total == 0:
        print("all cells already fetched", file=sys.stderr)
        return done

    results = list(done)
    with PARTIAL_FILE.open("a") as partial_fh:
        for i, batch in enumerate(chunked(remaining, chunk_size), 1):
            lats = ",".join(f"{p['lat']:.4f}" for p in batch)
            lons = ",".join(f"{p['lon']:.4f}" for p in batch)
            q = urllib.parse.urlencode({
                "latitude": lats,
                "longitude": lons,
                "current": ",".join(CURRENT_FIELDS),
                "timezone": "Asia/Kolkata",
            })
            url = f"{API}?{q}"
            print(f"  chunk {i}/{total}: {len(batch)} points", file=sys.stderr)
            try:
                data = fetch_with_backoff(url)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    print(
                        f"  rate-limited after {len(results) - len(done)} new cells "
                        f"(plus {len(done)} resumed). Re-run later to continue.",
                        file=sys.stderr,
                    )
                    return results
                raise
            chunk_results = data if isinstance(data, list) else [data]
            for p, res in zip(batch, chunk_results):
                cur = res.get("current", {})
                rec = {
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "time": cur.get("time"),
                    "temperature_2m": cur.get("temperature_2m"),
                    "apparent_temperature": cur.get("apparent_temperature"),
                    "relative_humidity_2m": cur.get("relative_humidity_2m"),
                    "precipitation": cur.get("precipitation"),
                    "weather_code": cur.get("weather_code"),
                    "wind_speed_10m": cur.get("wind_speed_10m"),
                }
                results.append(rec)
                partial_fh.write(json.dumps(rec) + "\n")
            partial_fh.flush()
            if i < total:
                time.sleep(sleep)
    return results


def summarize(weather: list[dict]) -> None:
    temps = [w["temperature_2m"] for w in weather if w["temperature_2m"] is not None]
    if not temps:
        return
    hottest = max(weather, key=lambda w: w["temperature_2m"] or -999)
    coolest = min(weather, key=lambda w: w["temperature_2m"] if w["temperature_2m"] is not None else 999)
    print(
        f"\ntemp: min={min(temps):.1f}°C  max={max(temps):.1f}°C  "
        f"mean={sum(temps)/len(temps):.1f}°C  (n={len(temps)})",
        file=sys.stderr,
    )
    print(f"hottest cell: {hottest['lat']},{hottest['lon']} = {hottest['temperature_2m']}°C", file=sys.stderr)
    print(f"coolest cell: {coolest['lat']},{coolest['lon']} = {coolest['temperature_2m']}°C", file=sys.stderr)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--resolution", type=float, default=0.25, help="Grid resolution in degrees (default 0.25)")
    p.add_argument("--chunk", type=int, default=100, help="Points per API call (default 100)")
    p.add_argument("--sleep", type=float, default=11.0, help="Sleep between chunks, seconds (free tier: 600 locations/min)")
    p.add_argument("--no-fetch", action="store_true", help="Only build the grid, skip the API calls")
    args = p.parse_args()

    polygons = load_india_polygons()
    print(f"india polygons: {len(polygons)} ring-set(s)", file=sys.stderr)

    grid = generate_grid(args.resolution, polygons)
    GRID_FILE.write_text(json.dumps(grid))
    print(f"grid: {len(grid)} cells at {args.resolution}° → {GRID_FILE.name}", file=sys.stderr)

    if args.no_fetch:
        return 0

    weather = fetch_grid(grid, chunk_size=args.chunk, sleep=args.sleep)

    # Write a compact columnar format — ~85% smaller than the array-of-objects
    # form because the keys aren't repeated 4k+ times.
    def _round(v, n):
        return None if v is None else round(v, n)
    cells = [[
        round(w["lat"], 4),
        round(w["lon"], 4),
        _round(w.get("temperature_2m"), 1),
        w.get("relative_humidity_2m"),
        _round(w.get("wind_speed_10m"), 1),
    ] for w in weather]
    WEATHER_FILE.write_text(json.dumps(
        {"format": "v2-columnar", "keys": ["lat", "lon", "t", "rh", "w"], "cells": cells},
        separators=(",", ":"),
    ))
    print(f"weather: {len(weather)} cells → {WEATHER_FILE.name} (columnar)", file=sys.stderr)
    summarize(weather)
    if len(weather) == len(grid) and PARTIAL_FILE.exists():
        PARTIAL_FILE.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
