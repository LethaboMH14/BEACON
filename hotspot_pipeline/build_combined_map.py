"""
Vuka / Discovery Gradhack — Combined Map Builder (Discovery claims + SAPS Q1 2026)

WHAT THIS SCRIPT DOES
----------------------
Builds hotspot_map.html with THREE distinct marker types, so the map never
implies "no marker = safe" for an area that simply has no Discovery claim:

    1. DISCOVERY + SAPS VERIFIED (green ring)   — hot-spot suburbs that have
       BOTH Discovery claims data AND a matched SAPS precinct. Popup shows
       both data sources.
    2. DISCOVERY ONLY (grey ring)                — hot-spot suburbs with
       Discovery claims data but no SAPS precinct mapped yet. Popup shows
       Discovery data only, with an explicit "no SAPS mapping yet" note.
    3. SAPS ONLY (blue square marker, not a circle) — real SAPS police
       precincts with significant crime activity but NO corresponding
       Discovery hot-spot at all (no Discovery member has claimed there in
       this dataset). These are shown as a DIFFERENT marker shape (square,
       not circle) specifically so they're visually distinguishable from
       the Discovery-scored circles at a glance — this data has NO Discovery
       claims cost behind it, so it is not comparable to the severity score
       used for the other two layers, and is deliberately never blended
       into it.

INPUT (must be in the same folder as this script)
---------------------------------------------------
  hotspots_with_saps.csv       (output of integrate_saps.py)
  saps_only_precincts.csv      (output of build_saps_only.py — OPTIONAL;
                                 if missing, the script still runs and just
                                 skips layer 3, printing a note about it)

OUTPUT
------
  hotspot_map.html                    -- overwrites the existing map
  hotspots_with_saps_geocoded.csv     -- geocoded Discovery+SAPS table
  saps_only_precincts_geocoded.csv    -- geocoded SAPS-only table
  geocode_cache.json                  -- shared cache, reused across runs
"""

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

import pandas as pd
import time
import json
import os
import requests

INPUT_CSV = "hotspots_with_saps.csv"
SAPS_ONLY_CSV = "saps_only_precincts.csv"
OUTPUT_GEOCODED_CSV = "hotspots_with_saps_geocoded.csv"
OUTPUT_SAPS_ONLY_GEOCODED_CSV = "saps_only_precincts_geocoded.csv"
OUTPUT_MAP_HTML = "hotspot_map.html"
GEOCODE_CACHE_PATH = "geocode_cache.json"

# Human-readable labels for the SAPS crime category columns produced by
# integrate_saps.py. Keys must match the "saps_<category>_q1_2026" column
# names exactly (lowercase, spaces replaced with underscores).
SAPS_CATEGORY_LABELS = {
    "saps_carjacking_q1_2026": "Carjacking",
    "saps_truck_hijacking_q1_2026": "Truck hijacking",
    "saps_robbery_with_aggravating_circumstances_q1_2026": "Robbery (aggravated)",
    "saps_burglary_at_residential_premises_q1_2026": "Residential burglary",
    "saps_theft_of_motor_vehicle_and_motorcycle_q1_2026": "Vehicle theft",
}


def load_hotspots_with_saps():
    df = pd.read_csv(INPUT_CSV)
    print(f"Loaded {len(df)} hot-spot suburbs from {INPUT_CSV}.")
    n_saps = df["saps_precinct_mapped"].sum()
    print(f"  -> {n_saps} of these have SAPS data mapped, {len(df) - n_saps} have Discovery claims data only.")
    return df


def load_geocode_cache():
    if os.path.exists(GEOCODE_CACHE_PATH):
        with open(GEOCODE_CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_geocode_cache(cache):
    with open(GEOCODE_CACHE_PATH, "w") as f:
        json.dump(cache, f)


def geocode_suburb(suburb_name, cache):
    """Geocode via OpenStreetMap Nominatim (free, no API key, rate-limited)."""
    if suburb_name in cache:
        return cache[suburb_name]

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"{suburb_name}, South Africa", "format": "json", "limit": 1}
    headers = {"User-Agent": "VukaGradhack2026DataPipeline/1.0"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if results:
            cache[suburb_name] = {"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"])}
        else:
            cache[suburb_name] = None
    except Exception as e:
        print(f"    Geocoding error for '{suburb_name}': {e}")
        cache[suburb_name] = None

    time.sleep(1)  # respect Nominatim's 1 req/sec usage policy
    return cache[suburb_name]


