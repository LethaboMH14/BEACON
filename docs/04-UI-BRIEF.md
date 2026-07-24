# BEACON — 04 UI + Interaction Logic (Connie/Ipeleng's spec)

> Owner: Connie. Status: v1.0, 2026-07-24. Day-one doc: `team/CONNIE.md`.

## 1. Who gets a dashboard? (the decision, reasoned)

One React app, three role-switched views — build in this order:

1. **Security-company ops console (PRIMARY — build first).** They are the actor: they verify suspicion candidates, dispatch, drive routes. The theme's "community assistance" requirement is about THEIR fuel and coverage. Most demo minutes happen here.
2. **Member/guardian view (SECOND).** The emotional demo beat: alert lands on the member's laptop, they see the clip + confidence + cancel window, tap Guardian verify. Also: arm camera, street safety score, Vitality Protect points. Mobile-frame styling (reuse VUKA phone-chrome CSS) even though it runs in a browser.
3. **Discovery exec view (THIRD — can be one tab).** Portfolio analytics: claims trend by peril/suburb, projected claims avoided, network growth. Exists to make the buyer see money.

## 2. Ops console — screens + logic

**Layout:** dark Discovery chrome header + nav pills (port from VUKA ops-dashboard), 3-panel body: map (left, dominant) · live feed (right) · detail drawer (bottom/overlay).

- **Map:** MapLibre + deck.gl H3 layer. Toggles: past claims heatmap / forecast (next-24h) / patrol routes / camera pins (green live, grey offline, amber pre-armed cordon). Time scrubber 00–23h — dragging it and watching hot-spots migrate to midnight is a demo moment.
- **Live feed:** streaming sighting/alert cards (WS). Alert card anatomy: thumbnail/clip · fused confidence bar (calibrated, one number) · factor chips ("3rd sighting · 00:14 · near-repeat zone · weapon-candidate") · countdown cancel ring · actions [Verify] [Dismiss] [Dispatch].
- **Verify queue (the human gate — make it beautiful, it's our ethics UI):** side-by-side evidence: sighting timeline on mini-map, embedding-match strength, whitelist check result. Actions: Flag / Dismiss / Add to whitelist. Every action logged to the evidence chain.
- **Entity detail:** sighting timeline, suspicion score history sparkline, factor breakdown (F1–F6 as labelled chips — mirrors docs/01 §4), trajectory cone on map when Flagged.
- **Routes panel:** tonight's Koper-dosed route per team; per-stop dwell timer (12 min); counters: "fuel −34% · coverage 82% of top-risk hex-hours" (values from Ndu's optimizer, never invented).

## 3. Member view — screens

Arm/disarm camera · alert card (same anatomy, softer language: "Unusual activity at your driveway") with [I'm fine — cancel] [Alert my Guardian] [Call armed response] · street safety score + tonight's forecast chip · Vitality Protect points + premium-discount line · privacy centre (what's stored: "embeddings, not photos — here's what that means" plain-language explainer; whitelist management: "Add my domestic worker / delivery regular").

## 4. Logic rules the UI must enforce (not just display)

1. No soft-evidence alert ever shows a "dispatch armed response" as the primary action — Verify is primary; Dispatch is behind confirmation.
2. Every probability shown is the ONE calibrated fused number + factor chips. Never raw per-model confidences to end users.
3. Cancel windows on everything actionable (15 s visual ring).
4. Stale data is marked stale (grey wash + timestamp), never blank, never silently fresh-looking.
5. `sim_` data gets a small "SIMULATED" corner tag in demo builds — judges see we label it even in the UI.
6. Copy follows the honesty ledger: "weapon-candidate detected", "possible repeat sighting" — never "criminal identified".

## 5. Design system

Reuse the VUKA redesign-v2 tokens: Discovery light theme for content panels, dark chrome header, CTA gradient tokens, phone-chrome for member view. Fonts/colours already extracted in the VUKA ops-dashboard — Lethabo will hand you the token file at G0. My widget mock from the brainstorm (ops console with fusion panel + hex map + member strip) is the visual reference — improve on it, don't feel bound by it.

## 6. Definition of done

- [ ] G0 (12:00): Figma (or HTML) mock of ops console 3-panel + alert card anatomy + member alert screen
- [ ] G1: React shell wired to WS (Lethabo pairs); live feed cards rendering real sightings
- [ ] G2: verify queue + entity detail + routes panel + member view functional on demo data
- [ ] G3: polish pass; demo click-path rehearsed (you drive the ops console live)
