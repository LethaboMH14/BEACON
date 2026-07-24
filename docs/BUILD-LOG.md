# ILISO — Build Log (newest first)

Every behaviour change gets an entry in the same commit. Plain-language section mandatory — anyone on the team must be able to read it.

---

## 2026-07-24 — G2: POST /v1/routes/plan — OR-Tools patrol routing, real centroids not H3 math

**What:** `server/src/routing/planner.py` (`plan_routes`) + `server/src/api/routes.py` (`POST /v1/routes/plan`). Wraps Google OR-Tools (`RoutingIndexManager`/`RoutingModel`) as a team-orienteering problem: each candidate hex (ranked by `risk/forecast.py`'s `rank_hotspots`) is an *optional* stop via `AddDisjunction`, with a skip penalty proportional to its risk score — so under a tight fuel/time budget the solver drops the lowest-value stops instead of failing outright. Distance dimension capped at `fuel_budget_km`, time dimension (haversine travel time + a fixed 12-minute Koper dwell per stop, from the deterrence literature cited in docs/01 §4) capped at `shift_window_minutes`. Hex→coordinate lookup uses the real average `Claim.lat`/`Claim.lng` for that hex, not H3 cell math — reported as `unlocatable` if a hex has no located claims.

**Why:** G2 checklist (team/SBU.md), completing the frozen contract's `POST /v1/routes/plan`. Two things worth flagging: (1) `h3` was pulled from `requirements.txt` entirely — `h3.cell_to_latlng()` raised `H3CellInvalidError` on the `hex_id` strings already used throughout the repo's fixtures/seed data, so rather than patch upstream hex generation mid-hackathon, centroids are derived from real claims data instead, same honesty-over-invented-infra principle as the risk fallback above. (2) Distance is haversine, not OSRM — the same feasibility nitpick raised at G0 in team/SBU.md, still deferred.

**Plain language:** Built the part that tells patrol teams where to actually go: given a shift length, a fuel budget, and how many teams are out, it picks the best set of hotspots to visit and in what order, skipping the least valuable ones first if there isn't enough time or fuel for everything. It figures out where a "hex" of the map actually is on the ground using real claim locations, not a hex-grid formula that didn't match the data we already had.

**Verified:** 66/66 server tests pass (8 new: empty-candidates, nearby-high-value preferred over far-low-value, fuel budget respected, unlocatable hex reported not silently dropped, dwell time counted against time budget, invalid inputs rejected, endpoint shape, endpoint validation).

---

## 2026-07-24 — G2: GET /v1/risk + /v1/hotspots — real claims fallback, no fake calibration

**What:** `server/src/risk/forecast.py` (`estimate_hex_risk`, `rank_hotspots`) + `server/src/api/risk.py` (`GET /v1/risk?hex=&hour=`, `GET /v1/hotspots?window=&limit=`). Built before Ndu's real forecast model (`data/`) has landed on `main` — rather than block on that or fake a calibrated number, this tiers: (1) trust a real `RiskCell` row if Ndu's pipeline has already written one for that hex+hour, pass its own `model_version`/`top_factors` straight through untouched; (2) otherwise fall back to a real score derived from actual `Claim` rows in that hex — claim count + a same-hour proximity boost using the same `{0,1,22,23}` peak-hour set as `suspicion/scorer.py`'s F2 (the real midnight spike, verified against `Gradhack_Insure_Data.xlsx`); (3) zero claims ever recorded for a hex → `risk_score=0.0`, labelled `no_data`, never silently omitted.

**Why:** G2 checklist (team/SBU.md), scoped to not depend on `data/` existing yet — same "serve the best real signal available, label honestly, let the real thing slot in later without a contract change" pattern VUKA's `compute_risk` used in the identical situation. The fallback is explicitly labelled "not a calibrated probability" in every response — this is a *display* score derived from real claim counts, not an invented calibration.

**Plain language:** Built the two endpoints that answer "how risky is this area right now" and "which areas are the worst right now" — before the real prediction model exists yet. Rather than wait or fake a number, it counts real historical claims in that area and weights them by whether the hour matches the real midnight spike we found in the data. It says plainly, every time, that this isn't a proper calibrated forecast — just a real, honest placeholder that the real model will silently replace once it's ready, since it writes to the same table.

**Verified:** 58/58 server tests pass (12 new: fallback labelling, peak-hour boost direction, claim-count ordering, real-model-row-wins-over-fallback, hour validation, endpoint shapes).

---

## 2026-07-24 — G1 wired: suspicion scorer + alerts + evidence integrity — fixed one real ethics-critical bug

**What:** `server/src/suspicion/scorer.py` — the F1–F6 log-odds fusion (docs/01 §4): recurrence, time anomaly, near-repeat crime correlation (haversine, OSRM deferred per my own G0 nitpick), casing, territory roaming, modal corroboration. `server/src/api/alerts.py` — POST/GET alerts, ack/cancel with a cancel-window (ADR-0002). `server/src/db/evidence_integrity.py` — `verify_chain()`, re-walks `evidence_chain` and recomputes every hash to detect tampering. `GET /v1/evidence/integrity`. Dependency pins bumped for Python 3.13 (fastapi/uvicorn/sqlalchemy/alembic/httpx/pytest-asyncio — original pins conflicted or predated 3.13 support).

**Found and fixed while reviewing (not just running) this work:**
1. **Real bug, ethics-critical:** `_write_evidence()` called `datetime.utcnow()` *twice* — once to build the hash input, again for the stored `ts` column — so every evidence row's stored hash was computed over a timestamp that was never actually persisted. Proved it live: wrote one real row through the actual endpoint, called `verify_chain()`, got `is_intact: False` on entirely legitimate data. This is the "who verified what when" evidence the ethics pitch leans on — it must be intact by construction. Fixed by computing `ts` once and reusing it for both the hash and the stored field. Added `test_write_evidence_produces_a_row_that_actually_verifies` — every other test in that file hand-built its own consistent rows and would never have caught a bug in the real writer.
2. **Test/architecture contradiction:** the scorer weighted F1 (recurrence — "the core rule" per docs/01 §4) at 0.30, below the 0.40 candidate threshold, so F1 alone could never reach candidate — contradicting ADR-0002's ladder, where candidate is the machine-reachable tier a human then reviews. Retuned F1's weight to land exactly on the threshold; the machine ceiling (never auto-"flagged") is untouched — this only affects how *readily* a lead surfaces for human review, not whether it can bypass the human gate.
3. **Flaky test, not a scorer bug:** `test_machine_ceiling_never_flagged` claimed to trigger "all factors" but its fixture put every sighting on one camera (F1 needs ≥2) with no weapon sighting (F6 needs one), and depended on the real wall-clock hour landing in the {0,1,22,23} peak set for F2 — passable or not depending on when you ran it. Rebuilt the fixture to deterministically satisfy all six factors' actual trigger conditions, anchored to "1 day ago at 00:30" (not a hardcoded calendar date, which silently ages out of the scorer's real 14-day window as time passes — caught this the hard way mid-fix).
4. **Environment plumbing**, not app bugs: `conftest.py`'s in-memory SQLite engine had no `StaticPool`, so the TestClient's app thread got a fresh, empty `:memory:` DB separate from the fixture's — "no such table" everywhere. `test_alerts_contract.py` had its own duplicate fixture copies (missing the StaticPool fix) instead of reusing conftest's.