def geocode_hotspots(hotspots):
    cache = load_geocode_cache()
    already_cached = sum(1 for s in hotspots["SUBURB"] if s in cache)
    print(f"\nGeocoding {len(hotspots)} suburbs ({already_cached} already cached, "
          f"{len(hotspots) - already_cached} new lookups needed)...")

    lats, lons = [], []
    for i, suburb in enumerate(hotspots["SUBURB"]):
        result = geocode_suburb(suburb, cache)
        lats.append(result["lat"] if result else None)
        lons.append(result["lon"] if result else None)
        if (i + 1) % 50 == 0:
            print(f"  ...{i + 1}/{len(hotspots)} processed")
            save_geocode_cache(cache)

    save_geocode_cache(cache)

    hotspots = hotspots.copy()
    hotspots["lat"] = lats
    hotspots["lon"] = lons

    geocoded = hotspots[hotspots["lat"].notna()].copy()
    print(f"\nGeocoded successfully: {len(geocoded)}/{len(hotspots)} "
          f"({len(hotspots) - len(geocoded)} failed/not found)")
    return geocoded


def load_saps_only_precincts():
    """Load the SAPS-only precincts table if it exists. Optional layer —
    the map still works without it, just skips layer 3."""
    if not os.path.exists(SAPS_ONLY_CSV):
        print(f"\nNote: {SAPS_ONLY_CSV} not found — skipping SAPS-only layer. "
              f"Run build_saps_only.py first if you want this layer included.")
        return None
    df = pd.read_csv(SAPS_ONLY_CSV)
    print(f"\nLoaded {len(df)} SAPS-only precincts (no Discovery match) from {SAPS_ONLY_CSV}.")
    return df


def geocode_saps_only(saps_only_df, cache):
    """Geocode SAPS-only station names, reusing the shared cache."""
    print(f"Geocoding {len(saps_only_df)} SAPS-only station names...")
    lats, lons = [], []
    for i, station in enumerate(saps_only_df["STATION"]):
        # Query with "Police Station" appended — station names alone are
        # more ambiguous than suburb names (e.g. many towns share names),
        # so this improves match quality for this specific layer.
        cache_key = f"{station} SAPS"
        if cache_key in cache:
            result = cache[cache_key]
        else:
            result = geocode_suburb(f"{station} Police Station", cache)
            cache[cache_key] = result
        lats.append(result["lat"] if result else None)
        lons.append(result["lon"] if result else None)
        if (i + 1) % 50 == 0:
            print(f"  ...{i + 1}/{len(saps_only_df)} processed")
            save_geocode_cache(cache)

    save_geocode_cache(cache)
    saps_only_df = saps_only_df.copy()
    saps_only_df["lat"] = lats
    saps_only_df["lon"] = lons
    geocoded = saps_only_df[saps_only_df["lat"].notna()].copy()
    print(f"Geocoded successfully: {len(geocoded)}/{len(saps_only_df)} "
          f"({len(saps_only_df) - len(geocoded)} failed/not found)")
    return geocoded

