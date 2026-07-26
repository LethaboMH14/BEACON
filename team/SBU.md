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

## Done since (2026-07-25 → 2026-07-26)

- [x] `operator_id` auth closed — `entities.py`'s `verify_entity` now requires `X-Operator-Token` matched against `OPERATOR_TOKENS` via `require_operator_token`. Same pattern was reused for the new vision escalate endpoint (below).
- [x] `server/Dockerfile` exists. Azure deploy templates written (`infra/main.bicep`, `infra/deploy.ps1`, `infra/README.md`) — not deployed yet, waiting on a fresh `az login` (unrelated token-expiry issue, not a code problem). Full writeup: `docs/HANDOVER-SBU.md`.
- [x] Vision detect→decide→escalate→notify backend landed: `server/src/vision/{detectors,decision,jobs}.py`, `server/src/notify/email.py`, `server/src/api/vision_jobs.py`. 166/166 tests passing. Read `docs/HANDOVER-SBU.md` before touching this — the human-gate rule (machine reaches Candidate, never Escalated, without a named operator) is load-bearing for the ethics story, same as the verify endpoint above.

## Now — while Azure login/deploy is blocked on Lethabo, real gaps you can close independently

- [ ] **The vision spine has no UI.** Backend is done and tested but nothing in `dashboard/app` renders it — grepped `dashboard/app/src` for `vision.frame`/`vision.decision`/`vision.escalated`, zero matches. These already stream over the existing ops WebSocket (`ws_manager.broadcast_to_ops`), same channel the live feed already listens to — this is a new event-type branch on an existing subscription, not a new integration. Minimum viable: a panel that shows job progress (`vision.frame`), the current decision level + reason (`vision.decision`), and an escalate button that POSTs `/v1/vision/jobs/{id}/escalate` with an `X-Operator-Token`. This is the actual ring-camera demo flow (`docs/DESIGN-BRIEF-demo-concepts.md`) and currently the single biggest gap between "backend works" and "judges can see it work."
- [ ] **`vision/backend/Dockerfile` and `vision/weapen_backend/Dockerfile` don't exist.** `infra/deploy.ps1` already checks for them and skips with a warning if missing — it won't fail the deploy, but the two vision Container Apps in `infra/main.bicep` will have nothing to run. Both services are already plain FastAPI apps (`vision/backend/app.py`, `vision/weapen_backend/app.py`) — a Dockerfile each (mirror `server/Dockerfile`'s pattern) is what's missing, not new code.
- [ ] **Run the vision pipeline end-to-end with real keys, once.** Every test so far is against synthetic detections (`test_vision_decision.py`) or was measured by Lethabo with his own Roboflow key. Get your own free-tier Roboflow key + SendGrid key (see `docs/HANDOVER-SBU.md` §1), point `.env` at them, upload one of the real ring-cam clips via `POST /v1/vision/jobs`, and confirm an escalation actually lands an email in your inbox. This is the one part of the honesty story ("does this actually work") that hasn't been proven outside Lethabo's machine.
- [ ] **Ndu's SAPS+claims map still isn't merged into the live dashboard**, and the known duplicate Sandton-suburb popup bug is still open (`hotspot_pipeline/combined_hotspot_map.html` on `origin/main`). If you have spare cycles before the UI work above, this is next in line — but the vision UI panel is the higher-value gap for the pitch.

Postgres+pgvector migration stays explicitly deprioritized ("don't gold-plate") — SQLite is fine for the pitch.

## Flagged for you (2026-07-26) — I patched this, you should know why

- **`server/requirements.txt` was missing `opencv-python-headless` and `numpy`.** Deploying the API container to Azure (`beacon-rg`, francecentral) it crashed on startup: `ModuleNotFoundError: No module named 'cv2'` from `src/vision/jobs.py` → `detectors.py`/`preprocess.py`, which import `cv2`/`numpy` directly. It worked on your machine because one of those was already present from an unrelated install — the declared dependency list itself was incomplete. This was blocking the deploy I was doing, so I added both (headless build, since the container has no GUI libs) and rebuilt — API is now healthy in Azure (`/health` returns 200). Committed in `6963534` alongside the infra region/Static-Web-App changes. Flagging per our usual rule that you own fixes in your areas — nothing else in `vision/` was touched.

## Watch-outs
- API keys (WeatherAPI, EskomSePush) — you hold them; `.env` only; repo is public.
- Fan-out budget ≤300 ms server-side; contract tests enforce shapes, not just status codes.
- The verify endpoint is load-bearing for our ethics story — it must write WHO verified WHAT WHEN to the evidence chain.
