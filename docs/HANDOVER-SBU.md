# Handover to Sbu — launching BEACON (2026-07-26)

You own `server/` and `ops-dashboard`/`dashboard/` (docs/CONTRIBUTING.md). This doc is
everything you need to run the app locally today, and what changes once Azure is live.
Read `CLAUDE.md` and `docs/BUILD-LOG.md` (top entry, 2026-07-26) first if you haven't —
this doc assumes you have.

**Status right now:** Azure infra is templated (`infra/`) but **not deployed yet** — my
login session expired and I'm waiting on a fresh `az login`. Everything below under
"Run it today" works with zero Azure dependency. Skip to "Once Azure is live" for what
changes after that.

---

## 1. Run it today (no Azure needed)

### Server

```bash
cd server
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Default `.env` is SQLite (`sqlite:///./beacon.db`) — no external DB required. Health
check: `GET http://localhost:8000/health`.

Set in `.env` before you need vision/escalation to actually work:

```env
ROBOFLOW_API_KEY=<yours>
EMAIL_PROVIDER=sendgrid
SENDGRID_API_KEY=<yours>
ESCALATION_FROM=<a SendGrid-verified sender — see §3>
ESCALATION_TO=<where escalation emails should land, comma-separated>
```

I hold my own Roboflow/SendGrid keys locally — repo is public, so per CONTRIBUTING.md
these never go in git, only in your own gitignored `.env`. Get your own keys (both free
tier) rather than sharing mine:
- Roboflow: roboflow.com → create account → Settings → API key
- SendGrid: sendgrid.com → create account → Settings → API Keys

### Dashboard

```bash
cd dashboard/app
npm install
npm run dev
```

Vite dev server, defaults to `localhost:5173`. `CORS_ORIGINS` in server `.env` already
includes it.

### Tests

```bash
cd server
pytest                       # 166 passed as of this handover
```

---

## 2. What's new since you last looked — the vision decision spine

This is the piece that was missing: a detection used to just sit there with a
confidence score and nothing downstream. Now there's a full path from "camera sees
something" to "a named human decided to act on it" to "an email actually sent."

```
video upload
   -> server/src/vision/jobs.py       (samples frames, runs as background job)
       -> server/src/vision/preprocess.py   (CLAHE for low light — from the ring-cam clip work)
       -> server/src/vision/detectors.py    (Roboflow plate + weapon models, run in parallel)
       -> server/src/vision/decision.py     (turns detections into a level + a reason)
   -> operator reviews via GET /v1/vision/jobs/{id}
   -> operator calls POST /v1/vision/jobs/{id}/escalate
       -> server/src/notify/email.py        (sends — ONLY if the escalate call succeeded)
```

**The one rule that matters, mirrored from `suspicion/scorer.py` (ADR-0002):** the
machine can reach `CANDIDATE` on its own. It can **never** reach `ESCALATED` without a
named operator calling `escalate()` — that function raises `ValueError` if the actor is
empty or the situation hasn't reached `CANDIDATE` yet. `notify/email.py` independently
re-checks `situation.level is Level.ESCALATED` before it will send anything. Two
separate gates, on purpose — don't remove either one to make a demo path shorter.

### API surface (all under `/v1`, see `server/src/api/vision_jobs.py`)

| Route | What it does |
|---|---|
| `GET /vision/backend` | which detector backend is active (hosted/local) |
| `POST /vision/jobs` | upload a video (mp4/mov/avi/mkv/webm, ≤60MB), starts processing |
| `GET /vision/jobs` | list jobs |
| `GET /vision/jobs/{id}` | poll status/progress/frames |
| `DELETE /vision/jobs/{id}` | cancel a running job |
| `POST /vision/jobs/{id}/escalate` | the human-decision endpoint — requires `X-Operator-Token`, body `{actor, note}` |

Progress also streams over the existing ops WebSocket (`ws.manager.ws_manager`) as
`vision.started` / `vision.frame` / `vision.decision` / `vision.escalated` /
`vision.failed` / `vision.cancelled` — same channel the dashboard already listens to for
sightings, so a live "processing frame 12/45" indicator is a small dashboard addition,
not a new integration.

**Operator tokens:** same pattern as the existing `POST /v1/entities/{id}/verify` — set
`OPERATOR_TOKENS={"op_001": "<token>"}` in `.env` (JSON). If unset, auth is skipped (fine
for local dev, not for the demo — set it before Sandton).

### What's NOT built yet (frontend)

The backend above is done and tested (`server/tests/test_vision_decision.py`, 20 tests).
**No UI consumes it yet.** This is the ring-camera side-panel flow from
`docs/DESIGN-BRIEF-demo-concepts.md`: upload/point a clip at a camera, show it framed
like a live feed, surface `vision.frame`/`vision.decision` events as they stream in, and
give the operator an escalate button that calls the endpoint above. That's open — pick
it up or hand it to Connie, your call.

### Known limitation, stated honestly

