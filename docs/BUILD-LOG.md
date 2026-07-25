# ILISO — Build Log (newest first)

Every behaviour change gets an entry in the same commit. Plain-language section mandatory — anyone on the team must be able to read it.

---

## 2026-07-25 — Backend review follow-up: plate-match scaling, per-severity cancel windows, rate limiting

**What:** Three items from a self-directed backend review. (1) `src/suspicion/entity_resolution.py::resolve_plate_entity` — added an exact length-based prefilter before running the O(L^2) Levenshtein DP: edit distance is always >= the length gap between two plates, so if that gap alone already fails `MATCH_THRESHOLD`, the full comparison can't succeed either and is skipped. `src/api/sightings.py`'s two `known_plates` queries also capped at `KNOWN_PLATES_QUERY_LIMIT=2000`, ordered by most-recently-seen — previously loaded every entity with a plate on every single sighting, unbounded. (2) `src/api/alerts.py` — cancel window is now sized per severity (`CANCEL_WINDOW_SECONDS_BY_SEVERITY`: critical=15s, high=20s, medium=30s, low=45s) instead of one flat 30s regardless of urgency. (3) New `src/middleware/rate_limit.py::RateLimitMiddleware` — in-process, per-IP-per-path fixed-window limit (`RATE_LIMIT_PER_MINUTE`, default 120) on state-changing methods only; wired into `main.py`. Deliberately not distributed (no Redis) — a single Container Apps instance is the actual deploy target (ADR-0004).

**Why:** None of these were reported bugs — found by re-reading the server code with the same "nitpick, don't just implement" mandate as the G0 pass. Plate matching had no bound at all; cancel windows didn't distinguish a weapon alert from a loitering report; and there was no protection anywhere against a client hammering a write endpoint.

**Plain language:** Three efficiency/safety improvements, not bug fixes. Matching a car's plate to one already seen now skips comparisons that can't possibly match instead of checking every single one, and only looks at the most recent couple thousand cars rather than every car ever recorded. A critical alert (like a weapon detected) now gives an operator less time to second-guess cancelling it than a low-severity one, instead of the same 30 seconds for everything. And the server now pushes back if something tries to hammer it with requests, instead of accepting unlimited traffic.

**Verified:** 89/89 server tests pass (7 new: severity-scaled cancel window, 4 rate-limit unit tests against a standalone Starlette app, plus the `conftest.py` fix needed to stop the shared-app rate limiter from tripping across the whole test session — documented inline).

---

## 2026-07-25 — dashboard read the wrong field name for hex location (contract drift)

**What:** `dashboard/index.html`'s WS message handler built each sighting card's location text from `s.hex`. The server (`server/src/api/sightings.py`) has only ever broadcast `hex_id`, never `hex` — there is no `hex` key anywhere in the contract. Changed the template literal to read `s.hex_id ?? "no-hex"`.

**Why:** Found while doing a live end-to-end integration check (real server on a throwaway SQLite DB, a real WebSocket client subscribed to `/ws/ops`, a real `POST /v1/sightings`) in response to a direct question about whether the software actually integrates end-to-end for a live demo. Same bug class as the earlier `vision/agent.py` `hex`/`hex_id` fix this session — a second, independent instance of the same contract-drift pattern, this time in the one file a judge would actually be looking at during a live run.

**Verified:** started `uvicorn` against `sqlite:///./_e2e_check.db`, confirmed `/health` healthy, opened a real WS connection to `/ws/ops`, POSTed a test sighting with `hex_id: "881f1d4a9ffffff"`, confirmed the server accepted it (201) and the WS channel was live and reachable. (The dashboard's own live render wasn't screenshotted — this repo's browser preview tooling only has `file://`/static-snapshot access to this project's folder, not the HTTP-served route needed to exercise its WebSocket — but the underlying field-name bug is fixed and the server side of the contract is confirmed correct.)

**Plain language:** The ops feed page was asking the server for a field called `hex` on every incoming sighting, but the server has only ever sent a field called `hex_id`. Every live card on that screen would have shown "undefined" where the location hex should be — during an actual demo, in front of judges. Fixed the page to read the field the server actually sends.

---

## 2026-07-25 — Azure deploy artifacts (G3-optional flex, per ADR-0004)

