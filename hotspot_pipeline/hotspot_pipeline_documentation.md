# **Claims Hot-Spot Pipeline — File Reference** 

_Vuka / Discovery Gradhack 2026 — how the hot-spot, geocoding, and map files were built_ 

This document explains, file by file, how every artifact in the claims hot-spot pipeline was produced — what each script does, what it reads, what it writes, and specifically how hotspot_map.html gets built. It's meant as a reference for the team and for answering judges' questions about methodology. 

## **1. Pipeline Overview** 

Three files run in sequence, each one feeding the next: 

|**Step**|**Script**|**Produces**|
|---|---|---|
|**1. Clean**|clean_claims_data.py|claims_cleaned.csv, claims_cleaned.xlsx|
|**2. Aggregate + Geocode +**<br>**Map**|build_hotspots.py|hotspots.csv, hotspots_geocoded.csv,<br>hotspot_map.html|



**Run order matters:** clean_claims_data.py must run first, since build_hotspots.py reads claims_cleaned.csv as its input. Both scripts use plain relative filenames, so they must be run from the same folder that contains the source Gradhack_Insure_Data.xlsx file. 

## **2. clean_claims_data.py** 

**Reads:** <mark>Gradhack_Insure_Data.xlsx</mark> (the raw file Discovery provided — 15,712 claim records) 

**Writes:** <mark>claims_cleaned.csv</mark> and <mark>claims_cleaned.xlsx</mark> 

Performs five cleaning steps, each one adding a column or fixing a gap in the raw data: 

- **Parse dates** — INCIDENT_DATE_TIME is parsed into separate hour, day_of_week, and month columns, so time-based patterns (e.g. "burglaries peak at midnight") can be grouped later. 

- **Backfill ITEM_CATEGORY** — 196 rows (mostly Armed Robbery claims) had no ITEM_CATEGORY value. These are filled in using the existing "<Item Type> - <Peril>" naming pattern already present in the data (e.g. "Home contents - Theft"), extended to cover Armed Robbery and Attempted Hijack. Every backfilled row is flagged (item_category_was_backfilled = True) so this is fully auditable. 

- **Flag missing SUBURB** — 651 rows have no suburb recorded. These are kept (not deleted) but flagged (suburb_missing = True), since they're still useful for peril/time analysis even though they can't be placed on a map. 

- **Flag anomalous CLAIM_AMOUNT** — 81 rows have a claim amount of zero or below. These are flagged (claim_amount_anomalous = True) rather than removed — they still count as a real incident (kept in frequency counts) but are excluded whenever cost/severity is calculated. 

- **Standardize SUBURB text** — whitespace is trimmed and casing is uppercased on every suburb name, so "Sandton" and " sandton " (for example) would be treated as the same place when grouping. On the actual dataset this step confirmed the suburb names were already consistent — no variants needed merging. 

## **3. build_hotspots.py** 

**Reads:** <mark>claims_cleaned.csv</mark> 

**Writes:** <mark>hotspots.csv</mark> , <mark>hotspots_geocoded.csv</mark> , <mark>hotspot_map.html</mark> , and a small cache file <mark>geocode_cache.json</mark> 

### **3.1 Aggregating into hot-spots** 

The script groups every cleaned claim row by SUBURB (excluding the 651 flagged as missing) and computes, for each suburb: 

- incident_count — how many claims occurred there in total 

- top_claim_type — the most frequent peril in that suburb (e.g. Theft, Hijack, Armed Robbery), plus a full breakdown of every peril type present 

- peak_month, peak_day_of_week, peak_hour — the most common date/time pattern for incidents in that suburb, using the hour/day/month columns added in the cleaning step 

- total_claim_cost and avg_claim_cost — calculated using only the non-anomalous claims (claim_amount_anomalous == False), so the 81 flagged rows don't distort the cost figures 

**Only suburbs with 5 or more incidents are kept as genuine "hot-spots."** This threshold exists because geocoding and plotting all 2,929 unique suburbs in the raw data — most with only 1–2 incidents each — would add noise rather than signal, and would make the geocoding step (below) take far longer than necessary. The 5-incident threshold keeps 764 suburbs, covering roughly 75% of all usable claims — a defensible cut that separates a real recurring pattern from a one-off. 

### **3.2 Calculating the severity score** 

Each hot-spot suburb is scored using both how often incidents happen there AND how much they cost, not incident count alone: 

1. Incident count is normalized to a 0–1 scale across all hot-spot suburbs (the suburb with the most incidents scores 1.0, the suburb with the fewest scores near 0). 

2. Total claim cost is normalized the same way, using the non-anomalous cost figures. 

3. The two normalized scores are combined with equal weight: severity_score = 0.5 × frequency_score + 0.5 × cost_score. 

This means a suburb with fewer but far costlier incidents can outrank a higher-volume, lower-cost suburb. On the real dataset, for example, Bryanston (89 incidents, high average claim cost) ranks above Johannesburg (110 incidents, lower average cost) for exactly this reason. The 50/50 weighting is a deliberate but adjustable choice, not a fixed law — it could be changed to weight cost or frequency more heavily depending on whether the priority is "patrol where crime is most frequent" or "prevent the costliest losses." 

