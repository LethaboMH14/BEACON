# BEACON — 07 Tech Stack

> Owner: Team (locked by ADR-0001, extended by G0/G1/G2 implementation).  
> Status: v1.1, 2026-07-24 (Sbu: G2 risk/hotspots/routing — see Version History).

This document tracks every technology choice, the rationale, and where it lives in the repo. It exists so any team member or reviewer can understand why we're using what we're using without digging through ADRs and commit history.

---

## Core Platform

| Component | Technology | Why | Where | Locked By |
|-----------|------------|-----|-------|-----------|
| **Language (backend)** | Python 3.11+ | Team fluency from VUKA; rich ML ecosystem for vision/suspicion; FastAPI async support; ruff/black/type-hints/pytest tooling already familiar | `server/`, `vision/`, `brain/`, `data/` | ADR-0001 |
| **Language (frontend)** | TypeScript (strict) | Type safety for complex dashboard state; VS Code integration; team experience from VUKA ops console | `dashboard/` | ADR-0001 |
| **Backend framework** | FastAPI | Async-first; automatic OpenAPI docs; Pydantic validation; WebSocket support built-in; matches VUKA relay pattern | `server/src/main.py` | ADR-0001 (D3) |
| **Web server** | Uvicorn (with uvloop on Unix) | ASGI reference implementation; hot reload for dev; standard for FastAPI | `server/requirements.txt` | G0 impl |
| **Database (G0–G1)** | SQLite | Zero-config; single-file; sufficient for demo; easy to reset; upgrade path to PostgreSQL | `server/src/db/database.py` | ADR-0001 (D3) |
| **Database (G2+)** | PostgreSQL + pgvector + H3 | Production-grade; vector similarity for face/plate matching; H3 hex indexing for geo queries | Planned G2 migration | ADR-0001 (D3) |
| **ORM** | SQLAlchemy 2.0 | Type-annotated ORM; async support; migration tooling via Alembic; team standard | `server/src/db/models.py` | G0 impl |
| **Migrations** | Alembic | Industry standard for SQLAlchemy; version-controlled schema changes; enables upgrade to PostgreSQL | `server/alembic/` | G0 impl |
| **Validation** | Pydantic v2 | FastAPI native; runtime validation; generates OpenAPI schemas; used for all request/response models | `server/src/api/*.py` | G0 impl |

---

## Vision / ML Layer

| Component | Technology | Why | Where | Locked By |
|-----------|------------|-----|-------|-----------|
| **Object detection** | Ultralytics YOLOv8 (n/s variants) | Pretrained on COCO; fine-tunable; ≥8 FPS on laptop GPU; person/vehicle/weapon classes | `vision/agent.py`, `vision/detectors/yolo_weapons.py` | ADR-0001 (D2) |
| **Face recognition** | InsightFace ArcFace (512-d embeddings) | State-of-art face embeddings; open-source; matches VUKA pipeline | `vision/detectors/faces.py` | ADR-0001 (D2) |
| **License plate OCR** | EasyOCR or PaddleOCR | Robust plate extraction; handles SA plate formats; open-source | `vision/detectors/plates.py` | ADR-0001 (D2) |
| **Audio detection** | YAMNet (ported from VUKA) | Pretrained on AudioSet; detects gunshots, glass-break, screams | `vision/detectors/sim_audio.py` (sim for G0) | ADR-0001 (D2) |
| **Model registry** | `vision/models/models.json` | SHA256 checksums; size tracking; reproducible deployments | `vision/models/` | CLAUDE.md §5 |

---

## Frontend / Dashboard

