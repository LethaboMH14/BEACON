# Vuka Claims Hot-Spot Map — Discovery Claims + SAPS Integration

Interactive hot-spot map combining Discovery's insurance claims data with
official SAPS (South African Police Service) crime statistics, built for
Project Vuka (Discovery Gradhack 2026).

**[See MAP_LEGEND_EXPLAINED.md](./MAP_LEGEND_EXPLAINED.md)** for a full
breakdown of every marker type, color, and legend entry on the map.

---

## What this is

A pipeline that:
1. Cleans Discovery's raw claims dataset (~15,700 incident records)
2. Aggregates it into per-suburb "hot-spots" with a severity score
3. Cross-references those hot-spots against real, official SAPS Q1 2026
   (January–March) crime statistics, where a matching police precinct exists
4. Fills in the gap that (3) alone leaves: SAPS precincts with real,
   significant crime activity but **no** corresponding Discovery claim, so
   the map never implies "no marker = safe" for an area Discovery simply
   has no data for
5. Plots all of it as a single interactive map (`hotspot_map.html`) you can
   open in any browser — no server, no login, no paid API required

---

## Quick start — regenerating the map

Run these five scripts, **in this exact order**, from the same folder:

```bash
python3 clean_claims_data.py      # -> claims_cleaned.csv
python3 build_hotspots.py          # -> hotspots.csv (claims-only hot-spots)
python3 integrate_saps.py          # -> hotspots_with_saps.csv
python3 build_saps_only.py         # -> saps_only_precincts.csv
python3 build_combined_map.py      # -> hotspot_map.html  (the final map)
```

Order matters — each script reads a file produced by the one before it.

### Required input files (must already be in the same folder)

| File | Where it comes from |
|---|---|
| `Gradhack_Insure_Data.xlsx` | Discovery's raw claims dataset, provided with the brief |
| `2025-2026_-_4th_Quarter_WEB.xlsx` | Official SAPS quarterly crime stats workbook, public download |

### What gets produced along the way

| File | Produced by | What it is |
|---|---|---|
| `claims_cleaned.csv` / `.xlsx` | `clean_claims_data.py` | Cleaned claims data, with data-quality flags added |
| `hotspots.csv` | `build_hotspots.py` | Claims-only hot-spot suburbs, with a severity score |
| `hotspots_with_saps.csv` | `integrate_saps.py` | Same table, with SAPS Q1 2026 figures joined on for suburbs with a known precinct mapping |
| `saps_only_precincts.csv` | `build_saps_only.py` | Real SAPS precincts with significant crime activity but **no** matching Discovery hot-spot |
| `hotspots_with_saps_geocoded.csv` | `build_combined_map.py` | The above, with map coordinates (lat/lon) attached |
| `saps_only_precincts_geocoded.csv` | `build_combined_map.py` | Same, for the SAPS-only precincts |
| `geocode_cache.json` | `build_combined_map.py` | Local cache of suburb/precinct name → coordinates, so re-running the pipeline doesn't repeatedly re-geocode the same names |
| **`hotspot_map.html`** | `build_combined_map.py` | **The final interactive map — open this in any browser** |

---

## Why regeneration takes time — geocoding

Suburb and precinct names in the raw data are just text (e.g. `"BRYANSTON"`,
`"Tembisa"`) — there's no latitude/longitude anywhere in the source files.
`build_combined_map.py` converts every name into map coordinates using
[OpenStreetMap's Nominatim](https://nominatim.openstreetmap.org/), a free,
public geocoding service that requires no account or API key.

Nominatim's usage policy caps requests at **1 per second**, so geocoding
hundreds of names takes several minutes on a fresh run. Every result gets
saved into `geocode_cache.json`, so **subsequent runs only geocode names
that weren't already resolved before** — a full re-run with a warm cache
typically finishes in seconds, not minutes.

---

## What the map shows, briefly

The map has **three distinct marker types**, so it never implies an area is
low-risk just because no marker happens to be there:

1. 🟢 **Green-ringed circles** — hot-spots with both Discovery claims data
   *and* a matched SAPS precinct (independently verified by both sources)
2. ⚪ **Grey-ringed circles** — hot-spots with Discovery claims data only, no
   SAPS precinct mapped yet
3. 🟦 **Blue squares** — real SAPS police precincts with significant crime
   activity but **no** corresponding Discovery claim at all

Circle size/color = Discovery severity score (combining incident frequency
and total claim cost). Square size/color = a separate, frequency-only SAPS
severity score — **the two scores are not directly comparable**, since SAPS
data has no claim-cost equivalent. See the full explainer doc for details.

---

## Known limitations

- **Suburb ↔ SAPS precinct mapping is manual.** SAPS records crime by
  police precinct, not suburb name, and there's no free, reliable public
  lookup table between the two. `integrate_saps.py` uses a small, hand-built
  mapping dictionary (`SUBURB_TO_PRECINCT`) that currently only covers a
  handful of suburbs — extend it with verified mappings for more coverage.
- **Geocoding matches by name + "South Africa" only**, not by province, so
  there's a small chance of matching a same-named place in the wrong part
  of the country. Worth spot-checking prominent markers before presenting.
- **The Discovery severity score's 50/50 frequency-vs-cost weighting is a
  design choice**, not derived from the data — it's a single configurable
  variable in `build_hotspots.py` if you want to adjust the priority.
- Only suburbs/precincts above a minimum incident threshold are included
  (5 for Discovery hot-spots, 10 for SAPS-only precincts) — this filters
  out one-off, statistically unreliable locations, not genuine risk areas
  below the noise floor.

---

## File/script reference

| Script | Reads | Writes |
|---|---|---|
| `clean_claims_data.py` | `Gradhack_Insure_Data.xlsx` | `claims_cleaned.csv`, `claims_cleaned.xlsx` |
| `build_hotspots.py` | `claims_cleaned.csv` | `hotspots.csv` (+ a claims-only version of the map, if run standalone) |
| `integrate_saps.py` | `hotspots.csv`, `2025-2026_-_4th_Quarter_WEB.xlsx` | `hotspots_with_saps.csv` |
| `build_saps_only.py` | `2025-2026_-_4th_Quarter_WEB.xlsx`, `hotspots_with_saps.csv` | `saps_only_precincts.csv` |
| `build_combined_map.py` | `hotspots_with_saps.csv`, `saps_only_precincts.csv` | `hotspot_map.html` and geocoded CSVs |
