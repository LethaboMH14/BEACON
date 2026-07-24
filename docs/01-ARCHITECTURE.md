# BEACON — 01 System Architecture

> Owner: Lethabo (with Sbu on §5 contract). Status: v1.0, 2026-07-24.

## 1. One-picture overview

```
CAMERAS (ring doorbells / webcams / RTSP)          CONTEXT FEEDS
   │  vision/agent.py per camera                    weather · load-reduction · events/marches
   │  YOLOv8 person/weapon/plate · ArcFace faces    paydays/holidays · SAPS stats (roadmap)
   │  EasyOCR plates · sim_audio (YAMNet port)              │
   ▼                                                        ▼
 ┌──────────────────────── server/ (FastAPI + WS) ────────────────────────┐
 │  /v1/sightings  →  SIGHTING GRAPH  →  brain/ suspicion (log-odds,     │
 │                     entity resolution     conflict gate, HUMAN GATE)   │
 │  /v1/claims     →  data/ pipeline   →  RISK FORECAST (hex × hour)      │
 │  /v1/routes     →  OR-Tools Koper-dosed patrol optimizer               │
 │  /v1/incidents, /v1/alerts, WS fan-out (≤2.0s to render)               │
 └────────────┬───────────────────┬────────────────────┬──────────────────┘
              ▼                   ▼                    ▼
      OPS CONSOLE (security)  EXEC VIEW (Discovery)  MEMBER VIEW (guardian)
      live map · alerts ·     portfolio analytics ·  arm camera · alerts ·
      verify queue · routes   claims saved · trends  safety score · Guardian
```

Two honest tracks, from the claims data itself:
- **Property track (93.6%)** — forecast → deter (Koper presence) → detect → recover/investigate. Minutes matter, not seconds.
- **Life-safety track (6.1%)** — person present, force used: hard triggers (panic, Guardian confirm, gunshot audio) bypass soft fusion straight to action with a cancel window. Ported VUKA principle.

## 2. Components

### 2.1 vision/ — camera agent (Sali + Lethabo)
One Python process per camera. Pipeline per frame batch:
1. **Tier 0 gate:** frame-difference motion score — skip everything if the scene is still (same cascade philosophy as VUKA: nothing expensive runs continuously).
2. **Tier 1:** YOLOv8n — person, vehicle, weapon-candidate (gun/knife classes fine-tuned by Sali). ≥8 FPS on demo laptop.
3. **Tier 2 (on Tier-1 hit):** face crop → ArcFace 512-d embedding; plate crop → EasyOCR text + plate image embedding; vehicle make/colour tags.
4. Emit `sighting` over WS: `{camera_id, ts, hex, kind: person|vehicle|weapon, embedding_ref, plate_text?, plate_quality?, bbox, confidence, clip_ref?}`.
5. **Privacy at source:** raw frames never leave the agent except an encrypted short clip on escalation. Embeddings only. Weapon detections are ONE fused input — never a standalone auto-alert (naive gun detectors false-positive on phones/tools; ZeroEyes ships human verification for exactly this reason).

### 2.2 server/ — backbone (Sbu)
FastAPI + WS, mirroring the VUKA relay. SQLite day-0, Postgres+pgvector+H3 at G2.
Tables: `cameras, sightings, entities, whitelist, watchlist, claims, risk_cells, incidents, alerts, routes, evidence_chain` (hash-chained, ported).

### 2.3 brain/ — suspicion + fusion (Lethabo, port of VUKA brain)
See §4. Calibrated log-odds, conflict gate, hysteresis, human gate (ADR-0002).

### 2.4 data/ — forecasting (Ndu) — full spec in docs/02
Claims ingest → geocode → H3 → enrich (weather, load-reduction, events/marches, paydays) → forecast per hex × hour → feeds map + routing + suspicion context factor.

