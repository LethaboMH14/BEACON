"""
SAPS Q1 2026 Crime Stats Integration

WHAT THIS DOES
--------------
Extracts Jan/Feb/Mar 2026 crime counts (per station, per crime category) from
the official SAPS quarterly workbook, and joins them onto your existing
claims-based hot-spot table (hotspots.csv) using a manually curated
suburb -> SAPS precinct mapping.

WHY A MANUAL MAPPING, NOT AN AUTOMATIC MATCH
----------------------------------------------
SAPS records crime by POLICE STATION/PRECINCT (e.g. "Sandton", "Douglasdale"),
not by suburb name (e.g. "Bryanston", "Fourways"). A straight string-match
between your hot-spot suburb names and SAPS station names will mostly fail,
because most suburbs aren't precinct names themselves — they're served BY a
precinct that covers a wider area. This was confirmed directly: searching
SAPS data for "Bryanston" returns zero rows; Bryanston is actually served by
the Sandton precinct.

There is no reliable free public "suburb to precinct" lookup table, so this
mapping has to be built by hand, suburb by suburb, checked against a source
like SAPS's own station-locator or local knowledge. SUBURB_TO_PRECINCT below
is a STARTER dict with only a handful of entries filled in from prior
verified work (e.g. Fourways -> Douglasdale, confirmed earlier). You need to
extend this dict with your own top hot-spot suburbs before this script will
cover more than a few of your 764 hot-spots.

WHAT THIS GIVES YOU THAT YOUR CLAIMS DATA ALONE DOESN'T
---------------------------------------------------------
- Independent verification: SAPS covers the whole population (not just
  Discovery's insured members), so a suburb flagged as high-risk in BOTH
  datasets is a much stronger claim than either alone.
- A trend direction ("Increased"/"Decreased"/"Stabilized") per crime type,
  which your claims data doesn't calculate.
- National station rankings, for context beyond your current suburb list.

INPUT FILES (must be in the same folder as this script)
--------------------------------------------------------
  2025-2026_-_4th_Quarter_WEB.xlsx   (the raw SAPS workbook)
  hotspots.csv                       (your existing claims-based hot-spot table)

OUTPUT
------
  hotspots_with_saps.csv   -- your existing hot-spot table, with SAPS columns
                              added for every suburb that has a precinct mapping
"""

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

import pandas as pd

SAPS_FILE = "2025-2026_-_4th_Quarter_WEB.xlsx"
HOTSPOTS_FILE = "hotspots.csv"
OUTPUT_FILE = "hotspots_with_saps.csv"

# ============================================================
# SUBURB -> SAPS PRECINCT MAPPING
# ============================================================
# STARTER dict. Extend this with your own hot-spot suburbs before relying
# on this for more than a handful of areas. Format: "SUBURB NAME (as it
# appears in hotspots.csv)": "SAPS Station name (exact match required)"
SUBURB_TO_PRECINCT = {
    "BRYANSTON": "Sandton",
    "FOURWAYS": "Douglasdale",   # confirmed in earlier session
    "SANDOWN": "Sandton",
    "SANDTON": "Sandton",
    "RANDBURG": "Randburg",
    # Add more mappings here as you verify them, e.g.:
    # "SOMERSET WEST": "Somerset West",
    # "RONDEBOSCH": "Rondebosch",
    # "JOHANNESBURG": "Johannesburg Central",
}

# Which SAPS crime categories to pull, and how they map to concepts your
# claims data already tracks. Add more from the full category list if useful
# (see the script's inspection output for all available category names).
RELEVANT_CRIME_CATEGORIES = [
    "Carjacking",
    "Truck hijacking",
    "Robbery with aggravating circumstances",
    "Burglary at residential premises",
    "Theft of motor vehicle and motorcycle",
]


def load_saps_raw_data():
    """Load and correctly parse the messy RAW Data sheet."""
    df = pd.read_excel(SAPS_FILE, sheet_name="RAW Data", header=None)
    # Real column headers live in row index 2 (0-indexed); data starts row 3
    headers = df.iloc[2].tolist()
    data = df.iloc[3:].copy()
    data.columns = headers
    print(f"Loaded SAPS RAW Data: {len(data)} rows.")
    return data


