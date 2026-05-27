#!/usr/bin/env python3
"""Fetch current weather + 24h forecast for Indian cities via Open-Meteo.

Open-Meteo is free, no API key, AGPLv3 server (self-hostable), CC BY 4.0 data.
Docs: https://open-meteo.com/en/docs
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.open-meteo.com/v1/forecast"
CITIES_FILE = Path(__file__).parent / "cities.json"

CURRENT_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
]
HOURLY_FIELDS = ["temperature_2m", "precipitation_probability"]


def fetch(cities: list[dict], hours: int = 24) -> dict:
    lats = ",".join(f"{c['lat']:.4f}" for c in cities)
    lons = ",".join(f"{c['lon']:.4f}" for c in cities)
    q = urllib.parse.urlencode({
        "latitude": lats,
        "longitude": lons,
        "current": ",".join(CURRENT_FIELDS),
        "hourly": ",".join(HOURLY_FIELDS),
        "forecast_hours": hours,
        "timezone": "Asia/Kolkata",
    })
    with urllib.request.urlopen(f"{API}?{q}", timeout=30) as r:
        data = json.loads(r.read())
    return data if isinstance(data, list) else [data]


def print_table(cities: list[dict], results: list[dict]) -> None:
    print(f"{'City':<22} {'State':<22} {'Temp °C':>8} {'Feels':>7} {'RH %':>6} {'Wind':>6}")
    print("-" * 75)
    for city, res in zip(cities, results):
        cur = res.get("current", {})
        print(
            f"{city['name']:<22} {city['state']:<22} "
            f"{cur.get('temperature_2m', '?'):>8} "
            f"{cur.get('apparent_temperature', '?'):>7} "
            f"{cur.get('relative_humidity_2m', '?'):>6} "
            f"{cur.get('wind_speed_10m', '?'):>6}"
        )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--city", help="Filter to a single city (case-insensitive substring)")
    p.add_argument("--json", action="store_true", help="Emit raw JSON instead of table")
    p.add_argument("--hours", type=int, default=24, help="Forecast hours (default 24)")
    args = p.parse_args()

    cities = json.loads(CITIES_FILE.read_text())
    if args.city:
        needle = args.city.lower()
        cities = [c for c in cities if needle in c["name"].lower()]
        if not cities:
            print(f"no city matched '{args.city}'", file=sys.stderr)
            return 1

    results = fetch(cities, hours=args.hours)

    if args.json:
        json.dump(
            [{"city": c, "weather": r} for c, r in zip(cities, results)],
            sys.stdout,
            separators=(",", ":"),
        )
        print()
    else:
        print_table(cities, results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
