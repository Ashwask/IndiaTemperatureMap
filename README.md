# India Heat · Open Temperature Platform

An open hyperlocal India temperature map in the OAQ tradition. Pulls and overlays
real-time temperature data from every public/freemium source we could reach.

## What's on the map

- **39 city points** — Open-Meteo current readings (state capitals + metros)
- **0.25° heat grid** — ~3,900 cells covering India landmass, colored by temperature
- **OpenAQ ground stations** — 570 India stations (509 CPCB + AirGradient + others), ~340 with sane current temperature
- **Weather Union ground sensors** — Zomato's hyperlocal sensor fleet, 37 discovered points across 14 cities
- **Multi-source sample points** — 7 sample localities, each with up to 12 source readings for cross-comparison
- **MODIS Aqua/Terra LST** — NASA EOSDIS GIBS satellite-derived Land Surface Temperature tiles

## Source matrix

| Source | Key | Status | Notes |
|---|---|---|---|
| Open-Meteo | none | ✅ | ICON/IFS/GFS blend, ~11km |
| MET Norway | none | ✅ | ECMWF-backed |
| 7Timer | none | ✅ | GFS forecast |
| METAR (Iowa State) | none | ✅ | Real airport instruments, 16 Indian ICAOs |
| NASA POWER | none | ⚠ | ~24h lag, often empty for today |
| Weather Union | `WEATHER_UNION_KEY` | ✅ | Zomato hyperlocal ground sensors |
| OpenAQ | `OPENAQ_API_KEY` | ✅ | CPCB + community AQ sensors with temperature |
| IMD | — | ❌ | `api.imd.gov.in` IP-gated; formal request only |
| CPCB realtime | data.gov.in key | ⚠ | AQ pollutants only, no temperature field |
| OpenWeatherMap / Visual Crossing / Tomorrow.io / Ambee / WeatherAPI | various | — | Wire when keys provided |

## Repo layout

| File | Purpose |
|---|---|
| `index.html` | Leaflet UI (Live Map, Trends, Sources, About tabs) |
| `fetch.py` | 39-city Open-Meteo snapshot |
| `grid.py` | 0.25° lattice fetch over India, rate-aware + resumable |
| `fetch_openaq.py` | OpenAQ India temperature stations |
| `fetch_datagovin.py` | CPCB AQ via data.gov.in (AQ only, kept for completeness) |
| `discover_weatherunion.py` | Probe Weather Union sensors across Indian metros |
| `india_temp_pull.py` | Multi-source comparison fetcher (12 sources) |
| `build_india_trend.py` | All-India 1980-2025 trend from Open-Meteo archive |
| `cities.json` | 39 city coordinate list |
| `india_polygon.json` | India MultiPolygon from Natural Earth 50m |

Keys are read from env vars; nothing API-key-related is checked in.

## Run locally

```
python3 -m http.server 8765
open http://localhost:8765/
```

## Acknowledgements

Open-Meteo · OpenAQ · NASA EOSDIS GIBS · Zomato Weather Union · MET Norway · Iowa State ASOS · 7Timer · Natural Earth · WRI Resource Watch.