Local (on-device) inference for the vision models could not be installed into the
server's Python environment — `pip install inference` pulls a pydantic version that
conflicts with everything else here and breaks the server. I did not force it. Current
default is the **hosted** Roboflow backend, measured at ~1.1s/frame with plate+weapon
running in parallel (down from 8-14s through the old sequential workflow endpoints).
Local inference belongs in its own container — that's exactly why the Azure table
separates vision into its own Container Apps (see §4). The ~0.1-0.3s local-latency
number that was floated earlier is **unproven** — don't quote it in the pitch as
measured, only as a target.

---

## 3. Gotchas that will bite you

- **SendGrid rejects your first send** unless you've done Settings → Sender
  Authentication → Single Sender Verification, and `ESCALATION_FROM` in `.env` matches
  that exact verified address. Do this before the demo, not during it.
- **Raw video is never committed.** `vision_jobs.py` streams uploads to a system temp
  dir (`UPLOAD_DIR`), never the repo — several demo clips are copyrighted broadcast
  footage. If you're testing locally, your own clips stay off git the same way.
- **The escalate endpoint is a one-way door on purpose** — once `escalated_by` is set on
  a situation, further `observe()` calls (more frames) cannot undo or downgrade it
  (`_derive_level()` checks this first). Don't "fix" this if it looks like a bug in
  testing — it's the point.

---

## 4. Azure is live (2026-07-26) — here's what you actually need

**The API is deployed and healthy:**

```bash
curl https://beacon-api.ambitiousflower-ff5d4625.francecentral.azurecontainerapps.io/health
# {"status":"healthy","database":"connected","websocket":"ready"}
```

`beacon-api` is the only Container App in `beacon-rg` now — the two standalone vision
services (`vision/backend`, `vision/weapen_backend`) were removed from `infra/main.bicep`
and deleted from Azure. They're superseded: `server/src/vision/detectors.py` already
calls Roboflow's hosted model directly from inside the API container, measured 3.5x
faster than the old workflow-based services (their own docstring has the numbers). No
separate vision deploy exists to think about.

### Your job: deploy the frontend(s) to Vercel

You deploy `dashboard/app` (and any other frontend, e.g. `app/web`) to Vercel yourself —
your account, your call on project settings. The only thing that has to be set is a
build-time env var so the deployed frontend stops assuming it's running behind vite's
local dev proxy:

```
VITE_API_BASE=https://beacon-api.ambitiousflower-ff5d4625.francecentral.azurecontainerapps.io
```

Set that in the Vercel project's Environment Variables before building. Without it,
every `fetch`/WebSocket call falls back to relative paths that only resolve locally —
see `dashboard/app/src/api/base.ts` and `dashboard/app/.env.example`. Nothing else in
the frontend code changes for a Vercel deploy; this is the one knob.

The demo itself runs off your deployed Vercel frontend hitting this live Azure API —
you don't run a local server, and you don't need a local Postgres.

### Your own Azure access, if you want it

You now have a service principal scoped **only** to `beacon-rg` (can't see or touch
anything else in the subscription) with Contributor rights. Lethabo will hand you the
credentials directly (not over a public channel, not committed). Once you have them:

```bash
az login --service-principal -u <appId> -p <password> --tenant <tenant>
az account set --subscription 96a8041a-e4db-4054-8dc6-a916b2951923
```

What that unlocks for you:
- **Set/rotate the Roboflow + SendGrid keys** on the live API without a full redeploy:
  ```powershell
  ./infra/set-vision-secrets.ps1 -ResourceGroup beacon-rg
  ```
  Prompts for both as SecureStrings — blank leaves that piece unwired, no error. Vision
  detection and escalation email aren't wired on the live API yet; this is how you'd do
  it with your own keys.
- Redeploy/adjust `infra/main.bicep` yourself if something needs fixing and Lethabo
  isn't around — full Contributor on `beacon-rg` covers that.

You do **not** need this just to deploy to Vercel — only if you want to touch Azure
directly (set the vision keys, poke at Postgres/Container Apps, redeploy infra).

### What's in beacon-rg today

| Resource | Purpose |
|---|---|
| `beacon-api` (Container App) | FastAPI + WS, the only compute — vision runs inside it |
| `beacon-pg-*` (Postgres Flexible Server) | Primary DB, `sslmode=require` |
| Storage account | clip/evidence storage |
| Key Vault | secret storage referenced by the API |
| Container Registry | holds the `beacon-api` image |

`DATABASE_URL`, `KEY_VAULT_URI`, `AZURE_STORAGE_ACCOUNT` are already wired into
`beacon-api`'s env — you don't set these yourself unless you're redeploying infra.

---

## 5. Where to look for more detail

- `docs/BUILD-LOG.md` (2026-07-26 entry) — the plain-language version of everything above
- `docs/adr.md` — ADR-0002 is the one this whole spine mirrors
- `server/src/vision/decision.py` — read this one file top to bottom, it's short and it's
  the actual contract
- `infra/README.md` — Azure specifics
