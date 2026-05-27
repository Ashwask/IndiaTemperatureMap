#!/usr/bin/env python3
"""Probe Weather Union (Zomato) for sensor coverage across Indian metros.

Tries ~80 neighborhood-level lat/lon points; saves every hit (with current
temperature + humidity + AQI) to stations_weatherunion.json. The map auto-loads
that file as a "Weather Union ground sensors" layer.

Requires WEATHER_UNION_KEY in env.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

KEY = os.environ.get("WEATHER_UNION_KEY", "").strip()
if not KEY:
    print("WEATHER_UNION_KEY not set. Get one from weatherunion.com", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).parent
OUT = ROOT / "stations_weatherunion.json"
API = "https://www.weatherunion.com/gw/weather/external/v0/get_weather_data"

# Neighborhood-level probe points. Bengaluru/Mumbai/Delhi/Pune/Hyderabad have
# the densest Zomato fleet, so we lean into those.
PROBES = [
    # Bengaluru
    ("Bengaluru · Indiranagar",    12.9784, 77.6408),
    ("Bengaluru · Whitefield",     12.9698, 77.7500),
    ("Bengaluru · Jayanagar",      12.9250, 77.5938),
    ("Bengaluru · Koramangala",    12.9352, 77.6245),
    ("Bengaluru · Electronic City",12.8400, 77.6770),
    ("Bengaluru · HSR Layout",     12.9100, 77.6400),
    ("Bengaluru · Hebbal",         13.0450, 77.5910),
    ("Bengaluru · Marathahalli",   12.9568, 77.7011),
    ("Bengaluru · Bellandur",      12.9258, 77.6760),
    ("Bengaluru · Sarjapur",       12.8780, 77.7180),
    ("Bengaluru · BTM Layout",     12.9165, 77.6101),
    ("Bengaluru · Banashankari",   12.9251, 77.5468),
    ("Bengaluru · Rajajinagar",    12.9890, 77.5520),
    ("Bengaluru · Yelahanka",      13.1007, 77.5963),
    ("Bengaluru · Jp Nagar",       12.9081, 77.5853),
    ("Bengaluru · Indiranagar 100ft",12.9700,77.6400),
    # Mumbai
    ("Mumbai · Bandra West",       19.0596, 72.8295),
    ("Mumbai · Andheri East",      19.1190, 72.8470),
    ("Mumbai · Andheri West",      19.1364, 72.8296),
    ("Mumbai · Powai",             19.1170, 72.9060),
    ("Mumbai · Dadar",             19.0180, 72.8420),
    ("Mumbai · Worli",             19.0180, 72.8150),
    ("Mumbai · Lower Parel",       18.9960, 72.8290),
    ("Mumbai · Goregaon",          19.1640, 72.8500),
    ("Mumbai · Thane",             19.2183, 72.9781),
    ("Mumbai · Navi Mumbai",       19.0330, 73.0297),
    ("Mumbai · Mulund",            19.1720, 72.9560),
    ("Mumbai · Borivali",          19.2290, 72.8570),
    # Delhi NCR
    ("Delhi · Connaught Place",    28.6315, 77.2167),
    ("Delhi · Saket",              28.5210, 77.2050),
    ("Delhi · Hauz Khas",          28.5470, 77.2070),
    ("Delhi · Karol Bagh",         28.6510, 77.1900),
    ("Delhi · Dwarka",             28.5910, 77.0460),
    ("Delhi · Lajpat Nagar",       28.5670, 77.2430),
    ("Delhi · Rohini",             28.7350, 77.1200),
    ("Delhi · Pitampura",          28.7000, 77.1320),
    ("Gurgaon · DLF",              28.4720, 77.0930),
    ("Gurgaon · Cyber City",       28.4950, 77.0890),
    ("Noida · Sector 18",          28.5700, 77.3260),
    ("Noida · Sector 62",          28.6240, 77.3650),
    # Pune
    ("Pune · Koregaon Park",       18.5362, 73.8939),
    ("Pune · Kothrud",             18.5080, 73.8150),
    ("Pune · Hadapsar",            18.5020, 73.9290),
    ("Pune · Hinjawadi",           18.5910, 73.7380),
    ("Pune · Viman Nagar",         18.5680, 73.9140),
    ("Pune · Baner",               18.5610, 73.7800),
    ("Pune · Aundh",               18.5590, 73.8080),
    ("Pune · Kharadi",             18.5520, 73.9540),
    # Hyderabad
    ("Hyderabad · Banjara Hills",  17.4180, 78.4500),
    ("Hyderabad · Madhapur",       17.4480, 78.3920),
    ("Hyderabad · Gachibowli",     17.4400, 78.3480),
    ("Hyderabad · Jubilee Hills",  17.4300, 78.4080),
    ("Hyderabad · HITEC City",     17.4485, 78.3812),
    ("Hyderabad · Kukatpally",     17.4849, 78.4138),
    ("Hyderabad · Secunderabad",   17.4399, 78.4983),
    ("Hyderabad · Kondapur",       17.4647, 78.3673),
    # Chennai
    ("Chennai · T Nagar",          13.0430, 80.2320),
    ("Chennai · Velachery",        12.9740, 80.2200),
    ("Chennai · OMR",              12.8900, 80.2250),
    ("Chennai · Anna Nagar",       13.0830, 80.2180),
    ("Chennai · Adyar",            13.0067, 80.2570),
    ("Chennai · Porur",            13.0380, 80.1580),
    ("Chennai · Tambaram",         12.9249, 80.1000),
    # Kolkata
    ("Kolkata · Park Street",      22.5550, 88.3510),
    ("Kolkata · Salt Lake",        22.5800, 88.4200),
    ("Kolkata · Howrah",           22.5890, 88.2600),
    ("Kolkata · Ballygunge",       22.5310, 88.3650),
    ("Kolkata · New Town",         22.5760, 88.4720),
    # Other tier-1 / tier-2 metros
    ("Ahmedabad · SG Highway",     23.0300, 72.5080),
    ("Ahmedabad · Satellite",      23.0300, 72.5160),
    ("Jaipur · Vaishali Nagar",    26.9110, 75.7450),
    ("Jaipur · Malviya Nagar",     26.8520, 75.8230),
    ("Lucknow · Hazratganj",       26.8510, 80.9490),
    ("Lucknow · Gomti Nagar",      26.8570, 81.0050),
    ("Chandigarh · Sector 17",     30.7330, 76.7790),
    ("Indore · Vijay Nagar",       22.7521, 75.8937),
    ("Bhopal · MP Nagar",          23.2310, 77.4350),
    ("Nagpur · Civil Lines",       21.1457, 79.0820),
    ("Surat · Adajan",             21.1956, 72.7910),
    ("Vadodara · Alkapuri",        22.3140, 73.1860),
    ("Coimbatore · RS Puram",      11.0024, 76.9568),
    ("Visakhapatnam · Beach Rd",   17.7100, 83.3200),
    ("Kochi · MG Road",            9.9676,  76.2820),
    ("Goa · Panaji",               15.4909, 73.8278),
    ("Bhubaneswar · Master Canteen",20.2700, 85.8400),
    ("Patna · Boring Road",        25.6090, 85.1180),
    ("Ranchi · Main Road",         23.3550, 85.3260),
    ("Guwahati · Paltan Bazar",    26.1830, 91.7460),
]


def probe(name: str, lat: float, lon: float) -> dict | None:
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon})
    req = urllib.request.Request(
        f"{API}?{q}",
        headers={"X-Zomato-Api-Key": KEY, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read())
    except Exception as e:
        return {"name": name, "lat": lat, "lon": lon, "error": str(e)[:80]}
    d = j.get("locality_weather_data", {})
    if d.get("temperature") is None:
        return {"name": name, "lat": lat, "lon": lon, "error": "no nearby sensor"}
    return {
        "name": name, "lat": lat, "lon": lon,
        "temperature_c": d.get("temperature"),
        "humidity_pct": d.get("humidity"),
        "wind_speed_ms": d.get("wind_speed"),
        "wind_direction": d.get("wind_direction"),
        "rain_intensity": d.get("rain_intensity"),
        "aqi_pm10": d.get("aqi_pm_10"),
        "aqi_pm25": d.get("aqi_pm_2_point_5"),
    }


def main() -> int:
    print(f"probing {len(PROBES)} points...", file=sys.stderr)
    hits = []
    misses = []
    for i, (name, lat, lon) in enumerate(PROBES, 1):
        res = probe(name, lat, lon)
        if "error" in res:
            misses.append(res)
        else:
            hits.append(res)
        if i % 10 == 0:
            print(f"  {i}/{len(PROBES)} — hits={len(hits)} misses={len(misses)}", file=sys.stderr)
        time.sleep(0.25)

    OUT.write_text(json.dumps({
        "source": "Weather Union (Zomato) — hyperlocal ground sensors",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "stations": hits,
        "probed_misses": len(misses),
    }, indent=2))
    print(f"\nhits: {len(hits)}/{len(PROBES)}", file=sys.stderr)
    print(f"saved to {OUT.name}", file=sys.stderr)
    if hits:
        temps = [h["temperature_c"] for h in hits]
        print(f"temp range: {min(temps):.1f}°C – {max(temps):.1f}°C  (mean {sum(temps)/len(temps):.1f}°C)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
