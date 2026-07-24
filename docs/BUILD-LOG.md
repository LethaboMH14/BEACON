# ILISO — Build Log (newest first)

Every behaviour change gets an entry in the same commit. Plain-language section mandatory — anyone on the team must be able to read it.

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
