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

---

## ADR-0004: Cloud provider selection — Azure for Students, per-workstream service map | Status: Accepted | 2026-07-24

**Context.** CLAUDE.md D3 commits to PostgreSQL + pgvector + H3 as the upgrade path from SQLite but names no cloud provider. The team needs one deploy target for the demo-day cloud fallback (docs/01 §6: "no cloud dependency to fail mid-pitch" — the demo itself runs on localhost + tunnel; cloud is the pre-recorded-video/live-backup safety net, not the critical path). Nobody on the team has a company card or existing cloud spend; student-tier free credit is the real constraint, not raw feature comparison.

**Decision.** **Azure for Students**, one provider, one shared resource group. Reasoning, compared directly against AWS and GCP for *this* team's situation:
- **No credit card required to activate** (verified via GitHub Student Developer Pack / academic email) — AWS Educate and GCP's free trial both still ask for a card, which is a real activation blocker mid-hackathon, not a hypothetical one.
- **$100/year credit, renews each academic year** — enough for a burstable Postgres instance + a small container app running for the ~2-week build window; AWS/GCP free-tier equivalents expire in 90 days or meter more aggressively on the always-on WebSocket connection BEACON needs.
- **Consistency with VUKA** (the sibling Gradhack project, same authors) already locked Azure as its primary (VUKA ADR-0015) — reusing the same provider means one set of learned quirks, one place credentials live, and a coherent story if a judge asks about infra across both submissions.
- Rejected AWS: broader service catalog doesn't matter at this scale, and the card requirement + steeper IAM setup cost more hackathon time than it buys.
- Rejected GCP: Cloud Run + Cloud SQL would work fine technically, but the $300 trial needs a card and the credit is a one-time 90-day pool, not an annual student allowance — wrong shape for a team that may keep iterating past the hackathon.

**Per-workstream service map** (one person's subscription hosts the shared resource group — see Consequences):

| Workstream | Owner | Azure service | Why this one, not an alternative |
|---|---|---|---|
| `server/` API + WS (docs/01 §2.2) | Sbu | **Azure Container Apps** | Native WebSocket support + scale-to-zero (cost control on a student credit); App Service works too but Container Apps' scale-to-zero matters more when the credit is finite |
| Postgres + pgvector + H3 (CLAUDE.md D3) | Sbu | **Azure Database for PostgreSQL – Flexible Server**, Burstable B1ms tier | pgvector ships as a supported extension; Burstable tier is the cheapest SKU that still gives predictable perf for the demo |
| Evidence clips / encrypted escalation media (docs/01 §2.1 privacy-at-source) | Sbu | **Azure Blob Storage** | Cheapest durable object store; SAS tokens give the short-lived signed-URL pattern the evidence chain needs |
| Secrets (DB creds, WeatherAPI/EskomSePush keys) | Sbu, shared read by all | **Azure Key Vault** | Free tier; avoids `.env` files with real keys ever touching a laptop that isn't the deploy target |
| `ml/` vision fine-tune training (Sali) | Sali | **Local/Colab GPU for training; Azure Blob Storage for model registry only** | Azure ML Compute GPU quota is not guaranteed to provision same-day on a fresh student subscription — don't gate training on it. Cloud is just where trained `.tflite`/`.pt` weights get versioned and pulled from, not where training happens |
| Ops dashboard hosting (Connie/Ipeleng) | Connie | **Azure Static Web Apps** | Free tier, GitHub-Actions-native CI/CD on push, matches the Vite/React build with zero extra config |
| `data/` claims ingest pipeline (Ndu) | Ndu | **Azure Functions** (timer-triggered) + **Azure Blob Storage** for raw/processed claims | Serverless matches the pipeline's actual shape (batch ingest → geocode → enrich → forecast, not a long-running service); avoids paying for an always-on VM for a job that runs a few times a day |
| RAG/LLM layer for the Vehicle-Specific Risk Routing idea (docs/01 §5 roadmap note, Ndu's idea) | Ndu | **Flagged risk, not yet resolved** | Azure OpenAI Service requires a separate access-request approval that is not guaranteed to clear during the hackathon window — do not build the RAG layer assuming it will. Fallback if it doesn't clear in time: call a model API directly (e.g. Anthropic/OpenAI with a personal key) and treat it as a `sim_`-labelled/manual-key integration in the pitch, not a "we deployed this on Azure" claim |

**Consequences.** One person's Azure for Students subscription hosts the shared resource group for anything that needs to be live for the demo (recommend Sbu's, since he owns `server/` and the deploy is server-centric) — everyone else gets Contributor/Reader access via Azure AD B2B guest invite, which is free and doesn't draw on their own $100 credit. Anyone who wants to experiment independently (e.g. Sali testing Azure ML Compute) can still activate their own student subscription for that alone — it just isn't the demo-day target. This is a G3-optional flex (docs/01 §6): the actual demo runs on localhost + cloudflared tunnel regardless, so a cloud outage on pitch day degrades gracefully to the already-proven local topology, not a hard failure.

---

## ADR-0005: Canonical suspicion-scoring engine — `server/src/suspicion/scorer.py` | Status: Accepted | 2026-07-25

**Context.** Two independent scoring implementations exist with no import relationship: `brain/fusion.py` (PR #7, in-memory `Entity` dataclass, F1+F6 only, standalone) and `server/src/suspicion/scorer.py` (PR #10, all six F1–F6 factors, reads real `Sighting`/`Claim` DB rows, wired into the live `/v1/entities` API and the hash-chained evidence log). A pitch whose ethics story rests on "one auditable score, human-gated" cannot ship with two scorers that could disagree on the same entity.

**Decision.** `server/src/suspicion/scorer.py` is canonical — it's the one actually reachable from the frozen API contract (docs/01 §5) and the one the evidence chain / human-verify gate is built against. `brain/fusion.py` is retained as a reference prototype (its F1 window logic and human-gate discipline are sound and match) but must not be wired into `server/` or the dashboard; no new factor work should land there. If `brain/`'s author wants F2–F5 parity or a different modelling approach, extend `scorer.py` directly rather than completing the parallel file.

**Consequences.** No code deleted (PR #7's author's call whether to remove or keep `brain/` as a design note). Any future PR wiring entity scoring into an endpoint must import from `server/src/suspicion/scorer.py`, not `brain/fusion.py`.
