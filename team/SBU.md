# Sbu — backend + systems (with Lethabo)

**Mission:** the server is the product's nervous system: sightings in, suspicion + risk + routes out, alerts fanned out in ≤300 ms. You own the API contract (docs/01 §5) — nobody changes it without your sign-off + an ADR.

## By 12:00 (G0)
- [ ] Read CLAUDE.md + docs/01. Nitpick pass: flag anything infeasible or mis-modelled TODAY in a `docs/adr.md` proposal or a blunt Notion comment — same expectation as VUKA ("Sbu nitpicks, not just implements")
- [ ] DB schema v0 (SQLite): cameras, sightings, entities, whitelist, claims, incidents, alerts — migrations from day one
- [ ] Take over `server/` v0 from Lethabo's skeleton; contract tests for /v1/sightings + WS echo (pytest, VUKA style)

## Then
- G1: entities + verify endpoint (human gate!), alerts with ack/cancel, WS rooms (ops vs member), evidence-chain port (hash-chained actions)
- G2: /v1/risk + /v1/hotspots serving Ndu's model output; /v1/routes/plan wrapping OR-Tools; Postgres+pgvector migration if time (SQLite is acceptable at the pitch — don't gold-plate)
- G3: demo orchestration with Lethabo: tunnel, seeders, demo clock, reset script (one command returns the whole system to demo-start state)

## Now (backend/systems — G0/G1/G2 done, non-UI so it doesn't collide with Connie)

G0–G2 are merged: schema, sightings ingest, entity resolution, verify+evidence chain, alerts, `/v1/risk`+`/v1/hotspots`, OR-Tools routing. Three real gaps left in your lane, found while reconciling `server/main.py` into `server/src/` (2026-07-25):

- [ ] **G3 demo orchestration** (`scripts/` currently only has `latency.py`) — the cloudflared tunnel launcher, `DEMO_TIME` clock override, and a **one-command reset script** that returns the whole system to demo-start state. There's no seed script at all right now — the only way data gets into the DB is live POSTs or test fixtures, so a second demo run means manually wiping `beacon.db` by hand.
- [ ] **Seed data script** — load `Gradhack_Insure_Data.xlsx` claims into the `claims` table for real (via pandas, same cleaning rules as docs/02 §2 if Ndu hasn't landed a parquet yet). F3 (near-repeat crime correlation) and the `/v1/risk` fallback both key off real `Claim` rows and currently have nothing outside tests.
- [ ] **`POST /v1/risk-cells` ingest endpoint** — checked `server/src/api/risk.py`: only `GET /v1/risk` and `GET /v1/hotspots` exist, no write path. When Ndu's forecast model is ready it has nowhere to land its output except writing directly to SQLite. Build this now so it's not a last-minute scramble when his G2 model lands.

Postgres+pgvector migration stays explicitly deprioritized ("don't gold-plate") — skip unless everything above is done with time to spare.

## Blocker found tracing the live path end-to-end (2026-07-25) — do this one first

- [ ] **`verify(flag)` never creates an Incident, but `POST /v1/alerts` requires one.** Traced the actual code, not just the endpoint list: `entities.py`'s `verify_entity` with `action=flag` sets `entity.state="flagged"`, adds a `Watchlist` row, writes evidence — but never touches the `incidents` table. `alerts.py:114` hard-404s `POST /v1/alerts` if `incident_id` doesn't already exist, and nothing in the live code path ever creates one (only test fixtures do). Net effect: **there is currently no live route from "operator clicks Verify → Flag" to "an alert fires"** — the exact Act 1 beat the whole demo script is built around (docs/06: flag → alert pops on Laptop C → the "1.4 seconds" number). This is a backend data-model gap, not a missing dashboard button — fixing the dashboard won't fix this. Fix: on `flag`, create (or reuse) an `Incident` row for that entity/hex, then either fire the alert directly from there or return the new `incident_id` so the dashboard has something valid to POST against.

## Further refinement, roughly in priority order once the blocker above is fixed

- [ ] **WebSocket catch-up on reconnect** — reconnection is currently client-side only with no replay (known G0 gap). The demo topology is 3 laptops across different houses over a tunnel (docs/06 §0); a network hiccup mid-Act-1 means the ops feed just goes silent with no way to recover missed events. Cheap fix: a `GET /v1/events/since?ts=` the dashboard calls on reconnect to replay anything it missed — no need for full server-side session state.
- [ ] **Camera/sensor health signal** — auto-registration (just added) creates a `Camera` row on first sighting, but nothing ever updates `last_seen_at` or exposes online/offline status. If a laptop's webcam or mic agent silently dies mid-demo, ops has zero signal why the feed stopped. Bump `last_seen_at` on every sighting from that camera + add `GET /v1/cameras` returning a status list — this is also what would feed a future "node health" dashboard view.
- [ ] **Route persistence** — `POST /v1/routes/plan` computes and returns a plan but never writes the `Route` row the schema already has (`server/src/api/routes.py` has no `db.add`/`db.commit`). Fine for a single-shot demo; matters only if Act 2 ever needs to reference a plan after the fact.
- [ ] **Evidence/incident report endpoint** — `GET /v1/evidence/integrity` only answers chain-intact yes/no. A `GET /v1/incidents/{id}/report` that bundles the entity, all its sightings, and its full evidence-chain trail into one document would make "structured to support a case" (the honesty-ledger claim) a real deliverable instead of just a true-but-unproven statement.

## Watch-outs
- API keys (WeatherAPI, EskomSePush) — you hold them; `.env` only; repo is public.
- Fan-out budget ≤300 ms server-side; contract tests enforce shapes, not just status codes.
- The verify endpoint is load-bearing for our ethics story — it must write WHO verified WHAT WHEN to the evidence chain.
