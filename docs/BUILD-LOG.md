# ILISO — Build Log (newest first)

Every behaviour change gets an entry in the same commit. Plain-language section mandatory — anyone on the team must be able to read it.

---

## 2026-07-24 — G0 spine: vision agent → server → dashboard, live end-to-end

**What:** Added `vision/agent.py` (webcam → YOLOv8n person/vehicle boxes, Tier 0 motion gate, POSTs `sighting` JSON matching docs/01 §5), `server/main.py` (FastAPI + WS hub — `POST /v1/sightings`, `GET /v1/entities/{id}`, `POST /v1/entities/{id}/verify`, `GET /v1/hotspots` stub, `WS /ws/ops` fan-out), and `dashboard/index.html` (single-file live-feed skeleton for Connie to replace with the full React/Vite/Tailwind app from docs/04). Added `.claude/launch.json` for local dashboard preview. Verified live: server health check, `POST /v1/sightings` → `WS /ws/ops sighting.new` broadcast, payload shape matches contract exactly (scratch WS client test, not committed).

**Why:** team/LETHABO.md G0 goal — prove the spine talks end-to-end before anyone's individual piece (Sali's fine-tuned weights, Ndu's forecast layer, Connie's real dashboard) lands, so they integrate into something already working instead of building in isolation.

**Plain language:** There's now a working (if bare-bones) BEACON: point a webcam at `vision/agent.py`, it detects people/vehicles and sends them to the server, and any dashboard connected to the server's live feed sees them appear instantly. No suspicion scoring, no faces, no plates yet — that's the Sighting Graph and lands at G2 (ADR-0002). This is just the wiring, proven to work, so everyone else has something real to plug into.

---

## 2026-07-24 — Rename to BEACON + Discovery alignment + contribution workflow

**What:** ADR-0003: platform renamed ILISO → **BEACON** ("the light that stays on") across CLAUDE.md, docs 01–06, README, team briefs (adr.md + genesis log entry keep ILISO as history). Added docs/05 §1b mapping BEACON to Adrian Gore's Four Principles + Discovery's core purpose. Added the collaboration kit: CONTRIBUTING.md, .github/PULL_REQUEST_TEMPLATE.md, .github/CODEOWNERS, design/ folder for mockups.

**Why:** Team decision — English name, Discovery-brand aligned. Repo about to go public on GitHub (Lethabo creates it); everyone starts adding mockups and code, so the see-review-amend loop needed to exist first.

**Plain language:** The project is now called BEACON. When you push work, you do it on your own branch and open a pull request — that's how the rest of us see what you added, comment on it, and improve it together. Mockups go in the `design/` folder via the same pull-request flow. Set GitHub notifications to "All activity" for this repo so you see every addition.

---

## 2026-07-24 — Project genesis: full architecture + team pack

**What:** Created the ILISO doc pack from scratch: CLAUDE.md master context, docs 01–06 (architecture, data/forecasting, vision ML, UI brief, business case, demo plan), ADR-0001 (name/stack/repo) + ADR-0002 (human-gated suspicion engine), five team briefs.

**Why:** Theme 3 brief ("Biometric community security network") + Gradhack_Insure_Data.xlsx analysis + research pass (Koper curve, near-repeat, RTM, NIST FRVT, Flock/ZeroEyes case studies, Discovery shared-value model). Leader guidance: 70/30 demo/slides, virtual over Teams, showable by 12:00 today.

**Plain language:** We started the new project for the real Gradhack theme. It has a name (ILISO — "the eye"), a plan, and a one-page starting document for each of us in `team/`. Read CLAUDE.md, then your own file, and you know exactly what to do this morning. The big design ideas: predict crime before it happens using Discovery's own claims data; spot repeat cars/people across cameras (the "seen 3 times" rule) but ALWAYS with a human confirming before anything happens; and route security patrols in 12-minute visits to the right streets at the right hours to save fuel and prevent break-ins.

**Breaks/risks:** Name needs a collision check before public use. Geocoding of suburbs must start early (slow API). The 00:00 data spike needs the hour_known caveat in every chart.
