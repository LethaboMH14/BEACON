# ILISO — Build Log (newest first)

Every behaviour change gets an entry in the same commit. Plain-language section mandatory — anyone on the team must be able to read it.

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