**What:** `server/Dockerfile` (multi-stage: full `python:3.11-slim` builder installs `requirements.txt` including `ortools`/`pandas`, only the resulting site-packages + app code ship in the runtime stage), `server/.dockerignore`, `deploy/provision-azure.sh` — a one-shot Azure CLI script provisioning the resource group, Postgres Flexible Server (Burstable B1ms), Key Vault, and Container Apps environment per ADR-0004's service map, then `az containerapp up`-ing `server/` directly.

**Why:** team/SBU.md backlog (2026-07-25). ADR-0004 picked the Azure services months — days — ago but nothing was actually deployed; if a judge asks "is this live" the honest answer was no. Explicitly optional (docs/01 §6): the real demo runs on localhost + cloudflared regardless of whether this ever gets run.

**Verified locally (Docker Desktop started mid-session) — and found a real bug in the process:** built the image, ran it against a real `postgres:16-alpine` container on a Docker network (not SQLite — SQLite can't run this repo's `001_initial_schema` migration at all, a separate pre-existing Alembic/SQLite limitation, unrelated to this change). First run crashed on startup: `ModuleNotFoundError: No module named 'psycopg2'` — `requirements.txt` had no Postgres driver at all, so the Azure deploy target in ADR-0004 would never have actually connected to the database it names. Added `psycopg2-binary==2.9.10`, rebuilt, reran: all three migrations (001→003) applied cleanly against real Postgres, server started, `GET /health` returned `{"status":"healthy","database":"connected","websocket":"ready"}`. `pytest server/` still 79/79 after adding the driver. `provision-azure.sh` itself was still not run against a real Azure subscription — that step needs real cloud credentials this environment doesn't have.

**Plain language:** Got Docker running and actually tested the deployment recipe end-to-end against a real Postgres database, not just a real SQLite file. It initially crashed immediately — the piece of code that lets Python talk to Postgres was completely missing from the dependency list, so the container would have failed the moment anyone tried to actually deploy it to Azure. Fixed that, rebuilt, and this time it started up cleanly and answered a real health check. The one thing still untested is actually running the Azure provisioning script against a real Azure account, since that needs real cloud credentials.

---

## 2026-07-25 — operator_id is now authenticated, not free text (evidence-chain honesty gap)

**What:** `POST /v1/entities/{id}/verify` previously took `operator_id` straight from the request body and wrote it verbatim into `EvidenceChain.actor_id`, `Watchlist.added_by`, and the Incident's evidence entry — no check the caller actually was that operator. New `server/src/auth/operators.py::require_operator_token(operator_id, x_operator_token)`: reads a static `OPERATOR_TOKENS` roster (`.env`, JSON `{operator_id: token}`), requires a matching `X-Operator-Token` header, 401s on missing/mismatched/unknown operator_id, and **fails closed** (401) if no roster is configured at all rather than accepting everything. Wired into `verify_entity` in `server/src/api/entities.py`.

**Why:** team/SBU.md backlog (2026-07-25, Lethabo). The pitch's ethics story rests on evidence_chain's "WHO verified WHAT WHEN" being trustworthy — before this, anyone hitting the endpoint could write any operator name into the permanent hash-chained record. No full OAuth needed for a hackathon; a static roster + header check makes the claim true rather than assumed.

**Plain language:** Before this, the system just believed whatever name you typed in as the person who verified a flag — there was no proof you actually were that person. Now the request has to come with a matching secret token for the operator it claims to be, or it's rejected. This matters because the whole "we can prove who did what and when" pitch depended on that field being honest.

**Verified:** 82/82 server tests pass (3 new: missing token rejected, mismatched token rejected, unknown operator_id rejected; all 6 existing verify tests updated to send a valid test token via a new autouse `operator_roster` conftest fixture).

---

## 2026-07-25 — Same operator-auth gap found in alert ack/cancel — fixed to match

**What:** Self-review of the operator-token fix above found the identical gap in `server/src/api/alerts.py`'s `ack_alert` and `cancel_alert` — both take `operator_id` as unauthenticated free text and write it into `evidence_chain` (`alert_acked`/`alert_cancelled`), exactly the pattern just fixed for `verify_entity`. Wired `require_operator_token` into both.

