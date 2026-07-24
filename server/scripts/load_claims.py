"""
Load the real Gradhack_Insure_Data.xlsx into the `claims` table
(team/SBU.md backlog, 2026-07-25): F3 near-repeat correlation and the
/v1/risk claims fallback both key off real Claim rows, and until now
nothing outside tests ever put real ones in the DB.

Cleaning rules applied (docs/02-DATA-FORECASTING.md §2 — Ndu's spec,
followed here so this isn't thrown away when his pipeline lands):
1. Negative CLAIM_AMOUNT (reversals) kept, not dropped.
2. Null/blank SUBURB -> "UNKNOWN", reported as a coverage % honestly.
3. Suburb strings uppercase-trimmed.
4. INCIDENT_DATE_TIME already carries real hour-of-day -> hour_known=True.
5. Dedupe by Incident id (checked: 0 duplicates in the current file).

Deliberately NOT done here (Ndu's ownership, docs/02 §3): geocoding
2,929 distinct suburbs to lat/lng/hex_id via Nominatim needs the
suburb_alias.csv hand-curation and the cached data/geocode/suburbs.json
this repo doesn't have yet. Claims load with hex_id=None until that
lands — the honest state is "no hex yet", not an invented coordinate.

Run: python scripts/load_claims.py <path-to-Gradhack_Insure_Data.xlsx>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from src.db.database import SessionLocal, init_db
from src.db.models import Claim


def load(xlsx_path: str) -> None:
    df = pd.read_excel(xlsx_path)

    before = len(df)
    df = df.drop_duplicates(subset=["Incident"])
    deduped = before - len(df)

    df["SUBURB"] = df["SUBURB"].fillna("UNKNOWN").astype(str).str.strip().str.upper()
    unknown_pct = (df["SUBURB"] == "UNKNOWN").mean() * 100

    init_db()
    db = SessionLocal()
    inserted = 0
    try:
        existing = {c for (c,) in db.query(Claim.claim_number).all()}
        for row in df.itertuples(index=False):
            claim_number = str(row.Incident)
            if claim_number in existing:
                continue
            ts = row.INCIDENT_DATE_TIME
            db.add(Claim(
                claim_number=claim_number,
                claim_type=str(row.PERIL),
                suburb=row.SUBURB,
                hex_id=None,  # pending geocoding — see module header
                claim_date=ts,
                hour=ts.hour,
                hour_known=True,
                amount=float(row.CLAIM_AMOUNT),
            ))
            inserted += 1
            if inserted % 1000 == 0:
                db.commit()
        db.commit()
    finally:
        db.close()

    print(f"Loaded {inserted} claims (skipped {deduped} duplicate Incident ids in source file).")
    print(f"Suburb coverage: {100 - unknown_pct:.1f}% known, {unknown_pct:.1f}% UNKNOWN.")
    print("hex_id is null for all rows — geocoding pending (Ndu, docs/02 §3).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/load_claims.py <path-to-Gradhack_Insure_Data.xlsx>")
    load(sys.argv[1])
