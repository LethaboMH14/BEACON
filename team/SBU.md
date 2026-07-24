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

## Done (2026-07-25) — G0–G3 backend closed out

Everything previously listed here is merged: schema, sightings ingest, entity resolution, verify+evidence chain, the flag→Incident→Alert blocker, `/v1/risk`+`/v1/hotspots`+`/v1/risk-cells`, OR-Tools routing + persistence, real claims data (15,712 rows), CI, demo reset script, WS reconnect catch-up, camera health, incident report endpoint. 85/85 tests passing on `main`. Full history in `docs/BUILD-LOG.md`.

## Now — two real gaps found doing a fresh pass over `server/src/` (2026-07-25), while Lethabo moves into UI design

- [ ] **`operator_id` is unauthenticated free text — undermines the evidence-chain honesty claim.** Checked `entities.py`'s `verify_entity`: `operator_id: str = Field(...)` comes straight from the request body and is written verbatim into `EvidenceChain.actor_id` (and `Watchlist.added_by`, the Incident's evidence entry, etc.) with **no check that the caller is who they claim to be**. The pitch's ethics story rests on "WHO verified WHAT WHEN" being trustworthy (CLAUDE.md-equivalent honesty ledger, docs/06) — right now anyone hitting `POST /v1/entities/{id}/verify` can write any operator name into the permanent hash-chained record. Doesn't need full OAuth for a hackathon: a small static roster in `.env` (`OPERATOR_TOKENS={"op_001": "<token>"}`), a required header (`X-Operator-Token`), and a lookup that rejects/401s if the token doesn't match the claimed `operator_id`, is enough to make the claim true rather than assumed. Add a contract test that a mismatched token/operator_id pair is rejected.
- [ ] **Nothing is actually deployed to Azure yet.** ADR-0015 (docs/adr.md) picked Azure Container Apps for `server/` + Key Vault for secrets months... well, days ago — but there's no `Dockerfile`, no bicep/terraform, no live Container Apps instance anywhere in the repo. This is explicitly a "G3-optional flex" per that ADR (the real demo runs on localhost + cloudflared regardless, so this isn't a blocker) — but if a judge asks "is this actually deployed" the honest answer right now is no. If there's spare time: (1) `server/Dockerfile` (multi-stage, slim base — `ortools`/`pandas` make the image big, worth checking final size), (2) a minimal bicep/CLI script provisioning the Container App + Key Vault per the ADR's service map, (3) point `DATABASE_URL`/secrets at Key Vault instead of `.env` for that deployment. Treat as genuinely optional — don't let it eat into anything Connie/Ndu still need from you.

Postgres+pgvector migration stays explicitly deprioritized ("don't gold-plate") — SQLite is fine for the pitch.

## Watch-outs
- API keys (WeatherAPI, EskomSePush) — you hold them; `.env` only; repo is public.
- Fan-out budget ≤300 ms server-side; contract tests enforce shapes, not just status codes.
- The verify endpoint is load-bearing for our ethics story — it must write WHO verified WHAT WHEN to the evidence chain.
