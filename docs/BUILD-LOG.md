# ILISO — Build Log (newest first)

Every behaviour change gets an entry in the same commit. Plain-language section mandatory — anyone on the team must be able to read it.

---

## 2026-07-24 — Project genesis: full architecture + team pack

**What:** Created the ILISO doc pack from scratch: CLAUDE.md master context, docs 01–06 (architecture, data/forecasting, vision ML, UI brief, business case, demo plan), ADR-0001 (name/stack/repo) + ADR-0002 (human-gated suspicion engine), five team briefs.

**Why:** Theme 3 brief ("Biometric community security network") + Gradhack_Insure_Data.xlsx analysis + research pass (Koper curve, near-repeat, RTM, NIST FRVT, Flock/ZeroEyes case studies, Discovery shared-value model). Leader guidance: 70/30 demo/slides, virtual over Teams, showable by 12:00 today.

**Plain language:** We started the new project for the real Gradhack theme. It has a name (ILISO — "the eye"), a plan, and a one-page starting document for each of us in `team/`. Read CLAUDE.md, then your own file, and you know exactly what to do this morning. The big design ideas: predict crime before it happens using Discovery's own claims data; spot repeat cars/people across cameras (the "seen 3 times" rule) but ALWAYS with a human confirming before anything happens; and route security patrols in 12-minute visits to the right streets at the right hours to save fuel and prevent break-ins.

**Breaks/risks:** Name needs a collision check before public use. Geocoding of suburbs must start early (slow API). The 00:00 data spike needs the hour_known caveat in every chart.