**Why:** G1 milestone (team/SBU.md) — entities + human-verify writing to the evidence chain, alert ack/cancel, suspicion scoring live. Reviewed rather than just run because item 1 is exactly the kind of gap that looks fine until the first real write.

**Plain language:** Built the part of the system that decides "is this car/face worth a human's attention" and the part that alerts and lets an operator confirm or cancel. While checking it — not just trusting that the tests were green — found that the tamper-evidence log (the thing that proves who verified what and when, which matters a lot for the "we did this responsibly" pitch) would have shown every real entry as broken the moment anyone actually used it, because of a timing bug that nothing was testing for. Fixed it, and added a test that exercises the real code path instead of a hand-built stand-in, so this can't silently break again.

**Verified:** 46/46 server tests pass (`pytest server/`), including the new evidence-write regression test and the corrected suspicion-scorer fixture.

---

## 2026-07-24 — G0 backend complete: FastAPI + SQLite + contract tests

**What:** Completed `server/` G0 milestone (Sbu's checklist from team/SBU.md). SQLite schema v0 with Alembic migrations (11 tables: cameras, sightings, entities, whitelist, watchlist, claims, risk_cells, incidents, alerts, routes, evidence_chain). FastAPI skeleton with CORS, health endpoints. Implemented POST /v1/sightings (single + batch), GET /v1/entities/{id} with **lazy suspicion-score decay** (score_now = base_score × 0.5^(days_elapsed/7), computed at read-time, no cron job), POST /v1/entities/{id}/verify (human gate: flag/dismiss/whitelist actions writing to hash-chained evidence_chain). WebSocket layer with room-based routing (/ws/ops, /ws/member) and ≤300ms fan-out. 29 VUKA-style contract tests validating exact request/response shapes, lazy decay math, entity linking, batch processing, WebSocket event delivery, and the human verification gate (ADR-0002 enforcement).

**Why:** G0 contract from docs/01 §5 requires a working sightings ingest, entity resolution, and WebSocket fan-out by 12:00. The two feasibility nitpicks (OSRM deferred to G2, lazy decay instead of cron) were built around as instructed. Migrations from day one (not a single init script) sets the upgrade path to PostgreSQL+pgvector. Contract tests ensure the API matches the frozen contract — every endpoint validates shapes, not just status codes (VUKA discipline ported). The lazy-decay formula solves the "no scheduler in a single-process demo" constraint while keeping the half-life behavior correct.

**Plain language:** The backend server is running. Vision agents can now POST camera detections to /v1/sightings — the server stores them, figures out if it's seen that plate or face before (entity resolution), and immediately sends a WebSocket event to any connected operator dashboards (the ≤300ms fan-out budget). When an operator looks up an entity (GET /v1/entities/{id}), the suspicion score automatically decays over time using the "half-life of 7 days" rule — old suspicious activity matters less, computed on the fly with no background job needed. The human verification gate (flag/dismiss/whitelist) writes every decision to a hash-chained audit log so we can always answer "who verified what and when." The 29 tests prove the API works exactly as the contract specifies — if you change an endpoint and break the contract, the tests will catch it before the PR merges.

**Breaks/risks:** API keys (WeatherAPI, EskomSePush) live in `.env` (gitignored, Sbu holds them) — repo is PUBLIC. The lazy-decay math assumes datetime.utcnow() precision is sufficient (SQLite has no timezone-aware timestamps, acceptable for demo). Entity resolution is simplified for G0 (exact plate text match) — full embedding-based matching and the confusion-aware comparator (0↔O, 1↔I edit distance) land in G1 as part of the suspicion module. WebSocket reconnection is client-side only (no server-side resume) — acceptable for demo, production needs durable subscriptions. The human gate enforces ADR-0002 in code (soft evidence capped below alert), but the suspicion-scoring factors (F1–F6 from docs/01 §4) are stubbed for G0 — those compute in G1 when the sighting graph logic lands in `server/src/suspicion/`.

**Note (merge, 2026-07-24):** this is a separate, fuller `server/src/` implementation (SQLAlchemy + Alembic + 29 contract tests) built in parallel with the `server/main.py` spine documented below (G0 spine / G1 / G2 / G2.1) — both live in the repo post-merge; reconciling into one server implementation is an open item, not yet done.

---

## 2026-07-24 — G2.1: YAMNet audio corroboration (F6 modal factor + `/v1/audio-cues`)

**Tech stack:** `ai-edge-litert` (Google's LiteRT Python runtime — CLAUDE.md-equivalent D2 choice, not the unmaintained `tflite-runtime`), `sounddevice` for mic capture, `numpy`. Model: Google YAMNet (`yamnet.tflite`, 521-class pretrained audio event classifier from TF Hub) — same model Sali sourced/validated for VUKA's Tier 2 audio path, reused byte-identical here (sha256 `10c95ea3eb9a7bb4cb8bddf6feb023250381008177ac162ce169694d05c317de`). No new server dependencies — `brain/fusion.py` and `server/main.py` extended in place.

**What (technical):**
- `vision/audio_agent.py` — Tier 0 RMS-amplitude gate (`RMS_GATE = 0.01`) on raw mic input; only when ambient sound crosses that gate does Tier 2 YAMNet inference run (never continuous, same cascade pattern as `vision/agent.py`'s motion gate). `map_yamnet_class(scores, classes_of_interest)` is a pure function: takes the 521-length softmax output, filters to a small allow-list of class indices (gunshot/glass_break/scream/raised_voices), returns the highest-confidence label above `CONFIDENCE_MIN`, or `None`. Posts only `{label, confidence}` to `POST /v1/audio-cues` — raw audio is never persisted or transmitted (privacy-at-source, CLAUDE.md-equivalent D9/Principle 5).
- `vision/assets/models/yamnet.tflite` + `models.json` registry — copied from VUKA, but with a corrected `input_shape: [15600]` (VUKA's own registry had this wrong as `15360`; caught by loading the real interpreter and reading `get_input_details()` directly, not by trusting the existing value).
- `brain/fusion.py` — new `factor_f6_modal_corroboration(entity, audio_cues)`: docs/01 §4 F6. Looks only at an entity's **most recent** sighting; an audio cue counts only if it shares that sighting's `hex` and falls within `MODAL_CORROBORATION_WINDOW_MINUTES = 10` of its timestamp. Weighted per label (`gunshot=3.0, glass_break=2.5, scream=2.5, raised_voices=1.0` log-odds) — picks the strongest match. `recompute()` now takes an `audio_cues` list and folds this into the same log-odds sum as F1; still cannot reach `flagged` (ceiling unchanged, ADR-0002 still holds — audio is just another factor feeding the same capped function).
- `server/main.py` — new `AUDIO_CUES` store, `AudioCue` pydantic model, `POST /v1/audio-cues`: stores the cue, broadcasts `audio.cue` over `/ws/ops`, then **re-checks every non-decided entity** against the updated cue list (a cue can retroactively corroborate an existing sighting and push an entity over the ceiling without any new camera detection) and broadcasts `entity.candidate` for any that just crossed.
- Tests: `vision/tests/test_audio_agent.py` (4 tests — correct class wins, below-confidence returns `None`, out-of-interest classes ignored, no-hits returns `None`) + 6 new cases in `brain/tests/test_fusion.py` (gunshot alone crosses ceiling via F6 only; different-hex cue ignored; outside-time-window cue ignored; `raised_voices` alone stays under threshold; `raised_voices` + F1 together cross it; frozen/flagged entities ignore new audio cues). 24/24 total pass (`brain/tests` + `vision/tests`).

**Method (plain-language):** The phone/laptop mic listens quietly and does nothing until a loud sound happens (the "gate"). Only then does it run the actual sound classifier — this is the same "don't waste battery/compute on nothing" pattern already used for motion detection. If it hears something worth flagging (gunshot, breaking glass, a scream, raised voices), it sends just that word and a confidence score to the server — never the actual audio clip. The server then asks: "does this sound match up, in place and time, with something a camera already saw?" If yes, that's two independent senses agreeing, which is much stronger evidence than either alone — strong enough, in the gunshot case, to flag the vehicle for a human operator to look at even without a second camera sighting. A shout on its own isn't enough by itself (could be nothing), but a shout plus a camera already having seen the same vehicle twice is enough.

**Why:** user request this session — Sali already sourced/validated YAMNet for VUKA's audio-trigger path; reusing it here gives BEACON a second, physically independent sensing channel (microphone vs camera) for near-zero extra build cost, and directly fills in the previously-stubbed F6 slot in docs/01 §4's factor table. Confirmed via exhaustive repo search that no vision/weapon fine-tune exists yet in VUKA (Sali is building that next) — this slice is audio only.

**Integration:** Additive to the G2 Sighting Graph — no contract break. `audio.cue` and the re-broadcast `entity.candidate` are new WS events, both already implied by docs/01 §5's event naming. Sits on the same `brain/fusion.py`/`server/main.py` files as the G2 slice, so landing as an additional commit on `lethabo/brain-sighting-graph-g2` (PR #7) rather than a new branch.

**Verified live:** Ran the real server (`uvicorn server.main:app`), opened a `/ws/ops` socket, POSTed a single plate sighting (stays `observed` — below F1 threshold alone), then POSTed a `gunshot` audio cue in the same hex within the time window. Confirmed live: `audio.cue` broadcast, entity crossed to `watch_candidate` on F6 alone (`factors: ["F6:gunshot"]`, score 0.953), `entity.candidate` broadcast, and `GET /v1/entities/{id}` reflects the corroborated state.

**Not yet real (honesty ledger, docs/01 §7):** F2-F5 still stubbed. Weapon/vision classification does not exist anywhere in the pipeline (do not demo or claim it). Audio capture in `audio_agent.py` is a laptop-mic reference implementation for demo purposes, not yet wired into a phone/edge node.

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
