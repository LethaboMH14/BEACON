# BEACON — 3D + motion pack (presentation set pieces)

> Owner: Lethabo. Status: v1.0, 2026-07-25. Companion to `design/PROMPT-PACK.md` (which covers the *product* screens).
> This file covers the **cinematic pieces** — the 30-60 second moments that sit inside the pitch and make judges lean in.
> Same rule as the prompt pack: paste the §2 preamble, then one §4 scene block.

---

## 1. How 3D and animation actually work on the web — and which to pick

There are six real routes. They are not interchangeable, and picking wrong costs a day.

| Route | What it actually gives you | Real cost | Where it wins |
|---|---|---|---|
| **CSS 3D transforms** (`perspective`, `transform-style: preserve-3d`, `rotateX/Y/Z`, `translateZ`) | Flat planes positioned in genuine 3D space. Real parallax, real depth stacking, real perspective. No geometry, no lighting. | Zero dependencies. Cannot crash. Renders identically everywhere. | Isometric cutaways, exploded/layered stacks, floor plans, device mockups, anything built from planes |
| **SVG 2.5D isometric** | Hand-authored vector geometry at a fixed isometric angle. Infinitely crisp, every line under your control. | Zero dependencies. The geometry itself is the labour. | The "architectural maquette / blueprint" look — reads as *designed*, not *rendered* |
| **React Three Fiber** (three.js in React) | True WebGL 3D — real cameras, lights, shadows, materials, orbit controls, imported GLTF models | ~600KB+, npm install, WebGL can fail on a locked-down machine, and **mediocre lighting reads as amateur** | Genuine free orbit around a model; extruded terrain; anything needing real shadow |
| **deck.gl** | GPU-extruded H3 hexagons on a real map | Already in our planned stack (docs/07) | The 3D risk terrain — *reuse what's already specced, don't rebuild it* |
| **Rive** | Interactive vector animation driven by state machines (idle → detecting → alerting) | Needs the Rive editor + runtime; authoring skill | Component-level state animation, e.g. the camera icon itself |
| **Pre-rendered video** | Guaranteed frame rate, zero crash risk | Not interactive; can't claim "this is live" | **The fallback. Always record one.** |

### Four judgement calls that matter more than the tool

1. **Over a Teams screen-share, live WebGL loses.** Video compression destroys smooth gradients and fast motion — a beautiful 60fps scene arrives as mush. Design *for the codec*: high contrast, chunky forms, **slow deliberate motion**, few simultaneous moving elements.
2. **A great CSS/SVG isometric beats a mediocre three.js scene, every time.** Bad 3D (flat lighting, default materials, floaty camera) reads instantly as a student project. Stylised 2.5D reads as art direction. Unless someone is genuinely strong in three.js, **route 1 or 2 is the higher-quality-looking answer, not the compromise.**
3. **Build it interactive, but record the run.** Then the recording is the safe pitch asset — and the interactivity becomes the hold-back (see §3).
4. **One thing moves at a time.** Confident motion is sequential. Five things easing at once is a screensaver.

**Recommendation:** CSS 3D + SVG for the house/street pieces, deck.gl for the hex terrain (already planned), Framer Motion as the sequencing layer over all of it. Reach for React Three Fiber only for the free-orbit shot, and only if the first attempt already looks good — if it doesn't in one pass, it won't.

---

## 2. The constant preamble (paste above every §4 scene block)

