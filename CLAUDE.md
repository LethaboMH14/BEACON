# CLAUDE.md — BEACON Master Build Context

> **Read this first, every session.** Single source of truth for how we build BEACON.
> Deep detail lives in `/docs` and `/team`. Amend only via the protocol in §9.
> Team: Lethabo (planning + build), Sbu (backend + systems), Sali (vision ML + Discovery alignment), Connie/Ipeleng (UI + logic), Ndu (data science + business).

---

## 1. What we are building

**BEACON** — *the light that stays on* — an AI community-safety network for the Discovery Gradhack 2026 Theme 3: **"AI for Safer Communities — Biometric community security network."**

A beacon warns early, summons focused response, and keeps shining when the streetlights die. That is the product in one word — and it is Discovery's language: their core purpose is to *make people healthier and **enhance and protect their lives***. BEACON productizes the "protect their lives" clause (see docs/05 §1b for the full Four Principles alignment).

Discovery supplies ring-doorbell cameras to members and partners with private security companies. BEACON is the intelligence layer on top:

1. **See** — faces, license plates, vehicles, weapons detected on camera streams (edge vision).
2. **Hear** — gunshots, glass-break, screams (acoustic channel, ported from VUKA).
3. **Know** — Discovery claims data fused with weather, load-reduction schedules, public events/marches, paydays → per-hex, per-hour **risk forecast** (not a heatmap of the past — a prediction of tonight).
4. **Connect** — the **Sighting Graph**: every camera detection becomes a node; repeat plates/faces across cameras at crime-correlated places and times build a calibrated **suspicion score** (see docs/01 §4 — this is our unique IP).
5. **Act** — human-verified alerts, Guardian confirmation, Koper-dosed patrol routes optimized for risk coverage per litre of fuel.

**The thesis:** everyone else will demo a detector and a heatmap. BEACON fuses four independent senses into one calibrated decision, forecasts crime *before* it happens, and is engineered to never harm an innocent person — then wraps it in Discovery's own shared-value model so prevention pays (**Vitality Protect**).

**Lineage:** BEACON is the community layer VUKA always had on its roadmap (ISIPHEPHELO), now realized for Theme 3. VUKA's UMKHUSELI (personal app) remains the roadmap integration for the person-present 6% of crimes.

**The data dictates the design (Gradhack_Insure_Data.xlsx, 15,712 claims):**
- 93.6% property crime (Theft 14,380 · Burglary 214 · jamming 7 …) → prevent / deter / recover / investigate.
- 6.1% violent crime (Hijack 680 · Armed Robbery 272) → real-time life-safety.
- Midnight spike: 00:00 hour = 1,296 claims, ~3× the 05:00 trough. Theft alone ≈ **R1.09bn** (contents R407M + vehicle R686M).

## Milestones

| Gate | When | What must exist |
|---|---|---|
| G0 skeleton | **Today 12:00** | Repo + docs live; webcam detection running; dashboard shell; claims loaded + first heatmap; UI mock |
| G1 wired | Tonight | Live detection → server → alert on second laptop over WS, end-to-end |
| G2 demo-ready | +1 day | Suspicion-graph replay, forecast layer, Koper route; 70/30 demo rehearsed on Teams |
| G3 pitch | Final day | Polished run + recorded fallback video |

---

## 2. Locked decisions (do not relitigate in code; amend via §9)

