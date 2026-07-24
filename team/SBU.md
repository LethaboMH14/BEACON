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

## Watch-outs
- API keys (WeatherAPI, EskomSePush) — you hold them; `.env` only; repo is public.
- Fan-out budget ≤300 ms server-side; contract tests enforce shapes, not just status codes.
- The verify endpoint is load-bearing for our ethics story — it must write WHO verified WHAT WHEN to the evidence chain.
