#!/usr/bin/env python3
"""Run fetch.py --json and reshape to snapshot_cities.json format."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "snapshot_cities.json"


def main() -> int:
    raw = subprocess.check_output(
        [sys.executable, str(ROOT / "fetch.py"), "--json"], text=True
    )
    payload = json.loads(raw)
    cities = []
    for entry in payload:
        c = entry["city"]
        cur = (entry.get("weather") or {}).get("current") or {}
        cities.append({
            "name": c["name"],
            "state": c["state"],
            "lat": c["lat"],
            "lon": c["lon"],
            "temperature_2m_c": cur.get("temperature_2m"),
            "apparent_temperature_c": cur.get("apparent_temperature"),
            "relative_humidity_pct": cur.get("relative_humidity_2m"),
            "wind_speed_10m_kmh": cur.get("wind_speed_10m"),
        })

    OUT.write_text(json.dumps({
        "source": "Open-Meteo /v1/forecast (current)",
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S+05:30"),
        "timezone": "Asia/Kolkata",
        "fields": ["temperature_2m_c", "apparent_temperature_c", "relative_humidity_pct", "wind_speed_10m_kmh"],
        "cities": cities,
    }, indent=2))
    print(f"wrote {len(cities)} cities → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
