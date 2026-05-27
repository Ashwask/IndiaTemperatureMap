# India Heat · Open Temperature Platform

An open hyperlocal India temperature map. Pulls and overlays real-time temperature
data from every public/freemium source we could reach.

**Live site:** https://ashwask.github.io/IndiaTemperatureMap/

## What's on the map

- **39 city points** — three models browser-live on every page load: Open-Meteo (ICON/IFS/GFS blend, batched), MET Norway (ECMWF-backed), and 7Timer (GFS). Popups show all three values plus the model-spread Δ.
- **0.25° heat grid** — **all 4,441 cells** covering India landmass (mainland + Andaman & Nicobar + Lakshadweep), colored by temperature. Range typically -19 °C in Ladakh to +41 °C in Rajasthan.
- **OpenAQ ground stations** — 570 India stations (509 CPCB + AirGradient + Clean Air Catalyst), ~340 with sane current temperature.
- **Weather Union ground sensors** — Zomato's hyperlocal sensor fleet, 37 discovered points spanning Bengaluru/Mumbai/Delhi-NCR/Pune/Hyderabad/Chennai/Kolkata/Ahmedabad/Jaipur/Lucknow/Chandigarh/Indore/Coimbatore.
- **Multi-source sample points** — every one of the 39 cities × up to 12 source readings, side-by-side comparison.
- **MODIS Aqua/Terra LST** — NASA EOSDIS GIBS satellite-derived Land Surface Temperature tiles, ~1 km native.

## Data freshness — what's live vs. cron

| Layer | Mode | Refresh |
|---|---|---|
| 39 cities · 3 models | **browser-live** | Every page load |
| MODIS LST | **live tiles** | NASA EOSDIS daily |
| 0.25° heat grid | server snapshot | Every 3 h via GitHub Actions |
| OpenAQ stations | server snapshot | Every 3 h via GitHub Actions |
| Weather Union sensors | server snapshot | Every 3 h via GitHub Actions |
| Multi-source comparison (12 sources) | server snapshot | Every 3 h via GitHub Actions |

The cron lives in `.github/workflows/refresh-data.yml`. It runs every 3 hours UTC and on manual trigger (`gh workflow run refresh-data.yml`), commits the refreshed JSON, and GitHub Pages rebuilds within ~1 minute.

## Source matrix

| Source | Key | Status | Browser-live? | Notes |
|---|---|---|---|---|
| Open-Meteo | none | ✅ | ✅ | ICON/IFS/GFS blend, ~11 km grid |
| MET Norway | none | ✅ | ✅ | ECMWF-backed, ~10 km |
| 7Timer | none | ✅ | ✅ | GFS forecast (first 3-hour slot) |
| METAR (Iowa State) | none | ✅ | ❌ (no CORS) | Real airport instruments, 16 Indian ICAOs |
| NASA POWER | none | ⚠ | ❌ | ~24 h lag, often empty for today |
| Weather Union | `WEATHER_UNION_KEY` | ✅ | ❌ (key) | Zomato hyperlocal ground sensors (lat/lon → nearest sensor) |
| OpenAQ | `OPENAQ_API_KEY` | ✅ | ❌ (key) | CPCB + community AQ sensors that also report temperature |
| IMD | — | ❌ | — | `api.imd.gov.in` IP-gated; formal request only |
| CPCB realtime · data.gov.in | data.gov.in key | ⚠ | — | AQ pollutants only, no temperature field |
| OpenWeatherMap | `OPENWEATHER_API_KEY` | — | ❌ (key) | Wire when key provided |
| Visual Crossing | `VISUAL_CROSSING_KEY` | — | ❌ (key) | Wire when key provided |
| Tomorrow.io | `TOMORROW_IO_KEY` | — | ❌ (key) | Wire when key provided |
| Ambee | `AMBEE_KEY` | — | ❌ (key) | India-based provider |
| WeatherAPI | `WEATHERAPI_KEY` | — | ❌ (key) | Wire when key provided |

Keys are read from env vars (locally) or repo secrets (in CI). Nothing API-key-related is checked in.

## Repo layout

| File | Purpose |
|---|---|
| `index.html` | Leaflet UI (Live Map · Trends · Sources · About tabs) |
| `.github/workflows/refresh-data.yml` | Cron: refreshes all snapshot JSONs every 3 hours |
| `fetch.py` | 39-city Open-Meteo snapshot (CLI) |
| `build_snapshot_cities.py` | Reshapes `fetch.py` output into the index.html input format |
| `grid.py` | 0.25° lattice fetch over India, rate-aware + resumable (JSONL partial) |
| `fetch_openaq.py` | OpenAQ India temperature stations (570 points) |
| `fetch_datagovin.py` | CPCB AQ via data.gov.in (AQ only, kept for completeness) |
| `discover_weatherunion.py` | Probe Weather Union sensors across 88 Indian neighborhoods |
| `india_temp_pull.py` | Multi-source comparison fetcher (12 sources × N locations) |
| `build_india_trend.py` | All-India 1980-2025 annual mean from Open-Meteo archive (ERA5) |
| `cities.json` | 39-city coordinate list (state capitals + major metros) |
| `all_cities.csv` | Same 39 cities in CSV form (input for `india_temp_pull.py` in CI) |
| `india_polygon.json` | India MultiPolygon from Natural Earth 50m |

### Generated data files (refreshed by cron)

| File | Description |
|---|---|
| `snapshot_cities.json` | 39 cities × current Open-Meteo readings |
| `india_grid.json` | 4,441 grid cells geometry |
| `india_grid_weather.json` | 4,441 cells × current weather |
| `india_temp_trend.json` | 1980-2025 annual mean temperature |
| `stations_openaq.json` | OpenAQ India temperature stations |
| `stations_weatherunion.json` | Weather Union discovered ground sensors |
| `india_temp_readings.json` | Multi-source comparison (39 cities × 12 sources) |

## Run locally

```bash
# 1. Serve the static site
python3 -m http.server 8765
open http://localhost:8765/

# 2. (Optional) Refresh any snapshot
python3 build_snapshot_cities.py
OPENAQ_API_KEY=...   python3 fetch_openaq.py
WEATHER_UNION_KEY=... python3 discover_weatherunion.py
python3 grid.py --resolution 0.25
WEATHER_UNION_KEY=... python3 india_temp_pull.py --locations all_cities.csv
```

## Triggering a refresh in CI

```bash
gh workflow run refresh-data.yml --repo Ashwask/IndiaTemperatureMap
```

The cron schedule is every 3 hours UTC. Repo secrets `OPENAQ_API_KEY` and
`WEATHER_UNION_KEY` are required.

## Acknowledgements

Open-Meteo · OpenAQ · NASA EOSDIS GIBS · Zomato Weather Union · MET Norway · Iowa State ASOS · 7Timer · Natural Earth · WRI Resource Watch.