```
You are building a cinematic set piece for BEACON — a real-time community safety platform
built for Discovery (South African insurer). Tagline: "the light that stays on."

This is not a product screen. It is a 30-60 second visual moment inside a pitch to judges,
shown over a Teams screen-share. It must look like a title sequence for a serious
infrastructure product — think Apple's "how Find My works" explainers, Stripe's network
diagrams, Cloudflare's globe, Linear's release films. Restrained, technical, expensive-looking.
Zero cartoon, zero playfulness, zero stock-3D-icon energy.

CRITICAL CONSTRAINT — it will be watched through video compression:
- High contrast between figure and ground. Avoid subtle gradient-on-gradient.
- Motion is SLOW and DELIBERATE. Long eases (600-1200ms), generous holds between beats.
- ONE element moves at a time. Sequential, never simultaneous.
- Chunky, legible forms. Thin 1px detail disappears over Teams — use 2px minimum for
  anything that must read.

VISUAL LANGUAGE
- Palette on a near-black canvas (#070B12):
  --beacon: #F5A623   signal amber — this is THE hero colour, it means "our system is alive"
  --beacon-glow: rgba(245,166,35,0.35)
  --discovery: #0B5FA5  deep blue — structure, architecture, the built world
  --edge: rgba(255,255,255,0.14)  geometry outlines
  --surface: #121A28 / #0D1421   building masses
  --warm: #FFC97A     ordinary domestic light (windows, streetlights) — this is what DIES
                      in the blackout, in contrast to --beacon which does not
  --risk ramp: #10B981 safe / #F59E0B watch / #F0653A high / #E11D48 critical
- Materials: matte, flat-shaded, architectural-model feel. NOT photoreal, NOT glossy.
  Think a physical scale maquette lit from above, or a technical drawing given depth.
- Every solid form carries a thin lighter outline on its top edges — this is what sells
  "designed object" instead of "grey blob".
- Type overlaid on the scene: Inter, small, uppercase 0.08em tracking for labels;
  tabular numerals for any counter.

TECHNICAL DIRECTION
Build with CSS 3D transforms (perspective + transform-style: preserve-3d + translateZ layering)
and inline SVG geometry, animated with Framer Motion. Do NOT use three.js, do NOT use any
external 3D library, do NOT load external assets, models, or fonts — everything inline and
self-contained. React + TypeScript + Tailwind, one file.

Include a small transport control (play / pause / restart / scrub) so the sequence can be
driven manually during a live presentation rather than only autoplaying.
```

---

## 3. Presentation strategy — what to show when

Three checkpoints: **today 09:00** (informal look at progress), **Sunday 10:00** (full judging), **top-6 refine hour → re-judge**.

- **Today 09:00** — show the working system, not the film. Progress check-ins reward *substance*; a polished animation this early invites "so is any of it real?"
- **Sunday 10:00** — the film runs as a **recording** inside the pitch. Safe, timed, no crash risk. Everything else is live.
- **The refine hour / top-6 round — the hold-back.** Re-open the same piece **live and interactive**: *"That sequence you saw? It wasn't a video. Here — orbit it. Click a node."* A reveal that something already shown was real all along lands far harder than a new asset, and it costs zero extra build because it's the same artefact.

