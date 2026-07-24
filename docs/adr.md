# ILISO — Architecture Decision Records (append-only)

---

## ADR-0001: Project name, stack, and repo | Status: Accepted | 2026-07-24

**Context.** Theme 3 ("Biometric community security network") is a new build, distinct from VUKA. We need a name, a stack the five of us can move on immediately, and a repo. Deadline pressure: showable by 12:00 today, virtual pitch over Teams.

**Decision.**
- Name: **ILISO** (isiXhosa, "the eye"; *iliso lomphakathi* — the community's eye). Working name — run a trademark/company collision check before anything public-facing beyond the hackathon (there are SA firms with "Iliso" in the name, e.g. consulting/engineering). Alternates if vetoed: **QAPHELA** (isiZulu, "be alert"), **MASIBONE** ("let us see").
- Stack: Python vision agent (Ultralytics YOLOv8 + InsightFace + EasyOCR) → FastAPI+WS → React/Vite/MapLibre dashboard. SQLite day-0 → Postgres+pgvector+H3. OR-Tools routing. Ports VUKA's fusion brain, server patterns, dashboard skeleton and Discovery light theme.
- Repo: new public GitHub repo `iliso` (LethaboMH14). VUKA repo untouched; ILISO cites it as lineage (ISIPHEPHELO realized).

**Consequences.** Reuse buys us ~days. Public repo ⇒ VUKA secret discipline applies from commit one. Renaming later is one find-replace while the name is only in docs — decide by G1.

---

## ADR-0002: Suspicion engine is human-gated (soft evidence never auto-dispatches) | Status: Accepted | 2026-07-24

**Context.** Our unique IP is the Sighting Graph: repeat appearances of a plate/face across cameras at crime-correlated places/times build a suspicion score, with trajectory prediction to pre-arm downstream cameras. The failure mode of every comparable system (Flock ALPR false stops from 0/O confusion; face-rec demographic false-positive gaps up to ~100× in NIST FRVT) is automated action against an innocent person.

**Decision.** Two-gate ladder, enforced in `brain/`, not in policy:
1. Machine may raise an entity only to **watch candidate** (suspicion score is capped below alert level regardless of evidence mass — same cap-not-demote pattern as VUKA's conflict gate).
2. Only a **human verification** (security ops or community watch captain, seeing the evidence) promotes candidate → **Flagged**. Only Flagged entities pre-arm cameras or route patrols.
3. Recurrence factors count only for entities absent from the street **whitelist** (residents/regulars, learned + member-managed).
4. Plate matching uses a confusion-aware comparator (0↔O, 1↔I, 8↔B edit distance) and reports match quality — never silently exact-matches.
5. Every score shown is calibrated; every alert carries a cancel window.

**Consequences.** We give up "fully automatic" headlines and gain the pitch's strongest slide: the system is engineered so the worst outcome — armed response to a wrong match — cannot happen by design. Latency cost of the human gate is acceptable because the property-crime track (93.6% of claims) is prevention/recovery, not seconds-critical.

---

## ADR-0003: Rename ILISO → BEACON; Discovery-alignment naming rationale | Status: Accepted | 2026-07-24 | Supersedes the naming portion of ADR-0001

**Context.** Team decision: the platform name should be English and align with Discovery's brand voice, core purpose ("make people healthier and enhance and protect their lives") and Adrian Gore's Four Principles (disciplined optimism, focused urgency, declared goals, the Pareto Tail). ILISO (isiXhosa, "the eye") read as surveillance-first and needed translation in the pitch.

**Decision.** Platform = **BEACON**, tagline *"the light that stays on."* Rationale: a beacon warns early (focused urgency), is light rather than a watching eye (disciplined optimism — protection framed as hope, not surveillance), is by definition a public visible commitment (declared goals), and concentrates light exactly where the dark is (the Pareto Tail — mirrors the law of crime concentration our whole design exploits). Load-shedding resonance: the light that stays on when the streetlights don't. Candidates considered: FORESIGHT (too cold/analytics), LIGHTHOUSE (name collision with Google's dev tool), SENTINEL (militaristic, overused). Repo: `beacon` under LethaboMH14 (user-created). Full alignment mapping: docs/05 §1b.

**Consequences.** All docs renamed in this commit; ADR-0001 and the genesis BUILD-LOG entry retain "ILISO" as historical record (append-only protocol). "Vitality Protect" stays as pitch framing for the member programme, explicitly not a Discovery trademark claim. Trademark/collision check still required before any public use beyond the hackathon ("beacon" is common in tech and security — e.g. BLE beacons; acceptable for a hackathon, revisit for production).
