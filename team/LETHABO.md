# Lethabo — planning + build (integration owner)

**Mission:** the spine. Vision agent → server → dashboard talks end-to-end before anyone's fancy piece lands, so everyone integrates into something that already works.

## By 12:00 (G0)
- [ ] Repo `beacon` created + this pack pushed; everyone added as collaborators; Notion board mirrored
- [ ] `vision/agent.py` v0: webcam → YOLOv8n person boxes → prints sighting JSON (30 lines, ultralytics quickstart)
- [ ] `server/` v0: FastAPI accepting POST /v1/sightings + echoing on /ws/ops (port VUKA relay — copy, rename, strip)
- [ ] Hand Connie the VUKA design-token file + dashboard skeleton

## Then
- G1: agent → server → dashboard live-feed card end-to-end on localhost + tunnel; `scripts/latency.py` ported and timing it
- G2: `brain/` port (log-odds fusion, conflict gate, human-gate cap per ADR-0002); Sighting Graph factors F1–F5 on sim streams; entity resolution (cosine + confusion-aware plate compare); demo clock override
- G3: run the demo orchestration; own the fallback recording

## Rules for me
- Copy VUKA patterns shamelessly (relay, WS client, latency harness, evidence chain) — rename, never reference VUKA in BEACON code comments.
- Every behaviour change = BUILD-LOG entry, same discipline as VUKA.
- I unblock others before I polish my own piece.
