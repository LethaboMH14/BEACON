"""
Vuka / Discovery Gradhack — Claims Hot-Spot Identification

Implements the two high-level requirements:
  1. Ingesting and processing claims data: identify recurring areas and their
     associated dates, claim type, and claim cost to determine severity/risk.
  2. Identify hot-spot locations: categorise hot-spots by location, date,
     and claim type — output ready to plot on a map.

INPUT: claims_cleaned.csv (output of clean_claims_data.py)

WHAT THIS SCRIPT DOES
----------------------
1. Filters to rows with a usable suburb (excludes the 651 flagged as missing)
2. Groups by SUBURB to compute, per suburb:
     - incident_count (frequency / recurrence)
     - top claim types present (PERIL breakdown)
     - peak month and peak hour (associated dates/times)
     - total and average claim cost, using ONLY non-anomalous claims
       (claim_amount_anomalous == False) for the cost figures, per the
       cleaning script's own guidance
     - a composite hot-spot severity score combining frequency AND cost,
       not just raw incident count (a suburb with fewer but costlier
       incidents can outrank a high-volume, low-cost suburb)
3. Restricts hot-spot output to suburbs with >= MIN_INCIDENTS incidents
   (default 5) — see note below on why this threshold, not geocoding all
   2,929 suburbs
4. Geocodes only the qualifying suburbs (via OpenStreetMap Nominatim,
   free, no API key) and caches results to avoid re-geocoding on reruns
5. Outputs:
     - hotspots.csv           (full table: every qualifying suburb + stats)
     - hotspots_geocoded.csv  (same, with lat/lon, only successfully geocoded rows)
     - hotspot_map.html       (interactive Leaflet map, open directly in a browser
                                or embed in a simple website for the demo)

WHY A MIN_INCIDENTS THRESHOLD, NOT ALL 2,929 SUBURBS
------------------------------------------------------
Geocoding 2,929 free-text suburb names against a public geocoder within a
hackathon timeline risks rate-limiting and hours of runtime for suburbs
that only have 1-2 incidents each (noise, not a genuine hot-spot pattern).
MIN_INCIDENTS=5 keeps 764 suburbs covering ~75% of usable claims — a
defensible "these are real recurring patterns" cutoff you can state
plainly if a judge asks why not every suburb is plotted.
"""

import pandas as pd
import time
import json
import os
import requests

INPUT_CSV = "claims_cleaned.csv"
OUTPUT_HOTSPOTS_CSV = "hotspots.csv"
OUTPUT_GEOCODED_CSV = "hotspots_geocoded.csv"
OUTPUT_MAP_HTML = "hotspot_map.html"
GEOCODE_CACHE_PATH = "geocode_cache.json"

MIN_INCIDENTS = 5  # threshold for a suburb to count as a genuine hot-spot


def load_cleaned_data():
    df = pd.read_csv(INPUT_CSV)
    df["INCIDENT_DATE_TIME"] = pd.to_datetime(df["INCIDENT_DATE_TIME"])
    print(f"Loaded {len(df)} cleaned claim rows.")
    return df


