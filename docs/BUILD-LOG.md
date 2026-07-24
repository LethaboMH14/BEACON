# ILISO — Build Log (newest first)

Every behaviour change gets an entry in the same commit. Plain-language section mandatory — anyone on the team must be able to read it.

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
