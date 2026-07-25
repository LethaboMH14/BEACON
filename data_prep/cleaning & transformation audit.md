# Vuka Insurance Data: Cleaning & Transformation Audit

**Source File:** `Gradhack_Insure_Data.xlsx`
**Output Files:** `claims_cleaned.csv` / `claims_cleaned.xlsx`
**Total Rows Preserved:** 15,712 (0 rows dropped to maintain frequency accuracy)

## 1. Schema Changes (New Columns Added)
The original dataset contained 11 columns. The cleaning pipeline expanded the schema to 17 columns to support spatio-temporal risk modeling and maintain auditability.

*   **`hour` (Integer):** Extracted from `INCIDENT_DATE_TIME`. Represents the hour of the day (0-23).
*   **`day_of_week` (String):** Extracted from `INCIDENT_DATE_TIME` (e.g., "Monday", "Friday").
*   **`month` (String):** Extracted from `INCIDENT_DATE_TIME` (e.g., "June").
*   **`item_category_was_backfilled` (Boolean):** `True` if the row originally had a missing `ITEM_CATEGORY` and was algorithmically filled.
*   **`suburb_missing` (Boolean):** `True` if the original `SUBURB` field was blank/null. 
*   **`claim_amount_anomalous` (Boolean):** `True` if the `CLAIM_AMOUNT` was R0.00 or negative.

## 2. Data Modifications & Transformations
No data was silently deleted. Modifications were made explicitly to handle nulls and extract predictive features.

### A. Temporal Parsing (15,712 rows)
*   **Action:** Parsed the `INCIDENT_DATE_TIME` column.
*   **Result:** Successfully extracted hour, day, and month for 100% of the dataset. There were zero unparseable timestamps, enabling immediate time-based risk aggregation.

### B. Category Backfilling (196 rows)
*   **Action:** Addressed missing values in the `ITEM_CATEGORY` column.
*   **Result:** 196 rows were repaired using a generated naming convention matching `ITEM_TYPE` and `PERIL`.
    *   126 rows: "Home contents - Armed Robbery"
    *   63 rows: "Motor Vehicle - Armed Robbery"
    *   4 rows: "Home contents - Theft"
    *   2 rows: "Motor Vehicle - Theft"
    *   1 row: "Home contents - Attempted Hijack"
*   **Note:** The original data only contained strings for "Theft". The new categories for Armed Robbery and Attempted Hijack were logically synthesized. Every altered row is flagged as `item_category_was_backfilled=True` for complete transparency.

### C. Spatial Data Handling (651 rows)
*   **Action:** Identified rows missing `SUBURB` location data.
*   **Result:** Instead of dropping these 651 records (which would incorrectly reduce the total incident count and total financial damage calculations), they were preserved and flagged with `suburb_missing=True`.

### D. Financial Outlier Handling (81 rows)
*   **Action:** Identified rows with zero or negative `CLAIM_AMOUNT` values.
*   **Result:** 81 rows were flagged with `claim_amount_anomalous=True`. These represent the occurrence of a crime but lack valid financial data.

### E. Text Standardization
*   **Action:** Applied `.str.strip().str.upper()` to the `SUBURB` column.
*   **Result:** Verified that the original casing and spacing were already clean. No variant merging was required.

## 3. Downstream Usage Guidelines for the Data Science Team
When querying `claims_cleaned.csv` for the forecasting model, apply the following filtering rules based on the new boolean flags:

1.  **For Crime Frequency (Volume Modeling):** Use all 15,712 rows. Do not filter. A missing suburb or zero-dollar claim does not negate the fact that an incident occurred at a specific time.
2.  **For Crime Severity (Financial Modeling):** Filter out anomalous claims using `df[df['claim_amount_anomalous'] == False]`. 
3.  **For Spatial/Area Risk Modeling:** Filter out unknown locations using `df[df['suburb_missing'] == False]`.