### 2.5 dashboard/ — three views, one app (Connie) — full spec in docs/04
Primary user is the **security company ops room** (they act on alerts and drive routes — the theme's "community assistance" buyer). Discovery exec view and member/guardian view are role-switched views of the same app.

## 3. Entity resolution (who is "the same" car/person)

- **Plates:** normalized text match with a confusion-aware comparator — edit distance where 0↔O, 1↔I, 8↔B, 5↔S substitutions cost 0.25. Match quality ∈ [0,1] travels with every match (Flock's 0-vs-O false stops are the cautionary tale — we never silently exact-match).
- **Vehicles without readable plates:** make/model/colour tags + image embedding cosine; only ever a *weak* factor.
- **Faces:** ArcFace cosine. ≥0.55 = candidate link, ≥0.65 = suggest to human (targets; Sali calibrates on a validation set). Below candidate = discarded.
- An **entity** is an embedding cluster with a random ID. BEACON never asserts a legal identity — a match is a lead (D9, ADR-0002).

## 4. The Sighting Graph — suspicion engine (our unique IP)

The intuition (Lethabo's rule): *"a plate or face that appears 3+ times on cameras it has no business near, at the times crimes happen there, then shows up somewhere else at weird times — that's territory-scanning behaviour."* Formalized as calibrated log-odds factors over the graph, all tuned so no single factor can dominate:

| # | Factor | Trigger | Weight source |
|---|---|---|---|
| F1 | **Recurrence** | ≥3 sightings, ≥2 distinct cameras, within 14 days, entity NOT on street whitelist | The core rule. Whitelist-first kills neighbour/domestic-worker/delivery false positives |
| F2 | **Time anomaly** | Sightings concentrated in that hex's claim-peak hours (e.g. the 00:00 spike) or resident-absent windows | From claims histogram per hex |
| F3 | **Crime correlation** | Sighting within the near-repeat kernel (≈400 m, ≈14 days) of an actual claim/incident | Johnson & Bowers near-repeat literature |
| F4 | **Casing behaviour** | Dwell/slow-pass: track duration ≫ typical pass-through for that camera; repeated circling within an hour | Per-camera baseline learned from history |
| F5 | **Territory roaming** | Same entity across ≥2 non-adjacent high-risk hexes in one week | "Scanning the territory" |
| F6 | **Modal corroboration** | Weapon detection, glass-break/gunshot audio, or member panic co-located in time+hex | Independent-channel fusion (VUKA Principle 6) |

**Escalation ladder (enforced in code, ADR-0002):**
```
observed → watch candidate (machine ceiling) → [HUMAN VERIFY] → flagged
                                                        │
                                     pre-arm digital cordon + notify patrol
```
Conflict gate: disagreeing evidence (e.g. F1 high but entity matches whitelist pattern, or face and plate point to different entities) routes to verification, capped — never escalated. Scores decay (half-life ≈ 7 days). Everything shown is calibrated.

**Trajectory prediction (digital cordon).** Cameras form a directed graph with edges weighted by road-network travel (OSRM) and learned transition counts. On a Flagged entity sighting with direction-of-travel, a Markov next-hop gives P(next camera) — the dashboard shows a **prediction cone**, pre-arms those cameras (higher sampling, priority processing), and suggests a patrol interception hex. Demo-real on simulated sighting streams (`sim_` labelled); live version is roadmap.

## 5. API + WS contract (Sbu owns; freeze at G1; changes need ADR + sign-off)

```
POST /v1/sightings            ← vision agents (batch ok)
GET  /v1/entities/{id}        → sightings timeline, factors, score (calibrated), state
POST /v1/entities/{id}/verify → human gate: {action: flag|dismiss|whitelist, operator_id, note}
GET  /v1/risk?hex=&hour=      → forecast score + top factors (explainable)
GET  /v1/hotspots?window=     → ranked hexes for map
POST /v1/routes/plan          → {teams, shift_window, fuel_budget} → Koper-dosed stops
GET  /v1/claims/summary       → exec analytics
POST /v1/alerts/{id}/ack|cancel
WS   /ws/ops        events: sighting.new, entity.candidate, entity.flagged, alert.new,
                     route.updated, forecast.updated      (≤300 ms server fan-out)
WS   /ws/member     events: alert.new (own cameras only), guardian.request
```

## 6. Latency + degradation budgets

Detection→render ≤2.0 s p95 (`scripts/latency.py`). Camera agent queues offline and replays. Server serves cached risk if `data/` is down. Dashboard marks stale, never blank. Demo runs fully on localhost + one tunnel — no cloud dependency to fail mid-pitch (Azure deploy is a G3-optional flex, ADR-0015 lineage).

## 7. Explicit sim boundary for the pitch

Demo-real: live webcam detection (person/weapon/plate/face), claims analytics, forecast model on real claims, route optimization, alert fan-out, human-verify flow.
Simulated (`sim_` + said out loud): multi-camera sighting streams for the graph replay, trajectory cone, acoustic events (unless YAMNet port lands), Discovery API integration.