def build_saps_only_popup_html(row):
    """
    Popup for a SAPS-only precinct (no Discovery match at all). Deliberately
    styled distinctly (blue-grey theme) so it's never confused with the
    Discovery-scored circle markers, and explicitly states there is no
    Discovery claims data for this location.
    """
    popup = (
        f"<div style='font-family:Arial, sans-serif; font-size:13px; min-width:220px;'>"
        f"<div style='font-size:15px; font-weight:bold; margin-bottom:6px;'>{row['STATION']} (SAPS precinct)</div>"
        f"<div style='border-left:4px solid #999999; padding-left:8px; margin-bottom:6px; color:#666; font-size:11px;'>"
        f"No Discovery claims data found for this area &mdash; shown here from "
        f"SAPS police records only."
        f"</div>"
        f"<div style='border-left:4px solid #1E7B34; padding-left:8px; margin-top:6px;'>"
        f"<div style='color:#1E7B34; font-weight:bold; font-size:12px; text-transform:uppercase; margin-bottom:3px;'>"
        f"SAPS Official Data (Q1 2026 &mdash; Jan&ndash;Mar)</div>"
        f"District: {row['District']}, {row['Province']}<br>"
        f"Total incidents (tracked categories): {row['total_q1_2026_incidents']}<br>"
        f"Top crime: {row['top_crime_type']} ({row['top_crime_count']}x) "
        f"<span style='color:#666;'>({row['top_crime_trend']})</span><br>"
        f"SAPS-only severity score: {row['saps_only_severity_score']:.2f} "
        f"<span style='color:#999; font-size:10px;'>(frequency-based only &mdash; "
        f"not directly comparable to the Discovery severity score, since SAPS "
        f"has no claim-cost equivalent)</span>"
        f"</div>"
        f"</div>"
    )
    return popup.replace("'", "\\'").replace("\n", "")


def build_popup_html(row):
    """
    Build popup content with two CLEARLY SEPARATED, visually distinct
    sections: Discovery claims data (blue) and SAPS official data (green,
    only present when saps_precinct_mapped is True).
    """
    # --- Discovery section (always present) ---
    discovery_section = (
        f"<div style='border-left:4px solid #2E5395; padding-left:8px; margin-bottom:6px;'>"
        f"<div style='color:#2E5395; font-weight:bold; font-size:12px; text-transform:uppercase; margin-bottom:3px;'>"
        f"Discovery Claims Data</div>"
        f"Incidents: {row['incident_count']}<br>"
        f"Top claim type: {row['top_claim_type']} ({row['top_claim_type_count']}x)<br>"
        f"Peak time: {row['peak_day_of_week']}s around {int(row['peak_hour'])}:00, "
        f"peaks in {row['peak_month']}<br>"
        f"Total claim cost: R{row['total_claim_cost']:,.0f}<br>"
        f"Avg claim cost: R{row['avg_claim_cost']:,.0f}<br>"
        f"Severity score: {row['severity_score']:.2f}"
        f"</div>"
    )

    # --- SAPS section (only if this suburb has a verified precinct mapping) ---
    if row.get("saps_precinct_mapped", False):
        saps_lines = []
        for col, label in SAPS_CATEGORY_LABELS.items():
            trend_col = col.replace("_q1_2026", "_trend")
            if col in row and pd.notna(row[col]):
                count = int(row[col])
                trend = row.get(trend_col, "")
                trend_arrow = {"Increased": "&#9650;", "Decreased": "&#9660;", "Stabilized": "&#9679;"}.get(trend, "")
                saps_lines.append(f"{label}: {count} <span style='color:#666;'>({trend_arrow} {trend})</span>")

        saps_body = "<br>".join(saps_lines) if saps_lines else "No matching categories found."

        saps_section = (
            f"<div style='border-left:4px solid #1E7B34; padding-left:8px; margin-top:6px;'>"
            f"<div style='color:#1E7B34; font-weight:bold; font-size:12px; text-transform:uppercase; margin-bottom:3px;'>"
            f"SAPS Official Data (Q1 2026 — Jan&ndash;Mar)</div>"
            f"Precinct: {row['saps_precinct_name']}<br>"
            f"{saps_body}"
            f"</div>"
        )
    else:
        saps_section = (
            f"<div style='border-left:4px solid #CCCCCC; padding-left:8px; margin-top:6px; color:#999; font-size:11px;'>"
            f"No SAPS precinct mapping yet for this suburb."
            f"</div>"
        )

    popup = (
        f"<div style='font-family:Arial, sans-serif; font-size:13px; min-width:220px;'>"
        f"<div style='font-size:15px; font-weight:bold; margin-bottom:6px;'>{row['SUBURB']}</div>"
        f"{discovery_section}"
        f"{saps_section}"
        f"</div>"
    )

    # Escape single quotes for safe embedding in the JS string literal below
    return popup.replace("'", "\\'").replace("\n", "")