| Component | Technology | Why | Where | Locked By |
|-----------|------------|-----|-------|-----------|
| **Framework** | React 18 + Vite | Fast HMR; modern build tooling; team experience | `dashboard/` | ADR-0001 (D4) |
| **Styling** | Tailwind CSS | Rapid prototyping; Discovery light theme alignment; utility-first | `dashboard/` | ADR-0001 (D4) |
| **Maps** | MapLibre GL JS | Open-source; no API key; vector tiles; works offline | `dashboard/` | ADR-0001 (D4) |
| **Geospatial viz** | deck.gl | Hex layer for risk cells; trajectory overlays; integrates with MapLibre | `dashboard/` | ADR-0001 (D4) |
| **State management** | React Query + Zustand | Server state caching; lightweight client state; matches VUKA pattern | `dashboard/` | G1 impl |

---

## Data / Forecasting

| Component | Technology | Why | Where | Locked By |
|-----------|------------|-----|-------|-----------|
| **Geocoding** | Nominatim (cached) | Free; no API key; suburb→lat/lng for claims data | `data/geocode/` | ADR-0001 (D5) |
| **Hex indexing** | H3 (res 8/9) | Hierarchical spatial index; hex cells for risk forecasting; industry standard for location intelligence | `data/enrich/` | ADR-0001 (D5) |
| **Forecasting model** | Gradient-boosted trees (LightGBM/XGBoost) | Handles mixed feature types; interpretable feature importance; seasonal baseline + near-repeat kernel | `data/forecast/` | ADR-0001 (D7) |
| **Route optimization** | Google OR-Tools 9.12.4544 (`RoutingIndexManager`/`RoutingModel`, team-orienteering via `AddDisjunction`) | Koper-dosed patrol stops (12min dwell) as *optional* visits with a risk-proportional skip penalty, not a hard TSP — lets the solver drop low-value hexes when fuel/time is tight instead of failing; open-source, no paid routing API | `server/src/routing/planner.py`, `server/src/api/routes.py` (G2, built) | ADR-0001 (D8) |
| **Interim risk model (G2)** | Real-claims fallback (3-tier: `RiskCell` model row → live `Claim` count/peak-hour heuristic → explicit "no_data") | Ndu's GBT forecaster (below) isn't trained yet — this fallback is honestly labelled and uses only real claims data (no invented calibration), so `/v1/risk` and `/v1/hotspots` return truthful numbers today and swap to the real model later without an API change | `server/src/risk/forecast.py`, `server/src/api/risk.py` (G2, built) | D10 (honesty ledger) |

---

## Infrastructure / DevOps

| Component | Technology | Why | Where | Locked By |
|-----------|------------|-----|-------|-----------|
| **Repo** | GitHub (public) | Team collaboration; PR workflow; Actions CI; CODEOWNERS for auto-review assignment | `github.com/LethaboMH14/BEACON` | ADR-0001 (D12) |
| **CI** | GitHub Actions | Automated tests on PR; lint/format checks; build verification | `.github/workflows/ci.yml` | CONTRIBUTING.md |
| **Environment config** | `.env` (gitignored) | Secrets never in repo; API keys distributed by Sbu directly | `server/.env.example` | ADR-0001 (D12) |
| **Dependency management** | pip + `requirements.txt` (pinned versions) | Simple; reproducible; exact versions per CLAUDE.md §5. Pins bumped for Python 3.13 compatibility (original versions predated 3.13 wheel support and failed to resolve): `fastapi==0.115.6`, `uvicorn[standard]==0.32.1`, `websockets==12.0`, `sqlalchemy==2.0.36`, `pytest==8.0.0`/`pytest-asyncio==0.23.6`, `ortools==9.12.4544` | `server/requirements.txt` | G0 impl |
| **Python formatting** | ruff + black | Fast linting; consistent style; team standard | Implicit (run locally) | CLAUDE.md §5 |

---

## Testing