def build_hotspot_table(df):
    """
    Group by SUBURB and compute frequency, claim-type breakdown, peak
    date/time patterns, and cost-based severity for each.
    """
    # Only rows with a usable suburb
    usable = df[df["suburb_missing"] == False].copy()
    print(f"Usable rows (suburb present): {len(usable)} / {len(df)}")

    # Cost figures use only non-anomalous claim amounts
    cost_rows = usable[usable["claim_amount_anomalous"] == False]

    records = []
    for suburb, group in usable.groupby("SUBURB"):
        incident_count = len(group)
        if incident_count < MIN_INCIDENTS:
            continue

        # Claim type breakdown (which perils occur here, and how often)
        peril_counts = group["PERIL"].value_counts()
        top_peril = peril_counts.index[0]
        top_peril_count = int(peril_counts.iloc[0])
        peril_breakdown = "; ".join(f"{p}:{c}" for p, c in peril_counts.items())

        # Associated dates: peak month and peak hour for this suburb
        peak_month = group["month"].value_counts().index[0]
        peak_hour = int(group["hour"].value_counts().index[0])
        peak_day_of_week = group["day_of_week"].value_counts().index[0]

        # Cost/severity — use only non-anomalous rows for this suburb
        suburb_cost_rows = cost_rows[cost_rows["SUBURB"] == suburb]
        total_cost = suburb_cost_rows["CLAIM_AMOUNT"].sum()
        avg_cost = suburb_cost_rows["CLAIM_AMOUNT"].mean() if len(suburb_cost_rows) > 0 else 0
        n_anomalous_excluded = incident_count - len(suburb_cost_rows)

        records.append({
            "SUBURB": suburb,
            "incident_count": incident_count,
            "top_claim_type": top_peril,
            "top_claim_type_count": top_peril_count,
            "claim_type_breakdown": peril_breakdown,
            "peak_month": peak_month,
            "peak_day_of_week": peak_day_of_week,
            "peak_hour": peak_hour,
            "total_claim_cost": round(total_cost, 2),
            "avg_claim_cost": round(avg_cost, 2),
            "anomalous_claims_excluded_from_cost": n_anomalous_excluded,
        })

    hotspots = pd.DataFrame(records)

    # Composite severity score: normalize frequency and total cost to 0-1
    # each, then combine equally. This means a suburb with FEWER but
    # COSTLIER incidents can still rank as high-severity, not just the
    # highest-volume suburbs.
    hotspots["freq_normalized"] = (
        hotspots["incident_count"] - hotspots["incident_count"].min()
    ) / (hotspots["incident_count"].max() - hotspots["incident_count"].min())
    hotspots["cost_normalized"] = (
        hotspots["total_claim_cost"] - hotspots["total_claim_cost"].min()
    ) / (hotspots["total_claim_cost"].max() - hotspots["total_claim_cost"].min())
    hotspots["severity_score"] = (
        0.5 * hotspots["freq_normalized"] + 0.5 * hotspots["cost_normalized"]
    ).round(4)

    hotspots = hotspots.sort_values("severity_score", ascending=False).reset_index(drop=True)

    print(f"\nIdentified {len(hotspots)} hot-spot suburbs (>= {MIN_INCIDENTS} incidents each).")
    return hotspots


