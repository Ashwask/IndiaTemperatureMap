#!/usr/bin/env python3
"""
india_temp_pull.py
==================
Pull real-time (and recent) temperature readings for any Indian location
from multiple open / freemium sources and write a side-by-side comparison.

Sources covered
---------------
NO KEY NEEDED (work out of the box):
  - Open-Meteo                  open-meteo.com
  - NASA POWER (hourly, ~1 day lag)
                                power.larc.nasa.gov
  - IMD city forecast (public)  api.imd.gov.in
  - IMD AWS/ARG (community scrape)
                                mausam.imd.gov.in

KEY NEEDED (free signup; put keys in env vars):
  - Weather Union (Zomato)      WEATHER_UNION_KEY
  - OpenWeatherMap              OPENWEATHER_API_KEY
  - Visual Crossing             VISUAL_CROSSING_KEY
  - Tomorrow.io                 TOMORROW_IO_KEY
  - Ambee                       AMBEE_KEY
  - WeatherAPI.com              WEATHERAPI_KEY

Usage
-----
    # Default: runs the built-in Bengaluru/Mumbai/Pune/Delhi sample
    python india_temp_pull.py

    # Single lat/lon
    python india_temp_pull.py --lat 12.9784 --lon 77.6408 --name "Indiranagar"

    # Bring your own locations CSV (columns: name,lat,lon[,wu_locality_id])
    python india_temp_pull.py --locations my_points.csv

    # Output paths
    python india_temp_pull.py --csv out.csv --json out.json

Set API keys before running:
    export WEATHER_UNION_KEY="..."
    export OPENWEATHER_API_KEY="..."
    # etc.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TIMEOUT = 15  # seconds, per request
IST = timezone(timedelta(hours=5, minutes=30))

# API keys (read from environment so the script stays shareable)
KEYS = {
    "weather_union":  os.getenv("WEATHER_UNION_KEY"),
    "openweather":    os.getenv("OPENWEATHER_API_KEY"),
    "visual_crossing":os.getenv("VISUAL_CROSSING_KEY"),
    "tomorrow":       os.getenv("TOMORROW_IO_KEY"),
    "ambee":          os.getenv("AMBEE_KEY"),
    "weatherapi":     os.getenv("WEATHERAPI_KEY"),
}

# Default points — Bengaluru-heavy because that's the most likely use case here.
# For Weather Union, you need a locality_id (not lat/lon). Find your locality ID
# at weatherunion.com — these are common Bengaluru ones (verify on their site).
DEFAULT_LOCATIONS = [
    # name, lat, lon, weather_union_locality_id (optional)
    ("Bengaluru - Indiranagar",   12.9784, 77.6408, "ZWL004957"),
    ("Bengaluru - Whitefield",    12.9698, 77.7500, "ZWL008752"),
    ("Bengaluru - Jayanagar",     12.9250, 77.5938, "ZWL004991"),
    ("Bengaluru - Koramangala",   12.9352, 77.6245, "ZWL005764"),
    ("Mumbai - Bandra West",      19.0596, 72.8295, "ZWL003221"),
    ("Pune - Koregaon Park",      18.5362, 73.8939, None),
    ("Delhi - Connaught Place",   28.6315, 77.2167, None),
]

# IMD station/city IDs for the public city-forecast endpoint.
# Find more at https://city.imd.gov.in/citywx/menu.php
IMD_CITY_IDS = {
    "Bengaluru":  "43295",
    "Mumbai":     "43003",
    "Pune":       "43063",
    "Delhi":      "42182",
    "Hyderabad":  "43128",
    "Chennai":    "43279",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Reading:
    source: str
    location: str
    lat: float
    lon: float
    temperature_c: Optional[float] = None
    feels_like_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    wind_kph: Optional[float] = None
    observation_ts: Optional[str] = None   # ISO string (IST when possible)
    notes: str = ""
    error: Optional[str] = None


# Friendly display name per fetcher function name
SOURCE_NAMES = {
    "fetch_open_meteo":      "Open-Meteo",
    "fetch_nasa_power":      "NASA POWER",
    "fetch_imd":             "IMD",
    "fetch_met_norway":      "MET Norway",
    "fetch_7timer":          "7Timer",
    "fetch_metar":           "METAR (Iowa State)",
    "fetch_weather_union":   "Weather Union",
    "fetch_openweather":     "OpenWeatherMap",
    "fetch_visual_crossing": "Visual Crossing",
    "fetch_tomorrow":        "Tomorrow.io",
    "fetch_ambee":           "Ambee",
    "fetch_weatherapi":      "WeatherAPI",
}

ICAO_BY_CITY = {
    "Bengaluru": "VOBL", "Bangalore": "VOBL",
    "Mumbai": "VABB",
    "Delhi": "VIDP",
    "Pune": "VAPO",
    "Chennai": "VOMM",
    "Hyderabad": "VOHS",
    "Kolkata": "VECC",
    "Ahmedabad": "VAAH",
    "Kochi": "VOCI",
    "Goa": "VOGO",
    "Trivandrum": "VOTV",
    "Lucknow": "VILK",
    "Jaipur": "VIJP",
    "Nagpur": "VANP",
    "Bhubaneswar": "VEBS",
    "Guwahati": "VEGT",
}

USER_AGENT = os.getenv("OPEN_INDIA_TEMP_UA", "open-india-temp/1.0 (replace-me@example.com)")


def safe(fn):
    """Decorator: catch exceptions, return a Reading with .error filled."""
    display = SOURCE_NAMES.get(fn.__name__, fn.__name__)
    def wrapped(loc, *args, **kwargs):
        try:
            return fn(loc, *args, **kwargs)
        except requests.HTTPError as e:
            return Reading(source=display, location=loc["name"],
                           lat=loc["lat"], lon=loc["lon"],
                           error=f"HTTP {e.response.status_code}: {e.response.text[:120]}")
        except Exception as e:
            return Reading(source=display, location=loc["name"],
                           lat=loc["lat"], lon=loc["lon"],
                           error=f"{type(e).__name__}: {e}")
    wrapped.__name__ = fn.__name__
    return wrapped


# ---------------------------------------------------------------------------
# Source 1: Open-Meteo (free, no key)
# ---------------------------------------------------------------------------

@safe
def fetch_open_meteo(loc) -> Reading:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m",
        "timezone": "Asia/Kolkata",
        "wind_speed_unit": "kmh",
    }
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json().get("current", {})
    return Reading(
        source="Open-Meteo",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=d.get("temperature_2m"),
        feels_like_c=d.get("apparent_temperature"),
        humidity_pct=d.get("relative_humidity_2m"),
        wind_kph=d.get("wind_speed_10m"),
        observation_ts=d.get("time"),
        notes="ICON/IFS/GFS blend, ~11km grid",
    )


# ---------------------------------------------------------------------------
# Source 2: NASA POWER hourly (free, no key) — ~24h lag
# ---------------------------------------------------------------------------

@safe
def fetch_nasa_power(loc) -> Reading:
    # POWER hourly is typically available with ~1 day lag; query yesterday IST.
    yesterday = (datetime.now(IST) - timedelta(days=1)).strftime("%Y%m%d")
    url = "https://power.larc.nasa.gov/api/temporal/hourly/point"
    params = {
        "parameters": "T2M,RH2M,WS10M",
        "community": "RE",
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "start": yesterday,
        "end": yesterday,
        "format": "JSON",
        "time-standard": "LST",
    }
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    series = j["properties"]["parameter"]
    # Take the latest hour available (max key)
    t_series = series.get("T2M", {})
    valid = {k: v for k, v in t_series.items() if v not in (None, -999)}
    if not valid:
        raise RuntimeError("No valid T2M values returned")
    last_hr = max(valid)
    return Reading(
        source="NASA POWER",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=valid[last_hr],
        humidity_pct=series.get("RH2M", {}).get(last_hr),
        wind_kph=(series.get("WS10M", {}).get(last_hr, 0) or 0) * 3.6,
        observation_ts=f"{last_hr[:4]}-{last_hr[4:6]}-{last_hr[6:8]}T{last_hr[8:]}:00",
        notes="Satellite + MERRA-2 reanalysis, hourly, ~24h lag, 0.5° grid",
    )


# ---------------------------------------------------------------------------
# Source 3: IMD city forecast (public REST)
# ---------------------------------------------------------------------------

@safe
def fetch_imd(loc) -> Reading:
    # IMD's public city forecast needs a station ID, not lat/lon.
    # We pick the nearest in our small lookup; for production, ship the full
    # station-mapping CSV from city.imd.gov.in.
    city_id = loc.get("imd_city_id")
    if not city_id:
        # crude nearest-name match
        for name, cid in IMD_CITY_IDS.items():
            if name.lower() in loc["name"].lower():
                city_id = cid
                break
    if not city_id:
        raise RuntimeError("No IMD city_id mapped for this location")

    url = f"https://city.imd.gov.in/api/cityweather_loc.php"
    r = requests.get(url, params={"id": city_id}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    # The IMD payload is a list with the latest observation first
    rec = data[0] if isinstance(data, list) and data else data
    return Reading(
        source="IMD",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=float(rec.get("Today_Max_temp") or rec.get("Temperature") or 0) or None,
        humidity_pct=float(rec.get("Humidity") or 0) or None,
        observation_ts=rec.get("Date") or rec.get("DateTime"),
        notes=f"IMD station {city_id}. Endpoint sometimes returns daily, not real-time.",
    )


# ---------------------------------------------------------------------------
# Source 3b: MET Norway (ECMWF-backed, no key, polite User-Agent required)
# ---------------------------------------------------------------------------

@safe
def fetch_met_norway(loc) -> Reading:
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    r = requests.get(url, params={"lat": loc["lat"], "lon": loc["lon"]},
                     headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    series = (r.json().get("properties") or {}).get("timeseries") or []
    if not series:
        raise RuntimeError("MET Norway returned no timeseries")
    head = series[0]
    inst = (head.get("data", {}).get("instant", {}).get("details", {}))
    return Reading(
        source="MET Norway",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=inst.get("air_temperature"),
        humidity_pct=inst.get("relative_humidity"),
        wind_kph=(inst.get("wind_speed") or 0) * 3.6,
        observation_ts=head.get("time"),
        notes="ECMWF-backed, ~10km global model",
    )


# ---------------------------------------------------------------------------
# Source 3c: 7Timer (GFS-based, no key, no signup)
# ---------------------------------------------------------------------------

@safe
def fetch_7timer(loc) -> Reading:
    url = "https://www.7timer.info/bin/api.pl"
    r = requests.get(url, params={
        "lon": loc["lon"], "lat": loc["lat"],
        "product": "civil", "output": "json",
    }, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    dataseries = j.get("dataseries") or []
    if not dataseries:
        raise RuntimeError("7Timer returned no dataseries")
    first = dataseries[0]
    init = j.get("init")  # e.g., "2026052712"
    ts = f"{init[:4]}-{init[4:6]}-{init[6:8]}T{init[8:10]}:00" if init else None
    return Reading(
        source="7Timer",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=float(first.get("temp2m")) if first.get("temp2m") is not None else None,
        humidity_pct=float(first.get("rh2m", "").replace("%", "")) if first.get("rh2m") else None,
        wind_kph=(first.get("wind10m") or {}).get("speed"),
        observation_ts=ts,
        notes="GFS-based, 3-hourly forecast (first slot)",
    )


# ---------------------------------------------------------------------------
# Source 3d: METAR via Iowa State ASOS (real airport instruments)
# ---------------------------------------------------------------------------

@safe
def fetch_metar(loc) -> Reading:
    icao = loc.get("icao")
    if not icao:
        for key, code in ICAO_BY_CITY.items():
            if key.lower() in loc["name"].lower():
                icao = code
                break
    if not icao:
        raise RuntimeError("No ICAO mapped for this location (use --icao or add to ICAO_BY_CITY)")

    # Iowa State's current.json is the simplest endpoint
    url = "https://mesonet.agron.iastate.edu/api/1/currents.json"
    r = requests.get(url, params={"network": "IN__ASOS", "station": icao}, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    stations = j.get("data") or j.get("stations") or []
    if not stations:
        # Fallback: NWS/aviationweather METAR
        r2 = requests.get(
            "https://aviationweather.gov/api/data/metar",
            params={"ids": icao, "format": "json"}, timeout=TIMEOUT,
        )
        r2.raise_for_status()
        rows = r2.json()
        if not rows:
            raise RuntimeError(f"no current METAR for {icao}")
        rec = rows[0]
        return Reading(
            source="METAR (Iowa State)",
            location=loc["name"], lat=loc["lat"], lon=loc["lon"],
            temperature_c=rec.get("temp"),
            humidity_pct=None,
            wind_kph=(rec.get("wspd") or 0) * 1.852 if rec.get("wspd") else None,  # kt → kph
            observation_ts=rec.get("reportTime") or rec.get("obsTime"),
            notes=f"{icao} airport instrument (aviationweather.gov fallback)",
        )
    rec = stations[0]
    # Iowa State returns tmpf (°F) — convert
    tmpf = rec.get("tmpf") or rec.get("airtemp")
    t_c = (tmpf - 32) * 5 / 9 if tmpf not in (None, "M") else None
    relh = rec.get("relh")
    return Reading(
        source="METAR (Iowa State)",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=t_c,
        humidity_pct=float(relh) if relh not in (None, "M") else None,
        wind_kph=(rec.get("sknt") or 0) * 1.852 if rec.get("sknt") not in (None, "M") else None,
        observation_ts=rec.get("utc_valid") or rec.get("valid"),
        notes=f"{icao} airport instrument (~30 min refresh)",
    )


# ---------------------------------------------------------------------------
# Source 4: Weather Union (Zomato) — requires free API key
# ---------------------------------------------------------------------------

@safe
def fetch_weather_union(loc) -> Reading:
    if not KEYS["weather_union"]:
        raise RuntimeError("WEATHER_UNION_KEY not set")
    # The lat/lon endpoint covers any point Weather Union has a sensor near.
    # No locality_id needed — they auto-resolve to the nearest hyperlocal station.
    url = "https://www.weatherunion.com/gw/weather/external/v0/get_weather_data"
    headers = {"X-Zomato-Api-Key": KEYS["weather_union"]}
    r = requests.get(url, params={"latitude": loc["lat"], "longitude": loc["lon"]},
                     headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    d = j.get("locality_weather_data", {})
    if d.get("temperature") is None:
        raise RuntimeError("Weather Union accepted the point but returned no temperature (no nearby station)")
    return Reading(
        source="Weather Union",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=d.get("temperature"),
        humidity_pct=d.get("humidity"),
        wind_kph=(d.get("wind_speed") or 0) * 3.6 if d.get("wind_speed") else None,
        observation_ts=datetime.now(IST).isoformat(timespec="seconds"),
        notes="Zomato hyperlocal ground sensor (auto-resolved by lat/lon)",
    )


# ---------------------------------------------------------------------------
# Source 5: OpenWeatherMap — free key required
# ---------------------------------------------------------------------------

@safe
def fetch_openweather(loc) -> Reading:
    if not KEYS["openweather"]:
        raise RuntimeError("OPENWEATHER_API_KEY not set")
    r = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"lat": loc["lat"], "lon": loc["lon"],
                "appid": KEYS["openweather"], "units": "metric"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    j = r.json()
    main = j.get("main", {})
    wind = j.get("wind", {})
    return Reading(
        source="OpenWeatherMap",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=main.get("temp"),
        feels_like_c=main.get("feels_like"),
        humidity_pct=main.get("humidity"),
        wind_kph=(wind.get("speed") or 0) * 3.6,
        observation_ts=datetime.fromtimestamp(j.get("dt", 0), IST).isoformat(timespec="seconds"),
        notes="Model + stations blend",
    )


# ---------------------------------------------------------------------------
# Source 6: Visual Crossing — free key required
# ---------------------------------------------------------------------------

@safe
def fetch_visual_crossing(loc) -> Reading:
    if not KEYS["visual_crossing"]:
        raise RuntimeError("VISUAL_CROSSING_KEY not set")
    url = (f"https://weather.visualcrossing.com/VisualCrossingWebServices/"
           f"rest/services/timeline/{loc['lat']},{loc['lon']}/today")
    r = requests.get(url, params={
        "key": KEYS["visual_crossing"],
        "unitGroup": "metric",
        "include": "current",
    }, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    c = j.get("currentConditions", {})
    return Reading(
        source="Visual Crossing",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=c.get("temp"),
        feels_like_c=c.get("feelslike"),
        humidity_pct=c.get("humidity"),
        wind_kph=c.get("windspeed"),
        observation_ts=c.get("datetime"),
        notes="Multi-source blended",
    )


# ---------------------------------------------------------------------------
# Source 7: Tomorrow.io — free key required
# ---------------------------------------------------------------------------

@safe
def fetch_tomorrow(loc) -> Reading:
    if not KEYS["tomorrow"]:
        raise RuntimeError("TOMORROW_IO_KEY not set")
    r = requests.get(
        "https://api.tomorrow.io/v4/weather/realtime",
        params={"location": f"{loc['lat']},{loc['lon']}",
                "units": "metric",
                "apikey": KEYS["tomorrow"]},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    d = r.json().get("data", {})
    v = d.get("values", {})
    return Reading(
        source="Tomorrow.io",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=v.get("temperature"),
        feels_like_c=v.get("temperatureApparent"),
        humidity_pct=v.get("humidity"),
        wind_kph=(v.get("windSpeed") or 0) * 3.6,
        observation_ts=d.get("time"),
        notes="Proprietary model",
    )


# ---------------------------------------------------------------------------
# Source 8: Ambee (India-based) — free trial key required
# ---------------------------------------------------------------------------

@safe
def fetch_ambee(loc) -> Reading:
    if not KEYS["ambee"]:
        raise RuntimeError("AMBEE_KEY not set")
    r = requests.get(
        "https://api.ambeedata.com/weather/latest/by-lat-lng",
        params={"lat": loc["lat"], "lng": loc["lon"]},
        headers={"x-api-key": KEYS["ambee"], "Content-type": "application/json"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    j = r.json()
    d = (j.get("data") or [{}])[0] if isinstance(j.get("data"), list) else j.get("data", {})
    return Reading(
        source="Ambee",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=d.get("temperature"),
        feels_like_c=d.get("apparentTemperature"),
        humidity_pct=(d.get("humidity") or 0) * 100 if d.get("humidity") and d["humidity"] < 1 else d.get("humidity"),
        wind_kph=(d.get("windSpeed") or 0) * 3.6,
        observation_ts=datetime.now(IST).isoformat(timespec="seconds"),
        notes="India-based provider",
    )


# ---------------------------------------------------------------------------
# Source 9: WeatherAPI.com — free key required
# ---------------------------------------------------------------------------

@safe
def fetch_weatherapi(loc) -> Reading:
    if not KEYS["weatherapi"]:
        raise RuntimeError("WEATHERAPI_KEY not set")
    r = requests.get(
        "https://api.weatherapi.com/v1/current.json",
        params={"key": KEYS["weatherapi"], "q": f"{loc['lat']},{loc['lon']}"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    c = r.json().get("current", {})
    return Reading(
        source="WeatherAPI",
        location=loc["name"], lat=loc["lat"], lon=loc["lon"],
        temperature_c=c.get("temp_c"),
        feels_like_c=c.get("feelslike_c"),
        humidity_pct=c.get("humidity"),
        wind_kph=c.get("wind_kph"),
        observation_ts=c.get("last_updated"),
        notes="",
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

FETCHERS = [
    fetch_open_meteo,
    fetch_met_norway,
    fetch_7timer,
    fetch_nasa_power,
    fetch_metar,
    fetch_imd,
    fetch_weather_union,
    fetch_openweather,
    fetch_visual_crossing,
    fetch_tomorrow,
    fetch_ambee,
    fetch_weatherapi,
]


def collect_for(loc: dict) -> list[Reading]:
    return [f(loc) for f in FETCHERS]


def print_table(readings: list[Reading]) -> None:
    """Plain-text comparison table, no extra deps."""
    by_loc: dict[str, list[Reading]] = {}
    for r in readings:
        by_loc.setdefault(r.location, []).append(r)

    for loc_name, rows in by_loc.items():
        print(f"\n=== {loc_name} ===")
        print(f"{'SOURCE':<18} {'TEMP °C':>8} {'FEELS':>8} {'RH%':>6} {'WIND':>7}   TIMESTAMP / NOTE")
        print("-" * 90)
        for r in rows:
            if r.error:
                print(f"{r.source:<18} {'—':>8} {'—':>8} {'—':>6} {'—':>7}   [skip] {r.error}")
                continue
            t  = f"{r.temperature_c:>8.1f}" if r.temperature_c is not None else f"{'—':>8}"
            fl = f"{r.feels_like_c:>8.1f}"  if r.feels_like_c is not None  else f"{'—':>8}"
            h  = f"{r.humidity_pct:>6.0f}"  if r.humidity_pct is not None  else f"{'—':>6}"
            w  = f"{r.wind_kph:>7.1f}"      if r.wind_kph is not None      else f"{'—':>7}"
            ts = r.observation_ts or ""
            print(f"{r.source:<18} {t} {fl} {h} {w}   {ts}  {r.notes}")


def write_csv(readings: list[Reading], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(readings[0]).keys()))
        w.writeheader()
        for r in readings:
            w.writerow(asdict(r))


def write_json(readings: list[Reading], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in readings], f, indent=2, ensure_ascii=False)


def load_locations(args) -> list[dict]:
    if args.locations:
        rows: list[dict] = []
        with open(args.locations, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append({
                    "name": row["name"],
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "wu_locality_id": row.get("wu_locality_id") or None,
                    "imd_city_id": row.get("imd_city_id") or None,
                })
        return rows
    if args.lat is not None and args.lon is not None:
        return [{"name": args.name or f"({args.lat},{args.lon})",
                 "lat": args.lat, "lon": args.lon,
                 "wu_locality_id": args.wu_id, "imd_city_id": args.imd_id,
                 "icao": args.icao}]
    return [{"name": n, "lat": la, "lon": lo, "wu_locality_id": wu}
            for n, la, lo, wu in DEFAULT_LOCATIONS]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lat", type=float, help="single point latitude")
    p.add_argument("--lon", type=float, help="single point longitude")
    p.add_argument("--name", type=str, help="label for single point")
    p.add_argument("--wu-id", dest="wu_id", help="Weather Union locality id for single point")
    p.add_argument("--imd-id", dest="imd_id", help="IMD city id for single point")
    p.add_argument("--icao", help="ICAO airport code (e.g. VOBL) for METAR lookup")
    p.add_argument("--locations", help="CSV file of locations (name,lat,lon[,wu_locality_id,imd_city_id])")
    p.add_argument("--csv",  default="india_temp_readings.csv", help="output CSV path")
    p.add_argument("--json", default="india_temp_readings.json", help="output JSON path")
    p.add_argument("--quiet", action="store_true", help="skip console table")
    args = p.parse_args()

    locs = load_locations(args)
    print(f"Pulling from {len(FETCHERS)} sources for {len(locs)} location(s)…", file=sys.stderr)

    # Show which keys are missing so the user knows what's skipped
    missing = [k for k, v in KEYS.items() if not v]
    if missing:
        print(f"  (no key set for: {', '.join(missing)} — those sources will report 'skip')",
              file=sys.stderr)

    all_readings: list[Reading] = []
    for loc in locs:
        all_readings.extend(collect_for(loc))

    if not args.quiet:
        print_table(all_readings)

    write_csv(all_readings,  args.csv)
    write_json(all_readings, args.json)
    print(f"\nWrote {args.csv} and {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