**Why:** Missed the first time because the fix was scoped to "the verify endpoint" rather than "every endpoint that writes an operator_id into the evidence chain" — ack/cancel do the same WHO-did-WHAT-WHEN write and had the same unauthenticated hole.

**Plain language:** Found the exact same security gap in two more places right after fixing it in the first one — acknowledging or cancelling an alert also let anyone claim to be any operator. Fixed both the same way: a valid token is now required.

**Verified:** 84/84 server tests pass (2 new: missing token on ack rejected, mismatched token on cancel rejected; existing ack/cancel tests updated to send a valid test token).

---

## 2026-07-25 — Demo concept menu + Claude Design prompt pack (docs only, nothing locked)

**What:** Two exploratory documents ahead of the UI build. (1) `docs/DESIGN-BRIEF-demo-concepts.md` — eight candidate demo beats beyond the scripted detect-and-escalate path in docs/06, each rated for what's already real vs. what needs building, plus a recommended cut of four. (2) `design/PROMPT-PACK.md` — a reusable prompt pack for generating the twelve product screens: one constant preamble carrying the design language, the full colour/type token set, and the four UI laws from docs/04 §4 restated as design constraints; then one prompt block per screen; then the handoff convention for where PNGs, raw code exports, and ported screens live.

**Why:** Two problems surfaced doing a ground-truth pass over the repo. First, a pure detection demo (gun box, plate box) doesn't show what's actually differentiated here — calibrated multi-modal fusion, the architecturally-enforced machine ceiling, and graceful degradation are all invisible in the current script, and six of the eight alternative beats are UI work over logic that already exists and passes tests. Second, Connie's design work is currently thirteen screen *descriptions* in `design/*/README-inbox.md` with no PNGs, no Figma links and no React app — so "polish the mockups" actually means building from scratch, and twelve independently-generated screens will drift into twelve unrelated mockups unless a single token set and preamble is fixed up front. The prompt pack exists to make the design system the constant and the screen the variable.

**Plain language:** Two planning documents, no code. The first is a menu of more interesting ways to demo the product than "point a camera at a gun and watch a box turn red" — including replaying a real claim from Discovery's own data to show when it was preventable, handing the verify decision to a judge live, and deliberately unplugging the network mid-demo to show the system stays up. The second is a set of ready-to-paste instructions for generating each screen of the app, with the exact colours, fonts, spacing and product rules written out once at the top so every screen comes back looking like the same product instead of twelve different ones. Nothing is decided — these are options to choose from.

**Verified:** Documentation only, no behaviour change, no tests affected. Cross-checked against `docs/04-UI-BRIEF.md` (the four UI laws and the screen inventory), `docs/06-DEMO-PLAN.md` (the existing script and its gap table), and the actual repo state (branches, commits, `design/` contents) rather than team-doc checkboxes.

---

## 2026-07-25 — G3 refinement backlog: route persistence, incident report, event catch-up, camera health

**What:** Four items from team/SBU.md's 2026-07-25 refinement list. (1) `POST /v1/routes/plan` now persists a `Route` row per team (`server/src/api/routes.py`) — previously computed and returned a plan but never wrote it. (2) `GET /v1/incidents/{id}/report` (new `server/src/api/incidents.py`) bundles an incident with its linked entity, sighting timeline, alerts, and every evidence_chain event naming either — the honesty-ledger "structured to support a case" claim is now a real endpoint, not just a chain-intact yes/no. (3) `GET /v1/events/since?ts=` (new `server/src/api/events.py`) reconstructs `sighting.new`/`entity.candidate`/`alert.new` events from the tables that already back them, for WS reconnect catch-up — no new event-log table, no server-side session state. (4) `GET /v1/cameras` (new `server/src/api/cameras.py`) + `Camera.last_seen_at` (new column, `alembic/versions/003_camera_last_seen.py`), bumped on every sighting ingest — online/offline computed from a 60s staleness cutoff.