def load_geocode_cache():
    if os.path.exists(GEOCODE_CACHE_PATH):
        with open(GEOCODE_CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_geocode_cache(cache):
    with open(GEOCODE_CACHE_PATH, "w") as f:
        json.dump(cache, f)


def geocode_suburb(suburb_name, cache):
    """
    Geocode a South African suburb name using OpenStreetMap Nominatim
    (free, no API key, but rate-limited to ~1 request/second per their
    usage policy — respected below with a sleep).
    """
    if suburb_name in cache:
        return cache[suburb_name]

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{suburb_name}, South Africa",
        "format": "json",
        "limit": 1,
    }
    headers = {
        # Nominatim's usage policy requires a real identifying User-Agent
        "User-Agent": "VukaGradhack2026DataPipeline/1.0"
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            cache[suburb_name] = {"lat": lat, "lon": lon}
        else:
            cache[suburb_name] = None  # cache the miss too, don't retry every run
    except Exception as e:
        print(f"    Geocoding error for '{suburb_name}': {e}")
        cache[suburb_name] = None

    time.sleep(1)  # respect Nominatim's 1 req/sec usage policy
    return cache[suburb_name]


def geocode_hotspots(hotspots):
    """Geocode every hot-spot suburb, with caching so reruns are fast."""
    cache = load_geocode_cache()
    print(f"\nGeocoding {len(hotspots)} suburbs (cached: {sum(1 for s in hotspots['SUBURB'] if s in cache)})...")

    lats, lons = [], []
    for i, suburb in enumerate(hotspots["SUBURB"]):
        result = geocode_suburb(suburb, cache)
        if result:
            lats.append(result["lat"])
            lons.append(result["lon"])
        else:
            lats.append(None)
            lons.append(None)
        if (i + 1) % 50 == 0:
            print(f"  ...{i + 1}/{len(hotspots)} processed")
            save_geocode_cache(cache)  # periodic save in case of interruption

    save_geocode_cache(cache)

    hotspots["lat"] = lats
    hotspots["lon"] = lons

    geocoded = hotspots[hotspots["lat"].notna()].copy()
    failed = len(hotspots) - len(geocoded)
    print(f"\nGeocoded successfully: {len(geocoded)}/{len(hotspots)} ({failed} failed/not found)")

    return hotspots, geocoded


def build_map_html(geocoded_df, output_path):
    """
    Build a self-contained Leaflet.js map showing hot-spots as circles,
    sized/colored by severity_score, with a popup showing claim type,
    peak date/time, and cost info. No API key needed (Leaflet + OSM tiles
    are free and open).
    """
    # Build marker data as a JS array
    markers_js = []
    for _, row in geocoded_df.iterrows():
        # Color scale: red = high severity, orange = medium, yellow = lower
        if row["severity_score"] >= 0.66:
            color = "#c0392b"
        elif row["severity_score"] >= 0.33:
            color = "#e67e22"
        else:
            color = "#f1c40f"

        radius = 6 + (row["severity_score"] * 20)  # 6px to 26px

        popup_html = (
            f"<b>{row['SUBURB']}</b><br>"
            f"Incidents: {row['incident_count']}<br>"
            f"Top claim type: {row['top_claim_type']} ({row['top_claim_type_count']}x)<br>"
            f"Peak time: {row['peak_day_of_week']}s around {row['peak_hour']}:00, "
            f"peaks in {row['peak_month']}<br>"
            f"Total claim cost: R{row['total_claim_cost']:,.0f}<br>"
            f"Avg claim cost: R{row['avg_claim_cost']:,.0f}<br>"
            f"Severity score: {row['severity_score']:.2f}"
        ).replace("'", "\\'")

        markers_js.append(
            f"L.circleMarker([{row['lat']}, {row['lon']}], {{"
            f"radius: {radius:.1f}, fillColor: '{color}', color: '#333', "
            f"weight: 1, opacity: 1, fillOpacity: 0.7"
            f"}}).bindPopup('{popup_html}').addTo(map);"
        )

    markers_block = "\n        ".join(markers_js)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Vuka Claims Hot-Spot Map</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css" />
    <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
    <style>
        body {{ margin: 0; font-family: Arial, sans-serif; }}
        #map {{ height: 100vh; width: 100%; }}
        #legend {{
            position: absolute; bottom: 20px; left: 20px; z-index: 1000;
            background: white; padding: 12px 16px; border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3); font-size: 13px;
        }}
        #legend h4 {{ margin: 0 0 8px 0; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 4px; }}
        .legend-dot {{ width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="legend">
        <h4>Claims Hot-Spot Severity</h4>
        <div class="legend-item"><span class="legend-dot" style="background:#c0392b"></span>High (frequency + cost)</div>
        <div class="legend-item"><span class="legend-dot" style="background:#e67e22"></span>Medium</div>
        <div class="legend-item"><span class="legend-dot" style="background:#f1c40f"></span>Lower</div>
        <div style="margin-top:8px; font-size:11px; color:#666;">Circle size = severity score</div>
    </div>
    <script>
        var map = L.map('map').setView([-28.5, 24.5], 6); // centered on South Africa

        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '&copy; OpenStreetMap contributors'
        }}).addTo(map);

        {markers_block}
    </script>
</body>
</html>
"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"\nMap saved to: {output_path}")


def main():
    df = load_cleaned_data()
    hotspots = build_hotspot_table(df)

    print("\nTop 10 hot-spots by severity score:")
    print(hotspots[["SUBURB", "incident_count", "top_claim_type", "total_claim_cost", "severity_score"]].head(10).to_string(index=False))

    hotspots.to_csv(OUTPUT_HOTSPOTS_CSV, index=False)
    print(f"\nSaved full hot-spot table to: {OUTPUT_HOTSPOTS_CSV}")

    hotspots_with_coords, geocoded = geocode_hotspots(hotspots)
    geocoded.to_csv(OUTPUT_GEOCODED_CSV, index=False)
    print(f"Saved geocoded hot-spot table to: {OUTPUT_GEOCODED_CSV}")

    if len(geocoded) > 0:
        build_map_html(geocoded, OUTPUT_MAP_HTML)
    else:
        print("No suburbs were successfully geocoded — map not built.")

    return hotspots_with_coords


if __name__ == "__main__":
    main()
