"""
Vuka / Discovery Gradhack — Claims Data Cleaning Pipeline

Implements exactly the 5-step data prep spec:
  1. Parse INCIDENT_DATE_TIME -> extract hour, day_of_week, month
  2. Backfill missing ITEM_CATEGORY (Armed Robbery + Theft + Attempted Hijack rows)
  3. Drop/flag rows with missing SUBURB (can't area-bucket these)
  4. Flag negative/zero CLAIM_AMOUNT as anomalous (exclude from severity, keep in frequency)
  5. Standardize SUBURB casing/whitespace before grouping

IMPORTANT NOTE ON STEP 2
-------------------------
The dataset's existing ITEM_CATEGORY values are ONLY:
  'Home contents - Theft'
  'Motor Vehicle - Theft'
There is no pre-existing category string for Armed Robbery or Attempted Hijack to match —
I'm inventing a consistent naming convention ('Home contents - Armed Robbery', etc.) to
match the existing "<ItemType> - <Peril>" pattern. If your team has a different naming
convention already in use elsewhere (e.g. in the pitch deck or ops dashboard schema),
rename these to match before this becomes a shared reference table.

VERIFIED COUNTS (re-checked against the actual file, correcting an earlier approximation):
  - 196 rows missing ITEM_CATEGORY total, broken down as:
      Armed Robbery, Contents : 126
      Armed Robbery, Vehicle  :  63
      Attempted Hijack, Contents : 1
      Theft, Contents         :   4
      Theft, Vehicle          :   2
  - 651 rows missing SUBURB (confirmed separately)
  - 81 rows with CLAIM_AMOUNT <= 0 (confirmed separately)

OUTPUT
------
Writes two files to /mnt/user-data/outputs/:
  - claims_cleaned.csv   (full cleaned dataset, ready for grouping/aggregation)
  - claims_cleaned.xlsx  (same data, for opening/inspecting in Excel)

Also prints a summary of every change made, so you can sanity-check nothing silently
went wrong (row counts before/after, backfill breakdown, flag counts).
"""

import pandas as pd

INPUT_PATH = "/mnt/user-data/uploads/Gradhack_Insure_Data.xlsx"
OUTPUT_CSV = "/mnt/user-data/outputs/claims_cleaned.csv"
OUTPUT_XLSX = "/mnt/user-data/outputs/claims_cleaned.xlsx"


def load_data():
    df = pd.read_excel(INPUT_PATH)
    print(f"Loaded {len(df)} rows, {len(df.columns)} columns.")
    return df


def step1_parse_datetime(df):
    """Extract hour, day_of_week, month from INCIDENT_DATE_TIME."""
    df["INCIDENT_DATE_TIME"] = pd.to_datetime(df["INCIDENT_DATE_TIME"])
    df["hour"] = df["INCIDENT_DATE_TIME"].dt.hour
    df["day_of_week"] = df["INCIDENT_DATE_TIME"].dt.day_name()  # e.g. 'Monday'
    df["month"] = df["INCIDENT_DATE_TIME"].dt.month_name()      # e.g. 'January'

    unparsed = df["INCIDENT_DATE_TIME"].isna().sum()
    print(f"\n[Step 1] Parsed INCIDENT_DATE_TIME -> hour, day_of_week, month.")
    print(f"          Unparseable dates (now NaT): {unparsed}")
    return df


def step2_backfill_item_category(df):
    """
    Backfill missing ITEM_CATEGORY using ITEM_TYPE + PERIL, following the
    dataset's existing '<ItemType> - <Peril>' naming convention (Contents ->
    'Home contents', Vehicle -> 'Motor Vehicle'). See module docstring note
    above: this convention is INVENTED for perils that had no prior category
    string, not matched against an existing label.
    """
    missing_before = df["ITEM_CATEGORY"].isna().sum()

    def infer_category(row):
        if pd.notna(row["ITEM_CATEGORY"]):
            return row["ITEM_CATEGORY"]
        item_type_label = "Home contents" if row["ITEM_TYPE"] == "Contents" else "Motor Vehicle"
        return f"{item_type_label} - {row['PERIL']}"

    df["ITEM_CATEGORY"] = df.apply(infer_category, axis=1)
    # NOTE: the correct "which rows were backfilled" flag requires the null
    # mask captured BEFORE this function runs (df already has nulls filled by
    # the time we're here). That flag is set separately in step2b_track_backfill_flag,
    # called right after this function with the pre-backfill mask passed in.

    missing_after = df["ITEM_CATEGORY"].isna().sum()
    print(f"\n[Step 2] Backfilled ITEM_CATEGORY.")
    print(f"          Missing before: {missing_before}, missing after: {missing_after}")
    return df