| # | Decision | Choice | Why |
|---|---|---|---|
| D1 | Demo platform | **Laptop-first, virtual over Teams.** Webcam = ring camera. No phones required for the demo | Pitch is virtual; judges see laptops |
| D2 | Vision stack | **Python: Ultralytics YOLOv8 (person/weapon/plate) + InsightFace ArcFace (face embeddings) + EasyOCR/PaddleOCR (plates)** | Pretrained, fine-tunable, runs on laptop; Sali owns fine-tuning |
| D3 | Backend | **FastAPI + WebSockets. SQLite day-0 → PostgreSQL + pgvector + H3** | Team fluency (VUKA); pgvector for face/plate matching; upgrade path |
| D4 | Dashboard | **React + Vite + Tailwind + MapLibre/deck.gl** — port VUKA ops-dashboard skeleton + Discovery light theme | Days of reuse, judge-familiar Discovery look |
| D5 | Geo | **H3 hexes res 8/9; suburbs geocoded via Nominatim (cached file, checked in)** | Claims have no lat/lng — geocoding is mandatory |
| D6 | Suspicion/fusion | **Calibrated log-odds fusion + conflict gate (ported VUKA brain) + human-verify gate.** Soft evidence alone can NEVER auto-dispatch | Survives scrutiny; the anti-Flock design |
| D7 | Forecasting | **Seasonal baseline (hex × hour × weekday) + near-repeat kernel + gradient-boosted model with context covariates (weather, load-reduction, events/marches, paydays)** | Literature-grounded (Johnson & Bowers; Caplan & Kennedy RTM); explainable |
| D8 | Routing | **Google OR-Tools team-orienteering: maximize risk-weighted coverage under fuel/time budget, 12-min Koper dwell per hot-spot** | Koper 1995: 11–15 min dose drops next-30-min crime 15%→4% |
| D9 | Privacy boundary | **Embeddings, not images. Faces/plates stored as vectors + short retention incident clips only. Watchlist entries require human verification. Resident/regular whitelist first-class** | POPIA by construction; NIST FRVT bias answer lives in the architecture |
| D10 | Honesty ledger | Carried from VUKA. Never: "prevents all crime", "identifies criminals" (it identifies *leads*), uncalibrated precision, silent simulation. `sim_` prefix on all simulated components | Credibility is the moat |
| D11 | Naming | Platform = **BEACON** ("the light that stays on" — ADR-0003, supersedes ADR-0001's ILISO). Suspicion engine = "Sighting Graph". Member programme = "Vitality Protect" (pitch framing only, not a Discovery trademark claim) | English, Discovery-toned, Four Principles-aligned |
| D12 | Repo | Public GitHub repo **[LethaboMH14/BEACON](https://github.com/LethaboMH14/BEACON)**. Same secret rules as VUKA: `.env` gitignored, keys via Sbu directly, never in commits | Repo is PUBLIC |
| D13 | Cloud provider | **Azure for Students, one shared subscription (Sbu's, hosting server/DB), per-workstream service map in ADR-0004.** No credit card to activate, $100/yr, consistent with VUKA's Azure choice | Student budget reality beats raw feature comparison; demo runs on localhost + tunnel regardless, cloud is the optional G3 flex |

---

## 3. Repo map (create exactly this)

```
beacon/
├── CLAUDE.md                  # this file
├── README.md
├── docs/                      # 01–06 + adr.md (append-only) + BUILD-LOG.md
├── team/                      # one brief per builder — your starting document
├── vision/                    # Sali+Lethabo: camera agent (Python)
│   ├── agent.py               # webcam/RTSP → detections → WS to server
│   ├── detectors/             # yolo_weapons.py, faces.py, plates.py, sim_audio.py
│   └── models/                # weights + models.json registry (name, sha256, size)
├── server/                    # Sbu: FastAPI
│   └── src/{api,ws,sightings,suspicion,incidents,risk,routes,db}
├── brain/                     # ported VUKA fusion: calibrated log-odds, conflict gate, hysteresis
├── data/                      # Ndu: ingest/, geocode/, enrich/, forecast/, eval/
├── dashboard/                 # Connie+Lethabo: React app (ops / exec / member views)
├── scripts/                   # demo orchestration, seeders, latency harness
├── design/                    # Connie: mockups, exports, screen specs (see design/README.md)
└── .github/                   # workflows/ci.yml, PULL_REQUEST_TEMPLATE.md, CODEOWNERS
```

**Collaboration flow (how everyone's adds show up):** work on branches `<name>/<thing>`, open a PR for EVERYTHING — code, docs, mockups. PRs are where we see, comment, and amend each other's additions (CONTRIBUTING.md has the 5-step loop). Everyone sets Watch → All activity on the repo so nothing lands silently.

---

## 4. Non-negotiable engineering principles

1. **Never harm an innocent.** A biometric match is a lead for a human, never a verdict (NIST FRVT: false-positive gaps up to ~100× across demographics — in SA this is existential). No auto-dispatch on soft evidence. Cancel windows on everything.
2. **Fuse independent senses.** Sight, sound, context, phone are physically independent channels. Never stack correlated evidence and call it confidence.
3. **Calibrated numbers only.** Any probability shown to an operator or judge comes from a calibrated head or is labelled "target".
4. **Forecast, then prevent.** The system's first job is that the crime never happens: pre-positioned Koper-dosed presence beats detection. Deterrence over confrontation — never engineer a violent encounter over a TV.
5. **Whitelist before watchlist.** Residents, domestic workers, delivery regulars are learned first. Recurrence only counts as suspicion when the entity is *unknown to the street*.
6. **Privacy at the source.** Embeddings not images; enforcement in the vision layer, not policy docs. Code persisting raw face crops outside the escalation path fails review.
7. **Demo-real vs simulated is always explicit.** `sim_` prefix in code AND named in the pitch. Judges forgive simulation; they don't forgive being misled.
8. **Two-second rule.** Camera detection → operator/member alert render ≤ 2.0 s p95 on the demo network. `scripts/latency.py` is the referee.
9. **Docs-or-it-didn't-happen.** Behaviour change ⇒ docs + BUILD-LOG entry in the same PR.
10. **Graceful degradation.** Camera works without server (local queue). Server works without vision (manual + claims-only mode). Dashboard shows stale-marked data, never blank.

---

## 5. Coding standards

Carried from VUKA verbatim: TypeScript strict in `dashboard/`; Python 3.11+ with ruff/black/type-hints/pytest in `vision/ server/ brain/ data/`; conventional commits; branch names `<name>/<thing>`; tests required for suspicion math, fusion, forecast eval, API contracts; secrets never in repo; model weights registered in `vision/models/models.json` with sha256.

---

## 6. Budgets (the referee numbers)

| Budget | Target | Enforced by |
|---|---|---|
| Detection → alert render | ≤ 2.0 s p95 | `scripts/latency.py` |
| Vision throughput (demo laptop) | ≥ 8 FPS person/weapon; plate+face on trigger frames | manual bench, `vision/bench.py` |
| Face match thresholds | candidate ≥ 0.55 cosine, verify-suggest ≥ 0.65 (targets — calibrate) | `brain/` tests |
| Forecast skill | beat naive last-4-week baseline on hit-rate@top-5% hexes (PAI) | `data/eval/` |
| Route value | ≥ 30% fuel saving vs fixed route at ≥ 80% coverage of top risk hex-hours (sim) | `data/eval/routes.py` |
| False-alarm budget | ≤ 1 unverified alert surfaced to member per camera-week (target) | tuned in eval |

---

## 7. How to work

Read order: this file → your brief in `team/<YOU>.md` → the doc for your area → `docs/adr.md` → `docs/BUILD-LOG.md` (top entries). Then branch, build, test, PR.

**Division of labour — fluid, not fenced:**
- **Lethabo** — planning + build everywhere; owns CLAUDE.md, docs/01; pairs with Sbu on backend and Sali on vision export.
- **Sbu** — `server/`, systems building, demo orchestration; owns docs/01 §5 API contract. Nitpicks feasibility on every brief — same expectation as VUKA.
- **Sali** — `vision/` fine-tuning (weapons, faces, plates), model eval; presentation + Discovery alignment; owns docs/03.
- **Connie (Ipeleng)** — `dashboard/` UI + interaction logic, all three views; owns docs/04.
- **Ndu** — `data/` ingestion, enrichment, forecasting, heatmaps; business case; owns docs/02 + docs/05.

**Tracking:** Notion board + GitHub. Everyone's `team/` brief is their day-one document — amend it as you learn.

---

## 8. Glossary

| Term | Meaning |
|---|---|
| Sighting | One camera detection event: (entity, camera, hex, ts, modality, confidence) |
| Entity | A resolved face/plate/vehicle identity (embedding cluster), never a legal identity |
| Sighting Graph | The store + logic linking sightings into recurrence, roaming, and trajectory patterns |
| Suspicion score | Calibrated log-odds over sighting-graph factors; capped below action without human verify |
| Whitelist | Residents/regulars known to a street; kills recurrence false-positives |
| Watch candidate → Flagged | Machine-proposed → human-verified watchlist states. Only Flagged pre-arms cameras |
| Digital cordon | Downstream cameras pre-armed along a predicted trajectory |
| Koper dose | 11–15 min patrol dwell at a hot-spot for maximum residual deterrence |
| Risk cell | H3 hexagon with per-hour forecast score |
| Near-repeat | Elevated burglary risk near a recent incident for ~1–2 weeks (Johnson & Bowers) |
| Hard trigger / soft track | Deterministic human trigger (panic, Guardian confirm) vs probabilistic ambient inference |
| Honesty ledger | Claims we refuse to make (docs/05 §6) |

---

## 9. Amendment protocol

Same as VUKA: propose via ADR in `docs/adr.md` (append-only), discuss in the PR, mark Accepted on merge, update the §2 table if a locked decision changed. Never edit history — supersede.

**Changelog:**
- 2026-07-24 — v1.0 — Initial doc pack as ILISO (docs 01–06, team briefs, ADR-0001/0002). Authors: Lethabo + Claude.
- 2026-07-24 — v1.1 — ADR-0003: renamed to **BEACON**; Four Principles + Discovery-purpose alignment added (docs/05 §1b); contribution workflow (CONTRIBUTING.md, PR template, CODEOWNERS, design/). Authors: Lethabo + Claude.
