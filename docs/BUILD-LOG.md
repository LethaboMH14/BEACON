# ILISO — Build Log (newest first)

Every behaviour change gets an entry in the same commit. Plain-language section mandatory — anyone on the team must be able to read it.

---

## 2026-07-24 — G2: brain/ Sighting Graph (entity resolution + F1 recurrence + human gate)

**Tech stack:** Python 3.11, stdlib only (`dataclasses`, `math`, `datetime`) — no new dependencies. FastAPI server imports `brain/` directly via a `sys.path` insert (server and brain are siblings at repo root, docs/01 §2.2/§2.3).

**What (technical):**
- `brain/entity_resolution.py` — `resolve_plate_entity()`. Confusion-aware Levenshtein: standard DP edit-distance table, but substitution cost is 0.25 (not 1.0) for OCR-confusable pairs `{0,O} {1,I} {8,B} {5,S}` (docs/01 §3). `match_quality()` normalizes to `[0,1]`; `MATCH_THRESHOLD = 0.80` decides same-entity vs new-entity. Quality always travels with the match, never silently exact-matched.
- `brain/fusion.py` — `Entity` dataclass (`entity_id, plate_text, sightings, state, score_log_odds, factors`). `factor_f1_recurrence()` implements docs/01 §4 F1 exactly: ≥3 sightings, ≥2 distinct `camera_id`s, within a 14-day window ending at the latest sighting, entity not on `WHITELIST_PLATES`. `recompute()` sums fired factors' log-odds (`F1 = +2.2`, placeholder pending G3 calibration), converts to a probability via standard logistic for display, and sets state — but the ceiling is hard-coded: this function can only reach `observed`/`watch_candidate`/`whitelisted`, never `flagged`. `human_verify(entity, action, operator_id)` is the only function that can set `flagged`/`dismissed`, and raises `ValueError` if `operator_id` is empty (ADR-0002 human-gate, enforced in code not just docs — CLAUDE.md §4.4 equivalent principle "hard triggers/human gate bypass nothing, ML never decides alone").
- `server/main.py` — `POST /v1/sightings` now: if `plate_text` present, resolves against all known entity plates, appends the sighting, calls `recompute()`; if state just crossed into `watch_candidate` this call, broadcasts `entity.candidate` over `/ws/ops` (new event, additive to docs/01 §5 contract — matches the event already named there). `GET /v1/entities/{id}` and `POST /v1/entities/{id}/verify` now return real `Entity` state instead of stub dicts; verify still broadcasts `entity.flagged`/`entity.updated`.
- Tests: `brain/tests/test_entity_resolution.py` (6 tests — identical/confused/different plates, resolve-match, symmetry) + `brain/tests/test_fusion.py` (8 tests — below/at/above recurrence threshold, single-camera never escalates, whitelist suppresses F1, **machine can never reach `flagged`**, `human_verify` requires `operator_id`, decision freezes state against later sightings). 14/14 pass.

**Method (plain-language):** Give the system three sightings of the same car on two different cameras within two weeks and it now genuinely raises its hand — "I think this is worth a look" — without ever being allowed to accuse anyone itself. I proved this live: posted three sightings of the *same* plate with realistic OCR noise (`CA123456`, `CAO123456`, `CA0123456` — a real OCR engine would read these differently frame to frame), watched the system correctly recognise all three as one car, watched it cross into `watch_candidate` and broadcast that over the live feed, then called the verify endpoint as a human operator and watched it become `flagged` only then. This is Act 1 of the demo script (docs/06) — "three sightings, two cameras... watch candidate... Verify → Flag" — no longer a scripted claim, it's real code doing real math live.

**Why:** team/LETHABO.md G2 goal — port `brain/` (log-odds fusion, conflict gate, human-gate cap per ADR-0002). Scoped to F1 only for this slice (F2-F6 need inputs — claims-peak histogram, near-repeat kernel, camera dwell baseline, road graph, weapon/audio events — that don't exist in this repo yet; stubbed as TODO in `fusion.py` so adding them later is additive, not a rewrite).

**Integration:** Sits directly on the G0/G1 spine — no contract changes needed beyond the `entity.candidate` event docs/01 §5 already names. Server is fully backward compatible: sightings without `plate_text` (plain person/vehicle detections) behave exactly as G0/G1.

**Verified live:** server running, WS-connected check script posted 3 sightings → confirmed `entity.candidate` broadcast with `state: watch_candidate`, `factors: ["F1"]`, `score: 0.9` → posted `/verify {action: flag}` → confirmed `entity.flagged` broadcast with `state: flagged`. Full loop, real math, real server, not a mock.

**Not yet real (honesty ledger, docs/01 §7):** F2-F6, conflict gate, trajectory prediction/digital cordon, face/vehicle-embedding entity resolution (needs vision/ Tier 2 — ArcFace/EasyOCR — not built), whitelist management UI.

---

## 2026-07-24 — G1: latency harness ported + tunnel proven live

**What:** Added `scripts/latency.py` — measures `POST /v1/sightings` → `WS /ws/ops sighting.new`, matched by `sighting_id` so a concurrent probe can't corrupt the result (same pattern as VUKA's `scripts/e2e_latency.py`). Ran it live against the G0 server: n=10, mean=278.8ms, p50=272.7ms, p95=318.4ms — well under the 2.0s budget (docs/01 §6). Also ran `cloudflared tunnel --url http://localhost:8000` (already installed from the VUKA playbook, ADR-0008 equivalent) and confirmed `/health` responds over the public `.trycloudflare.com` URL — the demo topology (docs/06 §0: server on A/B + tunnel so B/C connect across houses) works. Tunnel was transient (torn down after the check, no URL committed per CONTRIBUTING.md secrets rule).

**Why:** team/LETHABO.md G1 goal — prove the spine is fast enough and reachable across machines before the real demo rehearsal, using real numbers instead of assuming.

**Plain language:** The system responds fast — a third of a second from camera to dashboard, way inside our 2-second promise. And the tunnel trick that lets three separate laptops (camera / ops console / member view) talk to each other over the internet during the Teams demo — the same one VUKA used — works for BEACON too. Nothing left to guess about on demo day for this part.

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
