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

## How they get into the pipeline

`scripts/vision_lens_demo.py` is the caller: it samples frames from a video, fans each frame out to
both services, runs InsightFace `buffalo_l` **in-process** for faces (no third service — a demo that
needs four servers up has four ways to fail on stage), and POSTs every detection to
`/v1/sightings`. From there detections flow through the same entity-resolution, scoring and evidence
path as everything else, and `dashboard/app/`'s Live AI Camera screen draws them from
`GET /v1/sightings` (ADR-0006).

## Known limits (measured, not assumed)

- **Plate OCR is unreliable.** Over a 1080p SA hijacking clip it returned markdown fencing, digit
  runs, and words read off a news chyron. `server/src/suspicion/plate_text.py` rejects what it can
  syntactically, but a plate-shaped piece of background text still gets through — a read is a lead,
  never an identification.
- **Face matching is uncalibrated.** The 0.40 cosine threshold is a starting point, not a tuned one.
  There is no face quality gate, so a 16×22 px face is accepted on the same terms as a good one.
- **No POPIA retention/deletion path for stored embeddings yet** (`docs/adr.md`, ADR-0006).