### **3.3 Geocoding — turning suburb names into map coordinates** 

The raw claims data only has suburb names as text (e.g. "SANDTON") — no latitude/longitude. To plot anything on a map, each hot-spot suburb name has to be converted into coordinates. This is done using **OpenStreetMap's Nominatim service** — a free, public geocoding API that requires no account or API key. 

How it works, step by step: 

4. For each hot-spot suburb, the script sends a request to Nominatim: "<suburb name>, South Africa" and asks for the best-matching location. 

5. If Nominatim finds a match, it returns a latitude and longitude, which is stored against that suburb. 

6. Every result (found or not found) is saved into a local cache file, geocode_cache.json, so that re-running the script later doesn't have to re-look-up suburbs it has already geocoded — this makes repeated runs much faster. 

7. Nominatim's usage policy requires no more than one request per second, so the script deliberately pauses for one second between each suburb lookup. For 764 hot-spot suburbs, this means the geocoding step takes roughly 13 minutes to complete on a full run. 

8. Suburbs that Nominatim can't find a match for are recorded as failed and excluded from the map (but remain in hotspots.csv, which has every hot-spot regardless of geocoding success). 

**Note on accuracy:** geocoding is done by suburb name alone (not suburb + province), so there's a small risk Nominatim occasionally matches a same-named suburb in the wrong province. It's worth spot-checking a handful of the top-ranked hot-spots on the resulting map against their known real location before presenting it. 

### **3.4 Building hotspot_map.html** 

Once every hot-spot has a latitude/longitude (from the geocoding step above), the script generates a single, selfcontained HTML file that renders an interactive map. Here's exactly what goes into it: 

- **Map engine:** Leaflet.js — a free, open-source JavaScript mapping library, loaded directly from a public CDN. No API key or paid service is required. 

- **Map tiles (the background map imagery):** OpenStreetMap's free tile service, also requiring no key. 

- **Markers:** one circle marker is placed on the map for every successfully geocoded hot-spot, at its latitude/longitude. 

- **Marker color and size are both driven by the severity score:** red circles for high severity (score ≥ 0.66), orange for medium (0.33–0.66), yellow for lower severity — and the circle's radius grows larger as severity increases, so the most severe hot-spots are visually the most prominent on the map at a glance. 

- **Pop-ups:** clicking any marker shows the suburb name, incident count, top claim type, peak day/time pattern, total and average claim cost, and the severity score — all pulled directly from that suburb's row in the aggregated hot-spot table. 

- **A legend** is fixed to the bottom-left of the map explaining the color scale. 

- **The map is centered on South Africa by default** (coordinates -28.5, 24.5) at a zoom level that shows the whole country on load. 

Because everything — the map library, the tile imagery, and all the marker data — is embedded or loaded from public sources inside one HTML file, **hotspot_map.html can be opened directly in any web browser by double-clicking it, with no server or installation needed** . It can also be uploaded to any basic web host, or embedded in a simple website, to satisfy the "map hosted on a website or mobile app" requirement from the brief. 

## **4. Output Files Reference** 

|**File**|**What it contains**|
|---|---|
|**claims_cleaned.csv / .xlsx**|Every original claim row, plus the added hour/day_of_week/month columns and the<br>three audit fags (item_category_was_backflled, suburb_missing,<br>claim_amount_anomalous).|
|**hotspots.csv**|One row per qualifying hot-spot suburb (764 total): incident count, claim-type<br>breakdown, peak date/tme, cost fgures, and severity score. No coordinates yet —<br>this is the full result of the aggregaton step, independent of whether geocoding<br>succeeds.|
|**hotspots_geocoded.csv**|Same as hotspots.csv, but only the rows that were successfully geocoded, with<br>lat/lon columns added. This is the exact data ploted on the map.|
|**hotspot_map.html**|The interactve map itself — open directly in a browser. Built from<br>hotspots_geocoded.csv's data at generaton tme (the coordinates and stats are<br>baked into the HTML fle, not loaded live).|
|**geocode_cache.json**|A small lookup fle mapping suburb name → coordinates (or "not found"), so re-<br>running the script doesn't repeat slow geocoding lookups for suburbs already<br>processed.|



## **5. Known Limitations** 

- Only suburbs with 5+ incidents are geocoded and mapped — lower-volume suburbs exist in the cleaned data but are intentionally excluded from the hot-spot view as noise. 

- Geocoding matches by suburb name + "South Africa" only, not suburb + province, so an occasional mismatch to a same-named suburb elsewhere in the country is possible and worth spot-checking. 

- The severity score's 50/50 frequency-vs-cost weighting is a design choice, not derived from the data — it can be adjusted if the team wants to prioritize differently. 

- Geocoding depends on a live internet connection to Nominatim at generation time; once hotspot_map.html is built, it is fully self-contained and works offline. 