def extract_q1_2026(saps_data):
    """
    Extract Jan/Feb/Mar 2026 monthly counts and the Q1 2026 total for each
    (Station, Crime_Category) pair. Returns a tidy dataframe.
    """
    jan_col = pd.Timestamp("2026-01-01")
    feb_col = pd.Timestamp("2026-02-01")
    mar_col = pd.Timestamp("2026-03-01")
    total_col = "January 2026 to \nMarch 2026"

    keep_cols = ["Station", "District", "Province", "Crime_Category",
                 jan_col, feb_col, mar_col, total_col, "Count direction",
                 "National contribution\nplacement",
                 "Provincial contribution\nplacement"]

    subset = saps_data[keep_cols].copy()
    subset.columns = ["Station", "District", "Province", "Crime_Category",
                       "jan_2026", "feb_2026", "mar_2026", "q1_2026_total",
                       "trend_direction", "national_rank", "provincial_rank"]

    print(f"Extracted Q1 2026 figures: {len(subset)} (station, crime category) rows.")
    return subset


def filter_relevant_crimes(saps_q1, categories):
    filtered = saps_q1[saps_q1["Crime_Category"].isin(categories)].copy()
    print(f"Filtered to {len(categories)} relevant crime categories: {len(filtered)} rows.")
    return filtered


def join_to_hotspots(hotspots_df, saps_q1_filtered, mapping):
    """
    For each hot-spot suburb with a known SAPS precinct mapping, pull that
    precinct's Q1 2026 figures across all relevant crime categories and
    attach them as new columns.
    """
    results = []

    for _, hs_row in hotspots_df.iterrows():
        suburb = hs_row["SUBURB"]
        precinct = mapping.get(suburb)

        row_out = hs_row.to_dict()

        if precinct is None:
            row_out["saps_precinct_mapped"] = False
            row_out["saps_precinct_name"] = None
        else:
            row_out["saps_precinct_mapped"] = True
            row_out["saps_precinct_name"] = precinct

            precinct_data = saps_q1_filtered[saps_q1_filtered["Station"] == precinct]

            for _, crime_row in precinct_data.iterrows():
                cat_key = crime_row["Crime_Category"].lower().replace(" ", "_")
                row_out[f"saps_{cat_key}_q1_2026"] = crime_row["q1_2026_total"]
                row_out[f"saps_{cat_key}_trend"] = crime_row["trend_direction"]

        results.append(row_out)

    joined = pd.DataFrame(results)
    n_mapped = joined["saps_precinct_mapped"].sum()
    print(f"\nJoined SAPS data to hot-spots: {n_mapped}/{len(joined)} suburbs had a precinct mapping.")
    print(f"({len(joined) - n_mapped} suburbs still need a mapping added to SUBURB_TO_PRECINCT)")

    return joined


def main():
    hotspots = pd.read_csv(HOTSPOTS_FILE)
    print(f"Loaded {len(hotspots)} existing hot-spot suburbs from {HOTSPOTS_FILE}.\n")

    saps_data = load_saps_raw_data()
    saps_q1 = extract_q1_2026(saps_data)
    saps_q1_filtered = filter_relevant_crimes(saps_q1, RELEVANT_CRIME_CATEGORIES)

    joined = join_to_hotspots(hotspots, saps_q1_filtered, SUBURB_TO_PRECINCT)

    # Show the suburbs that DID get matched, so you can eyeball the result
    matched = joined[joined["saps_precinct_mapped"] == True]
    if len(matched) > 0:
        print("\n--- Suburbs successfully matched to SAPS data ---")
        preview_cols = ["SUBURB", "saps_precinct_name", "severity_score"]
        preview_cols += [c for c in matched.columns if c.startswith("saps_") and c.endswith("_q1_2026")]
        print(matched[preview_cols].to_string(index=False))

    joined.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