Second hold-back candidate: the load-shedding blackout beat (§4.1's final 10 seconds). If time is short on Sunday, cut it — then open the refine round with it.

---

## 4. Scene prompts

### 4.1 The House — "one night, one camera, one decision" (**build this first**)

The piece the whole idea is built on: a home, an approach, the signal travelling, the human gate, and the blackout.
Runs ~60s. Contains three separable beats, so it degrades gracefully if time runs out.

```
SCENE: An isometric cutaway of a suburban Johannesburg home at night, presented as a matte
architectural scale model floating on a near-black canvas. Single-storey house, walled yard,
paved driveway, a sliding gate to the street, a short strip of street with a kerb and one
streetlight. Slight continuous rotation (very slow, ~40s per full pass) so it always feels alive.

The house has a cutaway front wall revealing two simple interior rooms with warm --warm light
spilling out. Everything else — walls, roof, driveway, gate — is matte --surface with thin
--edge outlines on every top edge.

Mounted beside the front door: the BEACON camera. Small, a matte housing with a single amber
lens dot that PULSES slowly (2s cycle) in --beacon. This dot is the emotional anchor of the
whole piece — it is the only amber thing on screen at the start.

Sequence in six beats, driven by a transport control:

BEAT 1 (0:00-0:08) — ESTABLISH. The model rotates. Warm windows. The amber camera dot pulses.
A small label chip anchors to the camera with a leader line: "CAMERA 01 · FRONT DOOR · LIVE"
with a cyan live dot. Nothing else happens. Let it breathe.

BEAT 2 (0:08-0:18) — APPROACH. A dark vehicle silhouette slides in along the street and stops
outside the gate. Its headlights cast two soft --warm cones onto the road, then cut. From the
camera, a translucent --beacon detection cone fans out across the driveway and gate (a soft
wedge, ~12% opacity, with a brighter 2px leading edge). Where the cone meets the vehicle, a
detection bracket snaps on with a label: "VEHICLE · JZ 84 KL GP". A beat later a second chip
appears beneath it in --critical: "WATCHLIST MATCH · 3 prior sightings · Randburg".

BEAT 3 (0:18-0:28) — THE FIGURE. A human silhouette (neutral, faceless, no detail — this is
deliberate, we never depict a person as a criminal) exits the vehicle and moves toward the gate.
A second cone from a driveway camera catches it. Bracket + chip: "PERSON · 00:14 · unfamiliar".
The camera's amber pulse quickens slightly. A compact fusion readout appears floating at the
model's edge: three factor chips stacking one at a time — "Repeat vehicle" · "Claim-peak hour"
· "Near-repeat zone" — and beneath them a single confidence bar filling to 84%, in stepped
increments as each chip lands. NOT one smooth fill — three discrete steps. This is the maths
made visible.

BEAT 4 (0:28-0:42) — THE NERVOUS SYSTEM. This is the money shot. Thin --edge lines, previously
invisible, illuminate to reveal the network: camera → a small hub on the house wall → a line
rising off the model to a floating node above it → branching to three destinations arranged
around the model at different heights:
  · a phone (the member) — floating, screen dark
  · a neighbouring house node — a small amber dot on a second, simpler house form
  · a patrol vehicle on the street
An amber pulse travels the path — visible as a bright travelling dot with a fading tail, moving
at a readable speed (not instant). As it reaches each destination, that destination lights and a
small tabular-numeral counter stamps beside it: "142ms", "196ms", "318ms". The phone's screen
illuminates with a miniature alert card.

BEAT 5 (0:42-0:52) — THE HUMAN GATE. Everything stops. The travelling pulse halts at the
floating node and holds. A card fades in beside it, calm and centred:
    "MACHINE CEILING REACHED
     Awaiting human verification"
Hold for a full 2 seconds of stillness — the pause IS the point. Then a check mark, an operator
name and timestamp ("Op. N. Dlamini · 00:14:22"), and only THEN does the patrol vehicle's light
bar illuminate and the vehicle begin to move along the street toward the house.

BEAT 6 (0:52-1:02) — THE BLACKOUT. Pull back slightly to reveal the model sits on a short strip
of six houses. One by one, right to left, the warm window lights and the streetlight go out —
staggered ~250ms apart, an unmistakable load-shedding cascade. The street goes cold and grey.
The BEACON amber nodes on each house STAY LIT, and the thin network lines between them stay
visible, now the only illuminated things on screen. Hold. Then type fades in, centred, small:
    "Stage 6. The light that stays on."

INTERACTION (for a live presenter, not just playback):
- Drag horizontally to orbit the model manually.
- Click any node (camera, hub, phone, patrol, neighbour) to pin its state card.
- A "Load shedding" toggle that triggers BEAT 6 on demand, at any point.
- Transport bar: play / pause / restart / scrub to any beat, with the beats labelled.
```

### 4.2 The Street Mesh — risk terrain rising

```
SCENE: Pull the camera up and back from a single house to an isometric block of a Johannesburg
suburb — roughly 20 simplified house forms along three streets, matte --surface, thin --edge
outlines, a few trees and parked vehicle forms for texture. Night. Sparse --warm windows.

BEAT 1: The block sits still. A handful of amber BEACON nodes pulse on scattered houses — not
all of them. A counter reads "7 of 20 homes protected".

BEAT 2: A hex grid fades in over the ground plane — flat at first, H3-styled hexagons with thin
--edge borders. Then each hex EXTRUDES upward, its height and colour driven by the risk ramp,
rising in a staggered wave from one corner. The result is a translucent risk terrain standing
over the neighbourhood — you can still see the houses through and beneath it. A time label
reads "00:00" and the tallest columns cluster in one corner.

BEAT 3: A time scrubber runs 18:00 → 00:00 → 06:00. As it moves, the columns rise and fall
fluidly, and the tall cluster MIGRATES across the block. This migration is the whole point —
say nothing, just let it move.

BEAT 4: A vehicle form drives the street. As it passes each amber node, a brief cone catches
it and a small sighting marker drops onto the map behind it. After the third, the markers
connect into a path and a translucent --watch trajectory cone extends forward from the last
one, projecting where it is heading. A single hex ahead of it highlights in --high with a label:
"SUGGESTED INTERCEPTION".

BEAT 5: A patrol route draws itself as a smooth glowing polyline threading the tall columns,
with numbered stops. Two counters animate up beside it: "FUEL −34%" and "COVERAGE 82%".

Interaction: drag to orbit, scrub the time control, toggle hex terrain on/off, click any hex
for its risk breakdown.
```

### 4.3 The Privacy X-ray — what we actually store (**cheap, unique, high-impact**)

```
SCENE: Deliberately simple and stark. Centred on a near-black canvas: a single neutral human
silhouette walking left to right, in a soft --discovery blue, seen through a camera frame with
thin corner brackets.

BEAT 1: The figure walks. A detection bracket tracks it. Label: "PERSON DETECTED". Normal,
expected, slightly uncomfortable — let the audience sit in the surveillance feeling for 3 seconds.

BEAT 2: Freeze. A line of text: "Here is what most systems store." Below the figure, a
photo-frame placeholder appears with the silhouette inside it, tagged with a name field, an
address field, a timestamp. It looks like a dossier. Hold 2 seconds.

BEAT 3: The dossier SHATTERS — the frame and fields dissolve into small particles that scatter
and fade. Text: "Here is what BEACON stores."

BEAT 4: The figure itself dissolves — from the outline inward — into a dense grid of small
--beacon amber numerals: a floating 128-dimension vector, drifting gently, unreadable as a
person. Beside it, one line of plain text:
    "A one-way mathematical signature. It cannot be turned back into a face.
     No photo. No name. No address."
Then, smaller: "Matched against your own whitelist, on your own devices."

BEAT 5: A second silhouette walks in. It converts to its own vector. The two vectors sit side by
side, and a similarity score appears between them with a threshold line — visibly BELOW the
line. Text: "Below threshold. No match. Nothing recorded."

Interaction: a slider that lets the presenter drag the similarity threshold and watch the
match/no-match state flip — showing the decision is a tunable, auditable number, not a black box.
```

### 4.4 The Device Family — title/closing hero

```
SCENE: The classic product hero, done well. On a near-black canvas with a very soft radial
--discovery glow behind: a laptop rendered as flat planes in CSS 3D, angled ~15° and floating,
showing the BEACON ops console; a phone floating in front-right at a different angle and depth
showing the member alert screen; a second phone back-left, dimmer and smaller, showing the
patrol officer view. Soft contact shadows beneath each, offset and blurred.

All three drift very slowly on independent gentle sine paths (different periods, so they never
sync) with subtle parallax — this is the entire animation, and its restraint is the point.

The screens are LIVE: the ops console's live feed has cards sliding in from the top every few
seconds; the phone's confidence bar breathes; a cyan live dot pulses on both.

Behind everything, at very low opacity, the network line motif from 4.1 — thin lines connecting
the three devices, with an occasional amber pulse travelling between them.

Bottom of frame: the BEACON wordmark, "by Discovery" lockup, and the tagline
"the light that stays on" — set small, confident, plenty of space around it.

Interaction: mouse position gently parallaxes the whole group (max 12px of travel — subtle).
```

---

## 5. Build order + what to cut

1. **4.1 The House** — this is the pitch moment. Everything else is optional.
2. **4.3 Privacy X-ray** — cheapest of the four, and it's the ethics slide made visual. Very high ratio.
3. **4.4 Device Family** — title or closing card. Fast to build, makes the deck look finished.
4. **4.2 Street Mesh** — most expensive, most overlapping with what the real ops map already does live. Build only if the live map isn't demoing well.

If time collapses to one thing: **4.1, beats 1-5 only, blackout cut and held back for the refine round.**

## 6. Refinement notes (append as scenes come back)

_(empty — dated notes as we iterate)_
