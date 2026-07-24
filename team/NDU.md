# Ndu — data science + engineering + business case

**Mission:** the brain's memory and the pitch's wallet. Real claims data → clean → geocoded → enriched (weather, load-reduction, marches/events, paydays) → forecast that beats a naive baseline → route optimizer counters → the money slide. Full spec: docs/02 + docs/05.

## By 12:00 (G0)
- [ ] Load Gradhack_Insure_Data.xlsx in pandas; apply cleaning rules docs/02 §2 (reversals, NULL suburbs, tz, hour_known flag); save parquet
- [ ] Charts: hour histogram (the 00:00 spike), peril split (93.6/6.1), top-20 suburbs, monthly trend — these open the demo
- [ ] Start Nominatim geocode of top suburbs → `data/geocode/suburbs.json` (rate-limited ~1/s — start EARLY, it runs while you do other things)

## Then
- G1: H3 assignment; baseline hex×hour×weekday model + near-repeat kernel; hand `risk_cells` JSON to Sbu's /v1/risk
- G2: LightGBM with covariates (weather + outage real via Sbu's keys; events/marches hand-seeded `sim_events.csv` — a known march date near a hot-spot makes a great demo beat); calibration + PAI eval vs naive baseline (the honest uplift number for the pitch); OR-Tools route run → fuel −X% / coverage Y% counters
- G3: business case slides with Sali (docs/05): the R1.09bn table, Vitality Protect loop, verified market figures (PSiRA guard count, Vumacam/DeepAlert status — verify before pitch, don't quote stale numbers)

## Watch-outs
- The 00:00 spike is partly "discovered next morning" coding — handle with hour_known, SAY IT in the pitch before a judge's analyst does.
- Every number on a slide traces to a query you can re-run. No invented precision — if it's a target, label it "target".
