# ILISO — the community's eye

AI community-safety network for Discovery Gradhack 2026 · Theme 3: AI for Safer Communities.

**One line:** ILISO fuses four independent senses — camera vision (faces, plates, weapons), acoustics, Discovery claims context, and member phones — into one calibrated decision; forecasts crime before it happens; routes Koper-dosed patrols to prevent it; and is engineered so it can never harm an innocent person.

Built by Team Sonar: Lethabo Hoaeane · Sbu · Salimata Mbaye · Ipeleng (Connie) · Ndumiso.

## Start here
1. [CLAUDE.md](CLAUDE.md) — master build context (read first, every session)
2. `team/<YOU>.md` — your day-one brief
3. `docs/01-ARCHITECTURE.md` → your area doc (02 data · 03 vision · 04 UI · 05 business · 06 demo)
4. `docs/adr.md` + `docs/BUILD-LOG.md` — decisions + what just changed

## The seven theme requirements → where they live
| Requirement | Component |
|---|---|
| Biometric recognition | `vision/detectors/faces.py` (ArcFace) + human-gated matching (ADR-0002) |
| Character recognition | `vision/detectors/plates.py` (YOLO + EasyOCR + confusion-aware compare) |
| Cross-multimedia comparison | Sighting Graph entity resolution (pgvector) |
| Alerting geo-correlated with hot-spots | `brain/` fusion + `server/` WS fan-out |
| Ingesting/processing claims | `data/ingest` (15,712 real claims) |
| Hot-spot mapping on web/mobile | `dashboard/` MapLibre + H3 forecast layers |
| Community assistance (route optimization) | `data/forecast` + OR-Tools Koper-dosed routing |

## Honesty
Simulated components carry a `sim_` prefix in code and are named as simulated in every demo. The claims we refuse to make are listed in `docs/05 §6`. That's the moat.