| Component | Technology | Why | Where | Locked By |
|-----------|------------|-----|-------|-----------|
| **Test framework** | pytest | Industry standard; fixtures; parametrization; async support | `server/tests/` | G0 impl |
| **Async test support** | pytest-asyncio | Required for WebSocket and async endpoint testing | `server/requirements.txt` | G0 impl |
| **HTTP client for tests** | httpx / FastAPI TestClient | In-memory app testing; WebSocket support; no network dependency | `server/tests/conftest.py` | G0 impl |
| **Test DB pooling** | SQLAlchemy `StaticPool` on `sqlite:///:memory:` | Without it, each new connection to an in-memory SQLite DB gets its own empty database — the TestClient's app-thread connection never saw the fixtures' tables. `StaticPool` shares one connection across the whole test | `server/tests/conftest.py` | G1 fix |
| **Contract test style** | VUKA pattern | Validate exact request/response shapes, not just status codes; enforces frozen API contract | `server/tests/test_*_contract.py` | G0 impl |

---

## Geospatial / Distance

| Component | Technology | Why | Where | Locked By |
|-----------|------------|-----|-------|-----------|
| **Distance calculation (G0–G1)** | Haversine formula (great-circle) | Simple; no external dependency; sufficient for near-repeat kernel (400 m) and roaming checks | `server/src/suspicion/scorer.py` | Feasibility note (team/SBU.md) |
| **Road-network routing (G2+)** | OSRM (Open Source Routing Machine) | Real travel times; cost matrix for OR-Tools; requires local .osm.pbf extract — deferred due to infra weight | Planned G2 | Feasibility note (team/SBU.md) |
| **Hex→coordinate lookup (routing)** | Real `Claim.lat`/`Claim.lng` centroid average, not H3 geo-math | Existing `hex_id` fixtures/seed data across the repo are not valid H3 cell indices (`h3.cell_to_latlng` raises `H3CellInvalidError` on them) — rather than patch upstream hex generation mid-hackathon, the router derives a stop's real-world location from the actual claims filed in that hex, and honestly reports a hex as `unlocatable` if it has none. `h3` dropped from `requirements.txt` entirely; same real-data-over-invented-math principle as the risk fallback above | `server/src/routing/planner.py::_hex_centroid` | D10 (honesty ledger) |

---

## External APIs (keys held by Sbu, never in repo)

| Service | Purpose | Why | Status |
|---------|---------|-----|--------|
| **WeatherAPI** | Context covariate for risk forecast | Temperature, precipitation, visibility affect crime patterns | .env only |
| **EskomSePush** | Load-reduction schedules | Outages correlate with property crime spikes | .env only |
| **Discovery API** | Claims data, member profiles | Theme 3 requirement; roadmap integration | Simulated G0–G1 |

---

## Design Principles (from CLAUDE.md §4)

1. **Never harm an innocent.** No auto-dispatch on soft evidence; human verify gate (ADR-0002).
2. **Fuse independent senses.** Sight, sound, context are physically independent channels.
3. **Calibrated numbers only.** All probabilities from calibrated heads or labeled "target".
4. **Forecast, then prevent.** Pre-positioned Koper-dosed presence beats detection.
5. **Whitelist before watchlist.** Residents/regulars suppress recurrence false positives.
6. **Privacy at the source.** Embeddings not images; enforcement in vision layer.
7. **Demo-real vs simulated is explicit.** `sim_` prefix in code and filenames.
8. **Two-second rule.** Detection → alert render ≤ 2.0 s p95 on demo network.
9. **Docs-or-it-didn't-happen.** Behaviour change ⇒ BUILD-LOG entry in same PR.
10. **Graceful degradation.** Camera works without server; server works without vision; dashboard marks stale data.

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-07-24 | 1.0 | Initial tech stack doc from G0/G1 implementation; consolidates ADR-0001 decisions and feasibility notes |

---

## Related Docs

- **CLAUDE.md §2** — Locked decisions table (D1–D12)
- **docs/adr.md** — ADR-0001 (name/stack/repo), ADR-0002 (human-gated suspicion), ADR-0003 (BEACON naming)
- **CONTRIBUTING.md** — PR workflow, branch naming, review process
- **server/README.md** — Backend setup, API contract, running tests
