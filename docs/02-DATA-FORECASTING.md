# BEACON — 02 Data Engineering + Forecasting (Ndu's spec)

> Owner: Ndu. Status: v1.0, 2026-07-24. Your day-one document is `team/NDU.md`; this is the full technical spec behind it.

## 1. The asset

`Gradhack_Insure_Data.xlsx` — 15,712 claims, 2021-07-04 → 2026-06-28.
Columns: Incident, PERIL, SUBURB, ITEM_TYPE, VEHICLE_MAKE, VEHICLE_MODEL, VEHICLE_YEAR, INCIDENT_DATE_TIME, CLAIM_AMOUNT, ITEM_CATEGORY, ITEM_PERIL_DESCR.

Known facts to build around (verified in exploration):
- PERIL: Theft 14,380 · Hijack 680 · Armed Robbery 272 · Burglary 214 · Stolen-and-recovered 66 · Attempted Theft 41 · Remote jamming 7 · SOS 4 …
- Theft splits: Contents 8,533 (R406.6M) / Vehicle 5,847 (R686.3M). Violent perils = 6.1%.
- Hour histogram: 00:00 = 1,296 claims (≈3× the 05:00 trough of 396); daytime plateau 10:00–15:00.
- Top suburbs: NULL 651(!), JOHANNESBURG 110, SOMERSET WEST 107, RONDEBOSCH 102, RUSTENBURG 99, CAPE TOWN CBD 93, BRYANSTON 89.
- CLAIM_AMOUNT: min −26,989 (reversals), max 2,749,949, mean 80,513.
- Vehicle makes: TOYOTA 1,939, VW 1,112, FORD 721 — matches national theft-target lists (credibility point).

## 2. Cleaning rules ("synthesize the data properly")

1. Negative amounts = reversals → keep, flag `is_reversal`, exclude from severity stats.
2. NULL/blank suburbs (651) → `unknown` bucket; report coverage % honestly on every chart.
3. Suburb strings: uppercase-trim, collapse variants (CBD suffixes, "EXT n"), maintain `suburb_alias.csv` mapping — checked in, hand-curated as you find junk.
4. Timestamps → Africa/Johannesburg; derive hour, weekday, month, is_holiday (SA public holidays lib), is_payday_window (25th–1st — SASSA/salary window is a known SA crime covariate), school_term flag.
5. Midnight caveat: part of the 00:00 spike is "discovered next morning, time unknown" coding. Handle with an `hour_known` flag — estimate the true overnight window (e.g. last-seen 22:00 → discovered 06:00) as an interval, don't pretend precision. Say this in the pitch; judges' analysts WILL ask.
6. Duplicates: same Incident id / same suburb+datetime+amount → dedupe with log.

## 3. Geocoding + spatial grid

- Nominatim (OpenStreetMap) batch geocode "SUBURB, South Africa" → lat/lng; cache to `data/geocode/suburbs.json` (checked in — never live-geocode in the demo). ~1s/req rate limit ⇒ run once, early. Fallback: manual coordinates for top-50 suburbs.
- Snap to **H3 res 8** (~0.7 km² — suburb-scale truth given no street addresses), res 9 display. Note honestly: claims resolve to suburb centroids; camera sightings are true point data — the fusion of coarse claims + precise cameras is the story, not a limitation.

## 4. Enrichment feeds (the context prior — our uniquely-SA edge)

| Feed | Source | Use |
|---|---|---|
| Weather | WeatherAPI (key already secured — get from Sbu directly, NEVER commit) | rain/temp/moon-dark nights correlate with burglary patterns |
| Load reduction / outages | EskomSePush API (key with Sbu) — area-level schedules incl. municipal load reduction, not just Eskom stages | dark streets, dead alarms, dead cameras ⇒ risk multiplier + "camera offline" ops awareness |
| Events / marches | SAPS Gatherings Act notices, municipal event calendars, EventsSA scraping — day-0: hand-seeded `events.csv` (`sim_` labelled) | crowd events shift patrol availability + displacement risk |
| Paydays/holidays/school terms | static calendars | known SA temporal covariates |
| SAPS quarterly stats | already extracted in VUKA work (Q3 2025-26) | station-area priors where claims are sparse |

## 5. Forecasting stack (the "massive unique forecasting")

Layered, explainable — each layer is a named, defensible technique:

1. **Baseline:** hex × hour × weekday Poisson/negative-binomial rates (statsmodels) with empirical-Bayes shrinkage toward suburb/city means (sparse-hex safety).
2. **Near-repeat kernel:** after each claim/incident, add exponentially-decaying risk (space ≈400 m, time ≈14 days) — Johnson & Bowers repeat-victimization; the "contagion" layer.
3. **Risk terrain (lite):** static environmental covariates per hex from OSM — taverns/shebeens, transit stops, highway on-ramps (getaway routes), vacant land, lighting proxy (Caplan & Kennedy RTM).
4. **Boosted correction:** LightGBM on (baseline, near-repeat, terrain, weather, outage, payday, event) → next-24h expected count per hex-hour. SHAP values give the "why" chips the UI shows.
5. **Calibration + eval:** reliability curve; headline metric = **hit-rate@top-5% hexes (PAI)** vs a naive last-4-weeks baseline. We show the honest uplift number, never "94.3% accurate".

Output: `risk_cells(hex, hour, score, top_factors[])` → map layer, routing input, suspicion factor F2/F3.

## 6. Routing (with Sbu)

OR-Tools team-orienteering / prize-collecting VRP: maximize Σ(risk × Koper-dose coverage) subject to shift time + fuel budget; 12-min dwell per stop (Koper 1995: 11–15 min dose → next-30-min crime likelihood 15%→4%); time-dynamic (route for 22:00–02:00 ≠ 14:00 route). Re-plan on alert. Output: fuel-saved % + coverage % vs naive fixed loop — THE demo counters.

## 7. Deliverables checklist

- [ ] G0 (12:00): xlsx → clean parquet; hour histogram + peril split charts; top-20 suburb table
- [ ] G0: geocode cache for top suburbs; first MapLibre heatmap JSON
- [ ] G1: baseline + near-repeat model; `risk_cells` endpoint feeding the map
- [ ] G2: LightGBM + calibration + PAI eval vs baseline; routing demo with fuel counter
- [ ] G2: enrichment feeds wired (weather + outage real; events `sim_` seeded)
- [ ] docs/05 business case numbers (with Sali)