def build_map_html(geocoded_df, output_path, saps_only_geocoded=None):
    """
    Build the combined Leaflet map with up to THREE marker layers:
      1. Discovery+SAPS verified circles (green ring)
      2. Discovery-only circles (grey ring)
      3. SAPS-only SQUARE markers (blue) for precincts with real crime
         activity but no Discovery claims data at all — passed in as
         saps_only_geocoded (optional; layer is skipped if None)

    Marker color/size for layers 1 and 2 is still driven by the Discovery
    severity_score, unchanged. Layer 3 uses squares (not circles) and its
    own blue color scale specifically so it's never visually confused with
    the Discovery-scored circles — the two scores are not computed the same
    way and are not meant to be compared directly.
    """
    markers_js = []
    for _, row in geocoded_df.iterrows():
        if row["severity_score"] >= 0.66:
            fill_color = "#c0392b"
        elif row["severity_score"] >= 0.33:
            fill_color = "#e67e22"
        else:
            fill_color = "#f1c40f"

        radius = 6 + (row["severity_score"] * 20)

        # Border color signals data source: green ring = SAPS-verified,
        # grey ring = Discovery claims only
        border_color = "#1E7B34" if row.get("saps_precinct_mapped", False) else "#999999"
        border_weight = 3 if row.get("saps_precinct_mapped", False) else 1

        popup_html = build_popup_html(row)

        markers_js.append(
            f"L.circleMarker([{row['lat']}, {row['lon']}], {{"
            f"radius: {radius:.1f}, fillColor: '{fill_color}', color: '{border_color}', "
            f"weight: {border_weight}, opacity: 1, fillOpacity: 0.75"
            f"}}).bindPopup('{popup_html}').addTo(map);"
        )

    # --- Layer 3: SAPS-only precincts, rendered as SQUARE markers ---
    # BUGFIX: an earlier version built these with L.rectangle using a
    # meters-to-degrees conversion (dividing by 111000), but then reused the
    # same 6-16 range meant for PIXEL radii. That produced squares only
    # ~13-26 METERS wide -- at the map's default South-Africa-wide zoom
    # level (zoom 6), that's roughly 1/100th of a screen pixel, so the
    # squares were mathematically correct but genuinely invisible on
    # screen. Fixed by using L.divIcon instead, which is sized in actual
    # screen pixels (like circleMarker's radius already is), so the square
    # stays a constant, visible size on screen regardless of zoom level.
    n_saps_only = 0
    if saps_only_geocoded is not None and len(saps_only_geocoded) > 0:
        n_saps_only = len(saps_only_geocoded)
        for _, row in saps_only_geocoded.iterrows():
            score = row["saps_only_severity_score"]
            if score >= 0.66:
                sq_color = "#1a5276"
            elif score >= 0.33:
                sq_color = "#2874a6"
            else:
                sq_color = "#5dade2"

            pixel_size = 12 + (score * 20)  # 12px to 32px square, in actual screen pixels
            popup_html = build_saps_only_popup_html(row)

            # L.divIcon renders a plain HTML/CSS square marker sized in
            # real screen pixels via the CSS width/height below -- this
            # stays visually constant regardless of zoom level, exactly
            # like circleMarker's radius does. This replaces the earlier
            # broken L.rectangle approach (see bugfix note above).
            markers_js.append(
                f"L.marker([{row['lat']}, {row['lon']}], {{"
                f"icon: L.divIcon({{"
                f"className: '', "
                f"html: \"<div style='width:{pixel_size:.0f}px; height:{pixel_size:.0f}px; "
                f"background:{sq_color}; border:2px solid #0B3D5C; box-sizing:border-box;'></div>\", "
                f"iconSize: [{pixel_size:.0f}, {pixel_size:.0f}], "
                f"iconAnchor: [{pixel_size/2:.0f}, {pixel_size/2:.0f}]"
                f"}})"
                f"}}).bindPopup('{popup_html}').addTo(map);"
            )

    markers_block = "\n        ".join(markers_js)
    n_saps = geocoded_df["saps_precinct_mapped"].sum()

    saps_only_legend = ""
    if n_saps_only > 0:
        saps_only_legend = f"""
        <div class="legend-divider"></div>
        <h4>SAPS-Only Precincts (square markers)</h4>
        <div class="legend-item"><span style="width:12px;height:12px;background:#1a5276;margin-right:8px;flex-shrink:0;"></span>High activity, no Discovery claim</div>
        <div class="legend-item"><span style="width:12px;height:12px;background:#5dade2;margin-right:8px;flex-shrink:0;"></span>Lower activity, no Discovery claim</div>
        <div style="font-size:11px; color:#666; margin-top:2px;">{n_saps_only} precincts &mdash; SAPS data only, no Discovery claims exist here</div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Vuka Hot-Spot Map — Discovery Claims + SAPS Data</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css" />
    <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
    <style>
        body {{ margin: 0; font-family: Arial, sans-serif; }}
        #map {{ height: 100vh; width: 100%; }}
        #legend {{
            position: absolute; bottom: 20px; left: 20px; z-index: 1000;
            background: white; padding: 12px 16px; border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3); font-size: 13px; max-width: 280px;
            max-height: 80vh; overflow-y: auto;
        }}
        #legend h4 {{ margin: 0 0 8px 0; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 4px; }}
        .legend-dot {{ width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; flex-shrink: 0; }}
        .legend-ring {{ width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; flex-shrink: 0;
                        background: white; box-sizing: border-box; }}
        .legend-divider {{ border-top: 1px solid #ddd; margin: 8px 0; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="legend">
        <h4>Hot-Spot Severity (Discovery data)</h4>
        <div class="legend-item"><span class="legend-dot" style="background:#c0392b"></span>High (frequency + cost)</div>
        <div class="legend-item"><span class="legend-dot" style="background:#e67e22"></span>Medium</div>
        <div class="legend-item"><span class="legend-dot" style="background:#f1c40f"></span>Lower</div>
        <div style="font-size:11px; color:#666; margin-top:2px;">Circle size = severity score</div>
        <div class="legend-divider"></div>
        <h4>Data Source (marker border)</h4>
        <div class="legend-item"><span class="legend-ring" style="border:3px solid #1E7B34;"></span>SAPS-verified ({n_saps} suburbs)</div>
        <div class="legend-item"><span class="legend-ring" style="border:1px solid #999999;"></span>Discovery claims only</div>
        {saps_only_legend}
    </div>
    <script>
        var map = L.map('map').setView([-28.5, 24.5], 6);

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
    print(f"  {n_saps} markers show a green ring (SAPS-verified)")
    print(f"  {len(geocoded_df) - n_saps} markers show a grey ring (Discovery claims only)")


def main():
    hotspots = load_hotspots_with_saps()
    geocoded = geocode_hotspots(hotspots)
    geocoded.to_csv(OUTPUT_GEOCODED_CSV, index=False)
    print(f"Saved geocoded table to: {OUTPUT_GEOCODED_CSV}")

    # Layer 3: SAPS-only precincts (no Discovery match). Optional — the
    # map still builds fine without it if build_saps_only.py hasn't been
    # run yet, it just won't show the square markers.
    saps_only_geocoded = None
    saps_only = load_saps_only_precincts()
    if saps_only is not None and len(saps_only) > 0:
        cache = load_geocode_cache()
        saps_only_geocoded = geocode_saps_only(saps_only, cache)
        saps_only_geocoded.to_csv(OUTPUT_SAPS_ONLY_GEOCODED_CSV, index=False)
        print(f"Saved SAPS-only geocoded table to: {OUTPUT_SAPS_ONLY_GEOCODED_CSV}")

    if len(geocoded) > 0:
        build_map_html(geocoded, OUTPUT_MAP_HTML, saps_only_geocoded=saps_only_geocoded)
    else:
        print("No suburbs were successfully geocoded — map not built.")


if __name__ == "__main__":
    main()
