# ILISO — 06 Demo Plan (70% demo / 30% slides, virtual over Teams)

> Owner: Lethabo (orchestration) + everyone has a driving role. Status: v1.0, 2026-07-24.
> Leader guidance: 70/30 split, demo as close to live as possible. No phones — laptops over Teams.

## 0. Topology

- **Laptop A (Sali or Lethabo):** vision agent + webcam = "the ring camera". Screen-shared during Act 1 with detection overlay window.
- **Laptop B (Connie):** ops console — the main shared screen for most of the demo.
- **Laptop C (Ndu):** member view — alert lands HERE live; camera on so judges see the human react.
- Server: localhost on A or B + cloudflared tunnel (VUKA playbook) so B and C connect across houses. Full rehearsal on the actual Teams call beforehand — screen-share pixel sizes lie.

## 1. Script (~9 min demo + ~4 min slides)

**Cold open (30 s, Laptop B).** Map of THEIR claims: 15,712 real claims, heatmap glowing. "This is your book of business. Watch the midnight spike." — time scrubber to 00:00, hexes ignite. First 30 seconds = we did real work on real data.

**Act 1 — LIVE detection (3 min, A→B→C).** The moment the leader asked for:
1. A's webcam live with overlay. Teammate walks past holding a **printed plate** (fake SA plate we made) → plate box + OCR text on screen → sighting card streams onto B's ops feed. *"Sighting one."*
2. Same plate passes again ("camera 2" — agent's camera-ID toggled). *"Sighting two — same entity, resolved by our confusion-aware matcher."*
3. Third pass at "00:14" (demo clock) + a printed weapon image in frame → weapon-candidate box → on B, the suspicion meter climbs and the entity hits **watch candidate**. *"Three sightings, two cameras, claim-peak hour, weapon-candidate — and notice: the machine CANNOT go further alone."*
4. Connie clicks **Verify → Flag** in the verify queue (evidence side-by-side on screen). Alert **pops live on C** — Ndu reacts on camera, shows the clip + cancel ring, taps **Guardian verify**. *"Detection to that laptop: 1.4 seconds."* (real number from `scripts/latency.py` — never invented).
5. Face beat, carefully: pre-enrolled TEAM face (consented) walks past → "recognised: watch-flagged entity" → factor chip. Consent line said out loud. No stranger faces, ever.

**Act 2 — Forecast + patrol (3 min, B).** Toggle past→forecast layer: "This isn't where crime WAS — it's tonight's prediction: near-repeat contagion + risk terrain + weather + load-reduction + payday." Click **Plan routes** → Koper-dosed route draws, counters animate: fuel −X%, coverage Y%. One breath on the science: "11–15 minute doses — Koper's curve — crime-in-next-30-min drops 15%→4%."

**Act 3 — Sighting Graph replay (2 min, B, `sim_` said out loud).** "Simulated camera network, real logic." Replay: same vehicle across 3 cameras over 2 nights near real claim locations → factor chips light F1/F2/F3 → candidate → verify → **trajectory cone** + suggested interception hex. *"The cordon closes before the third break-in — that's near-repeat prevention, live."*

**Slides (4 min, Sali + Ndu).** Business case → honesty/bias slide (the mic-drop: "here's what this system refuses to do") → roadmap (UMKHUSELI personal layer, SAPS, mesh).

## 2. Fallback ladder (rehearse every rung)

1. Full live (target) → 2. Act 1 pre-recorded screen capture, Acts 2–3 live (map+replay are local, low-risk) → 3. Full recorded video + live voiceover. Record the fallback video at G2, not the night before.

## 3. Rehearsal checklist

- [ ] Tunnel + WS reconnect tested on real Teams call, all three laptops, cameras on
- [ ] Printed props ready: 2 fake plates, weapon printout, enrolled team face
- [ ] Demo clock override (`DEMO_TIME=00:14`) working
- [ ] Latency harness numbers captured for the script
- [ ] Every `sim_` moment has its spoken disclosure line in the script
- [ ] Timed full run ≤ 13 min twice
