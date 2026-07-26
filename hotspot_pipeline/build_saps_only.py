"""
SAPS-Only Precincts — stations with NO corresponding Discovery hot-spot

WHY THIS EXISTS
----------------
The combined map (build_combined_map.py) only ever plots suburbs that
already exist in hotspots_with_saps.csv — i.e. suburbs where a Discovery
member filed a claim. But SAPS tracks crime at ~1,241 police precincts
nationally, and only 186 of those share an exact name with something in
Discovery's claims data. That means potentially hundreds of real, officially
documented crime precincts were previously INVISIBLE on the map, purely
because no Discovery-insured member happened to claim there — not because
the area is actually safe.

This script fixes that blind spot: it identifies every SAPS precinct that
has NO matching entry anywhere in the Discovery hot-spot table, computes a
SAPS-only severity score for each (same normalize-and-combine logic as the
Discovery severity score, but built purely from SAPS incident counts across
the RELEVANT_CRIME_CATEGORIES), and outputs them as a separate table ready
to be plotted as their own distinct layer.

INPUT
-----
  2025-2026_-_4th_Quarter_WEB.xlsx   (raw SAPS workbook)
  hotspots_with_saps.csv             (existing Discovery+SAPS joined table,
                                       used only to know which suburb names
                                       are ALREADY covered)

OUTPUT
------
  saps_only_precincts.csv   -- every SAPS precinct with no Discovery match,
                                with a saps_only_severity_score, ready to
                                geocode and plot as a third marker style
"""

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

import pandas as pd

SAPS_FILE = "2025-2026_-_4th_Quarter_WEB.xlsx"
DISCOVERY_HOTSPOTS_FILE = "hotspots_with_saps.csv"
OUTPUT_FILE = "saps_only_precincts.csv"

MIN_TOTAL_INCIDENTS = 10  # threshold for a SAPS-only precinct to be worth plotting

# Same relevant categories used in integrate_saps.py, for consistency
RELEVANT_CRIME_CATEGORIES = [
    "Carjacking",
    "Truck hijacking",
    "Robbery with aggravating circumstances",
    "Burglary at residential premises",
    "Theft of motor vehicle and motorcycle",
]


def load_saps_raw_data():
    df = pd.read_excel(SAPS_FILE, sheet_name="RAW Data", header=None)
    headers = df.iloc[2].tolist()
    data = df.iloc[3:].copy()
    data.columns = headers
    print(f"Loaded SAPS RAW Data: {len(data)} rows.")
    return data


def extract_q1_2026(saps_data):
    jan_col = pd.Timestamp("2026-01-01")
    feb_col = pd.Timestamp("2026-02-01")
    mar_col = pd.Timestamp("2026-03-01")
    total_col = "January 2026 to \nMarch 2026"

    keep_cols = ["Station", "District", "Province", "Comp level", "Crime_Category",
                 jan_col, feb_col, mar_col, total_col, "Count direction"]

    subset = saps_data[keep_cols].copy()
    subset.columns = ["Station", "District", "Province", "Comp_level", "Crime_Category",
                       "jan_2026", "feb_2026", "mar_2026", "q1_2026_total",
                       "trend_direction"]

    # CRITICAL: the raw sheet mixes individual police STATION rows together
    # with District, Province, and National rollup/aggregate rows (identified
    # by the 'Comp level' column). Plotting a rollup row (e.g. "Gauteng",
    # "Republic Of South Africa") as if it were a single police precinct
    # would be wrong and would visually swamp real station-level hot-spots
    # with enormous province/national totals. Keep ONLY real station rows.
    before = len(subset)
    subset = subset[subset["Comp_level"] == "Station"].copy()
    print(f"Filtered to Station-level rows only: {len(subset)} / {before} "
          f"(excluded District/Province/National rollup rows)")

    return subset


def get_already_covered_suburbs():
    """Suburb names already present in the Discovery hot-spot table — these
    are excluded from the SAPS-only table since they're already shown on
    the map via the combined layer."""
    hotspots = pd.read_csv(DISCOVERY_HOTSPOTS_FILE)
    covered = set(hotspots["SUBURB"].str.upper().str.strip())
    print(f"Discovery hot-spot table covers {len(covered)} suburb names.")
    return covered


def build_saps_only_table(saps_q1, covered_suburbs):
    """
    For every SAPS station NOT already covered by a Discovery hot-spot,
    compute total incidents (across relevant categories) and a SAPS-only
    severity score based purely on incident frequency (no cost data exists
    on the SAPS side, so this score uses frequency only — see note below).
    """
    filtered = saps_q1[saps_q1["Crime_Category"].isin(RELEVANT_CRIME_CATEGORIES)].copy()

    records = []
    for station, group in filtered.groupby("Station"):
        station_upper = str(station).upper().strip()
        if station_upper in covered_suburbs:
            continue  # already shown via the combined Discovery+SAPS layer

        total_incidents = group["q1_2026_total"].sum()
        if total_incidents < MIN_TOTAL_INCIDENTS:
            continue

        crime_breakdown = "; ".join(
            f"{row['Crime_Category']}:{int(row['q1_2026_total'])}"
            for _, row in group.iterrows()
        )
        top_crime_row = group.loc[group["q1_2026_total"].idxmax()]

        district = group["District"].iloc[0]
        province = group["Province"].iloc[0]

        records.append({
            "STATION": station,
            "District": district,
            "Province": province,
            "total_q1_2026_incidents": int(total_incidents),
            "top_crime_type": top_crime_row["Crime_Category"],
            "top_crime_count": int(top_crime_row["q1_2026_total"]),
            "top_crime_trend": top_crime_row["trend_direction"],
            "crime_breakdown": crime_breakdown,
        })

    saps_only = pd.DataFrame(records)

    if len(saps_only) == 0:
        print("No SAPS-only precincts met the minimum incident threshold.")
        return saps_only

    # SAPS-only severity score: FREQUENCY ONLY, since SAPS data has no cost
    # figure equivalent to Discovery's claim amounts. This is a real,
    # meaningful difference from the Discovery severity score, worth
    # stating plainly rather than pretending the two scores are computed
    # the same way.
    saps_only["saps_only_severity_score"] = (
        (saps_only["total_q1_2026_incidents"] - saps_only["total_q1_2026_incidents"].min())
        / (saps_only["total_q1_2026_incidents"].max() - saps_only["total_q1_2026_incidents"].min())
    ).round(4)

    saps_only = saps_only.sort_values("saps_only_severity_score", ascending=False).reset_index(drop=True)
    print(f"\nFound {len(saps_only)} SAPS-only precincts (no Discovery match, "
          f">= {MIN_TOTAL_INCIDENTS} incidents) not currently shown on the map.")
    return saps_only


def main():
    covered_suburbs = get_already_covered_suburbs()
    saps_data = load_saps_raw_data()
    saps_q1 = extract_q1_2026(saps_data)

    saps_only = build_saps_only_table(saps_q1, covered_suburbs)

    if len(saps_only) > 0:
        print("\nTop 10 SAPS-only precincts by severity score:")
        print(saps_only[["STATION", "Province", "total_q1_2026_incidents",
                          "top_crime_type", "saps_only_severity_score"]].head(10).to_string(index=False))

        saps_only.to_csv(OUTPUT_FILE, index=False)
        print(f"\nSaved: {OUTPUT_FILE}")
    else:
        print("Nothing to save.")


if __name__ == "__main__":
    main()