def step2b_track_backfill_flag(df, original_missing_mask):
    """Separate pass to correctly flag which rows were backfilled (needs the
    original pre-backfill null mask, captured before step2 runs)."""
    df["item_category_was_backfilled"] = original_missing_mask
    n_flagged = df["item_category_was_backfilled"].sum()
    print(f"          Rows flagged as backfilled: {n_flagged}")
    print("          Backfill breakdown (PERIL, ITEM_TYPE):")
    breakdown = df[df["item_category_was_backfilled"]].groupby(["PERIL", "ITEM_TYPE"]).size()
    for (peril, item_type), count in breakdown.items():
        print(f"            {peril} / {item_type}: {count}")
    return df


def step3_flag_missing_suburb(df, drop=False):
    """
    Flag rows with missing SUBURB. Per spec: 'drop OR flag' — default here is
    FLAG (safer default: preserves the row for peril-frequency/time-based
    analysis that doesn't require area-bucketing, while making it trivial to
    exclude from suburb-level aggregation). Set drop=True to hard-drop instead.
    """
    missing_suburb = df["SUBURB"].isna()
    n_missing = missing_suburb.sum()

    df["suburb_missing"] = missing_suburb

    if drop:
        df = df[~missing_suburb].copy()
        print(f"\n[Step 3] Dropped {n_missing} rows with missing SUBURB.")
    else:
        print(f"\n[Step 3] Flagged {n_missing} rows with missing SUBURB (suburb_missing=True).")
        print("          These rows are KEPT for hour/peril-level analysis but should be")
        print("          EXCLUDED from any suburb-level groupby (filter on suburb_missing==False).")

    return df


def step4_flag_anomalous_claim_amount(df):
    """
    Flag CLAIM_AMOUNT <= 0 as anomalous. Kept in the dataset (so incident
    FREQUENCY counts remain accurate) but flagged so severity/value-based
    aggregations (e.g. average claim cost per suburb) can exclude them.
    """
    anomalous_mask = df["CLAIM_AMOUNT"] <= 0
    df["claim_amount_anomalous"] = anomalous_mask

    n_anomalous = anomalous_mask.sum()
    print(f"\n[Step 4] Flagged {n_anomalous} rows with CLAIM_AMOUNT <= 0 (claim_amount_anomalous=True).")
    print("          Kept in dataset for frequency counts.")
    print("          EXCLUDE these when computing severity/average claim value")
    print("          (filter on claim_amount_anomalous==False first).")
    print("          Breakdown by PERIL:")
    breakdown = df[anomalous_mask]["PERIL"].value_counts()
    for peril, count in breakdown.items():
        print(f"            {peril}: {count}")

    return df


def step5_standardize_suburb(df):
    """Strip whitespace and uppercase SUBURB for consistent grouping.
    Only applied to non-null suburb values."""
    before_unique = df["SUBURB"].nunique()

    df["SUBURB"] = df["SUBURB"].apply(
        lambda x: x.strip().upper() if isinstance(x, str) else x
    )

    after_unique = df["SUBURB"].nunique()
    print(f"\n[Step 5] Standardized SUBURB casing/whitespace.")
    print(f"          Unique suburb values before: {before_unique}, after: {after_unique}")
    if before_unique != after_unique:
        print(f"          -> {before_unique - after_unique} suburb variants were merged by standardization.")
    else:
        print("          -> No variants merged; suburb strings were already consistent.")

    return df


def main():
    df = load_data()

    df = step1_parse_datetime(df)

    # Capture the missing-ITEM_CATEGORY mask BEFORE backfilling, so we can
    # accurately flag which rows were touched (step2's internal placeholder
    # mask is wrong by construction — this is the correct one).
    original_missing_category_mask = df["ITEM_CATEGORY"].isna()

    df = step2_backfill_item_category(df)
    df = step2b_track_backfill_flag(df, original_missing_category_mask)

    df = step3_flag_missing_suburb(df, drop=False)  # flag, not drop — see docstring
    df = step4_flag_anomalous_claim_amount(df)
    df = step5_standardize_suburb(df)

    print(f"\nFinal shape: {df.shape}")

    df.to_csv(OUTPUT_CSV, index=False)
    df.to_excel(OUTPUT_XLSX, index=False)
    print(f"\nSaved cleaned dataset to:\n  {OUTPUT_CSV}\n  {OUTPUT_XLSX}")

    return df


if __name__ == "__main__":
    main()