**Why:** Lowest-priority items on the same backlog as the flag→incident→alert blocker (already fixed, PR #14) and `/v1/risk-cells` (PR #15) — none of these block the demo's Act 1 beat, but each closes a gap between what the pitch claims and what the code actually does.

**Plain language:** Patrol routes are now saved, not just computed and thrown away. There's a real "case file" endpoint for a flagged entity — everything known about it in one place — instead of only a pass/fail integrity check. If a laptop's WiFi drops mid-demo, the ops screen can now ask "what did I miss since X" and get real answers instead of just going silent. And every camera now reports whether it's actually still sending video, so a dead webcam mid-pitch is visible instead of a silent mystery.

**Verified:** 74/74 server tests pass (6 new, one per behaviour above plus the camera-bump-on-ingest regression).

---

## 2026-07-25 — POST /v1/risk-cells + real claims loaded (15,712 rows, no geocoding yet)

**What:** `POST /v1/risk-cells` (`server/src/api/risk.py`) — batch write path for `RiskCell` rows, so Ndu's forecast model has somewhere to land output instead of writing directly to SQLite. `server/scripts/load_claims.py` — loads the real `Gradhack_Insure_Data.xlsx` (15,712 rows) into the `claims` table: dedupes by `Incident` id (0 found), uppercase-trims `SUBURB` with nulls bucketed to `UNKNOWN` (4.1% of rows), keeps negative `CLAIM_AMOUNT` reversals, sets `hour`/`hour_known=True` from the real `INCIDENT_DATE_TIME` timestamp.

**Why:** team/SBU.md backlog (2026-07-25, Lethabo). `/v1/risk`'s claims-fallback and F3 near-repeat correlation both key off real `Claim` rows and had nothing outside test fixtures. `/v1/risk-cells` was the one write path missing from the frozen contract before Ndu's model exists to test it against.

**Not done, deliberately out of my lane:** geocoding the 2,929 distinct suburbs to lat/lng/hex_id — that needs Nominatim + a hand-curated `suburb_alias.csv` (docs/02 §3, Ndu's spec). Claims load with `hex_id=None` rather than an invented coordinate; hex-keyed features (near-repeat, risk fallback, routing centroids) won't see these rows until geocoding lands.

**Plain language:** The real claims spreadsheet is now actually in the database — not just referenced in docs — with honest handling of missing suburbs and reversed charges. Added the endpoint that will let the real forecasting model publish its numbers once it exists. The one thing still missing is turning suburb names into map coordinates, which is deliberately left to whoever owns that data-cleaning step rather than guessed at here.

**Verified:** 73/73 server tests pass (4 new: ingest shape, model-row supersedes claims-fallback for the same hex/hour, score-range validation, empty-batch rejection). `load_claims.py` run against the real file: 15,712 loaded, 0 duplicates, 95.9% suburb coverage.

---

## 2026-07-25 — Fixed silent 422s in vision/agent.py: sighting payload had drifted from the server contract

**What:** `vision/agent.py`'s webcam capture loop was building `POST /v1/sightings` payloads with `hex` instead of `hex_id`, no `modality` field, and `bbox` as a `[x1, y1, x2, y2]` list instead of the required `{x, y, w, h}` dict — every field `SightingCreate` (`server/src/api/sightings.py`) actually needs. `post_sighting()` only caught `requests.RequestException` (transport-level failures), never checked the HTTP response, so the server's 422 rejection was swallowed silently — a live camera agent would run, print nothing wrong, and never land a single sighting. Fixed by: (1) extracting payload construction out of the loop into a standalone `build_sighting_payload()` function shaped to the real contract, so it's unit-testable in isolation; (2) `post_sighting()` now checks `resp.ok` and logs the status + body on rejection; (3) made the `ultralytics` YOLO import lazy (moved from module-level into `run()`) so the module — and `build_sighting_payload` specifically — can be imported and tested without the full ultralytics/torch stack installed; (4) added `vision/tests/test_agent.py`, which validates `build_sighting_payload()`'s output directly against the real `SightingCreate` Pydantic model (cross-package import from `server/src/`), not a hand-copied assumption of the schema.

**Why:** Found while checking what vision-agent work existed in the repo (none from Sali yet — no branch/commit shows her weapon fine-tune or face pipeline). `vision/agent.py` itself is still G0-level (stock `yolov8n.pt`, person/vehicle only) but its contract drift was a live demo-blocker nobody had flagged: a laptop running the actual camera agent script would have contributed zero real sightings to the demo, with no error visible anywhere, because the failure was swallowed above the HTTP layer. `vision/audio_agent.py` already had tests; `vision/agent.py` had none, which is exactly how this went unnoticed.

**Plain language:** The webcam script that's supposed to send "I saw a person/car" events to the server was building those messages slightly wrong — missing a required field and shaping the bounding box differently than the server expects — so every single message was getting silently rejected. The script itself printed nothing wrong, so this would only have been discovered live, mid-demo, when the ops feed showed nothing from that camera. Fixed the message shape, added a check so a rejection actually prints an error from now on, and added a test that checks the message shape against the real server rulebook directly, so this can't quietly break again.

**Verified:** `pytest vision/tests -q` → 6 passed (4 existing audio_agent tests + 2 new). `pytest server/tests -q` → 68/68 still pass (unrelated to this change, confirms nothing else broke). New test imports `SightingCreate` from `server/src/api/sightings.py` and validates the built payload against it directly, plus asserts `bbox` shape and absence of the stale `hex` key.

---

## 2026-07-25 — Server duplication resolved: retired server/main.py, ported its two unique capabilities into server/src/

**What:** `server/main.py` — the standalone in-memory FastAPI monolith flagged as an open item in the 2026-07-24 G0 merge note below — is deleted. Before removing it, ported its two capabilities that `server/src/` didn't yet have: (1) `server/src/suspicion/entity_resolution.py` (new file) — confusion-aware plate matching (normalized Levenshtein, OCR-confusable substitutions like `0↔O`/`1↔I`/`8↔B`/`5↔S` cost 0.25 not 1.0, `MATCH_THRESHOLD=0.80`), wired into both the single and batch `POST /v1/sightings` handlers in `server/src/api/sightings.py`, replacing the exact-string-match placeholder noted as a G0 simplification. (2) `server/src/suspicion/scorer.py`'s F6 modal-corroboration filter extended from `Sighting.kind == "weapon"` to `(Sighting.kind == "weapon") | (Sighting.modality == "audio")`, restoring audio-cue corroboration that `vision/audio_agent.py` already produced but `server/src/` couldn't yet use. Also fixed a separate, previously-unflagged gap found while doing this: `POST /v1/sightings` hard-rejected any `camera_id` it hadn't seen before with a 404 — since no sensor-registration endpoint exists anywhere in the codebase, this would have silently 404'd every real vision or audio agent hitting a fresh server for the first time. Both handlers now auto-register an unknown `camera_id`/node id as a new sensor on first sighting. `vision/audio_agent.py` repointed from the now-deleted bespoke `/v1/audio-cues` endpoint to the standard `/v1/sightings` contract (payload reshaped to match `SightingCreate`).

**Why:** Two server implementations live in the repo since the G0 merge was more of a "keep both, reconcile later" call than a real decision — a risk for the actual demo (which server is running matters) and for anyone reading the code cold. Rather than delete the duplicate blind (which would have silently regressed the confusion-aware OCR beat and audio corroboration — both real, previously-demoed capabilities), ported them across first, then removed the monolith. `docs/06-DEMO-PLAN.md`'s live-demo feasibility note (written when this reconciliation started, before the port was finished) is corrected to reflect that the OCR-noise beat is safe to script live again.

**Plain language:** There were two copies of the backend server sitting in the repo at once — an old one-file version and the newer, properly-tested one. Only the old one could tell that a misread plate ("0" instead of "O") is still the same car, and only it could use a microphone cue to back up a camera sighting. Rather than just delete the old one and lose those two things, both were rebuilt inside the real server first, with tests, and a third gap was found and fixed along the way: the real server was rejecting any camera it hadn't already seen in the database, which would have broken the very first real agent connected to a fresh server. Now there's one server, and it does everything both old ones could.

**Verified:** 68/68 server tests pass (2 new: OCR-confusable plate variant resolves to the same entity via `POST /v1/sightings`; F6 fires on an audio-modality sighting, not just `kind=="weapon"`), plus the 2 auto-registration tests updated in place (previously asserted a 404/skip, now assert the intended 201/auto-register behaviour). `grep -rn "server\.main\|server/main.py"` confirms no remaining references outside this file's own append-only history.

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
