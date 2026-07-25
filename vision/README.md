# vision/ — Sali's computer vision services

Two standalone FastAPI services, each wrapping a Roboflow-hosted inference workflow. Not yet wired
into `server/` or `dashboard/app/` — they run independently and return the raw Roboflow workflow
result for now.

- `backend/` — license plate detection (`POST /detect`, multipart file upload)
- `weapen_backend/` — weapon detection (`POST /detect`, multipart file upload)

## Run locally

```bash
cd vision/backend   # or vision/weapen_backend
pip install -r requirements.txt
cp .env.example .env   # then fill in ROBOFLOW_API_KEY yourself — never commit a real key
uvicorn app:app --reload --port 8001   # weapen_backend: use a different port, e.g. 8002
```

`ROBOFLOW_API_KEY` — get one at https://app.roboflow.com/settings/api. Not entered here or by any
automated tooling; add it to your own local `.env`, which is gitignored.

## Not yet done

- No integration with `dashboard/app/`'s Live AI Camera screen — that screen currently shows an
  honest "no backing endpoint" message for plate/weapon detection (`docs/BUILD-LOG.md`, 2026-07-25).
- No integration with `server/src/api/sightings.py` — a real wiring path would have these services
  (or a caller of them) POST results to `/v1/sightings` so detections flow through the same
  entity-scoring/evidence pipeline as everything else, instead of living in a separate silo.
