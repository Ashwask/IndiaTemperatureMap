# India Temperature Map

[![License: CC BY-SA 4.0](https://img.shields.io/badge/License-CC%20BY--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-sa/4.0/)
[![Live](https://img.shields.io/badge/live-indiatemperaturemap.pages.dev-008080)](https://indiatemperaturemap.pages.dev/)

An open hyperlocal India temperature platform. Pulls real-time temperature
data from every public/freemium source we could reach and overlays them on a
single Leaflet map — three browser-live models per city, a 4,647-cell heat
grid covering India's full claim, plus ground-sensor networks where they exist.

**Live site:** https://indiatemperaturemap.pages.dev/

## On the map

- **39 city points** — three independent models browser-live on every page load:
  *Open-Meteo* (ICON/IFS/GFS blend, batched), *MET Norway* (ECMWF-backed), and
  *7Timer* (GFS). Popups show all three values plus the model-spread Δ; if the
  spread exceeds 3 °C, it's flagged red.
- **0.25° heat grid · 4,647 cells (~27 × 25 km each)** covering India's full
  territorial claim — mainland + Andaman & Nicobar + Lakshadweep + J&K (incl.
  PoK) + Ladakh (incl. Aksai Chin + Karakoram). Polygon: simplified from
  `datameet/maps` composite. Range typically –22 °C in Karakoram to +41 °C in
  Rajasthan.
- **OpenAQ ground stations** — ~570 India stations (509 CPCB regulatory +
  AirGradient + Clean Air Catalyst). ~340 report current temperature.
- **Weather Union ground sensors** — Zomato's hyperlocal fleet, ~37 discovered
  points across Bengaluru / Mumbai / Delhi-NCR / Pune / Hyderabad / Chennai /
  Kolkata / Ahmedabad / Jaipur / Lucknow / Chandigarh / Indore / Coimbatore.
- **Multi-source comparison sample** — all 39 cities × up to 12 source readings,
  side-by-side in the **Sources** tab.

## UI

Four tabs:

| Tab | What it shows |
|---|---|
| **Live Map** | Leaflet map with overlays. Layer control starts collapsed; hover to expand, mouse-out to dismiss. Pan-locked to India's bbox with a translucent mask fading out neighbouring countries. |
| **Trends** | Today's 39-city distribution, six-band histogram, and the All-India 1980-2025 annual-mean trend (Open-Meteo ERA5 archive). |
| **Sources** | All 12 providers with status badges (`ok · key needed · IP gated · idle`), plus the per-city × per-source comparison matrix. |
| **About** | Project description, data sources, what's gated, and License. |

Responsive: sidebar stacks above map on ≤ 768 px, cards collapse to single
column on ≤ 480 px, Leaflet zoom buttons enlarge to 36 × 36 px for touch.

## Data freshness

| Layer | Mode | Refresh |
|---|---|---|
| 39 cities · 3 models | **browser-live** | every page load |
| 0.25° heat grid | server snapshot | every 3 h via GitHub Actions |
| OpenAQ stations | server snapshot | every 3 h via GitHub Actions |
| Weather Union sensors | server snapshot | every 3 h via GitHub Actions |
| Multi-source comparison | server snapshot | every 3 h via GitHub Actions |

The cron lives in `.github/workflows/refresh-data.yml`. It runs every 3 hours
UTC (and on manual trigger via `gh workflow run refresh-data.yml`), commits the
refreshed JSONs, and GitHub Pages rebuilds within ~1 minute. Repo secrets
`OPENAQ_API_KEY` and `WEATHER_UNION_KEY` are required.

## Source matrix

| Source | Key | Status | Browser-live? | Notes |
|---|---|---|---|---|
| Open-Meteo | none | ✅ | ✅ | ICON/IFS/GFS blend, ~11 km grid; batched call |
| MET Norway | none | ✅ | ✅ (streamed) | ECMWF-backed, ~10 km |
| 7Timer | none | ✅ | ✅ (streamed) | GFS forecast, first 3-hour slot |
| METAR (Iowa State) | none | ✅ | ❌ (no CORS) | Real airport instruments, 16 Indian ICAOs |
| NASA POWER | none | ⚠ | ❌ | ~24 h lag; often empty for today |
| Weather Union | `WEATHER_UNION_KEY` | ✅ | ❌ (key) | Zomato hyperlocal ground sensors; lat/lon auto-resolved |
| OpenAQ | `OPENAQ_API_KEY` | ✅ | ❌ (key) | CPCB + community AQ sensors with temperature |
| IMD | — | ❌ | — | `api.imd.gov.in` IP-gated; formal request only |
| CPCB realtime · data.gov.in | data.gov.in key | ⚠ | — | AQ pollutants only, no temperature field |
| OpenWeatherMap | `OPENWEATHER_API_KEY` | — | ❌ (key) | Wire when key provided |
| Visual Crossing | `VISUAL_CROSSING_KEY` | — | ❌ (key) | Wire when key provided |
| Tomorrow.io | `TOMORROW_IO_KEY` | — | ❌ (key) | Wire when key provided |
| Ambee | `AMBEE_KEY` | — | ❌ (key) | India-based provider |
| WeatherAPI | `WEATHERAPI_KEY` | — | ❌ (key) | Wire when key provided |

Keys are read from env vars locally and from repo secrets in CI — never
checked in.

## Performance

The page is engineered to render fast even on a cold cache:

- **First paint** uses one batched Open-Meteo call + small static JSONs (~10 KB).
- **MET Norway + 7Timer** (78 per-city calls) fire AFTER initial render and
  stream into popups in the background (concurrency-capped at 8 to avoid
  socket exhaustion).
- **Grid weather** uses a compact columnar format (`{keys, cells}` instead of
  array-of-objects) — 845 KB → 116 KB (–86%).
- **All JSONs** are emitted with `separators=(',',':')` (no indentation) and
  gzipped on the wire by GitHub Pages.
- **Preconnect** hints for `api.open-meteo.com`, `api.met.no`, `www.7timer.info`
  shave 200–400 ms off the first model fetch.

## Repo layout

| File | Purpose |
|---|---|
| `index.html` | Leaflet UI (Live Map · Trends · Sources · About tabs) |
| `.github/workflows/refresh-data.yml` | Cron: refresh all snapshots every 3 h |
| `fetch.py` | 39-city Open-Meteo snapshot (CLI) |
| `build_snapshot_cities.py` | Reshape `fetch.py` output into `snapshot_cities.json` |
| `grid.py` | 0.25° lattice fetch over India, rate-aware + resumable (JSONL partial); writes v2-columnar weather file |
| `fetch_openaq.py` | OpenAQ India temperature stations |
| `fetch_datagovin.py` | CPCB AQ via data.gov.in (kept for completeness; AQ only) |
| `discover_weatherunion.py` | Probe Weather Union sensors across 88 Indian neighborhoods |
| `india_temp_pull.py` | Multi-source comparison fetcher (12 sources × N locations) |
| `build_india_trend.py` | All-India 1980-2025 annual mean from Open-Meteo archive (ERA5) |
| `cities.json` | 39-city coordinate list (state capitals + major metros) |
| `all_cities.csv` | Same 39 cities in CSV form (input to `india_temp_pull.py` in CI) |
| `india_polygon.json` | India full-claim MultiPolygon, simplified from datameet/maps |
| `LICENSE` · `NOTICE` | CC BY-SA 4.0 license + third-party source attributions |

### Generated data files (refreshed by cron)

| File | Description | Format |
|---|---|---|
| `snapshot_cities.json` | 39 cities × current Open-Meteo readings | array of city objects |
| `india_grid.json` | Grid-cell geometry | array of `{lat, lon}` |
| `india_grid_weather.json` | Grid-cell current weather | **v2-columnar** `{keys, cells}` |
| `india_temp_trend.json` | 1980-2025 All-India annual mean | array of `{year, temperature_c}` |
| `stations_openaq.json` | OpenAQ India temperature stations | array of station objects |
| `stations_weatherunion.json` | Weather Union discovered sensors | array of sensor objects |
| `india_temp_readings.json` | Multi-source comparison (12 × 39) | array of readings |

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
python3 build_india_trend.py
```

## Triggering a refresh in CI

```bash
gh workflow run refresh-data.yml --repo Ashwask/IndiaTemperatureMap
```

## Acknowledgements

Open-Meteo · OpenAQ · Zomato Weather Union · MET Norway · Iowa State ASOS ·
7Timer · NASA POWER · datameet/maps (India full-claim polygon).

## License

This work is licensed under the
[Creative Commons Attribution-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-sa/4.0/)
(CC BY-NC-SA 4.0). See [`LICENSE`](./LICENSE) for the full legal code and
[`NOTICE`](./NOTICE) for third-party data licenses.

In short: you may copy, share, and adapt the code and data freely **for
non-commercial purposes**, provided you give attribution and license any
derivative work under the same terms.
