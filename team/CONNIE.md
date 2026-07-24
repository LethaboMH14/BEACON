# Connie (Ipeleng) — UI + interaction logic

**Mission:** three views, one app — and the ops console IS the demo stage for ~6 of 9 minutes. Full spec + the reasoned who-gets-a-dashboard answer: docs/04.

## By 12:00 (G0)
- [ ] Read docs/04 §1–2. Mock the ops console (Figma or straight HTML): 3-panel layout, alert-card anatomy (thumbnail · calibrated confidence bar · factor chips · cancel ring · Verify/Dismiss/Dispatch), verify-queue screen
- [ ] Mock the member alert screen (soft language, cancel + Guardian actions)
- [ ] Get VUKA token file + dashboard skeleton from Lethabo — Discovery light theme, dark chrome header

## Then
- G1: React shell on the skeleton, WS live-feed cards rendering real sightings (Lethabo pairs on wiring)
- G2: verify queue + entity detail (factor chips F1–F6, suspicion sparkline, trajectory cone) + routes panel (Koper dwell timers, fuel/coverage counters) + member view
- G3: polish; YOU drive the ops console live in the pitch — rehearse the click-path until boring

## The four UI laws (docs/04 §4 — you enforce them in code)
1. Verify is always the primary action; Dispatch is behind confirmation.
2. One calibrated number + factor chips; never raw model confidences.
3. Stale is marked stale; sim data carries a SIMULATED tag even in the UI.
4. Copy is honesty-ledger compliant: "weapon-candidate", "possible repeat sighting" — never "criminal identified".
