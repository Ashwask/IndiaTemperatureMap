#!/usr/bin/env python3
"""Build an All-India annual mean temperature trend (1980-present).

Aggregates Open-Meteo's free historical-archive endpoint across 8 representative
cities spanning India's climatic zones. Output: india_temp_trend.json — drives
the sidebar sparkline in index.html.

No API key needed; the archive endpoint is unrestricted.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "india_temp_trend.json"

CITIES = [
    ("Delhi",     28.61, 77.21),
    ("Jaipur",    26.91, 75.79),
    ("Mumbai",    19.08, 72.88),
    ("Kolkata",   22.57, 88.36),
    ("Guwahati",  26.14, 91.74),
    ("Nagpur",    21.15, 79.09),
    ("Bangalore", 12.97, 77.59),
    ("Chennai",   13.08, 80.27),
]
START = "1980-01-01"
END = "2025-12-31"

def fetch() -> list[dict]:
    lats = ",".join(f"{c[1]}" for c in CITIES)
    lons = ",".join(f"{c[2]}" for c in CITIES)
    q = urllib.parse.urlencode({
        "latitude": lats,
        "longitude": lons,
        "start_date": START,
        "end_date": END,
        "daily": "temperature_2m_mean",
        "timezone": "Asia/Kolkata",
    })
    url = f"https://archive-api.open-meteo.com/v1/archive?{q}"
    with urllib.request.urlopen(url, timeout=180) as r:
        return json.loads(r.read())

def main() -> int:
    print(f"fetching {len(CITIES)} cities × {START[:4]}–{END[:4]}", file=sys.stderr)
    data = fetch()
    if not isinstance(data, list):
        data = [data]
    print(f"  got {len(data)} location series", file=sys.stderr)

    per_city = []
    for city, payload in zip(CITIES, data):
        daily = payload.get("daily", {})
        times = daily.get("time", [])
        temps = daily.get("temperature_2m_mean", [])
        by_year = defaultdict(list)
        for t, v in zip(times, temps):
            if v is None:
                continue
            by_year[int(t[:4])].append(v)
        annual = {y: sum(vs) / len(vs) for y, vs in by_year.items() if len(vs) >= 350}
        per_city.append((city[0], annual))

    # All-India mean = mean across cities for each year
    years = sorted(set().union(*[a.keys() for _, a in per_city]))
    series = []
    for y in years:
        vals = [a[y] for _, a in per_city if y in a]
        if len(vals) < len(CITIES) * 0.75:
            continue
        series.append({"year": y, "temperature_c": round(sum(vals) / len(vals), 3)})

    OUT.write_text(json.dumps({
        "source": "Open-Meteo /v1/archive (ERA5 reanalysis + recent IFS)",
        "title": "All-India mean temperature, 1980-present",
        "cities": [c[0] for c in CITIES],
        "method": "Annual mean per city, then mean across cities. Years with <350 days dropped.",
        "series": series,
    }, separators=(",", ":")))
    print(f"saved {len(series)} annual values → {OUT.name}", file=sys.stderr)
    delta = series[-1]["temperature_c"] - series[0]["temperature_c"]
    print(f"  {series[0]['year']}: {series[0]['temperature_c']}°C  →  {series[-1]['year']}: {series[-1]['temperature_c']}°C  (Δ {delta:+.2f}°C)", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
