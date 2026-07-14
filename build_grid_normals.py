#!/usr/bin/env python3
"""Build a 1991-2020 monthly temperature climatology for every grid cell.

The live grid (`india_grid_weather.json`) shows absolute temperature. To answer
"is this hotter or cooler than normal?" the frontend needs a baseline: the
WMO-standard 30-year (1991-2020) mean temperature for each cell, per calendar
month. We fetch ERA5 daily means from Open-Meteo's Archive API and average them
into 12 monthly normals.

Cost note: an archive call is weighted by locations × days, so a 30-year request
costs ~50 "API units" per location — the free tier's 5,000/hour budget only
covers ~100 locations/hour. Fetching all 4,647 grid cells directly would take
~2 days. Instead we fetch a COARSE lattice (default 1.0°, ~300 land points) and
interpolate each fine 0.25° cell from its nearest coarse points via inverse-
distance weighting. Monthly temperature normals vary smoothly in space, so this
is physically sound; mountain gradients are the main approximation.

Output `india_grid_normals.json` is STATIC — normals don't change, so this runs
once (or rarely), is committed, and is deliberately NOT part of the 3-hourly
refresh workflow. Re-run (optionally at a finer --coarse-res) only to refresh.

Reuses grid.py for the India polygon, lattice generation, and batching. The
fetch loop waits out Open-Meteo's hourly limit and resumes from a partial file.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from math import cos, radians
from pathlib import Path

from grid import chunked, generate_grid, load_india_polygons

ARCHIVE_API = "https://archive-api.open-meteo.com/v1/archive"
ROOT = Path(__file__).parent
GRID_FILE = ROOT / "india_grid.json"
NORMALS_FILE = ROOT / "india_grid_normals.json"
PARTIAL_FILE = ROOT / "india_grid_normals.partial.jsonl"

START_DATE = "1991-01-01"
END_DATE = "2020-12-31"
BASELINE = "1991-2020"


def load_grid() -> list[dict]:
    if not GRID_FILE.exists():
        raise SystemExit(f"{GRID_FILE.name} not found — run grid.py --no-fetch first")
    return json.loads(GRID_FILE.read_text())


def load_partial() -> tuple[list[dict], set[tuple[float, float]]]:
    """Read prior coarse-point results so a re-run can resume (mirrors grid.py)."""
    if not PARTIAL_FILE.exists():
        return [], set()
    done, keys = [], set()
    for line in PARTIAL_FILE.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        done.append(rec)
        keys.add((rec["lat"], rec["lon"]))
    return done, keys


def monthly_means(times: list[str], temps: list) -> list:
    """Average a daily series into 12 monthly normals. times are 'YYYY-MM-DD'."""
    sums = [0.0] * 12
    counts = [0] * 12
    for t, v in zip(times, temps):
        if v is None:
            continue
        month = int(t[5:7]) - 1
        sums[month] += v
        counts[month] += 1
    return [round(sums[m] / counts[m], 1) if counts[m] else None for m in range(12)]


def _seconds_until_utc_reset() -> float:
    """Seconds until just after the next 00:00 UTC (Open-Meteo's daily reset)."""
    now = datetime.now(timezone.utc)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return max(60.0, (nxt - now).total_seconds())


def fetch_archive_waiting(url: str, sleep_on_limit: float, max_wait_h: float) -> dict | list:
    """Fetch, waiting out Open-Meteo's rate limits and retrying transient errors.

    - Hourly 429 → sleep `sleep_on_limit` (default 10 min) and retry.
    - Daily 429 ("try again tomorrow") → sleep until just past the next 00:00 UTC.
    - Transient 400/5xx → short exponential backoff, a few attempts, then raise.
    Resumability (the JSONL partial) makes even an interrupted multi-day run safe.
    """
    waited = 0.0
    delay = 8.0
    transient = 0
    while True:
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()
            except Exception:
                pass
            low = body.lower()
            if e.code == 429:
                if "daily" in low:
                    wait = _seconds_until_utc_reset()
                    kind = "daily limit"
                elif "hourly" in low:
                    wait, kind = sleep_on_limit, "hourly limit"
                else:
                    wait, kind = sleep_on_limit, "rate limit"
                if waited + wait > max_wait_h * 3600:
                    raise RuntimeError(f"gave up after {waited/3600:.1f}h waiting: {body[:200]}")
                print(f"    {kind} — sleeping {wait:.0f}s (waited {waited/3600:.1f}h so far)", file=sys.stderr)
                time.sleep(wait)
                waited += wait
                continue
            # Non-429: occasionally the archive returns a transient 400/5xx. Retry
            # a few times, then give up (resume picks up where we left off).
            transient += 1
            if transient > 4:
                raise RuntimeError(f"HTTP {e.code} after {transient} retries: {body[:200]}")
            print(f"    HTTP {e.code} (transient {transient}/4) — backing off {delay:.0f}s: {body[:120]}", file=sys.stderr)
            time.sleep(delay)
            delay = min(delay * 2, 120)


def fetch_coarse(points: list[dict], chunk_size: int, sleep: float,
                 sleep_on_limit: float, max_wait_h: float) -> list[dict]:
    done, fetched_keys = load_partial()
    if done:
        print(f"resuming: {len(done)} coarse points already in {PARTIAL_FILE.name}", file=sys.stderr)
    remaining = [p for p in points if (p["lat"], p["lon"]) not in fetched_keys]
    total = (len(remaining) + chunk_size - 1) // chunk_size
    if total == 0:
        print("all coarse points already fetched", file=sys.stderr)
        return done

    results = list(done)
    with PARTIAL_FILE.open("a") as partial_fh:
        for i, batch in enumerate(chunked(remaining, chunk_size), 1):
            lats = ",".join(f"{p['lat']:.4f}" for p in batch)
            lons = ",".join(f"{p['lon']:.4f}" for p in batch)
            q = urllib.parse.urlencode({
                "latitude": lats,
                "longitude": lons,
                "start_date": START_DATE,
                "end_date": END_DATE,
                "daily": "temperature_2m_mean",
                "timezone": "Asia/Kolkata",
            })
            url = f"{ARCHIVE_API}?{q}"
            print(f"  chunk {i}/{total}: {len(batch)} coarse points", file=sys.stderr)
            data = fetch_archive_waiting(url, sleep_on_limit, max_wait_h)
            chunk_results = data if isinstance(data, list) else [data]
            for p, res in zip(batch, chunk_results):
                daily = res.get("daily", {}) or {}
                rec = {
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "normals": monthly_means(
                        daily.get("time", []) or [],
                        daily.get("temperature_2m_mean", []) or [],
                    ),
                }
                results.append(rec)
                partial_fh.write(json.dumps(rec) + "\n")
            partial_fh.flush()
            if i < total:
                time.sleep(sleep)
    return results


def interpolate(fine: list[dict], coarse: list[dict], k: int = 4) -> list[dict]:
    """Inverse-distance-weighted monthly normals for each fine cell from its k
    nearest coarse points. Equirectangular distance (fine for India's extent)."""
    # Drop coarse points with no usable data.
    coarse = [c for c in coarse if any(v is not None for v in c["normals"])]
    if not coarse:
        raise SystemExit("no coarse points with data — nothing to interpolate from")
    out = []
    for f in fine:
        flat, flon = f["lat"], f["lon"]
        cosl = cos(radians(flat))
        # squared equirectangular distance to every coarse point
        dists = []
        for c in coarse:
            dlat = c["lat"] - flat
            dlon = (c["lon"] - flon) * cosl
            dists.append((dlat * dlat + dlon * dlon, c))
        dists.sort(key=lambda t: t[0])
        nearest = dists[:k]
        # exact hit → use it directly
        if nearest[0][0] < 1e-9:
            out.append({"lat": flat, "lon": flon, "normals": list(nearest[0][1]["normals"])})
            continue
        normals = []
        for m in range(12):
            num = den = 0.0
            for d2, c in nearest:
                v = c["normals"][m]
                if v is None:
                    continue
                w = 1.0 / d2
                num += w * v
                den += w
            normals.append(round(num / den, 1) if den else None)
        out.append({"lat": flat, "lon": flon, "normals": normals})
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--coarse-res", type=float, default=1.0,
                   help="Coarse lattice resolution in degrees (default 1.0). Finer = better but slower.")
    p.add_argument("--chunk", type=int, default=50,
                   help="Coarse points per API call (default 50; archive rejects very large batches)")
    p.add_argument("--sleep", type=float, default=2.0, help="Sleep between successful chunks, seconds")
    p.add_argument("--sleep-on-limit", type=float, default=600.0,
                   help="Sleep when the hourly limit is hit, seconds (default 600)")
    p.add_argument("--max-wait-hours", type=float, default=48.0,
                   help="Give up if total rate-limit waiting exceeds this (default 48h — spans daily resets)")
    args = p.parse_args()

    fine = load_grid()
    polygons = load_india_polygons()
    coarse_pts = generate_grid(args.coarse_res, polygons)
    print(f"fine cells: {len(fine)} · coarse lattice ({args.coarse_res}°): {len(coarse_pts)} pts", file=sys.stderr)

    coarse = fetch_coarse(coarse_pts, args.chunk, args.sleep, args.sleep_on_limit, args.max_wait_hours)
    if len(coarse) < len(coarse_pts):
        print(f"incomplete: {len(coarse)}/{len(coarse_pts)} coarse points. Re-run to resume.", file=sys.stderr)
        return 1

    print(f"interpolating {len(fine)} fine cells from {len(coarse)} coarse points (IDW)…", file=sys.stderr)
    normals = interpolate(fine, coarse)

    cells = [[r["lat"], r["lon"], *r["normals"]] for r in normals]
    NORMALS_FILE.write_text(json.dumps(
        {
            "format": "v1-normals",
            "baseline": BASELINE,
            "source": "Open-Meteo /v1/archive (ERA5 reanalysis), daily temperature_2m_mean",
            "method": f"{args.coarse_res}° lattice ({len(coarse)} pts), IDW-interpolated to 0.25° grid",
            "keys": ["lat", "lon", "m1", "m2", "m3", "m4", "m5", "m6",
                     "m7", "m8", "m9", "m10", "m11", "m12"],
            "cells": cells,
        },
        separators=(",", ":"),
    ))
    print(f"normals: {len(cells)} cells → {NORMALS_FILE.name} (columnar)", file=sys.stderr)
    if PARTIAL_FILE.exists():
        PARTIAL_FILE.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
