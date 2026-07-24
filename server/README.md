# BEACON Server

FastAPI + WebSockets + SQLite backend for BEACON community-safety network.

**Owner:** Sbu (with Lethabo)  
**Contract:** docs/01-ARCHITECTURE.md §5

## Setup

```powershell
# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## Environment Variables

Create `.env` file in `server/` directory:

```env
DATABASE_URL=sqlite:///./beacon.db
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
SQL_ECHO=false
```

## Running Tests

```powershell
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_sightings_contract.py

# Run contract tests only
pytest -m contract
```

## API Endpoints

### Core (G0)
- `GET /` — Health check
- `POST /v1/sightings` — Create sighting from vision agent
- `POST /v1/sightings/batch` — Batch sighting creation
- `GET /v1/entities/{id}` — Get entity with lazy-decayed suspicion score
- `POST /v1/entities/{id}/verify` — Human verification gate (flag/dismiss/whitelist)
- `WS /ws/ops` — Ops console WebSocket (all events)
- `WS /ws/member` — Member/guardian WebSocket (filtered events)

### Coming (G1)
- `GET /v1/risk?hex=&hour=` — Risk forecast
- `GET /v1/hotspots?window=` — Ranked hot hexes
- `POST /v1/routes/plan` — Koper-dosed patrol routing
- `POST /v1/alerts/{id}/ack` — Acknowledge alert
- `POST /v1/alerts/{id}/cancel` — Cancel alert

## Database Migrations

```powershell
# Create new migration
alembic revision -m "description"

# Run migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current revision
alembic current
```

## Architecture

```
server/
├── src/
│   ├── main.py              # FastAPI app + lifespan
│   ├── api/                 # REST endpoints
│   │   ├── sightings.py     # POST /v1/sightings
│   │   └── entities.py      # GET/POST /v1/entities
│   ├── ws/                  # WebSocket layer
│   │   ├── manager.py       # Connection manager (room-based)
│   │   └── router.py        # /ws/ops, /ws/member
│   ├── db/                  # Database layer
│   │   ├── models.py        # SQLAlchemy models (11 tables)
│   │   └── database.py      # Engine + session
│   ├── sightings/           # Sighting graph logic (G1)
│   ├── suspicion/           # Suspicion scoring (G1)
│   ├── incidents/           # Incident management (G1)
│   ├── risk/                # Risk forecast serving (G2)
│   └── routes/              # Route optimization (G2)
├── tests/                   # VUKA-style contract tests
├── alembic/                 # Database migrations
│   └── versions/            # Migration scripts
├── requirements.txt
└── README.md
```

## Lazy Suspicion-Score Decay

**Formula:** `score_now = base_score * 0.5^(days_elapsed/7)`

Computed at **read-time** in `GET /v1/entities/{id}` — no cron job needed (single-process SQLite demo server). Half-life of ~7 days.

## Human Verification Gate (ADR-0002)

Escalation ladder (enforced in code):
```
observed → candidate (machine ceiling) → [HUMAN VERIFY] → flagged
```

Every verification writes WHO/WHAT/WHEN to `evidence_chain` (hash-chained).

## WebSocket Events (G0)

**Ops room (`/ws/ops`):**
- `sighting.new` — Single sighting created
- `sighting.batch` — Batch sightings created
- `entity.flagged` — Entity promoted to flagged state

**Member room (`/ws/member`):**
- (G1) `alert.new` — Alert for own cameras
- (G1) `guardian.request` — Guardian panic trigger

## Contract Tests

VUKA-style: validate **exact shapes**, not just status codes.

- `test_sightings_contract.py` — POST /v1/sightings validation
- `test_websocket_contract.py` — WebSocket connection, echo, event delivery
- `test_entities_contract.py` — Entity GET/verify, lazy decay, evidence chain

Run: `pytest -v`
